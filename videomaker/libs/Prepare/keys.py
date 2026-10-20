"""Chaves de asset (`asset_key`) para o manifest do vídeo."""
import hashlib

from libs.MediaDownloader import _sanitize_source


def _h(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def ai_key(block: dict, parameters: dict, resolution: tuple | None = None) -> str:
    """Chave de IA. `cache_key` explícito vence; `resolution` entra no hash (fundo)."""
    from libs.AIProviders.params import cache_key
    if block.get("cache_key"):
        return "ai_" + block["cache_key"]
    params = dict(parameters)
    if resolution:
        params["width"], params["height"] = int(resolution[0]), int(resolution[1])
    return "ai_" + cache_key(block, params)


def url_key(url: str) -> str:
    return "dl_" + _h(_sanitize_source(url))


def remote_asset_key(scene_id: str, element_path: str, slug: str) -> str:
    return "ra_" + _h(f"{scene_id}:{element_path}:{slug}")


def directory_key(scene_id: str, element_path: str, abs_dir: str) -> str:
    return "dir_" + _h(f"{scene_id}:{element_path}:{abs_dir}")
