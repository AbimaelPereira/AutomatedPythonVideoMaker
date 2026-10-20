"""Varre as cenas e lista os assets que precisam ser resolvidos para disco.

Pura: sem rede e sem disco. `type: "directory"` NÃO é coletado: a escolha da
pasta depende da duração da cena (só conhecida depois do TTS) e pode montar
vários segmentos; fixar um arquivo aqui mudaria o vídeo final.
"""
from dataclasses import dataclass

from libs.utils import deep_merge

# Defaults históricos de `visual_elements[].source.type == "ai"`.
VE_AI_DEFAULTS = {"model": "flux", "width": 576, "height": 1024}
THUMBNAIL_INDEX = -1


@dataclass(frozen=True)
class AssetTask:
    asset_key: str
    kind: str                 # "ai" | "download" | "remote_asset"
    provider: str | None
    spec: dict
    refs: tuple = ()          # ((scene_index, element_path), ...)


def _is_url(value) -> bool:
    return isinstance(value, str) and value.strip().lower().startswith(("http://", "https://", "["))


def effective_background_visual(scene: dict, effective_gs: dict) -> dict:
    """Mesmo merge do BackgroundEngine: gs.background (cena) < scene.background."""
    gs_bg = (effective_gs or {}).get("background") or {}
    scene_bg = scene.get("background")
    merged = deep_merge(gs_bg, scene_bg) if scene_bg is not None else dict(gs_bg)
    return dict(merged.get("visual") or {})


def thumbnail_resolution(thumb: dict, video_resolution: tuple) -> tuple:
    w, h = thumb.get("width"), thumb.get("height")
    if w and h:
        return int(w), int(h)
    vw, vh = video_resolution
    return (1280, 720) if vw >= vh else (720, 1280)


def _visual_tasks(visual: dict, scene_id: str, element_path: str, gs: dict,
                  ai_resolution, ai_defaults, where: str) -> list:
    """Tasks de um bloco visual (fundo ou elemento) — 0 ou 1 item."""
    from libs.Prepare import keys

    vtype = visual.get("type")
    source = visual.get("source")

    if element_path != "background" and isinstance(source, dict) and source.get("type") == "ai":
        block, vtype = source, "ai"
    else:
        block = visual

    if vtype == "ai":
        if not block.get("prompt"):
            return []
        from libs.AIProviders.params import resolve_parameters
        params = resolve_parameters(block, gs, where, defaults=ai_defaults)
        provider = block.get("provider", "pollinations")
        content_type = block.get("content_type", "image")
        key = keys.ai_key(block, params, ai_resolution)
        return [(key, "ai", provider, {
            "prompt": block["prompt"], "parameters": params, "content_type": content_type,
            "resolution": tuple(ai_resolution) if ai_resolution else None,
            "provider": provider,
        })]

    if vtype == "remote_asset" and isinstance(source, str) and source:
        key = keys.remote_asset_key(scene_id, element_path, source)
        return [(key, "remote_asset", None, {
            "slug": source, "register_as": visual.get("register_remote_asset_as"),
        })]

    if vtype in ("image", "video", "file") and _is_url(source):
        return [(keys.url_key(source), "download", "download", {"url": source})]

    return []


def collect_tasks(ctx, scene_indexes=None, include_thumbnail: bool = False) -> list:
    from libs.AIProviders.params import validate_video_ai_blocks

    selected = [s for s in ctx.scenes
                if scene_indexes is None or s["_index"] in set(scene_indexes)]
    thumb = None
    if include_thumbnail:
        yt = deep_merge((ctx.channel_config or {}).get("youtube", {}) or {},
                        ctx.video_data.get("youtube", {}) or {})
        cand = yt.get("thumbnail")
        if isinstance(cand, dict) and cand.get("type") == "scene":
            thumb = cand
    validate_video_ai_blocks(selected, None)

    found = {}  # key -> [kind, provider, spec, refs]

    def add(items, index, element_path):
        for key, kind, provider, spec in items:
            entry = found.setdefault(key, [kind, provider, spec, []])
            entry[3].append((index, element_path))

    for scene in selected:
        idx = scene["_index"]
        gs = scene.get("_effective_gs") or ctx.global_settings
        sid = scene.get("id") or f"scene_{idx + 1:02d}"
        bg = effective_background_visual(scene, gs)
        add(_visual_tasks(bg, sid, "background", gs, ctx.resolution, None,
                          f"cena '{sid}' background.visual"), idx, "background")
        for i, el in enumerate(scene.get("visual_elements") or []):
            path = f"visual_elements[{i}]"
            add(_visual_tasks(el, sid, path, gs, None, VE_AI_DEFAULTS,
                              f"cena '{sid}' visual_elements.source"), idx, path)

    if thumb is not None:
        gs = ctx.global_settings
        res = thumbnail_resolution(thumb, ctx.resolution)
        bg = effective_background_visual({"background": thumb.get("background")}
                                         if thumb.get("background") else {}, gs)
        add(_visual_tasks(bg, "thumbnail", "background", gs, res, None,
                          "youtube.thumbnail background.visual"), THUMBNAIL_INDEX, "background")
        for i, el in enumerate(thumb.get("visual_elements") or []):
            path = f"visual_elements[{i}]"
            add(_visual_tasks(el, "thumbnail", path, gs, None, VE_AI_DEFAULTS,
                              "youtube.thumbnail visual_elements.source"), THUMBNAIL_INDEX, path)

    return [AssetTask(key, kind, provider, spec, tuple(refs))
            for key, (kind, provider, spec, refs) in found.items()]
