"""Resolve para `{output}/{slug}/assets/` os assets visuais das cenas."""
import copy
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field

from libs.Prepare.AssetStore import AssetStore
from libs.Prepare.collect import THUMBNAIL_INDEX, collect_tasks
from libs.Prepare.resolvers import RESOLVERS
from libs.utils import ai_cache_enabled_by_env

_ORDER = {"ai": 0, "remote_asset": 1, "download": 2}
_EL_PATH = re.compile(r"^visual_elements\[(\d+)\]$")


@dataclass
class PrepareResult:
    resolved: dict = field(default_factory=dict)
    failed: dict = field(default_factory=dict)
    skipped: int = 0
    duration_s: float = 0.0

    def to_json(self) -> dict:
        return asdict(self)


def ai_cache_enabled(video_data: dict, global_settings: dict) -> bool:
    """`"ai_cache": false` (raiz ou global_settings) ou env AI_CACHE=0 desligam."""
    flag = video_data.get("ai_cache")
    if flag is None:
        flag = (global_settings or {}).get("ai_cache")
    return ai_cache_enabled_by_env() if flag is None else bool(flag) and ai_cache_enabled_by_env()


class PrepareEngine:
    def __init__(self, ctx, *, scene_indexes=None, force: bool = False,
                 include_thumbnail: bool = False, max_workers: int | None = None,
                 remote_asset_manager=None):
        self.ctx = ctx
        self.scene_indexes = scene_indexes
        self.force = force
        self.include_thumbnail = include_thumbnail
        self.max_workers = max_workers
        self.store = AssetStore(ctx.assets_dir)
        self._remote_asset_manager = remote_asset_manager
        self.tasks = []
        self.result = None

    def _remote_manager(self):
        if self._remote_asset_manager is None:
            from libs.RemoteAssetManager import RemoteAssetManager
            self._remote_asset_manager = RemoteAssetManager(
                config=self.ctx.global_settings.get("remote_assets", {}))
        return self._remote_asset_manager

    def _reuse_allowed(self, task) -> bool:
        if self.force:
            return False
        if task.kind == "ai":
            return ai_cache_enabled(self.ctx.video_data, self.ctx.global_settings)
        return True

    def _resolve_one(self, task, pinned_url):
        deps = {"pinned_url": pinned_url}
        if task.kind == "remote_asset":
            deps["remote_asset_manager"] = self._remote_manager()
        return RESOLVERS[task.kind](task, self.ctx, self.store, **deps)

    def run(self) -> PrepareResult:
        start = time.monotonic()
        self.tasks = collect_tasks(self.ctx, self.scene_indexes, self.include_thumbnail)
        result = PrepareResult()
        entries = self.store.entries()

        pending = []
        for task in self.tasks:
            hit = self.store.get(task.asset_key) if self._reuse_allowed(task) else None
            if hit:
                result.resolved[task.asset_key] = hit
                result.skipped += 1
            else:
                pinned = ((entries.get(task.asset_key) or {}).get("meta") or {}).get("url") \
                    if task.kind == "remote_asset" else None
                pending.append((task, pinned))

        pending.sort(key=lambda tp: _ORDER.get(tp[0].kind, 9))
        if pending:
            workers = self.max_workers or min(32, len(pending))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [(task, pool.submit(self._resolve_one, task, pinned))
                           for task, pinned in pending]
                for task, fut in futures:
                    try:
                        result.resolved[task.asset_key] = fut.result()
                    except Exception as e:
                        result.failed[task.asset_key] = f"{type(e).__name__}: {e}"
                        print(f"[Prepare] ❌ {task.kind} {task.asset_key}: {e}")

        result.duration_s = round(time.monotonic() - start, 3)
        generated = len(result.resolved) - result.skipped
        print(f"[Prepare] {len(self.tasks)} assets: {result.skipped} cache, "
              f"{generated} gerados, {len(result.failed)} falhas em {result.duration_s:.1f} s")
        self.result = result
        return result

    def apply(self, scenes: list) -> list:
        """Cópias das cenas com os sources resolvidos apontando para disco.

        `scenes[i]` corresponde a `ctx.scenes[i]` (mesma normalização).
        Assets em `failed` ficam intocados (o render faz o fallback atual).
        """
        out = [copy.deepcopy(s) for s in scenes]
        if self.result is None:
            return out
        for task in self.tasks:
            path = self.result.resolved.get(task.asset_key)
            if not path:
                continue
            for index, element_path in task.refs:
                if index == THUMBNAIL_INDEX or not (0 <= index < len(out)):
                    continue
                _rewrite(out[index], element_path, task.kind, path)
        return out


def _rewrite(scene: dict, element_path: str, kind: str, path: str) -> None:
    if element_path == "background":
        bg = scene.get("background")
        if not isinstance(bg, dict):
            bg = scene["background"] = {}
        visual = bg.get("visual")
        if not isinstance(visual, dict):
            visual = bg["visual"] = {}
        if kind == "ai":
            # Mantém `type: "ai"`: o resize/contain do fundo de IA difere do
            # cover de `image` e mudaria o vídeo final.
            visual["_resolved_path"] = path
        else:
            visual["source"] = path
        return

    match = _EL_PATH.match(element_path)
    if not match:
        return
    elements = scene.get("visual_elements") or []
    i = int(match.group(1))
    if i < len(elements):
        elements[i]["source"] = path
