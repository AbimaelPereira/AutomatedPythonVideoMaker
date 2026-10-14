"""Regras das operações de YouTube por canal.

O canal é resolvido SEMPRE pelo `videomaker/channels_config/{slug}.json`, nunca
pela tabela `app_channels`: o seed (`seed_channels.py`) copia o JSON para o
banco uma única vez e pula o que já existe, então o banco é uma cópia que pode
estar velha. O JSON é a fonte de verdade — é de onde o próprio pipeline lê.

Nada aqui escreve no banco. O snapshot de analytics vai para arquivo; o
histórico de `app_videos` continua sendo só dos vídeos que o pipeline gerou.
"""
import json
import os
import sys
from pathlib import Path

VIDEOMAKER = Path(__file__).resolve().parent.parent.parent / "videomaker"
CHANNELS_CONFIG = VIDEOMAKER / "channels_config"
ANALYTICS_DIR = VIDEOMAKER / "output" / "analytics"

# O videomaker precisa ser importável e os caminhos relativos das suas configs
# (`tokens/`, `assets/`) partem da pasta dele.
if str(VIDEOMAKER) not in sys.path:
    sys.path.insert(0, str(VIDEOMAKER))


class CanalNaoEncontrado(Exception):
    pass


# ---------------------------------------------------------------------------
# RESOLUÇÃO DE CANAL
# ---------------------------------------------------------------------------
def carregar_config(slug: str) -> dict:
    """O `channels_config/{slug}.json` inteiro."""
    # Barra o path traversal: `slug` vem da URL.
    if not slug or "/" in slug or "\\" in slug or slug.startswith("."):
        raise CanalNaoEncontrado(f"Slug inválido: {slug!r}")

    caminho = CHANNELS_CONFIG / f"{slug}.json"
    if not caminho.exists():
        raise CanalNaoEncontrado(f"channels_config/{slug}.json não existe")
    return json.loads(caminho.read_text())


def _limpar_comentarios(d: dict) -> dict:
    """Remove as chaves de comentário (terminadas em `/`), convenção do pipeline."""
    return {k: v for k, v in d.items() if not k.endswith("/")}


def montar_params(slug: str, overrides: dict | None = None) -> dict:
    """Params do `YouTube`, com o mesmo merge que o pipeline faz.

    Ordem: `channels_config.youtube` < overrides da requisição.

    O `token_dir` é fixado em `videomaker/tokens` porque o default do
    `YouTube.py` é o relativo `"tokens"`: o pipeline faz `chdir` para
    `videomaker/` antes de rodar, mas o processo da API não — sem isto, um
    `token_file_name` sem caminho (ex. "the_touchline_record.json") seria
    procurado em `api/tokens/` e nunca encontrado.
    """
    base = _limpar_comentarios(carregar_config(slug).get("youtube", {}))
    if overrides:
        base.update({k: v for k, v in overrides.items() if v is not None})
    base.setdefault("token_dir", str(VIDEOMAKER / "tokens"))
    return base


def _youtube(slug: str, overrides: dict | None = None):
    from libs.YouTube import YouTube
    return YouTube(params=montar_params(slug, overrides))


def _credenciais(slug: str):
    """Credenciais OAuth do canal, renovando o access token se preciso.

    Falha explicitamente quando não há token em disco: sem isso, o
    `_get_credentials()` do pipeline chamaria `generate_token()`, que abre um
    navegador e BLOQUEIA esperando o clique — num processo de API isso trava a
    request para sempre.
    """
    yt = _youtube(slug)
    if not os.path.exists(yt.token_path):
        raise CanalNaoEncontrado(
            f"Token OAuth não encontrado para {slug!r}: {yt.token_path}. "
            "Gere-o numa máquina com navegador (YouTube.generate_token()).")
    return yt._get_credentials()


def canal_id(slug: str) -> str:
    """O ID do canal: o declarado na config, ou o dono do token."""
    cfg = carregar_config(slug)
    declarado = (cfg.get("youtube") or {}).get("channel_id") or cfg.get("channel_id")
    if declarado:
        return declarado

    from libs.YouTubeReader import YouTubeReader
    dono = YouTubeReader(_credenciais(slug), canal_id="", verbose=False).canal_do_token()
    if not dono:
        raise CanalNaoEncontrado(f"Não foi possível descobrir o canal de {slug!r}")
    return dono["id"]


# ---------------------------------------------------------------------------
# TOKEN
# ---------------------------------------------------------------------------
def status_token(slug: str) -> dict:
    """Diagnóstico do token. Não abre navegador nem chama a API."""
    yt = _youtube(slug)
    return {"slug": slug, **yt.status_token()}


# ---------------------------------------------------------------------------
# UPLOAD
# ---------------------------------------------------------------------------
def validar(slug: str, overrides: dict | None = None,
            check_video: bool = True) -> dict:
    """O dry-run: checa os metadados sem subir nada."""
    yt = _youtube(slug, overrides)
    problemas = yt.validar(check_video=check_video)
    return {
        "slug": slug,
        "ok": not problemas,
        "problemas": problemas,
        "resumo": {
            "video_path": yt.video_path,
            "title": yt.title,
            "title_chars": len(yt.title or ""),
            "description_chars": len(yt.description or ""),
            "tags": yt.tags,
            "privacy_status": yt.privacy_status,
            "publish_at": yt.publish_at,
            "timezone": yt.timezone,
            "category_id": yt.category_id,
            "default_language": yt.default_language,
            "thumbnail": yt.thumbnail,
            "token_path": yt.token_path,
        },
    }


def upload(slug: str, overrides: dict | None = None) -> dict:
    """Sobe um MP4 já renderizado. Levanta se a validação falhar.

    Roda em job: o upload de um arquivo grande leva muito mais que o timeout de
    uma request HTTP.
    """
    yt = _youtube(slug, overrides)

    problemas = yt.validar()
    if problemas:
        raise ValueError("Metadados inválidos: " + "; ".join(problemas))

    video_id = yt.upload()

    thumb = yt._resolve_thumbnail_path()
    thumb_ok = None
    if thumb:
        # O vídeo já está no canal; falha de thumbnail não invalida o upload.
        thumb_ok = yt.upload_thumbnail(video_id, thumb)

    return {
        "slug": slug,
        "video_id": video_id,
        "url": f"https://youtu.be/{video_id}",
        "thumbnail_enviada": thumb_ok,
        "thumbnail_path": thumb,
        # `containsSyntheticMedia` é write-only: a API nunca devolve esse campo.
        "conferir_no_studio": bool(yt.config.get("contains_synthetic_media")),
    }


def enviar_thumbnail(slug: str, video_id: str, path: str | None = None) -> dict:
    """Reenvia a thumbnail de um vídeo que já está no canal."""
    yt = _youtube(slug, {"thumbnail": {"type": "file", "source": path}} if path else None)
    caminho = path or yt._resolve_thumbnail_path()
    if not caminho:
        raise ValueError("Nenhuma thumbnail configurada nem informada.")
    if not os.path.exists(caminho):
        raise ValueError(f"Thumbnail não encontrada: {caminho}")
    return {"slug": slug, "video_id": video_id, "path": caminho,
            "enviada": yt.upload_thumbnail(video_id, caminho)}


# ---------------------------------------------------------------------------
# PLAYLISTS
# ---------------------------------------------------------------------------
def _playlists(slug: str):
    from libs.YouTubePlaylists import YouTubePlaylists
    return YouTubePlaylists(_credenciais(slug))


def listar_playlists(slug: str) -> list:
    return [
        {"id": p["id"],
         "titulo": p["snippet"]["title"],
         "descricao": p["snippet"].get("description", ""),
         "privacidade": (p.get("status") or {}).get("privacyStatus"),
         "videos": (p.get("contentDetails") or {}).get("itemCount")}
        for p in _playlists(slug).listar()
    ]


def garantir_playlist(slug: str, titulo: str, descricao: str = "",
                      privacy_status: str = "public",
                      default_language: str | None = None) -> dict:
    if default_language is None:
        default_language = montar_params(slug).get("default_language")
    return _playlists(slug).garantir(titulo, descricao, privacy_status,
                                     default_language)


def adicionar_na_playlist(slug: str, playlist_id: str, video_id: str) -> dict:
    return _playlists(slug).adicionar(playlist_id, video_id)


# ---------------------------------------------------------------------------
# SYNC / ANALYTICS
# ---------------------------------------------------------------------------
def caminho_analytics(slug: str, path: str | None = None) -> Path:
    """Destino do snapshot: o `path` pedido, ou o fallback por canal."""
    if path:
        p = Path(path).expanduser()
        # Relativo resolve a partir de `videomaker/`, como no resto do pipeline.
        return p if p.is_absolute() else (VIDEOMAKER / p)
    return ANALYTICS_DIR / f"{slug}.json"


def sync(slug: str, path: str | None = None, inicio: str = "2020-01-01",
         fim: str | None = None, com_analytics_por_video: bool = True) -> dict:
    """Coleta tudo sobre o canal e grava num JSON.

    Escrita atômica (`.tmp` + `os.replace`): uma queda no meio não deixa um
    JSON truncado no lugar do snapshot anterior, que ainda serve.
    """
    from libs.YouTubeReader import YouTubeReader

    cid = canal_id(slug)
    leitor = YouTubeReader(_credenciais(slug), canal_id=cid, inicio=inicio, fim=fim)
    dados = leitor.coletar_tudo(com_analytics_por_video=com_analytics_por_video)
    dados["slug"] = slug

    destino = caminho_analytics(slug, path)
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(destino.suffix + ".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2))
    os.replace(tmp, destino)

    stats = (dados.get("canal") or {}).get("statistics") or {}
    # Este resumo vira `Job.output`, que é VARCHAR(255) — por isso é enxuto e
    # sem a lista de erros. O conteúdo completo (e os erros) está no JSON
    # gravado, cujo caminho vai em `arquivo`.
    return {
        "slug": slug,
        "arquivo": str(destino),
        "total_videos": dados["total_videos"],
        "inscritos": stats.get("subscriberCount"),
        "views": stats.get("viewCount"),
        "consultas_recusadas": len(dados["erros"]),
    }


def ler_analytics(slug: str, path: str | None = None) -> dict:
    """Relê o último snapshot gravado."""
    destino = caminho_analytics(slug, path)
    if not destino.exists():
        raise CanalNaoEncontrado(
            f"Nenhum snapshot em {destino}. Rode POST /youtube/{slug}/sync antes.")
    return json.loads(destino.read_text())
