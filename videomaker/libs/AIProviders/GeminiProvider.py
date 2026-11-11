import os
import re
import json
import time
from pathlib import Path

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-flash-latest",
]

IMAGE_MODEL = "gemini-3.1-flash-image"  # Nano Banana 2
VIDEO_MODEL = "veo-3.1-lite-generate-001"   # Veo 3.1 Lite (Vertex AI)

_VIDEOMAKER_DIR = Path(__file__).parent.parent.parent


class GeminiProvider:
    def __init__(self, api_key: str = None, models: list[str] = None, retry_delay: float = 2.0):
        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise EnvironmentError("Defina GEMINI_API_KEY no ambiente.")

        self.client = genai.Client(api_key=key)   # AI Studio: texto/imagem (créditos pré-pagos)
        self.models = models or MODELS
        self.retry_delay = retry_delay
        self._vertex = None

    @property
    def vertex(self) -> genai.Client:
        """Cliente Vertex AI (vídeo/Veo), cobrado no Cloud Billing via service account."""
        if self._vertex is None:
            cred = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "tokens/gcp-videomaker-sa.json")
            cred_path = Path(cred)
            if not cred_path.is_absolute():
                cred_path = (_VIDEOMAKER_DIR / cred_path).resolve()
            if not cred_path.exists():
                raise EnvironmentError(f"Credencial da service account não encontrada: {cred_path}")
            from google.oauth2 import service_account
            creds = service_account.Credentials.from_service_account_file(
                str(cred_path), scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            self._vertex = genai.Client(
                vertexai=True,
                project=os.getenv("GCP_PROJECT", "automatevideospython"),
                location=os.getenv("GCP_LOCATION", "us-central1"),
                credentials=creds,
            )
        return self._vertex

    def generate_text(self, prompt: str, temperature: float = 0.2) -> str:
        """Envia um prompt e retorna o texto da resposta. Tenta os modelos em sequência."""
        config = types.GenerateContentConfig(temperature=temperature)
        last_error = None

        for model_name in self.models:
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config,
                )
                return response.text.strip()
            except Exception as e:
                last_error = e
                time.sleep(self.retry_delay)

        raise RuntimeError(f"Todos os modelos Gemini falharam. Último erro: {last_error}")

    def generate_json(self, prompt: str, temperature: float = 0.2) -> any:
        """Envia um prompt e retorna o resultado já parseado como JSON."""
        config = types.GenerateContentConfig(
            temperature=temperature,
            response_mime_type="application/json",
        )
        last_error = None

        for model_name in self.models:
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config,
                )
                raw = response.text.strip()
                raw = re.sub(r"```(?:json)?", "", raw).strip("` \n")
                return json.loads(raw)
            except Exception as e:
                last_error = e
                time.sleep(self.retry_delay)

        raise RuntimeError(f"Todos os modelos Gemini falharam. Último erro: {last_error}")

    # ------------------------------------------------------------------ #
    # Imagem (Nano Banana) e vídeo (Veo)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _load_image(src: str) -> types.Part:
        """Carrega imagem de URL, data URI (base64) ou caminho local como Part."""
        import base64
        import mimetypes
        import requests

        if src.startswith("data:"):
            header, b64 = src.split(",", 1)
            mime = header[5:].split(";")[0] or "image/png"
            return types.Part.from_bytes(data=base64.b64decode(b64), mime_type=mime)
        if src.startswith(("http://", "https://")):
            resp = requests.get(src, timeout=60)
            resp.raise_for_status()
            data = resp.content
            mime = resp.headers.get("content-type", "").split(";")[0] or None
        else:
            data = Path(src).read_bytes()
            mime = None
        mime = mime or mimetypes.guess_type(src)[0] or "image/png"
        return types.Part.from_bytes(data=data, mime_type=mime)

    def _image_once(self, model, contents, config, output_path: Path) -> Path:
        response = self.client.models.generate_content(model=model, contents=contents, config=config)
        for cand in response.candidates or []:
            for part in (cand.content.parts if cand.content else []) or []:
                if part.inline_data and part.inline_data.data:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(part.inline_data.data)
                    return output_path
        reason = getattr(response, "prompt_feedback", None) or (
            response.candidates[0].finish_reason if response.candidates else "sem candidatos"
        )
        raise RuntimeError(f"Resposta sem imagem ({reason})")

    def generate_image(
        self,
        prompt: str,
        output_path: str,
        reference_images: list[str] = None,
        model: str = IMAGE_MODEL,
        fallback_models: list[str] = None,
        aspect_ratio: str = "9:16",
        resolution: str = None,
        output_format: str = "png",
    ) -> Path:
        """Gera uma imagem a partir do prompt + imagens de referência."""
        refs = [self._load_image(src) for src in (reference_images or [])]
        contents = [*refs, prompt]
        config = types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(
                aspect_ratio=aspect_ratio,
                **({"image_size": resolution} if resolution else {}),
            ),
        )
        out = Path(output_path).with_suffix(f".{output_format}")
        models = [model, *(fallback_models or [])]

        last_error = None
        for m in models:
            try:
                return self._image_once(m, contents, config, out)
            except Exception as e:
                last_error = e
                time.sleep(self.retry_delay)
        raise RuntimeError(f"Falha ao gerar imagem ({models}). Último erro: {last_error}")

    def generate_video(
        self,
        prompt: str,
        image: str,
        output_path: str,
        model: str = VIDEO_MODEL,
        negative_prompt: str = None,
        aspect_ratio: str = "9:16",
        duration_seconds: int = 8,
        resolution: str = "720p",
        generate_audio: bool = None,
        seed: int = None,
        poll_interval: float = 10,
        timeout: float = 600,
    ) -> Path:
        """Gera um clipe a partir de uma imagem (image-to-video) no Vertex AI, aguarda e salva o MP4.

        Durações aceitas dependem do modelo; o Vertex devolve erro se inválida.
        """

        ref = self._load_image(image)
        config = types.GenerateVideosConfig(
            aspect_ratio=aspect_ratio,
            duration_seconds=duration_seconds,
            resolution=resolution,
            number_of_videos=1,
            negative_prompt=negative_prompt,
            seed=seed,
            **({"generate_audio": generate_audio} if generate_audio is not None else {}),
        )

        client = self.vertex
        op = client.models.generate_videos(
            model=model,
            prompt=prompt,
            image=types.Image(image_bytes=ref.inline_data.data, mime_type=ref.inline_data.mime_type),
            config=config,
        )

        deadline = time.monotonic() + timeout
        while not op.done:
            if time.monotonic() > deadline:
                raise TimeoutError(f"Veo não terminou em {timeout}s (operação {op.name}).")
            time.sleep(poll_interval)
            op = client.operations.get(op)

        if op.error:
            raise RuntimeError(f"Veo falhou: {op.error}")
        videos = op.response.generated_videos if op.response else None
        if not videos:
            filtered = getattr(op.response, "rai_media_filtered_reasons", None)
            raise RuntimeError(f"Veo não retornou vídeo (filtro: {filtered}).")

        video = videos[0].video
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        if video.video_bytes:
            out.write_bytes(video.video_bytes)
        elif video.uri and video.uri.startswith("gs://"):
            raise RuntimeError(f"Vídeo salvo em GCS ({video.uri}); output_gcs_uri não é suportado aqui.")
        else:
            video.save(str(out))
        return out
