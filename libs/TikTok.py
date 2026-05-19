import os
import json
import time
import webbrowser
import urllib.parse
import hashlib
import secrets
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
from dotenv import load_dotenv

load_dotenv()


class TikTok:
    def __init__(self, params=None):
        defaults = {
            "client_key":       os.getenv("TIKTOK_CLIENT_KEY"),
            "client_secret":    os.getenv("TIKTOK_CLIENT_SECRET"),
            "token_dir":        os.getenv("TOKEN_DIR", "tokens"),
            "token_file_name":  "tiktok_token.json",
            "video_path":       None,
            "caption":          "",
            "privacy_level":    "SELF_ONLY",
            "disable_duet":     False,
            "disable_comment":  False,
            "disable_stitch":   False,
            "verbose":          True,
        }
        if params:
            defaults.update(params)

        self.config = defaults
        for k, v in defaults.items():
            setattr(self, k, v)

        os.makedirs(self.token_dir, exist_ok=True)
        self.token_path = os.path.join(self.token_dir, self.token_file_name)

        self._AUTH_URL     = "https://www.tiktok.com/v2/auth/authorize/"
        self._TOKEN_URL    = "https://open.tiktokapis.com/v2/oauth/token/"
        self._UPLOAD_INIT  = "https://open.tiktokapis.com/v2/post/publish/video/init/"
        self._SCOPES       = "user.info.basic,video.publish,video.upload"
        # TIKTOK_REDIRECT_URI deve ser a URL pública cadastrada no app (ex: URL do ngrok)
        # O servidor local sempre escuta na porta 8085 independente da URI pública
        self._REDIRECT_URI      = os.getenv("TIKTOK_REDIRECT_URI", "http://localhost:8085/callback")
        self._LOCAL_SERVER_PORT = 8085

    # ---------------------------------------------------------
    # AUTENTICAÇÃO
    # ---------------------------------------------------------
    def _load_token(self):
        if not os.path.exists(self.token_path):
            return None
        try:
            with open(self.token_path) as f:
                return json.load(f)
        except Exception as e:
            print(f"[TikTok] Erro ao carregar token: {e}")
            return None

    def _save_token(self, token_data):
        token_data["saved_at"] = int(time.time())
        with open(self.token_path, "w") as f:
            json.dump(token_data, f, indent=2)
        if self.verbose:
            print(f"[TikTok] Token salvo em: {self.token_path}")

    def _is_token_expired(self, token_data):
        saved_at    = token_data.get("saved_at", 0)
        expires_in  = token_data.get("expires_in", 0)
        # considera expirado 60 segundos antes para margem de segurança
        return int(time.time()) >= saved_at + expires_in - 60

    def _refresh_token(self, token_data):
        refresh_token = token_data.get("refresh_token")
        if not refresh_token:
            raise RuntimeError("[TikTok] Nenhum refresh_token disponível. Execute generate_token().")

        print("[TikTok] Renovando access_token...")
        resp = requests.post(self._TOKEN_URL, data={
            "client_key":     self.client_key,
            "client_secret":  self.client_secret,
            "grant_type":     "refresh_token",
            "refresh_token":  refresh_token,
        })
        resp.raise_for_status()
        new_data = resp.json()

        if new_data.get("error"):
            raise RuntimeError(f"[TikTok] Falha ao renovar token: {new_data}")

        # preserva o refresh_token antigo caso o novo não venha na resposta
        if "refresh_token" not in new_data:
            new_data["refresh_token"] = refresh_token

        self._save_token(new_data)
        print("[TikTok] Token renovado com sucesso.")
        return new_data

    def _get_access_token(self):
        token_data = self._load_token()

        if not token_data:
            self.generate_token()
            token_data = self._load_token()

        if self._is_token_expired(token_data):
            token_data = self._refresh_token(token_data)

        return token_data["access_token"]

    def generate_token(self):
        """Abre o navegador e gera um novo token OAuth2 via Authorization Code Flow."""
        if not self.client_key or not self.client_secret:
            raise RuntimeError(
                "[TikTok] TIKTOK_CLIENT_KEY e TIKTOK_CLIENT_SECRET devem estar configurados."
            )

        code_verifier  = secrets.token_urlsafe(64)
        code_challenge = hashlib.sha256(code_verifier.encode()).hexdigest()
        state          = secrets.token_hex(16)

        auth_params = {
            "client_key":              self.client_key,
            "scope":                   self._SCOPES,
            "response_type":           "code",
            "redirect_uri":            self._REDIRECT_URI,
            "state":                   state,
            "code_challenge":          code_challenge,
            "code_challenge_method":   "S256",
        }
        auth_url = self._AUTH_URL + "?" + urllib.parse.urlencode(auth_params)

        print("[TikTok] Abrindo navegador para autenticação...")
        print(f"[TikTok] URL: {auth_url}")
        webbrowser.open(auth_url)

        # captura o callback via servidor HTTP temporário
        auth_code = self._capture_auth_code(state)

        print("[TikTok] Trocando código de autorização por access_token...")
        resp = requests.post(self._TOKEN_URL, data={
            "client_key":     self.client_key,
            "client_secret":  self.client_secret,
            "code":           auth_code,
            "grant_type":     "authorization_code",
            "redirect_uri":   self._REDIRECT_URI,
            "code_verifier":  code_verifier,
        })
        resp.raise_for_status()
        token_data = resp.json()

        if token_data.get("error"):
            raise RuntimeError(f"[TikTok] Falha ao obter token: {token_data}")

        self._save_token(token_data)
        print("[TikTok] Autenticação concluída com sucesso!")

    def _capture_auth_code(self, expected_state):
        """Sobe um servidor HTTP local temporário para capturar o código OAuth2."""
        captured = {}

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                params = urllib.parse.parse_qs(parsed.query)
                captured["code"]  = params.get("code",  [None])[0]
                captured["state"] = params.get("state", [None])[0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"<h2>Autoriza\xc3\xa7\xc3\xa3o conclu\xc3\xadda! Pode fechar esta aba.</h2>")

            def log_message(self, format, *args):
                pass  # silencia logs do servidor

        server = HTTPServer(("localhost", self._LOCAL_SERVER_PORT), CallbackHandler)
        server.handle_request()  # aguarda exatamente uma requisição
        server.server_close()

        if captured.get("state") != expected_state:
            raise RuntimeError("[TikTok] State OAuth2 inválido — possível ataque CSRF.")
        if not captured.get("code"):
            raise RuntimeError("[TikTok] Nenhum código de autorização recebido.")

        return captured["code"]

    # ---------------------------------------------------------
    # UPLOAD DE VÍDEO
    # ---------------------------------------------------------
    def _init_upload(self, access_token, file_size):
        """Inicializa o upload via Direct Post e retorna publish_id + upload_url."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/json; charset=UTF-8",
        }
        body = {
            "post_info": {
                "title":           self.caption,
                "privacy_level":   self.privacy_level,
                "disable_duet":    self.disable_duet,
                "disable_comment": self.disable_comment,
                "disable_stitch":  self.disable_stitch,
            },
            "source_info": {
                "source":          "FILE_UPLOAD",
                "video_size":      file_size,
                "chunk_size":      file_size,
                "total_chunk_count": 1,
            },
        }

        resp = requests.post(self._UPLOAD_INIT, headers=headers, json=body)

        if self.verbose:
            print(f"[TikTok] Init upload status: {resp.status_code}")

        resp.raise_for_status()
        data = resp.json()

        if data.get("error", {}).get("code") not in (None, "ok"):
            raise RuntimeError(f"[TikTok] Falha ao inicializar upload: {data}")

        publish_id = data["data"]["publish_id"]
        upload_url = data["data"]["upload_url"]
        return publish_id, upload_url

    def _send_video_chunk(self, upload_url, video_bytes, file_size):
        """Envia o vídeo em um único chunk para a upload_url retornada pelo TikTok."""
        headers = {
            "Content-Range":  f"bytes 0-{file_size - 1}/{file_size}",
            "Content-Type":   "video/mp4",
            "Content-Length": str(file_size),
        }
        resp = requests.put(upload_url, headers=headers, data=video_bytes)

        if self.verbose:
            print(f"[TikTok] Chunk upload status: {resp.status_code}")

        if resp.status_code not in (200, 201, 204):
            raise RuntimeError(
                f"[TikTok] Falha ao enviar chunk: HTTP {resp.status_code} — {resp.text}"
            )

    def upload(self):
        """Realiza o upload do vídeo para o TikTok via Content Posting API (Direct Post)."""
        if not self.video_path or not os.path.exists(self.video_path):
            raise FileNotFoundError(f"[TikTok] Arquivo de vídeo não encontrado: {self.video_path}")

        if not self.client_key or not self.client_secret:
            raise RuntimeError(
                "[TikTok] TIKTOK_CLIENT_KEY e TIKTOK_CLIENT_SECRET devem estar configurados."
            )

        access_token = self._get_access_token()

        with open(self.video_path, "rb") as f:
            video_bytes = f.read()
        file_size = len(video_bytes)

        if self.verbose:
            print(f"[TikTok] Iniciando upload: {os.path.basename(self.video_path)} ({file_size // 1024}KB)")
            print(f"[TikTok] Caption: {self.caption[:80]}{'...' if len(self.caption) > 80 else ''}")
            print(f"[TikTok] Privacy: {self.privacy_level}")

        publish_id, upload_url = self._init_upload(access_token, file_size)
        print(f"[TikTok] Upload inicializado. publish_id: {publish_id}")

        self._send_video_chunk(upload_url, video_bytes, file_size)

        print(f"[TikTok] Upload concluído! publish_id: {publish_id}")
        return publish_id

    # ---------------------------------------------------------
    # UTILITÁRIOS
    # ---------------------------------------------------------
    def set_item(self, key, value):
        """Altera qualquer configuração dinamicamente."""
        self.config[key] = value
        setattr(self, key, value)


if __name__ == "__main__":
    # Exemplo: gera token OAuth2 para a conta TikTok
    # Configure TIKTOK_CLIENT_KEY e TIKTOK_CLIENT_SECRET no .env antes de executar
    tt = TikTok(params={"token_file_name": "tiktok_devocional.json"})
    tt.generate_token()
