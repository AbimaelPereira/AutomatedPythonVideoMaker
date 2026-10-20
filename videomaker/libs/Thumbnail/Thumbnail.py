"""Thumbnail `type: "scene"` sobre o motor de preview (pose de repouso, 1 quadro).

Assets do bloco passam pelo PrepareEngine e ficam em `{slug}/assets/`. Itens
inválidos nunca levantam exceção: viram aviso e são ignorados.
"""
import copy
import os
import shutil
import tempfile
from dataclasses import dataclass, field

from libs.utils import _default_safe_paddings

_MAX_BYTES = 2 * 1024 * 1024  # limite de upload do YouTube
_DEFAULT_LANDSCAPE = (1280, 720)
_DEFAULT_PORTRAIT = (720, 1280)
_ALLOWED_KEYS = {"type", "background", "visual_elements", "width", "height",
                 "padding_top", "padding_bottom", "padding_side"}
_TIMELINE_KEYS = ("animation", "motion")
_SCENE_ONLY_KEYS = ("narration", "subtitle", "transitions", "duration", "tts")


@dataclass
class ThumbnailResult:
    path: str | None
    warnings: list = field(default_factory=list)


def _default_size(video_resolution) -> tuple:
    if video_resolution and video_resolution[0] < video_resolution[1]:
        return _DEFAULT_PORTRAIT
    return _DEFAULT_LANDSCAPE


def _validate_size(cfg: dict, video_resolution, warn) -> tuple:
    default = _default_size(video_resolution)
    w, h = cfg.get("width"), cfg.get("height")
    if w is None and h is None:
        return default
    try:
        w, h = int(w), int(h)
    except (TypeError, ValueError):
        warn(f"thumbnail: width/height inválidos ({cfg.get('width')}x{cfg.get('height')}); "
             f"usando {default[0]}x{default[1]}")
        return default
    ratio = w / h if h else 0
    if abs(ratio - 16 / 9) <= (16 / 9) * 0.01:
        if w < 640:
            warn(f"thumbnail: largura {w} < 640; usando {default[0]}x{default[1]}")
            return default
    elif abs(ratio - 9 / 16) <= (9 / 16) * 0.01:
        if h < 640:
            warn(f"thumbnail: altura {h} < 640; usando {default[0]}x{default[1]}")
            return default
    else:
        warn(f"thumbnail: proporção {w}x{h} não é 16:9 nem 9:16; usando {default[0]}x{default[1]}")
        return default
    return (w, h)


def validate_thumbnail(cfg: dict, video_resolution: tuple) -> tuple:
    """(cfg limpo, avisos). Nunca levanta."""
    warnings = []
    warn = warnings.append
    cfg = copy.deepcopy(cfg) if isinstance(cfg, dict) else {}
    clean = {"type": "scene"}

    for key in list(cfg):
        if key in _SCENE_ONLY_KEYS:
            warn(f"thumbnail: '{key}' ignorado")
        elif key not in _ALLOWED_KEYS:
            warn(f"thumbnail: chave desconhecida '{key}' ignorada")

    bg = cfg.get("background")
    if isinstance(bg, dict):
        bg = dict(bg)
        visual = bg.get("visual")
        if isinstance(visual, dict):
            visual = dict(visual)
            for k in _TIMELINE_KEYS:
                if k in visual:
                    visual.pop(k)
                    warn(f"thumbnail: '{k}' ignorado em background")
            bg["visual"] = visual
        clean["background"] = bg
    elif bg is not None:
        warn("thumbnail: 'background' inválido ignorado")

    elements = []
    raw_elements = cfg.get("visual_elements") or []
    if not isinstance(raw_elements, list):
        warn("thumbnail: 'visual_elements' inválido ignorado")
        raw_elements = []
    for i, el in enumerate(raw_elements):
        if not isinstance(el, dict):
            warn(f"thumbnail: visual_elements[{i}] inválido ignorado")
            continue
        el = dict(el)
        for k in _TIMELINE_KEYS:
            if k in el:
                el.pop(k)
                warn(f"thumbnail: '{k}' ignorado em visual_elements[{i}]")
        elements.append(el)
    clean["visual_elements"] = elements

    for key in ("padding_top", "padding_bottom", "padding_side"):
        if cfg.get(key) is not None:
            try:
                clean[key] = int(cfg[key])
            except (TypeError, ValueError):
                warn(f"thumbnail: '{key}' inválido ignorado")

    clean["width"], clean["height"] = _validate_size(cfg, video_resolution, warn)
    for w in warnings:
        print(f"[Thumbnail] ⚠️ {w}")
    return clean, warnings


def _layout_params(resolution: tuple, cfg: dict, global_settings: dict,
                   video_resolution: tuple = None) -> dict:
    """Paddings do canal só são herdados se a orientação for a mesma do vídeo;
    os do bloco da thumbnail sempre vencem."""
    gs = global_settings or {}
    defaults = _default_safe_paddings(resolution)
    params = {"width": resolution[0], "height": resolution[1],
              "stack_gap_percent": gs.get("stack_gap_percent", 0.02)}
    same_orientation = (
        video_resolution is None
        or (video_resolution[0] >= video_resolution[1]) == (resolution[0] >= resolution[1])
    )
    for key in ("padding_top", "padding_bottom", "padding_side"):
        if cfg.get(key) is not None:
            value = cfg[key]
        elif same_orientation and gs.get(key) is not None:
            value = gs[key]
        else:
            value = defaults[key]
        try:
            params[key] = int(value)
        except (TypeError, ValueError):
            params[key] = defaults[key]
    return params


def _enforce_size_limit(path: str, log_prefix: str = "[Thumbnail]"):
    """Teto de 2MB do YouTube: recomprime em JPEG mantendo o caminho (.png)."""
    try:
        if os.path.getsize(path) <= _MAX_BYTES:
            return
    except OSError:
        return
    from PIL import Image

    jpeg_path = os.path.splitext(path)[0] + ".jpg"
    with Image.open(path) as im:
        rgb = im.convert("RGB")
        for quality in (92, 85, 75, 65, 50):
            rgb.save(jpeg_path, "JPEG", quality=quality, optimize=True)
            if os.path.getsize(jpeg_path) <= _MAX_BYTES:
                break
    print(f"{log_prefix} PNG acima de 2MB — recomprimido em JPEG "
          f"({os.path.getsize(jpeg_path) // 1024}KB)")
    os.replace(jpeg_path, path)


def minimal_context(output_dir: str, global_settings: dict | None = None,
                    video_resolution: tuple | None = None):
    """VideoContext sem JSON de vídeo (API de preview de thumbnail, YouTube sem ctx)."""
    from libs.VideoContext import VideoContext
    resolution = tuple(video_resolution) if video_resolution else _DEFAULT_LANDSCAPE
    output_dir = os.path.abspath(output_dir)
    return VideoContext(
        video_data={}, channel_config={}, global_settings=dict(global_settings or {}),
        output_config={}, resolution=resolution,
        layout_params={"width": resolution[0], "height": resolution[1]},
        slug=os.path.basename(output_dir), output_dir=output_dir,
        assets_dir=os.path.join(output_dir, "assets"),
        previews_dir=os.path.join(output_dir, "previews"), scenes=[],
    )


def build_thumbnail(cfg: dict, ctx, *, output_path: str | None = None,
                    asset_store=None, remote_asset_manager=None) -> ThumbnailResult:
    from libs.Prepare.AssetStore import AssetStore
    from libs.Prepare.PrepareEngine import PrepareEngine
    from libs.Preview.SceneFrame import render_frame
    from libs.Preview.warnings import extract_warnings

    clean, warnings = validate_thumbnail(cfg, ctx.resolution)
    resolution = (clean["width"], clean["height"])
    output_path = output_path or os.path.join(ctx.output_dir, "thumbnail.png")

    gs = copy.deepcopy(ctx.global_settings or {})
    scene = {"background": clean.get("background"),
             "visual_elements": clean["visual_elements"]}
    if not scene["background"]:
        scene.pop("background")
        if not gs.get("background"):
            scene["background"] = {"visual": {"type": "color", "color": "#000000"}}

    try:
        prepare = PrepareEngine(ctx, scene_indexes=[], thumbnail_cfg=clean,
                                remote_asset_manager=remote_asset_manager)
        prepare.run()
        warnings += [f"thumbnail: asset {k} falhou: {v}" for k, v in prepare.result.failed.items()]
        scene = prepare.apply_thumbnail(scene)
    except Exception as e:
        warnings.append(f"thumbnail: prepare falhou: {e}")

    layout = _layout_params(resolution, clean, gs, ctx.resolution)
    os.makedirs(ctx.output_dir, exist_ok=True)
    work_dir = tempfile.mkdtemp(prefix=".thumbnail-", dir=ctx.output_dir)
    import contextlib
    import io
    import sys
    log = io.StringIO()
    try:
        with contextlib.redirect_stdout(log):
            render_frame(scene, gs, resolution, layout, output_path, work_dir=work_dir,
                         asset_store=asset_store or AssetStore(ctx.assets_dir),
                         remote_asset_manager=remote_asset_manager, rest_pose=True,
                         log_prefix="[Thumbnail]")
        _enforce_size_limit(output_path)
    except Exception as e:
        warnings.append(f"thumbnail: render falhou: {type(e).__name__}: {e}")
        output_path = None
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        captured = log.getvalue()
        sys.stdout.write(captured)
        warnings += extract_warnings(captured)

    if output_path:
        print(f"[Thumbnail] ✅ {output_path}")
    return ThumbnailResult(output_path, warnings)
