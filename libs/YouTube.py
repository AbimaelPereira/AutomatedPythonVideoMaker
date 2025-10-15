import os
import datetime
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

            # parâmetros padrão de upload
            "video_path": os.getenv("VIDEO_PATH", "test_video.mp4"),
            "title": os.getenv("VIDEO_TITLE", "🎥 Teste de Upload via API"),
            "description": os.getenv("VIDEO_DESCRIPTION", "Vídeo de teste enviado automaticamente via API do YouTube."),
            "tags": os.getenv("VIDEO_TAGS", "python,youtube,teste").split(","),
            "category_id": os.getenv("VIDEO_CATEGORY_ID", "22"),  # 22 = People & Blogs
            "privacy_status": os.getenv("VIDEO_PRIVACY", "private"),  # private | unlisted | public
            "publish_at": os.getenv("VIDEO_PUBLISH_AT"),  # formato: YYYY-MM-DD HH:MM:SS
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

        # Atualiza token expirado automaticamente
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
    # UPLOAD DE VÍDEO
    # ---------------------------------------------------------
    def upload(self):
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

        # Agendamento opcional
        if self.publish_at and self.privacy_status == "private":
            dt = datetime.datetime.strptime(self.publish_at, "%Y-%m-%d %H:%M:%S")
            request_body["status"]["publishAt"] = dt.isoformat() + "Z"

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
