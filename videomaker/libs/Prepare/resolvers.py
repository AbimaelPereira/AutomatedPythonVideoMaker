"""Um resolver por `kind`: `resolve(task, ctx, store, **deps) -> caminho absoluto`."""
import os
import threading
import uuid

from libs.MediaDownloader import MediaDownloader
from libs.Prepare.RateLimiter import call_with_backoff, limiter_for

# RemoteAssetManager grava JSON em disco; as threads do prepare não podem intercalar.
_remote_lock = threading.Lock()


def _incoming_dir(store) -> str:
    path = os.path.join(store.assets_dir, "dl", "_incoming", uuid.uuid4().hex)
    os.makedirs(path, exist_ok=True)
    return path


def _adopt_download(store, key: str, kind: str, downloaded: str, meta: dict) -> str:
    """Move o arquivo baixado para `path_for(key)` e registra (sem cópia)."""
    ext = os.path.splitext(downloaded)[1].lstrip(".") or "bin"
    dest = store.path_for(key, kind, ext)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    os.replace(downloaded, dest)
    try:
        os.rmdir(os.path.dirname(downloaded))
    except OSError:
        pass
    return store.put(key, dest, kind=kind, ext=ext, meta=meta)


def resolve_ai(task, ctx, store, **_):
    from libs.AIProviders import ai_manager

    spec = task.spec
    params = dict(spec["parameters"])
    if spec.get("resolution"):
        params["width"], params["height"] = spec["resolution"]
    content_type = spec.get("content_type", "image")
    gen = ai_manager.generate_video if content_type == "video" else ai_manager.generate_image
    limiter = limiter_for(task.provider, ctx.global_settings)

    def attempt():
        with limiter:
            return gen(prompt=spec["prompt"], provider=task.provider, **params)

    result = call_with_backoff(attempt)
    if not result or not result.get("success"):
        raise RuntimeError(f"geração IA falhou: {(result or {}).get('error')}")
    return store.put(task.asset_key, result["content"], kind="ai",
                     ext="mp4" if content_type == "video" else "png",
                     meta={"provider": task.provider, "prompt": spec["prompt"]})


def resolve_download(task, ctx, store, **_):
    url = task.spec["url"]
    with limiter_for("download", ctx.global_settings):
        path = MediaDownloader.resolve_source_path(url, _incoming_dir(store))
    if not path:
        raise RuntimeError(f"download falhou: {url[:80]}")
    return _adopt_download(store, task.asset_key, "download", path, {"url": url})


def resolve_remote_asset(task, ctx, store, *, remote_asset_manager=None, pinned_url=None, **_):
    slug = task.spec["slug"]
    if pinned_url:
        with limiter_for("download", ctx.global_settings):
            path = MediaDownloader.resolve_source_path(pinned_url, _incoming_dir(store))
        if path:
            return _adopt_download(store, task.asset_key, "remote_asset", path,
                                   {"url": pinned_url, "slug": slug})
        print(f"[Prepare] URL fixada de '{slug}' falhou; selecionando outra")

    if remote_asset_manager is None:
        raise RuntimeError(f"remote_asset '{slug}' sem RemoteAssetManager")

    while True:
        with _remote_lock:
            url = remote_asset_manager.select_url(slug)
        if not url:
            raise RuntimeError(f"nenhuma URL válida restante no slug '{slug}'")

        def on_success(u):
            with _remote_lock:
                remote_asset_manager.mark_download_success(u)

        def on_fail(u):
            with _remote_lock:
                remote_asset_manager.mark_download_failed(u)

        with limiter_for("download", ctx.global_settings):
            path = MediaDownloader.resolve_source_path(
                url, _incoming_dir(store),
                on_success_callback=on_success, on_fail_callback=on_fail)
        if path:
            register_as = task.spec.get("register_as")
            if register_as and url.startswith("http"):
                with _remote_lock:
                    remote_asset_manager.register_url(register_as, url)
            return _adopt_download(store, task.asset_key, "remote_asset", path,
                                   {"url": url, "slug": slug})
        print(f"[Prepare] remote_asset '{slug}': falha no download, tentando próxima URL")


RESOLVERS = {
    "ai": resolve_ai,
    "download": resolve_download,
    "remote_asset": resolve_remote_asset,
}
