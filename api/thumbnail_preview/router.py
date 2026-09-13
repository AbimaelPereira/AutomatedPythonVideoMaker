"""Preview de thumbnail composta — renderiza `background` + `visual_elements`
e devolve o PNG, para testar o `youtube.thumbnail` com `type: "scene"` sem
precisar rodar um vídeo inteiro.

A renderização acontece num SUBPROCESSO (`render_worker.py`), não aqui: o
renderer real do videomaker depende de MoviePy (numpy<2, handles de mídia), que
não deve ser carregado dentro do processo da API. O custo é um fork por
requisição — aceitável para um endpoint de preview manual, e o preço de reusar
exatamente a mesma engine que gera a thumbnail em produção.

O corpo aceito é o MESMO bloco `youtube.thumbnail` do JSON do vídeo, então o que
se testa aqui pode ser colado no JSON sem tradução.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from middleware.auth import get_current_user
from auth.models import User

router = APIRouter()

_VIDEOMAKER_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "videomaker")
)
_WORKER = os.path.join(os.path.dirname(__file__), "render_worker.py")
_FONTS_DIR = os.path.join(_VIDEOMAKER_DIR, "assets", "fonts")


# Interpretador já validado. O teste de import custa ~1s e o resultado não
# muda em runtime, então roda uma vez por processo.
_CACHED_PYTHON: Optional[str] = None


def _has_moviepy(python: str) -> bool:
    """Testa se o interpretador consegue importar MoviePy."""
    try:
        return subprocess.run(
            [python, "-c", "import moviepy"],
            capture_output=True, timeout=30,
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _videomaker_python() -> str:
    """Interpretador que roda o videomaker.

    NÃO é o `sys.executable` da API: o videomaker exige `moviepy==1.0.3` com
    `numpy<2`, enquanto o venv da API traz numpy 1.26 e nenhum MoviePy.

    Cada candidato é VERIFICADO importando MoviePy, em vez de confiar no nome.
    Motivo: quando a API sobe com o venv ativado (é o que o `dev.sh` faz), um
    `which("python3")` resolve justamente para o python da API — sem MoviePy —
    e o render falharia com ModuleNotFoundError. Checar o que o interpretador
    realmente tem é a única forma de escolher certo em qualquer ambiente.

    Ordem: env `VIDEOMAKER_PYTHON` (respeitada sem teste, é escolha explícita)
    → venv do videomaker → pythons do sistema, fora do venv da API.
    """
    env_python = os.getenv("VIDEOMAKER_PYTHON")
    if env_python:
        return env_python

    global _CACHED_PYTHON
    if _CACHED_PYTHON:
        return _CACHED_PYTHON

    candidates = [
        os.path.join(_VIDEOMAKER_DIR, ".venv", "bin", "python"),
        # Caminhos absolutos do sistema: imunes ao PATH do venv da API.
        "/usr/bin/python3",
        "/usr/local/bin/python3",
    ]
    # `which` por último e sem o venv da API no PATH, para não reencontrar o
    # interpretador que justamente não serve.
    clean_path = os.pathsep.join(
        p for p in os.environ.get("PATH", "").split(os.pathsep)
        if ".venv" not in p and "virtualenv" not in p
    )
    found = shutil.which("python3", path=clean_path)
    if found:
        candidates.append(found)

    for candidate in candidates:
        if os.path.exists(candidate) and _has_moviepy(candidate):
            _CACHED_PYTHON = candidate
            return candidate

    # Nenhum serve: falha com uma mensagem que diz o que fazer, em vez de
    # deixar o ModuleNotFoundError cru chegar ao usuário.
    raise HTTPException(
        status_code=500,
        detail="Nenhum Python com MoviePy encontrado para renderizar a "
               "thumbnail. Defina VIDEOMAKER_PYTHON apontando para o "
               "interpretador do videomaker (o mesmo que roda `python main.py`).",
    )


def _parse_warnings(stdout: str) -> list:
    """Avisos de degradação silenciosa, na última linha JSON do worker."""
    for line in reversed((stdout or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line).get("warnings") or []
            except json.JSONDecodeError:
                continue
    return []


# ----------------------------------------------------------------------
# Fundos gerados (cache de preview)
# ----------------------------------------------------------------------
#
# Gerar uma imagem de IA custa tempo e dinheiro, e o preview re-renderiza a
# cada ajuste de texto. Guardamos o fundo gerado em disco e passamos a
# referenciá-lo por id, para o painel iterar nos elementos visuais sem disparar
# uma nova geração a cada tecla.

_BACKGROUNDS_DIR = os.path.join(tempfile.gettempdir(), "thumbnail_preview_bg")

# Um fundo de preview é descartável: expira sozinho para a pasta não crescer
# indefinidamente numa máquina de longa duração.
_BACKGROUND_TTL_SECONDS = 6 * 60 * 60


def _background_path(background_id: str) -> str:
    """Caminho local de um fundo gerado, validando o id.

    O id vem do cliente e vira caminho de arquivo — só aceitamos o formato que
    nós mesmos emitimos (hex), para a requisição não conseguir apontar para
    fora da pasta de fundos.
    """
    if not re.fullmatch(r"[0-9a-f]{32}", background_id or ""):
        raise HTTPException(status_code=422, detail="background_id inválido")
    return os.path.join(_BACKGROUNDS_DIR, f"{background_id}.png")


def _purge_expired_backgrounds():
    """Remove fundos vencidos. Barato: a pasta tem poucos arquivos."""
    if not os.path.isdir(_BACKGROUNDS_DIR):
        return
    cutoff = time.time() - _BACKGROUND_TTL_SECONDS
    for name in os.listdir(_BACKGROUNDS_DIR):
        path = os.path.join(_BACKGROUNDS_DIR, name)
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
        except OSError:
            pass


# Uma thumbnail com fundo de IA depende de uma chamada externa de geração; o
# resto é local e rápido. O teto cobre o caso lento sem deixar a requisição presa.
_TIMEOUT_SECONDS = 180

_RESOLUTIONS = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "16:9-2k": (2560, 1440),
    "9:16-2k": (1440, 2560),
}


class ThumbnailPreviewRequest(BaseModel):
    """Bloco `youtube.thumbnail` (type: "scene") + contexto do vídeo.

    `background` e `visual_elements` são repassados às engines sem tradução —
    por isso são dicts livres: qualquer campo que o videomaker aceita numa cena
    (fit_mode, focus, filters, animation, placement, …) vale aqui também.
    """

    background: Optional[Dict[str, Any]] = None
    visual_elements: List[Dict[str, Any]] = Field(default_factory=list)

    width: int = 1280
    height: int = 720

    # Área segura. None → default por orientação da thumbnail.
    padding_top: Optional[int] = None
    padding_bottom: Optional[int] = None
    padding_side: Optional[int] = None

    # Contexto do vídeo: `global_settings` permite herdar o fundo/paddings do
    # canal; `output_ratio` só informa a orientação do vídeo, para decidir se os
    # paddings do canal são herdáveis pela thumbnail.
    global_settings: Dict[str, Any] = Field(default_factory=dict)
    output_ratio: Optional[str] = None

    # Fundo já gerado por `POST /background` — substitui `background` para o
    # painel iterar nos elementos sem custear uma nova geração de IA por tecla.
    background_id: Optional[str] = None


class BackgroundRequest(BaseModel):
    """Geração isolada do fundo, para ser reaproveitado entre previews."""

    background: Dict[str, Any]
    width: int = 1280
    height: int = 720
    global_settings: Dict[str, Any] = Field(default_factory=dict)


def _run_worker(payload: dict) -> list:
    """Executa o worker de render e devolve os avisos. Levanta HTTPException."""
    try:
        result = subprocess.run(
            [_videomaker_python(), _WORKER],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            cwd=_VIDEOMAKER_DIR,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=504,
            detail=f"Renderização excedeu {_TIMEOUT_SECONDS}s "
                   f"(geração por IA lenta ou download travado)",
        )

    if result.returncode != 0:
        # O stderr do worker traz o traceback real da engine — é o que
        # explica um `source` inexistente ou um tipo não suportado.
        detail = (result.stderr or "").strip().splitlines()
        raise HTTPException(
            status_code=400,
            detail=f"Falha ao renderizar thumbnail: "
                   f"{detail[-1] if detail else 'erro desconhecido'}",
        )

    if not os.path.exists(payload["output_path"]):
        raise HTTPException(status_code=500,
                            detail="Renderização terminou sem gerar o arquivo")

    return _parse_warnings(result.stdout)


@router.post("/background")
def generate_background(
    body: BackgroundRequest,
    current_user: User = Depends(get_current_user),
):
    """Gera SÓ o fundo e guarda em disco, devolvendo o id para reutilização.

    Existe para separar o que é caro (uma imagem de IA) do que é barato (mexer
    no texto): o painel gera o fundo uma vez e referencia por `background_id`
    nas renderizações seguintes.
    """
    if body.width < 16 or body.height < 16 or body.width > 4096 or body.height > 4096:
        raise HTTPException(status_code=422,
                            detail="width/height devem estar entre 16 e 4096")

    os.makedirs(_BACKGROUNDS_DIR, exist_ok=True)
    _purge_expired_backgrounds()

    background_id = uuid.uuid4().hex
    output_path = _background_path(background_id)

    work_root = tempfile.mkdtemp(prefix="thumb_bg_")
    try:
        warnings = _run_worker({
            "videomaker_dir": _VIDEOMAKER_DIR,
            "thumbnail": {
                "type": "scene",
                "width": body.width,
                "height": body.height,
                "background": body.background,
                "visual_elements": [],  # só o fundo
            },
            "output_path": output_path,
            "work_dir": work_root,
            "global_settings": body.global_settings,
            "video_resolution": None,
        })
    finally:
        shutil.rmtree(work_root, ignore_errors=True)

    return {
        "background_id": background_id,
        "width": body.width,
        "height": body.height,
        "warnings": warnings,
    }


@router.delete("/background/{background_id}", status_code=204)
def discard_background(
    background_id: str,
    current_user: User = Depends(get_current_user),
):
    """Descarta um fundo gerado. Idempotente: já removido também é sucesso."""
    try:
        os.remove(_background_path(background_id))
    except FileNotFoundError:
        pass
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Falha ao descartar: {e}")
    return Response(status_code=204)


@router.post("")
def preview_thumbnail(
    body: ThumbnailPreviewRequest,
    current_user: User = Depends(get_current_user),
):
    if body.width < 16 or body.height < 16 or body.width > 4096 or body.height > 4096:
        raise HTTPException(status_code=422,
                            detail="width/height devem estar entre 16 e 4096")

    # Um fundo já gerado vence o `background` declarado: é exatamente a imagem
    # que o usuário aprovou no painel, e reusá-la evita regerar IA a cada tecla.
    background = body.background
    if body.background_id:
        path = _background_path(body.background_id)
        if not os.path.exists(path):
            raise HTTPException(
                status_code=410,
                detail="fundo gerado não está mais disponível — gere novamente",
            )
        background = {"visual": {"type": "image", "source": path,
                                 "fit_mode": "cover"}}

    if not background and not body.visual_elements \
            and not body.global_settings.get("background"):
        raise HTTPException(
            status_code=422,
            detail="informe ao menos `background` ou `visual_elements`",
        )

    video_resolution = _RESOLUTIONS.get(body.output_ratio) if body.output_ratio else None

    work_root = tempfile.mkdtemp(prefix="thumb_preview_")
    output_path = os.path.join(work_root, "thumbnail.png")

    thumbnail_cfg = {
        "type": "scene",
        "width": body.width,
        "height": body.height,
        "background": background,
        "visual_elements": body.visual_elements,
    }
    for key in ("padding_top", "padding_bottom", "padding_side"):
        value = getattr(body, key)
        if value is not None:
            thumbnail_cfg[key] = value

    payload = {
        "videomaker_dir": _VIDEOMAKER_DIR,
        "thumbnail": thumbnail_cfg,
        "output_path": output_path,
        "work_dir": os.path.join(work_root, "assets"),
        "global_settings": body.global_settings,
        "video_resolution": list(video_resolution) if video_resolution else None,
    }

    try:
        warnings = _run_worker(payload)
        with open(output_path, "rb") as f:
            content = f.read()
    finally:
        shutil.rmtree(work_root, ignore_errors=True)

    # O renderer recomprime em JPEG quando o PNG passa de 2MB (limite do
    # YouTube), mantendo o nome do arquivo — o mimetype segue o conteúdo real.
    media_type = "image/jpeg" if content[:3] == b"\xff\xd8\xff" else "image/png"

    headers = {}
    if warnings:
        # O corpo é a imagem, então os avisos viajam num header: um asset que
        # falhou vira fundo preto silencioso, e o painel precisa poder dizer
        # por quê em vez de mostrar um preview vazio sem explicação.
        headers["X-Thumbnail-Warnings"] = json.dumps(warnings, ensure_ascii=True)

    return Response(content=content, media_type=media_type, headers=headers)


@router.get("/fonts")
def list_fonts(current_user: User = Depends(get_current_user)):
    """Fontes disponíveis para `text_box.style.font_path`."""
    fonts = []
    if os.path.isdir(_FONTS_DIR):
        for root, _dirs, files in os.walk(_FONTS_DIR):
            for f in files:
                if f.lower().endswith(".ttf"):
                    abs_path = os.path.join(root, f)
                    rel = os.path.relpath(abs_path, _VIDEOMAKER_DIR)
                    fonts.append({
                        "path": "./" + rel.replace(os.sep, "/"),
                        "label": os.path.splitext(f)[0],
                        "family": os.path.basename(os.path.dirname(abs_path)),
                    })
    fonts.sort(key=lambda x: (x["family"], x["label"]))
    return fonts


@router.get("/example")
def get_example(current_user: User = Depends(get_current_user)):
    """Corpo de exemplo pronto para POST — serve de ponto de partida no painel."""
    return {
        "width": 1280,
        "height": 720,
        "background": {
            "visual": {
                "type": "ai",
                "prompt": "dark moody cathedral interior, cinematic light, 4k",
                "model": "flux",
            }
        },
        "visual_elements": [
            {
                "type": "gradient",
                "direction": "to_top",
                "stops": [
                    {"color": "#000000", "opacity": 0.9, "at": 0.0},
                    {"color": "#000000", "opacity": 0.0, "at": 0.6},
                ],
                "placement": {
                    "anchor": ["center", "center"],
                    "width": "100%", "height": "100%",
                    "relative_to": "screen",
                },
            },
            {
                "type": "text_box",
                "content": "ELE NUNCA\nTE ABANDONOU",
                "style": {
                    "font_path": "./assets/fonts/Montserrat/Montserrat-Black.ttf",
                    "font_size": 96,
                    "text_color": "#FFE24A",
                    "background_color": "transparent",
                    "stroke_color": "#000000",
                    "stroke_width": 8,
                    "shadow": {"offset": [6, 6], "color": "#000000",
                               "blur": 4, "opacity": 0.8},
                    "line_spacing": 1.05,
                    "align": "left",
                },
                "placement": {"anchor": ["left", "bottom"], "width": "62%"},
            },
        ],
    }
