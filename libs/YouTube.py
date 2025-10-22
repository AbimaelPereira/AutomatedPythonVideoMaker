import os
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

            # parâmetros padrão de upload
            "video_path": os.getenv("VIDEO_PATH", "test_video.mp4"),
            "title": os.getenv("VIDEO_TITLE", "🎥 Teste de Upload via API"),
            "description": os.getenv("VIDEO_DESCRIPTION", "Vídeo de teste enviado automaticamente via API do YouTube."),
            "pinned_comment": os.getenv("VIDEO_PINNED_COMMENT", False),
            "tags": os.getenv("VIDEO_TAGS", "python,youtube,teste").split(","),
            "category_id": os.getenv("VIDEO_CATEGORY_ID", "22"),  # 22 = People & Blogs
            "privacy_status": os.getenv("VIDEO_PRIVACY", "private"),  # private | unlisted | public
            "publish_at": os.getenv("VIDEO_PUBLISH_AT"),  # formato: YYYY-MM-DD HH:MM:SS
            "timezone": os.getenv("TIMEZONE", "America/Sao_Paulo"),  # Fuso horário padrão
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
    # CONVERSÃO DE FUSO HORÁRIO
    # ---------------------------------------------------------
    def _convert_to_utc(self, datetime_str, timezone_str):
        """
        Converte um datetime local para UTC (formato ISO 8601).
        
        Args:
            datetime_str: String no formato "YYYY-MM-DD HH:MM:SS"
            timezone_str: Nome do fuso horário (ex: "America/Sao_Paulo")
        
        Returns:
            String no formato ISO 8601 com timezone UTC (ex: "2025-10-16T15:00:00Z")
        """
        try:
            # Parse da data sem timezone
            dt_naive = datetime.datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
            
            # Adiciona timezone local
            local_tz = ZoneInfo(timezone_str)
            dt_local = dt_naive.replace(tzinfo=local_tz)
            
            # Converte para UTC
            dt_utc = dt_local.astimezone(ZoneInfo("UTC"))
            
            # Formata para ISO 8601
            iso_format = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            
            if self.verbose:
                print(f"🕐 Horário local ({timezone_str}): {dt_local.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                print(f"🌍 Horário UTC: {dt_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                print(f"📅 Formato ISO 8601: {iso_format}")
            
            return iso_format
            
        except Exception as e:
            print(f"❌ Erro ao converter timezone: {e}")
            print(f"💡 Usando horário sem conversão")
            # Fallback: tenta formato direto
            dt = datetime.datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
            return dt.isoformat() + "Z"

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

        if self.pinned_comment:
            request_body["snippet"]["pinnedComment"] = self.pinned_comment

        # Agendamento opcional - SEMPRE em UTC
        if self.publish_at and self.privacy_status == "private":
            print(f"📅 Agendando publicação...")
            
            # Converte para UTC usando o timezone configurado
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