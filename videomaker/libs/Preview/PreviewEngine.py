"""PNG por cena em pose de repouso, com cache por hash de cena."""
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field

from libs.Prepare.PrepareEngine import PrepareEngine, PrepareResult
from libs.Preview.hashing import asset_fingerprint, scene_hash
from libs.Preview.SceneFrame import make_rest_pose
from libs.utils import _resolve_scene_layout_params

_PNG_NAME = re.compile(r"^\d{2,3}-.+\.png$")


@dataclass
class ScenePreview:
    index: int
    scene_id: str
    path: str | None
    status: str
    error: str | None = None
    warnings: list = field(default_factory=list)


@dataclass
class PreviewResult:
    slug: str
    previews_dir: str
    scenes: list
    prepare: PrepareResult
    duration_s: float

    def to_json(self) -> dict:
        return {
            "slug": self.slug,
            "previews_dir": self.previews_dir,
            "scenes": [asdict(s) for s in self.scenes],
            "prepare": self.prepare.to_json(),
            "duration_s": self.duration_s,
        }


def preview_filename(index: int, scene: dict, total: int) -> str:
    width = 3 if total > 99 else 2
    raw = scene.get("id") or f"scene_{index + 1:0{width}d}"
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", str(raw))
    return f"{index + 1:0{width}d}-{safe}.png"


def _render_scene_job(job: dict) -> dict:
    """Worker (função de topo, picklável): renderiza 1 cena e captura avisos."""
    from libs.Prepare.AssetStore import AssetStore
    from libs.Preview.SceneFrame import render_frame
    from libs.Preview.warnings import extract_warnings
    from libs.RemoteAssetManager import RemoteAssetManager

    log = io.StringIO()
    out = {"index": job["index"], "error": None, "warnings": []}
    work_dir = tempfile.mkdtemp(prefix=".work-", dir=job["previews_dir"])
    try:
        with contextlib.redirect_stdout(log):
            render_frame(
                job["scene"], job["effective_gs"], tuple(job["resolution"]),
                job["layout_params"], job["output_path"], work_dir=work_dir,
                asset_store=AssetStore(job["assets_dir"]),
                remote_asset_manager=RemoteAssetManager(config=job["remote_assets_config"]),
                rest_pose=True,
            )
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        captured = log.getvalue()
        sys.stderr.write(captured)
        out["warnings"] = extract_warnings(captured)
    return out


def _write_json_atomic(path: str, data) -> None:
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, path)


class PreviewEngine:
    def __init__(self, ctx, *, scenes=None, force: bool = False, max_workers: int | None = None):
        self.ctx = ctx
        self.selection = scenes
        self.force = force
        self.max_workers = max_workers or int(os.getenv("MAX_PARALLEL_SCENES", 2))

    def _load_cache(self) -> dict:
        try:
            with open(os.path.join(self.ctx.previews_dir, ".cache.json"), encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (FileNotFoundError, ValueError):
            return {}

    def run(self) -> PreviewResult:
        start = time.monotonic()
        ctx = self.ctx
        indexes = ctx.select_scenes(self.selection)
        os.makedirs(ctx.previews_dir, exist_ok=True)

        prepare = PrepareEngine(ctx, scene_indexes=indexes, force=self.force)
        prepare_result = prepare.run()
        prepared = prepare.apply(ctx.scenes)

        total = len(ctx.scenes)
        cache = self._load_cache()
        results, jobs, hashes = {}, [], {}
        gs_remote = ctx.global_settings.get("remote_assets", {})

        for idx in indexes:
            scene = prepared[idx]
            gs = scene.get("_effective_gs") or ctx.global_settings
            name = preview_filename(idx, scene, total)
            path = os.path.join(ctx.previews_dir, name)
            scene_id = scene.get("id") or name[:-4].split("-", 1)[1]
            layout = _resolve_scene_layout_params(ctx.layout_params, scene)
            rest_scene, rest_gs = make_rest_pose(scene, gs)
            fps = {k: asset_fingerprint(k, p) for k, p in prepare.scene_assets(idx).items()}
            h = scene_hash(rest_scene, rest_gs, ctx.resolution, layout, fps)
            hashes[name] = h

            if not self.force and cache.get(name) == h and os.path.isfile(path):
                results[idx] = ScenePreview(idx + 1, scene_id, path, "cached")
                continue
            results[idx] = ScenePreview(idx + 1, scene_id, path, "rendered")
            jobs.append({
                "index": idx, "scene": {k: v for k, v in scene.items() if k != "_effective_gs"},
                "effective_gs": gs, "resolution": list(ctx.resolution),
                "layout_params": ctx.layout_params, "output_path": path,
                "previews_dir": ctx.previews_dir, "assets_dir": ctx.assets_dir,
                "remote_assets_config": gs_remote,
            })

        if jobs:
            if self.max_workers <= 1 or len(jobs) == 1:
                outs = [_render_scene_job(j) for j in jobs]
            else:
                with ProcessPoolExecutor(max_workers=min(self.max_workers, len(jobs))) as pool:
                    outs = list(pool.map(_render_scene_job, jobs))
            for out in outs:
                sp = results[out["index"]]
                sp.warnings = out["warnings"]
                if out["error"] or not os.path.isfile(sp.path):
                    sp.status, sp.path = "error", None
                    sp.error = out["error"] or "PNG não gerado"
                    print(f"[Preview] ❌ cena {sp.index} ({sp.scene_id}): {sp.error}")

        for idx, sp in results.items():
            name = preview_filename(idx, prepared[idx], total)
            if sp.status == "error":
                cache.pop(name, None)
            else:
                cache[name] = hashes[name]

        if self.selection is None:
            expected = {preview_filename(i, s, total) for i, s in enumerate(prepared)}
            for fname in os.listdir(ctx.previews_dir):
                if _PNG_NAME.match(fname) and fname not in expected:
                    os.remove(os.path.join(ctx.previews_dir, fname))
                    cache.pop(fname, None)
            cache = {k: v for k, v in cache.items() if k in expected}

        _write_json_atomic(os.path.join(ctx.previews_dir, ".cache.json"), cache)

        scenes = [results[i] for i in indexes]
        duration = round(time.monotonic() - start, 3)
        n = {s: sum(1 for p in scenes if p.status == s) for s in ("rendered", "cached", "error")}
        print(f"[Preview] {len(scenes)} cenas: {n['rendered']} renderizadas, "
              f"{n['cached']} cache, {n['error']} erros em {duration:.1f} s")
        return PreviewResult(ctx.slug, ctx.previews_dir, scenes, prepare_result, duration)
