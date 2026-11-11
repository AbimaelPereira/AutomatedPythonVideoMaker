"""Geração paga de imagem (Nano Banana, AI Studio) e vídeo (Veo, Vertex AI).

Uso exclusivo via API — o pipeline do videomaker NÃO usa isto. O chamador manda
o prompt + imagem(ns) de referência (URL, data URI base64) e recebe o arquivo.
Cada chamada gera 1 arquivo; para N imagens/vídeos, chame N vezes.

Auth: header `X-Service-Token`.
"""

import importlib.util
import os
import tempfile
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from middleware.auth import require_service_token
from videomaker_runtime import VIDEOMAKER_DIR

router = APIRouter(
    dependencies=[Depends(require_service_token)],
    responses={401: {"description": "`X-Service-Token` ausente ou inválido."}},
)

_provider = None


def _get_provider():
    """Carrega só o GeminiProvider (sem o __init__ do pacote, que puxa outros providers)."""
    global _provider
    if _provider is None:
        path = os.path.join(VIDEOMAKER_DIR, "libs", "AIProviders", "GeminiProvider.py")
        spec = importlib.util.spec_from_file_location("_gemini_provider", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _provider = mod.GeminiProvider()
    return _provider


class ImageRequest(BaseModel):
    prompt: str = Field(
        description="Descrição da imagem a gerar. Com referência, descreva o cenário em que o produto deve aparecer.",
        examples=["O produto da imagem sobre uma bancada de mármore, luz natural de manhã, fotografia publicitária"],
    )
    reference_images: List[str] = Field(
        default_factory=list,
        description="Imagens de referência (ex.: foto do produto). Cada item: URL http(s) ou data URI "
                    "`data:image/png;base64,...`. Vazio = geração só por texto.",
        examples=[["https://exemplo.com/produto.png"]],
    )
    aspect_ratio: str = Field(
        default="9:16",
        description='Proporção da imagem. Ex.: "1:1", "2:3", "3:4", "4:5", "9:16", "16:9".',
    )
    resolution: Optional[str] = Field(
        default=None,
        description='Tamanho da imagem: "1K", "2K" ou "4K". Omitido = padrão do modelo (1K). Maior = mais caro.',
    )
    model: Optional[str] = Field(
        default=None,
        description="Modelo de imagem. Omitido = `gemini-3.1-flash-image` (Nano Banana 2).",
    )


class VideoRequest(BaseModel):
    prompt: str = Field(
        description="Movimento/ação do vídeo a partir da imagem inicial (câmera, ação, clima).",
        examples=["Câmera aproxima lentamente do produto, vapor subindo da xícara, luz suave"],
    )
    image: str = Field(
        description="Imagem inicial (primeiro quadro): URL http(s) ou data URI `data:image/png;base64,...`.",
        examples=["https://exemplo.com/cenario.png"],
    )
    aspect_ratio: str = Field(default="9:16", description='"9:16" (vertical) ou "16:9" (horizontal).')
    duration_seconds: int = Field(
        default=8,
        description="Duração em segundos. Valores aceitos dependem do modelo (Veo 3.1: 4, 6 ou 8). "
                    "Inválido = erro 502 vindo do Vertex.",
    )
    resolution: str = Field(default="720p", description='"720p" ou "1080p". 1080p custa mais.')
    negative_prompt: Optional[str] = Field(default=None, description="O que evitar no vídeo.",
                                           examples=["texto, marca d'água, distorção do produto"])
    generate_audio: Optional[bool] = Field(default=None, description="Gerar áudio junto. Omitido = padrão do modelo.")
    seed: Optional[int] = Field(default=None, description="Semente para resultado reprodutível.")
    model: Optional[str] = Field(default=None, description="Modelo de vídeo. Omitido = `veo-3.1-lite-generate-001`.")


_ERRORS = {
    400: {"description": "Parâmetro inválido ou credencial ausente (GEMINI_API_KEY / service account)."},
    401: {"description": "`X-Service-Token` ausente ou inválido."},
    502: {"description": "Falha no Google: modelo recusou (filtro de segurança), parâmetro rejeitado, "
                         "créditos do AI Studio esgotados (402) ou cota."},
    504: {"description": "Vídeo não ficou pronto dentro do timeout (600 s)."},
}


def _run(fn, suffix: str, media_type: str, **kwargs) -> Response:
    with tempfile.TemporaryDirectory() as tmp:
        try:
            out = fn(output_path=os.path.join(tmp, f"out{suffix}"), **kwargs)
        except (ValueError, EnvironmentError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        except TimeoutError as e:
            raise HTTPException(status_code=504, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))
        with open(out, "rb") as f:
            return Response(content=f.read(), media_type=media_type)


@router.post(
    "/image",
    response_class=Response,
    summary="Gerar imagem (Nano Banana)",
    responses={200: {"content": {"image/png": {}}, "description": "Imagem PNG gerada."}, **_ERRORS},
)
def generate_image(req: ImageRequest):
    """Gera **1 imagem PNG** a partir de prompt + imagens de referência opcionais.

    - **Provedor:** Gemini API (AI Studio), modelo padrão `gemini-3.1-flash-image`.
    - **Cobrança:** créditos pré-pagos do AI Studio (projeto `automatevideospython`). Sem crédito → 502.
    - **Várias imagens:** chame o endpoint N vezes (ex.: 4 cenários = 4 chamadas).
    - **Resposta:** bytes do PNG (`image/png`), não JSON.

    Exemplo:
    ```
    curl -X POST /ai-generation/image -H "X-Service-Token: <token>" -H "Content-Type: application/json" \
      -d '{"prompt": "produto numa cozinha moderna", "reference_images": ["https://.../produto.png"]}' -o cena.png
    ```
    """
    p = _get_provider()
    kwargs = req.model_dump(exclude_none=True)
    return _run(p.generate_image, ".png", "image/png", **kwargs)


@router.post(
    "/video",
    response_class=Response,
    summary="Gerar vídeo a partir de imagem (Veo)",
    responses={200: {"content": {"video/mp4": {}}, "description": "Vídeo MP4 gerado."}, **_ERRORS},
)
def generate_video(req: VideoRequest):
    """Gera **1 vídeo MP4** (image-to-video) usando a imagem como primeiro quadro.

    - **Provedor:** Vertex AI, modelo padrão `veo-3.1-lite-generate-001`, região `us-central1`.
    - **Cobrança:** Cloud Billing do projeto `automatevideospython` (cartão), por segundo de vídeo.
      Não usa os créditos do AI Studio.
    - **Síncrono:** a requisição fica aberta até o vídeo ficar pronto (~1–3 min). Use timeout de cliente ≥ 10 min.
    - **Vários vídeos:** chame o endpoint N vezes.
    - **Resposta:** bytes do MP4 (`video/mp4`), não JSON.

    Exemplo:
    ```
    curl -X POST /ai-generation/video -H "X-Service-Token: <token>" -H "Content-Type: application/json" \
      -d '{"prompt": "câmera gira ao redor do produto", "image": "https://.../cena.png", "duration_seconds": 6}' \
      --max-time 900 -o clipe.mp4
    ```
    """
    p = _get_provider()
    kwargs = req.model_dump(exclude_none=True)
    return _run(p.generate_video, ".mp4", "video/mp4", **kwargs)
