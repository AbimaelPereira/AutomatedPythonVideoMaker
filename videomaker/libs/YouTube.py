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

# Escopos completos da conta do YouTube. O upload sozinho precisa apenas de
# `youtube.upload`, mas o mesmo token serve a leitura (Analytics, listagem de
# vídeos privados) e a playlists — pedir tudo de uma vez evita um segundo
# consentimento no navegador quando essas funções são usadas.
#
# ATENÇÃO: um token gerado com menos escopos NÃO ganha os novos sozinho. O
# Analytics devolve HTTP 403 com um token de escopo único, e o erro parece ser
# de permissão do canal. Regere o token (`generate_token()`) para ampliar.
SCOPES = [
    # Data API v3
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.channel-memberships.creator",
    "https://www.googleapis.com/auth/youtube.third-party-link.creator",
    "https://www.googleapis.com/auth/youtubepartner",
    "https://www.googleapis.com/auth/youtubepartner-channel-audit",
    # Analytics / Reporting API
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/yt-analytics-monetary.readonly",
]


class YouTube:
    def __init__(self, params=None):
        def to_bool(value):
            return str(value).lower() in ("true", "1", "yes", "on")

        defaults = {
            "client_secrets_file": os.getenv("CLIENT_SECRETS_FILE", "tokens/youtube_client_secret.json"),
            "token_dir": os.getenv("TOKEN_DIR", "tokens"),
            "token_file_name": os.getenv("TOKEN_FILE_NAME", "token_default.json"),
            "scopes": SCOPES,
            "verbose": to_bool(os.getenv("VERBOSE", True)),

            "video_path": os.getenv("VIDEO_PATH", "test_video.mp4"),
            "title": os.getenv("VIDEO_TITLE", "🎥 Teste de Upload via API"),
            "description": os.getenv("VIDEO_DESCRIPTION", "Vídeo de teste enviado automaticamente via API do YouTube."),
            "tags": os.getenv("VIDEO_TAGS", "python,youtube,teste").split(","),
            "category_id": os.getenv("VIDEO_CATEGORY_ID", "22"),
            # Idioma do título/descrição e do áudio falado. Sem eles o YouTube
            # não sabe em que língua o vídeo está, o que prejudica legenda
            # automática, legenda traduzida e alcance internacional.
            # `None` = não enviar o campo, para não rotular errado quem não
            # declarou nada.
            "default_language": os.getenv("VIDEO_DEFAULT_LANGUAGE"),
            "default_audio_language": os.getenv("VIDEO_DEFAULT_AUDIO_LANGUAGE"),
            "privacy_status": os.getenv("VIDEO_PRIVACY", "private"),
            "publish_at": os.getenv("VIDEO_PUBLISH_AT"),
            "timezone": os.getenv("TIMEZONE", "America/Sao_Paulo"),
            "thumbnail": None,  # {"type": "file"|"directory"|"ai"|"scene", ...}
            # Contexto injetado pelo UnifiedVideoEngine para o `type: "scene"`
            # compor a thumbnail com as mesmas engines do vídeo (fundo herdado,
            # assets do vídeo e slugs de remote_asset compartilhados).
            "global_settings": None,
            "asset_store": None,
            "remote_asset_manager": None,
            "video_resolution": None,
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
    def _escopos_do_token(self) -> list:
        """Os escopos que o token em disco REALMENTE tem.

        Crucial: um token antigo foi concedido com menos escopos do que o
        `SCOPES` de hoje. Pedir ao Google a renovação com escopos que o
        refresh_token não cobre falha com `invalid_scope: Bad Request` — e o
        canal que fazia upload normalmente pararia de funcionar.
        Por isso o token manda, não a constante.
        """
        try:
            import json as _json
            gravados = _json.load(open(self.token_path)).get("scopes")
            if gravados:
                return gravados
        except Exception:
            pass
        return self.scopes

    def _get_credentials(self):
        """Carrega o token salvo ou cria um novo."""
        creds = None

        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(
                self.token_path, self._escopos_do_token())
        else:
            self.generate_token()
            creds = Credentials.from_authorized_user_file(
                self.token_path, self._escopos_do_token())

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                self.generate_token()
                creds = Credentials.from_authorized_user_file(
                    self.token_path, self._escopos_do_token())

        return creds

    def generate_token(self):
        """Abre o navegador e gera um novo token OAuth2.

        Faz backup do token anterior em `.bak` antes de sobrescrever: um
        consentimento interrompido no meio deixaria o canal sem token nenhum.
        """
        import shutil

        print("🌐 Iniciando autenticação no Google...")
        if os.path.exists(self.token_path):
            shutil.copy2(self.token_path, self.token_path + ".bak")

        flow = InstalledAppFlow.from_client_secrets_file(self.client_secrets_file, self.scopes)
        creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

        with open(self.token_path, "w") as token:
            token.write(creds.to_json())
        os.chmod(self.token_path, 0o600)

        print(f"✅ Token gerado e salvo em: {self.token_path}")

        negados = set(self.scopes) - set(creds.granted_scopes or creds.scopes or [])
        if negados:
            print(f"⚠️  Escopos NEGADOS: {sorted(negados)}")
        else:
            print("✅ Todos os escopos concedidos.")

    def status_token(self) -> dict:
        """Diagnostica o token sem abrir navegador nem chamar a API.

        Serve ao `GET /youtube/{slug}/token`: diz se o arquivo existe, se as
        credenciais ainda valem e quais escopos foram concedidos. Nunca dispara
        o fluxo de consentimento — por isso não usa `_get_credentials()`.
        """
        info = {"token_path": self.token_path, "existe": os.path.exists(self.token_path)}
        if not info["existe"]:
            return info

        try:
            creds = Credentials.from_authorized_user_file(
                self.token_path, self._escopos_do_token())
        except Exception as e:
            info["erro"] = f"{type(e).__name__}: {e}"
            return info

        concedidos = set(creds.granted_scopes or creds.scopes or [])
        faltando = sorted(set(SCOPES) - concedidos)
        # Sem estes dois a Analytics API recusa tudo com 403 — é o que separa
        # um token que só sobe vídeo de um que também lê métricas.
        analytics = {"https://www.googleapis.com/auth/yt-analytics.readonly",
                     "https://www.googleapis.com/auth/yt-analytics-monetary.readonly"}
        info.update({
            "valido": bool(creds.valid),
            "expirado": bool(creds.expired),
            "tem_refresh_token": bool(creds.refresh_token),
            "escopos_concedidos": sorted(concedidos),
            "escopos_faltando": faltando,
            "pode_ler_analytics": not (analytics - concedidos),
            "precisa_regerar": bool(faltando),
        })
        return info

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
          - type: "scene"     → compõe background + visual_elements (mesmas engines
                                do vídeo) e salva em output/{slug}/thumbnail.png
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

        if thumb_type == "scene":
            return self._generate_thumbnail_scene(thumb_config)

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
            parameters      (dict) opcional    — argumentos do provider, e SÓ aqui:
                model           default "flux"
                width / height  default 1280 / 720
                quality         "low"|"medium"|"high"|"hd", default "hd"
                seed, negative_prompt, enhance, enable_fallback

        Argumento do provider solto em thumb_config é erro (ver AIProviders/params.py).
        O default do canal em global_settings.ai.parameters também vale aqui.
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

        from libs.AIProviders.params import resolve_parameters
        try:
            generate_params = resolve_parameters(
                thumb_config, self.global_settings, "youtube.thumbnail",
                defaults={
                    "model": "flux", "width": 1280, "height": 720,
                    "quality": "hd", "enhance": False,
                    "negative_prompt": "worst quality, blurry, text, watermark, low resolution",
                },
            )
        except ValueError as e:
            print(f"[YouTube] ❌ {e}")
            return None

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

    def _generate_thumbnail_scene(self, thumb_config: dict) -> str | None:
        """Compõe a thumbnail a partir de `background` + `visual_elements`.

        Delega ao `ThumbnailRenderer`, que reusa as engines do vídeo. Os
        intermediários vão para a pasta do vídeo, então uma imagem de IA gerada
        aqui fica visível junto do resto do material do render.
        """
        try:
            from libs.Thumbnail import ThumbnailRenderer
        except ImportError as e:
            print(f"[YouTube] ❌ ThumbnailRenderer não disponível: {e}")
            return None

        output_path = self._resolve_thumbnail_output_path()
        work_dir = os.path.join(os.path.dirname(output_path), "thumbnail_tmp")

        try:
            return ThumbnailRenderer.render(
                thumb_config,
                output_path,
                global_settings=self.global_settings,
                work_dir=work_dir,
                asset_store=self.asset_store,
                remote_asset_manager=self.remote_asset_manager,
                video_resolution=self.video_resolution,
                log_prefix="[YouTube]",
            )
        except Exception as e:
            print(f"[YouTube] ❌ Falha ao compor thumbnail: {type(e).__name__}: {e}")
            return None

    THUMBNAIL_MAX_TENTATIVAS = 5

    def upload_thumbnail(self, video_id: str, thumbnail_path: str) -> bool:
        """Faz upload da thumbnail para o vídeo especificado.

        Chamado DEPOIS do vídeo já estar no canal, então uma falha aqui não
        pode derrubar o processo: o vídeo existe e a thumbnail é reenviável a
        qualquer momento (por esta função ou pelo Studio). Por isso tenta
        algumas vezes e devolve False em vez de levantar exceção.
        """
        import time

        if not os.path.exists(thumbnail_path):
            print(f"[YouTube] Thumbnail não encontrada: {thumbnail_path}")
            return False

        creds = self._get_credentials()
        youtube = build("youtube", "v3", credentials=creds)

        ext = os.path.splitext(thumbnail_path)[1].lower()
        mimetype = "image/png" if ext == ".png" else "image/jpeg"

        for tentativa in range(1, self.THUMBNAIL_MAX_TENTATIVAS + 1):
            try:
                # O MediaFileUpload é recriado a cada tentativa de propósito:
                # um upload não-retomável que falhou deixa o objeto inutilizável.
                media = MediaFileUpload(thumbnail_path, mimetype=mimetype, resumable=True)
                youtube.thumbnails().set(videoId=video_id, media_body=media).execute()
                print(f"✅ Thumbnail enviada: {os.path.basename(thumbnail_path)}")
                return True
            except Exception as e:
                print(f"  [thumbnail] tentativa {tentativa}/"
                      f"{self.THUMBNAIL_MAX_TENTATIVAS} falhou: {type(e).__name__}")
                if tentativa == self.THUMBNAIL_MAX_TENTATIVAS:
                    print(f"⚠️  Thumbnail NÃO enviada. Suba manualmente: {thumbnail_path}")
                    return False
                time.sleep(2 ** tentativa)
        return False

    # ---------------------------------------------------------
    # UPLOAD DE VÍDEO
    # ---------------------------------------------------------
    # Teto de tags do YouTube: 500 caracteres somando TODAS as tags mais as
    # vírgulas que as separam. Estourar devolve HTTP 400 `invalidTags`:
    #     "The request metadata specifies invalid video keywords."
    # A mensagem não menciona comprimento, então o erro parece ser de caractere
    # inválido. Custou um render de 2h57m em 22/09/2026 (547 chars).
    TAGS_MAX_CHARS = 500

    @classmethod
    def _tags_dentro_do_limite(cls, tags) -> list:
        """Corta as tags que não cabem, preservando a ORDEM.

        As primeiras tags são as de maior valor de SEO, então descartar a
        cauda é melhor do que falhar o upload inteiro depois do render.
        """
        if not tags:
            return []
        mantidas, total = [], 0
        for tag in tags:
            custo = len(tag) + (1 if mantidas else 0)
            if total + custo > cls.TAGS_MAX_CHARS:
                print(f"[YouTube] ⚠️ Tags passam de {cls.TAGS_MAX_CHARS} chars — "
                      f"cortando {len(tags) - len(mantidas)} do fim "
                      f"(a partir de {tag!r}).")
                break
            mantidas.append(tag)
            total += custo
        return mantidas

    # Limites do YouTube que só aparecem como HTTP 400 depois do upload começar.
    TITLE_MAX_CHARS = 100
    DESCRIPTION_MAX_CHARS = 5000
    THUMBNAIL_MAX_BYTES = 2 * 1024 * 1024

    def validar(self, check_video: bool = True) -> list[str]:
        """Checa os metadados ANTES de renderizar/subir. Devolve lista de problemas.

        Toda regra aqui é de algo que só falharia depois do upload ter começado
        — ou, pior, que subiria errado em silêncio. Rodar isto custa
        milissegundos; descobrir no fim de um render custa horas.

        `check_video=False` ignora a existência do MP4, para validar metadados
        antes de o arquivo existir (é o caso da checagem pré-render).
        """
        problemas = []

        if check_video:
            if not self.video_path:
                problemas.append("video_path não configurado.")
            elif not os.path.exists(self.video_path):
                problemas.append(f"MP4 não existe: {self.video_path}")

        titulo = self.title or ""
        if not titulo.strip():
            problemas.append("Título vazio.")
        elif len(titulo) > self.TITLE_MAX_CHARS:
            problemas.append(f"Título tem {len(titulo)} chars — o YouTube corta "
                             f"em {self.TITLE_MAX_CHARS}.")

        if len(self.description or "") > self.DESCRIPTION_MAX_CHARS:
            problemas.append(f"Descrição tem {len(self.description)} chars "
                             f"(limite {self.DESCRIPTION_MAX_CHARS}).")

        # Mesma conta do `_tags_dentro_do_limite`: soma das tags + as vírgulas.
        tags = self.tags or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        custo = sum(len(t) for t in tags) + max(0, len(tags) - 1)
        if custo > self.TAGS_MAX_CHARS:
            problemas.append(f"Tags somam {custo} chars (limite "
                             f"{self.TAGS_MAX_CHARS}) — as do fim seriam cortadas.")

        problemas += self._validar_thumbnail()
        problemas += self._validar_agendamento()

        # Sem token, `_get_credentials()` chama `generate_token()`, que abre o
        # navegador e BLOQUEIA esperando o clique. Num job de madrugada isso
        # trava para sempre, depois do render inteiro.
        if not os.path.exists(self.token_path):
            problemas.append(f"Token OAuth não encontrado: {self.token_path} "
                             "(o upload abriria o navegador pedindo login).")

        return problemas

    def _validar_thumbnail(self) -> list[str]:
        """Checagens da thumbnail que não exigem gerá-la."""
        th = self.thumbnail or {}
        if not th:
            return []

        tipo = th.get("type", "file")
        source = th.get("source")

        # `ai` e `scene` produzem a imagem durante o upload; não há o que
        # conferir antes, o arquivo ainda não existe.
        if tipo in ("ai", "scene"):
            if tipo == "ai" and not (th.get("prompt") or {}):
                return ["thumbnail.type='ai' sem `prompt`."]
            return []

        if not source:
            return [f"thumbnail.type={tipo!r} sem `source`."]

        if tipo == "directory":
            if not os.path.isdir(source):
                return [f"Diretório de thumbnail não encontrado: {source}"]
            válidas = (".jpg", ".jpeg", ".png", ".webp")
            if not [f for f in os.listdir(source) if f.lower().endswith(válidas)]:
                return [f"Nenhuma imagem válida em: {source}"]
            return []

        # type == "file"
        if not os.path.exists(source):
            return [f"Thumbnail não encontrada: {source}"]
        if os.path.getsize(source) > self.THUMBNAIL_MAX_BYTES:
            return [f"Thumbnail passa de 2MB ({os.path.getsize(source)/1e6:.1f} MB) "
                    "— o YouTube recusa."]
        return []

    def _validar_agendamento(self) -> list[str]:
        """Checagens do `publish_at`.

        A regra que mais machuca: o agendamento SÓ vale com
        `privacy_status='private'`. Com qualquer outro valor o upload descarta o
        `publishAt` com um aviso e o vídeo fica VISÍVEL na hora — o oposto do
        pretendido.
        """
        if not self.publish_at:
            return []

        problemas = []
        tz = self.timezone or "America/Sao_Paulo"

        if self.privacy_status != "private":
            problemas.append(
                f"publish_at com privacy_status={self.privacy_status!r} — o "
                "agendamento é IGNORADO e o vídeo sai imediatamente. Use 'private'.")

        try:
            quando = datetime.datetime.strptime(self.publish_at, "%Y-%m-%d %H:%M:%S") \
                .replace(tzinfo=ZoneInfo(tz))
            faltam = (quando - datetime.datetime.now(ZoneInfo(tz))).total_seconds()
            if faltam < 0:
                problemas.append(f"publish_at já passou ({self.publish_at} {tz}) "
                                 "— o YouTube publicaria na hora.")
            elif faltam < 900:
                problemas.append(f"publish_at em {faltam/60:.0f} min — o upload de "
                                 "um arquivo grande pode não terminar a tempo.")
        except Exception as e:
            problemas.append(f"publish_at inválido ({self.publish_at!r} / {tz!r}): {e}")

        # Canal em inglês com o timezone default brasileiro desloca a
        # publicação em várias horas, silenciosamente.
        if tz == "America/Sao_Paulo" and (self.default_language or "").startswith("en"):
            problemas.append("timezone='America/Sao_Paulo' (o default) num canal em "
                             "inglês — declare o fuso do público, ex. 'America/New_York'.")

        return problemas

    def upload(self) -> str:
        """Realiza o upload do vídeo para o canal autenticado."""
        creds = self._get_credentials()
        youtube = build("youtube", "v3", credentials=creds)

        tags = self._tags_dentro_do_limite(self.tags)

        request_body = {
            "snippet": {
                "title": self.title,
                "description": self.description,
                "tags": tags,
                "categoryId": self.category_id
            },
            "status": {
                "privacyStatus": self.privacy_status
            }
        }

        # Idioma: só entra quando declarado. Enviar `None` faz a API recusar o
        # campo, e cravar um default rotularia errado os canais em português.
        if self.default_language:
            request_body["snippet"]["defaultLanguage"] = self.default_language
        if self.default_audio_language:
            request_body["snippet"]["defaultAudioLanguage"] = \
                self.default_audio_language

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

        # "Conteúdo alterado ou sintético" (a pergunta de IA do Studio). Não se
        # marca por default: a pergunta é sobre conteúdo confundível com a
        # realidade (pessoa real, lugar real, simulação realista), e ilustração
        # estilizada de gente fictícia não é nada disso — o YouTube isenta
        # animação não realista explicitamente.
        #
        # O campo é WRITE-ONLY: `videos().list` NUNCA o devolve. A única forma
        # de conferir depois é abrir o Studio.
        if self.config.get("contains_synthetic_media"):
            request_body["status"]["containsSyntheticMedia"] = True
            print("🤖 Declarado 'Uso de IA' = Sim (pedido na config).")

        return self._upload_resiliente(request_body)

    # Blocos de 10MB: o protocolo resumable do Google permite repetir apenas o
    # bloco que falhou. Com `chunksize=-1` (arquivo inteiro numa requisição),
    # qualquer queda de conexão joga fora tudo que já subiu — num MP4 de 800MB
    # isso é meia hora de upload perdida.
    UPLOAD_CHUNK_MB = 10
    UPLOAD_MAX_TENTATIVAS = 12

    def _upload_resiliente(self, request_body: dict) -> str:
        """Sobe o MP4 em blocos, retomando de onde parou quando a conexão cai.

        O `request` é criado UMA vez e reusado entre as tentativas — é isso que
        preserva o progresso. Recriar o request começaria do zero e poderia
        gerar um vídeo duplicado no canal.
        """
        import random as _random
        import time

        creds = self._get_credentials()
        youtube = build("youtube", "v3", credentials=creds)

        media = MediaFileUpload(self.video_path,
                                chunksize=self.UPLOAD_CHUNK_MB * 1024 * 1024,
                                resumable=True, mimetype="video/mp4")
        request = youtube.videos().insert(part="snippet,status", body=request_body,
                                          media_body=media)

        total_mb = os.path.getsize(self.video_path) / 1e6
        print(f"📤 Enviando {total_mb:.0f} MB em blocos de {self.UPLOAD_CHUNK_MB} MB...")

        response, falhas, ultimo_pct = None, 0, -1
        while response is None:
            try:
                status, response = request.next_chunk()
                falhas = 0                      # progrediu: zera o contador
                if status and self.verbose:
                    pct = int(status.progress() * 100)
                    if pct != ultimo_pct:
                        print(f"  {pct:3d}%  ({status.resumable_progress/1e6:.0f}/"
                              f"{total_mb:.0f} MB)", flush=True)
                        ultimo_pct = pct
            except Exception as e:
                falhas += 1
                if falhas > self.UPLOAD_MAX_TENTATIVAS:
                    raise RuntimeError(
                        f"Upload abortado após {self.UPLOAD_MAX_TENTATIVAS} "
                        f"tentativas seguidas: {e}. O upload é retomável — rode "
                        "de novo quando a conexão estabilizar.") from e
                espera = min(60, 2 ** falhas) + _random.uniform(0, 1)
                print(f"  [{type(e).__name__}] tentativa {falhas}/"
                      f"{self.UPLOAD_MAX_TENTATIVAS}, aguardando {espera:.0f}s...",
                      flush=True)
                time.sleep(espera)

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
