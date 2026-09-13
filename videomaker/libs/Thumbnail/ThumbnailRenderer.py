"""ThumbnailRenderer — compõe uma thumbnail como se fosse uma cena de 1 frame.

Uma thumbnail com fundo + overlays é exatamente uma cena de vídeo congelada: o
mesmo `background.visual`, os mesmos `visual_elements`, o mesmo `placement`. Em
vez de reimplementar composição, este módulo monta uma "cena falsa" de duração
mínima e a entrega às MESMAS engines que o pipeline de vídeo usa:

  - fundo    → `BackgroundEngine.build_scene_background`
  - overlays → `Compositor.build_visual_layer` (VisualClip + LayoutEngine)

Só o final difere: em vez de encodar um MP4, salva-se um único frame em PNG.
Consequência prática: todo tipo de fundo (ai/image/video/color/directory/
remote_asset) e todo elemento visual (text_box, gradient, image, color, …) já
funcionam aqui no dia em que funcionam no vídeo, sem código paralelo.

Não há legenda nem áudio: uma thumbnail não tem narração, e a legenda é uma
propriedade da fala, não do quadro.
"""

import os
import shutil
import tempfile


# Padrão do YouTube. Override por `width`/`height` no bloco da thumbnail.
DEFAULT_SIZE = (1280, 720)

# Duração nominal da cena. Nada é encodado — só existe porque as engines
# exigem uma duração para construir clips.
_FRAME_DURATION = 1.0

# Limite de upload de thumbnail do YouTube.
_MAX_BYTES = 2 * 1024 * 1024


def _resolve_size(cfg: dict) -> tuple:
    """(width, height) da thumbnail, com o padrão 1280x720."""
    try:
        w = int(cfg.get("width") or DEFAULT_SIZE[0])
        h = int(cfg.get("height") or DEFAULT_SIZE[1])
    except (TypeError, ValueError):
        return DEFAULT_SIZE
    if w < 16 or h < 16:
        return DEFAULT_SIZE
    return (w, h)


def _default_safe_paddings(resolution: tuple) -> dict:
    """Área segura por orientação da tela.

    Cópia deliberada de `UnifiedVideoEngine._default_safe_paddings`: importar o
    módulo original custaria ~9s (TTS, Whisper, transições) por uma função de
    aritmética pura. Os valores DEVEM acompanhar o original — 9:16 preserva os
    históricos calibrados para a legenda; 16:9 usa ~5% simétrico.
    """
    w, h = resolution
    if w >= h:
        return {"padding_side": int(w * 0.05),
                "padding_top": int(h * 0.05),
                "padding_bottom": int(h * 0.05)}
    return {"padding_side": 50, "padding_top": 100, "padding_bottom": 850}


def _layout_params(resolution: tuple, cfg: dict, global_settings: dict,
                   video_resolution: tuple = None) -> dict:
    """`layout_params` da thumbnail — mesmo formato que o `UnifiedVideoEngine` monta.

    A área segura sai de `_default_safe_paddings` (a mesma regra por orientação
    do vídeo). Cada padding pode ser sobrescrito pelo `global_settings` e, com
    precedência maior, pelo próprio bloco da thumbnail — que costuma querer
    margens diferentes das do vídeo (a thumbnail não tem faixa de legenda).
    """
    gs = global_settings or {}
    defaults = _default_safe_paddings(resolution)

    params = {
        "width": resolution[0],
        "height": resolution[1],
        "stack_gap_percent": gs.get("stack_gap_percent", 0.02),
    }

    # Os paddings do canal são calibrados para a ORIENTAÇÃO do vídeo (um 9:16
    # típico traz padding_bottom 850, reservando a faixa da legenda). Herdá-los
    # numa thumbnail de outra orientação colapsaria a área útil. Só herdamos do
    # `global_settings` quando a thumbnail tem a mesma orientação do vídeo.
    same_orientation = (
        video_resolution is None
        or (video_resolution[0] >= video_resolution[1]) == (resolution[0] >= resolution[1])
    )

    for key in ("padding_top", "padding_bottom", "padding_side"):
        if cfg.get(key) is not None:
            value = cfg[key]
        elif same_orientation and gs.get(key) is not None:
            value = gs[key]
        else:
            value = defaults[key]
        try:
            params[key] = int(value)
        except (TypeError, ValueError):
            params[key] = defaults[key]
    return params


def _prefetch_ai_background(scene: dict, effective_gs: dict, resolution: tuple,
                            ai_cache, work_dir: str, log_prefix: str):
    """Resolve um fundo `type: "ai"` para arquivo ANTES do BackgroundEngine.

    Duas coisas melhoram ao passar pelo `SceneBridge.resolve_ai_background`:

    1. Ele GRAVA no AICache; o `_build_ai` do BackgroundEngine só lê (`get`),
       nunca escreve, então cada preview regeraria a imagem pelo mesmo prompt —
       lento e pago. Aqui a segunda chamada reaproveita o arquivo.
    2. O cache passa a ser compartilhado com o render do vídeo: a imagem
       aprovada no preview é a mesma usada quando o vídeo roda.

    Falhar aqui não é fatal — devolve a cena intocada e o BackgroundEngine
    tenta pelo caminho normal.
    """
    bg = dict((effective_gs.get("background") or {}).get("visual") or {})
    bg.update(((scene.get("background") or {}).get("visual") or {}))

    if bg.get("type") != "ai" or bg.get("content_type", "image") != "image":
        return scene
    if ai_cache is None:
        return scene

    try:
        from libs.Render import SceneBridge
        path = SceneBridge.resolve_ai_background(bg, resolution, ai_cache, work_dir)
    except Exception as e:
        print(f"{log_prefix} Fundo de IA não pôde ser pré-resolvido ({e}) — "
              f"seguindo pelo BackgroundEngine")
        return scene

    # O fundo vira uma imagem em disco; o resto do pipeline não muda.
    scene = dict(scene)
    scene["background"] = {"visual": {"type": "image", "source": path,
                                      "fit_mode": "cover",
                                      "focus": bg.get("focus", "center")}}
    return scene


def _build_scene(cfg: dict, global_settings: dict) -> tuple:
    """Traduz o bloco da thumbnail para o par (scene, effective_gs) das engines.

    O `background` da thumbnail é mesclado sobre o do canal/vídeo, então uma
    thumbnail pode herdar o fundo padrão e sobrescrever só o `prompt` — mesma
    semântica de merge que uma cena tem hoje.
    """
    scene = {}

    background = cfg.get("background")
    if background:
        scene["background"] = background

    scene["visual_elements"] = list(cfg.get("visual_elements") or [])

    # A thumbnail não fala: legenda e transição não se aplicam a um quadro.
    effective_gs = dict(global_settings or {})
    effective_gs.pop("subtitle", None)
    effective_gs.pop("transitions", None)
    scene["subtitle"] = {"enabled": False}
    scene["transitions"] = {"enabled": False}

    if not background and not effective_gs.get("background"):
        # Sem fundo declarado em lugar nenhum, o BackgroundEngine cairia no
        # fallback preto. Explicitar evita depender desse acaso.
        scene["background"] = {"visual": {"type": "color", "color": "#000000"}}

    return scene, effective_gs


def _uses_ai(scene: dict, effective_gs: dict) -> bool:
    """A thumbnail depende de geração por IA?"""
    bg = dict((effective_gs.get("background") or {}).get("visual") or {})
    bg.update(((scene.get("background") or {}).get("visual") or {}))
    if bg.get("type") == "ai":
        return True
    # `source` também aceita um bloco de IA em visual_elements.
    return any(isinstance(el.get("source"), dict)
               and el["source"].get("type") == "ai"
               for el in (scene.get("visual_elements") or []))


def _default_ai_cache():
    """`AICache` apontando para o mesmo diretório que o pipeline de vídeo usa.

    Compartilhar o diretório é intencional: uma imagem gerada no preview da
    thumbnail é reaproveitada quando o vídeo roda de verdade (e vice-versa),
    em vez de custar uma segunda geração pelo mesmo prompt.
    """
    try:
        from libs.AIProviders.AICache import AICache
    except ImportError:
        return None  # sem o sistema de IA, `type: "ai"` já não funcionaria

    # Mesmo caminho do `UnifiedVideoEngine`; relativo ao cwd, que é a pasta
    # do videomaker tanto no CLI quanto no worker de preview.
    return AICache(os.path.join(os.getcwd(), "cache", "ai_generated"))


def render(cfg: dict, output_path: str, global_settings: dict = None,
           work_dir: str = None, ai_cache=None, remote_asset_manager=None,
           video_resolution: tuple = None, log_prefix: str = "[Thumbnail]") -> str:
    """Renderiza a thumbnail composta e devolve o caminho do PNG salvo.

    `cfg` é o bloco `youtube.thumbnail` (com `type: "scene"`). `work_dir` guarda
    os artefatos intermediários (imagens de IA, downloads); quando omitido, usa
    um diretório temporário descartado ao final. `video_resolution` só serve
    para decidir se os paddings do canal são herdáveis (ver `_layout_params`).

    `ai_cache` é opcional: sem ele, um é criado apontando para o mesmo
    `cache/ai_generated` do pipeline de vídeo.
    """
    from libs.Background.BackgroundEngine import BackgroundEngine
    from libs.Thumbnail import Compositor

    resolution = _resolve_size(cfg)
    scene, effective_gs = _build_scene(cfg, global_settings)

    if ai_cache is None and _uses_ai(scene, effective_gs):
        # Sem AICache o BackgroundEngine recusa `type: "ai"` e cai em fundo
        # preto. Criamos um só quando a cena realmente usa IA: o import do
        # AICache puxa o SDK do Gemini (~2,3s) e a maioria das thumbnails
        # (cor, imagem, pasta) não precisa dele.
        ai_cache = _default_ai_cache()

    owns_work_dir = work_dir is None
    if owns_work_dir:
        work_dir = tempfile.mkdtemp(prefix="thumbnail_")
    else:
        os.makedirs(work_dir, exist_ok=True)

    print(f"{log_prefix} Compondo thumbnail {resolution[0]}x{resolution[1]}...")

    scene = _prefetch_ai_background(scene, effective_gs, resolution,
                                    ai_cache, work_dir, log_prefix)

    clips_to_close = []
    try:
        bg_engine = BackgroundEngine(
            resolution_output=resolution,
            dir_clips_cache={},
            ai_cache=ai_cache,
            remote_asset_manager=remote_asset_manager,
        )
        background_clip = bg_engine.build_scene_background(
            effective_gs, scene, _FRAME_DURATION, work_dir, work_dir
        )
        clips_to_close.append(background_clip)

        layout_params = _layout_params(resolution, cfg, global_settings,
                                       video_resolution)

        visual_clips = Compositor.build_visual_layer(
            scene.get("visual_elements") or [], _FRAME_DURATION, work_dir,
            resolution, layout_params, remote_asset_manager,
        )
        clips_to_close.extend(visual_clips)

        composed = Compositor.compose(background_clip, visual_clips,
                                      resolution, _FRAME_DURATION)
        clips_to_close.append(composed)

        os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)

        # Salva o primeiro frame. `t=0` é determinístico: animações de zoom/fade
        # começam no estado inicial, que é o que se quer numa imagem estática.
        composed.save_frame(output_path, t=0)

        _enforce_size_limit(output_path, log_prefix)

        print(f"{log_prefix} ✅ Thumbnail gerada: {output_path}")
        return output_path

    finally:
        for clip in clips_to_close:
            try:
                clip.close()
            except Exception:
                pass
        if owns_work_dir:
            shutil.rmtree(work_dir, ignore_errors=True)


def _enforce_size_limit(path: str, log_prefix: str):
    """Garante o teto de 2MB do YouTube, recomprimindo em JPEG se preciso.

    Um PNG 1280x720 de fundo fotográfico passa de 2MB com facilidade; sem isso,
    o upload falharia só no final do pipeline, depois do vídeo inteiro pronto.
    O arquivo mantém a extensão .png — o `upload_thumbnail` decide o mimetype
    pela extensão, e o YouTube aceita o conteúdo JPEG de qualquer forma, então
    reescrevemos como JPEG apenas quando não há alternativa.
    """
    try:
        if os.path.getsize(path) <= _MAX_BYTES:
            return
    except OSError:
        return

    from PIL import Image

    jpeg_path = os.path.splitext(path)[0] + ".jpg"
    with Image.open(path) as im:
        rgb = im.convert("RGB")
        for quality in (92, 85, 75, 65):
            rgb.save(jpeg_path, "JPEG", quality=quality, optimize=True)
            if os.path.getsize(jpeg_path) <= _MAX_BYTES:
                break

    size_kb = os.path.getsize(jpeg_path) // 1024
    print(f"{log_prefix} PNG acima de 2MB — recomprimido em JPEG ({size_kb}KB): "
          f"{os.path.basename(jpeg_path)}")

    # Substitui o PNG pelo JPEG, preservando o caminho esperado por quem chamou.
    os.replace(jpeg_path, path)
