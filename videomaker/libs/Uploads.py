"""Bloco `uploads`: um destino por chave (youtube, instagram, tiktok, r2).

    "uploads": {
      "youtube":   {...},
      "instagram": {...},
      "r2":        {"prefix": "videos/{channel}/{slug}"}
    }

- Canal (`channels_config`) e vídeo são mesclados com `deep_merge`; o vídeo vence.
- `"enabled": false` (ou `false` direto) desliga um destino herdado do canal.
- `"r2": true` / `"r2": {}` liga com os defaults.
- Legado: `youtube`/`instagram`/`tiktok`/`r2` na raiz continuam valendo; se a
  mesma chave existir em `uploads`, ela é mesclada por cima da raiz.
"""
import os
from datetime import datetime

from libs.utils import channel_slug, deep_merge

DESTINATIONS = ("youtube", "instagram", "tiktok", "r2")
R2_DEFAULT_PREFIX = "videos/{channel}/{slug}"
_MISSING = object()


def _raw(cfg: dict | None, name: str):
    """Config de um destino em `cfg`: raiz (legado) mesclada com `uploads.<name>`.
    Retorna _MISSING se o destino não aparece em lugar nenhum."""
    cfg = cfg or {}
    found = _MISSING
    for value in (cfg.get(name, _MISSING), (cfg.get("uploads") or {}).get(name, _MISSING)):
        if value is _MISSING or value is None:
            continue
        if value is True:
            value = {}
        if value is False:
            value = {"enabled": False}
        if not isinstance(value, dict):
            continue
        found = value if found is _MISSING else deep_merge(found, value)
    return found


def upload_config(name: str, channel_config: dict | None, video_data: dict | None) -> dict:
    """Config mesclada (canal × vídeo) de um destino, SEM filtrar `enabled`.
    Útil para ler metadados (ex. `youtube.thumbnail`) mesmo com upload desligado."""
    out = {}
    for src in (channel_config, video_data):
        raw = _raw(src, name)
        if raw is not _MISSING:
            out = deep_merge(out, raw)
    return out


def resolve_uploads(channel_config: dict | None, video_data: dict | None,
                    global_settings: dict | None = None) -> dict:
    """{destino: config} só com os destinos ativos."""
    result = {}
    for name in DESTINATIONS:
        present = [r for r in (_raw(channel_config, name), _raw(video_data, name)) if r is not _MISSING]
        # TikTok legado também podia vir em global_settings.tiktok.
        if name == "tiktok" and not present and (global_settings or {}).get("tiktok"):
            present = [global_settings["tiktok"]]
        if not present:
            continue
        cfg = {}
        for p in present:
            cfg = deep_merge(cfg, p)
        if cfg.get("enabled", True) is False:
            continue
        cfg.pop("enabled", None)
        # youtube/instagram/tiktok vazios não têm o que publicar; r2 vazio = defaults.
        if not cfg and name != "r2":
            continue
        result[name] = cfg
    return result


# ── R2 ────────────────────────────────────────────────────────────────────────

def r2_prefix(cfg: dict, *, slug: str, channel_name: str | None) -> str:
    tpl = cfg.get("prefix") or R2_DEFAULT_PREFIX
    now = datetime.now()
    prefix = tpl.format(slug=slug, channel=channel_slug(channel_name) or "sem_canal",
                        date=now.strftime("%Y-%m-%d"), year=now.strftime("%Y"),
                        month=now.strftime("%m"))
    return prefix.strip("/")


def validate_r2(cfg: dict, *, slug: str, channel_name: str | None) -> list:
    from libs.R2 import IG_PREFIX, R2
    problemas = []
    try:
        prefix = r2_prefix(cfg, slug=slug or "x", channel_name=channel_name)
        if prefix == IG_PREFIX or prefix.startswith(IG_PREFIX + "/"):
            problemas.append(f"r2.prefix não pode começar com '{IG_PREFIX}/' "
                             "(prefixo temporário do Instagram, apagado em 1 dia)")
    except (KeyError, IndexError, ValueError) as e:
        problemas.append(f"r2.prefix inválido ({e}); use {{slug}}, {{channel}}, {{date}}, {{year}}, {{month}}")
    try:
        R2(client=object())  # só checa as variáveis do .env
    except ValueError as e:
        problemas.append(str(e))
    return problemas


def upload_r2(cfg: dict, files: list, *, slug: str, channel_name: str | None, r2=None) -> list:
    """Sobe `files` para `{prefix}/{basename}`. Retorna [{"key", "url"}]."""
    from libs.R2 import R2
    r2 = r2 or R2()
    prefix = r2_prefix(cfg, slug=slug, channel_name=channel_name)
    out = []
    for path in files:
        if not path or not os.path.exists(path):
            continue
        key = f"{prefix}/{os.path.basename(path)}"
        url = r2.upload_file(path, key)
        print(f"[R2] {os.path.basename(path)} → {url}")
        out.append({"key": key, "url": url})
    return out
