import os
import random
import datetime
from zoneinfo import ZoneInfo
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from dotenv import load_dotenv

load_dotenv()

class YouTube:
    def __init__(self, params=None):
        def to_bool(value):
            return str(value).lower() in ("true", "1", "yes", "on")

        defaults = {
            "client_secrets_file": os.getenv("CLIENT_SECRETS_FILE", "tokens/youtube_client_secret.json"),
            "token_dir": os.getenv("TOKEN_DIR", "tokens"),
            "token_file_name": os.getenv("TOKEN_FILE_NAME", "token_default.json"),
            "scopes": ["https://www.googleapis.com/auth/youtube"],
            "verbose": to_bool(os.getenv("VERBOSE", True)),

            "video_path": os.getenv("VIDEO_PATH", "test_video.mp4"),
            "title": os.getenv("VIDEO_TITLE", "🎥 Teste de Upload via API"),
            "description": os.getenv("VIDEO_DESCRIPTION", "Vídeo de teste enviado automaticamente via API do YouTube."),
            "tags": os.getenv("VIDEO_TAGS", "python,youtube,teste").split(","),
            "category_id": os.getenv("VIDEO_CATEGORY_ID", "22"),
            "privacy_status": os.getenv("VIDEO_PRIVACY", "private"),
            "publish_at": os.getenv("VIDEO_PUBLISH_AT"),
            "timezone": os.getenv("TIMEZONE", "America/Sao_Paulo"),
            "thumbnail": None,  # {"type": "file"|"directory"|"ai", ...}
        }
        if params:
            defaults.update(params)

        self.config = defaults
        for k, v in defaults.items():
            setattr(self, k, v)

        os.makedirs(self.token_dir, exist_ok=True)
        self.token_path = os.path.join(self.token_dir, self.token_file_name)

    # ---------------------------------------------------------
    # AUTENTICAÇÃO
    # ---------------------------------------------------------
    def _get_credentials(self):
        """Carrega o token salvo ou cria um novo."""
        creds = None

        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, self.scopes)
        else:
            self.generate_token()

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                self.generate_token()
                creds = Credentials.from_authorized_user_file(self.token_path, self.scopes)

        return creds

    def generate_token(self):
        """Abre o navegador e gera um novo token OAuth2."""
        print("🌐 Iniciando autenticação no Google...")
        flow = InstalledAppFlow.from_client_secrets_file(self.client_secrets_file, self.scopes)
        creds = flow.run_local_server(port=0)

        with open(self.token_path, "w") as token:
            token.write(creds.to_json())

        print(f"✅ Token gerado e salvo em: {self.token_path}")

    # ---------------------------------------------------------
    # CONVERSÃO DE FUSO HORÁRIO
    # ---------------------------------------------------------
    def _convert_to_utc(self, datetime_str, timezone_str):
        try:
            dt_naive = datetime.datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
            local_tz = ZoneInfo(timezone_str)
            dt_local = dt_naive.replace(tzinfo=local_tz)
            dt_utc = dt_local.astimezone(ZoneInfo("UTC"))
            iso_format = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

            if self.verbose:
                print(f"🕐 Horário local ({timezone_str}): {dt_local.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                print(f"🌍 Horário UTC: {dt_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                print(f"📅 Formato ISO 8601: {iso_format}")

            return iso_format

        except Exception as e:
            print(f"❌ Erro ao converter timezone: {e}")
            dt = datetime.datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
            return dt.isoformat() + "Z"

    # ---------------------------------------------------------
    # THUMBNAIL
    # ---------------------------------------------------------
    def _resolve_thumbnail_output_path(self) -> str:
        """
        Deriva o caminho de saída da thumbnail a partir do video_path.
        Salva sempre na mesma pasta do vídeo: output/{slug}/thumbnail.png
        """
        video_dir = os.path.dirname(os.path.abspath(self.video_path))
        return os.path.join(video_dir, "thumbnail.png")

    def _resolve_thumbnail_path(self) -> str | None:
        """
        Resolve o caminho da thumbnail a partir da config.

        Modos suportados:
          - type: "file"      → caminho direto para um arquivo local
          - type: "directory" → escolhe aleatoriamente uma imagem da pasta
          - type: "ai"        → gera via Pollinations e salva em output/{slug}/thumbnail.png
                                Parâmetros: prompt (obrigatório), provider, model,
                                width, height, quality, seed, negative_prompt, enhance
        """
        thumb_config = self.thumbnail
        if not thumb_config:
            return None

        thumb_type = thumb_config.get("type", "file")
        source = thumb_config.get("source")

        if thumb_type == "directory":
            if not source:
                print("[YouTube] thumbnail.source não configurado")
                return None
            if not os.path.isdir(source):
                print(f"[YouTube] Diretório de thumbnail não encontrado: {source}")
                return None
            valid_extensions = (".jpg", ".jpeg", ".png", ".webp")
            files = [f for f in os.listdir(source) if f.lower().endswith(valid_extensions)]
            if not files:
                print(f"[YouTube] Nenhuma imagem válida em: {source}")
                return None
            return os.path.join(source, random.choice(files))

        if thumb_type == "ai":
            return self._generate_thumbnail_ai(thumb_config)

        # type == "file"
        if not source:
            print("[YouTube] thumbnail.source não configurado")
            return None
        if not os.path.exists(source):
            print(f"[YouTube] Arquivo de thumbnail não encontrado: {source}")
            return None
        return source

    def _generate_thumbnail_ai(self, thumb_config: dict) -> str | None:
        """
        Gera thumbnail via Pollinations API e salva na pasta do vídeo.

        A thumbnail é salva em output/{slug}/thumbnail.png automaticamente,
        derivado de video_path — sem precisar configurar nenhum caminho no JSON.

        Configuração esperada em thumb_config:
            prompt          (str)  obrigatório — descrição da imagem
            provider        (str)  opcional    — default "pollinations"
            model           (str)  opcional    — default "flux"
            width           (int)  opcional    — default 1280
            height          (int)  opcional    — default 720
            quality         (str)  opcional    — "low"|"medium"|"high"|"hd", default "hd"
            seed            (int)  opcional    — para reproduzibilidade
            negative_prompt (str)  opcional    — o que evitar na imagem
            enhance         (bool) opcional    — deixar IA melhorar o prompt
        """
        try:
            from libs.AIProviders import ai_manager
        except ImportError:
            print("[YouTube] ❌ AIProviders não disponível para geração de thumbnail")
            return None

        prompt = thumb_config.get("prompt", "")
        if not prompt:
            print("[YouTube] ❌ thumbnail.prompt é obrigatório para type: 'ai'")
            return None

        # Deriva o caminho de saída a partir do video_path — sempre na pasta do vídeo
        output_path = self._resolve_thumbnail_output_path()
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        generate_params = {
            "model":           thumb_config.get("model", "flux"),
            "width":           thumb_config.get("width", 1280),
            "height":          thumb_config.get("height", 720),
            "quality":         thumb_config.get("quality", "hd"),
            "enhance":         thumb_config.get("enhance", False),
            "negative_prompt": thumb_config.get(
                "negative_prompt",
                "worst quality, blurry, text, watermark, low resolution"
            ),
        }

        if "seed" in thumb_config:
            generate_params["seed"] = thumb_config["seed"]

        provider = thumb_config.get("provider", "pollinations")

        print(f"[YouTube] 🎨 Gerando thumbnail via IA (provider={provider}, model={generate_params['model']})...")
        print(f"[YouTube] Prompt: {prompt[:80]}{'...' if len(prompt) > 80 else ''}")
        print(f"[YouTube] Salvando em: {output_path}")

        result = ai_manager.generate_image(prompt=prompt, provider=provider, **generate_params)

        if not result.get("success"):
            print(f"[YouTube] ❌ Falha ao gerar thumbnail: {result.get('error')}")
            return None

        with open(output_path, "wb") as f:
            f.write(result["content"])

        model_used = result.get("model_used", generate_params["model"])
        attempts   = result.get("attempts", 1)
        size_kb    = len(result["content"]) // 1024

        print(f"[YouTube] ✅ Thumbnail gerada: {output_path}")
        print(f"[YouTube]    Modelo: {model_used} | Tentativas: {attempts} | Tamanho: {size_kb}KB")

        return output_path

    def upload_thumbnail(self, video_id: str, thumbnail_path: str):
        """Faz upload da thumbnail para o vídeo especificado."""
        if not os.path.exists(thumbnail_path):
            print(f"[YouTube] Thumbnail não encontrada: {thumbnail_path}")
            return

        creds = self._get_credentials()
        youtube = build("youtube", "v3", credentials=creds)

        ext = os.path.splitext(thumbnail_path)[1].lower()
        mimetype = "image/png" if ext == ".png" else "image/jpeg"

        media = MediaFileUpload(thumbnail_path, mimetype=mimetype, resumable=True)
        youtube.thumbnails().set(videoId=video_id, media_body=media).execute()

        print(f"✅ Thumbnail enviada: {os.path.basename(thumbnail_path)}")

    # ---------------------------------------------------------
    # UPLOAD DE VÍDEO
    # ---------------------------------------------------------
    def upload(self) -> str:
        """Realiza o upload do vídeo para o canal autenticado."""
        creds = self._get_credentials()
        youtube = build("youtube", "v3", credentials=creds)

        request_body = {
            "snippet": {
                "title": self.title,
                "description": self.description,
                "tags": self.tags,
                "categoryId": self.category_id
            },
            "status": {
                "privacyStatus": self.privacy_status
            }
        }

        if self.publish_at and self.privacy_status == "private":
            print(f"📅 Agendando publicação...")
            utc_time = self._convert_to_utc(self.publish_at, self.timezone)
            request_body["status"]["publishAt"] = utc_time
            print(f"✅ Vídeo será publicado em: {self.publish_at} ({self.timezone})")
        elif self.publish_at and self.privacy_status != "private":
            print("⚠️  AVISO: Para agendar publicação, o vídeo deve estar como 'private'")
            print("⚠️  Ignorando agendamento e mantendo privacidade configurada")

        if not os.path.exists(self.video_path):
            raise FileNotFoundError(f"Arquivo de vídeo não encontrado: {self.video_path}")

        media = MediaFileUpload(self.video_path, chunksize=-1, resumable=True)

        print("📤 Iniciando upload...")
        upload = youtube.videos().insert(
            part="snippet,status",
            body=request_body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = upload.next_chunk()
            if status and self.verbose:
                print(f"Progresso: {int(status.progress() * 100)}%")

        print("✅ Upload concluído!")
        print(f"🔗 Link do vídeo: https://youtu.be/{response['id']}")

        return response["id"]

    # ---------------------------------------------------------
    # UTILITÁRIOS
    # ---------------------------------------------------------
    def set_item(self, key, value):
        """Altera qualquer configuração dinamicamente."""
        self.config[key] = value
        setattr(self, key, value)


if __name__ == "__main__":
    FILE_JSON_SAVE = "the_touchline_record.json"
    yt = YouTube(params={"token_file_name": FILE_JSON_SAVE})
    yt.generate_token()
