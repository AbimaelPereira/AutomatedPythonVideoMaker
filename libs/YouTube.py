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
            "thumbnail": None,  # {"type": "file"|"directory", "source": "..."}
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
    def _resolve_thumbnail_path(self) -> str | None:
        """Resolve o caminho da thumbnail a partir da config."""
        thumb_config = self.thumbnail
        if not thumb_config:
            return None

        thumb_type = thumb_config.get("type", "file")
        source = thumb_config.get("source")

        if not source:
            print("[YouTube] thumbnail.source não configurado")
            return None

        if thumb_type == "directory":
            if not os.path.isdir(source):
                print(f"[YouTube] Diretório de thumbnail não encontrado: {source}")
                return None
            valid_extensions = (".jpg", ".jpeg", ".png", ".webp")
            files = [f for f in os.listdir(source) if f.lower().endswith(valid_extensions)]
            if not files:
                print(f"[YouTube] Nenhuma imagem válida em: {source}")
                return None
            return os.path.join(source, random.choice(files))

        # type == "file"
        if not os.path.exists(source):
            print(f"[YouTube] Arquivo de thumbnail não encontrado: {source}")
            return None
        return source

    def upload_thumbnail(self, video_id: str, thumbnail_path: str):
        """Faz upload da thumbnail para o vídeo especificado."""
        if not os.path.exists(thumbnail_path):
            print(f"[YouTube] Thumbnail não encontrada: {thumbnail_path}")
            return

        creds = self._get_credentials()
        youtube = build("youtube", "v3", credentials=creds)

        media = MediaFileUpload(thumbnail_path, mimetype="image/jpeg", resumable=True)
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
    FILE_JSON_SAVE = "geopolitica_em_foco.json"
    yt = YouTube(params={"token_file_name": FILE_JSON_SAVE})
    yt.generate_token()