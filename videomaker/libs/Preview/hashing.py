"""Hash de cena para o cache de preview."""
import hashlib
import json
import os

# Incrementar quando a lógica de render do preview mudar (invalida todos os PNGs).
PREVIEW_ENGINE_VERSION = 1

_SCENE_EXCLUDE = {"narration", "subtitle", "transitions", "duration", "tts", "id",
                  "_index", "_effective_gs", "_chapter_gs"}
_GS_KEYS = ("background", "padding_top", "padding_bottom", "padding_side",
            "stack_gap_percent", "fonts", "font_path")


def asset_fingerprint(asset_key: str, path: str) -> str:
    try:
        st = os.stat(path)
        return f"{asset_key}:{st.st_mtime_ns}:{st.st_size}"
    except OSError:
        return f"{asset_key}:missing"


def scene_hash(scene: dict, effective_gs: dict, resolution, layout_params,
               asset_fingerprints: dict) -> str:
    gs = effective_gs or {}
    data = {
        "scene": {k: v for k, v in scene.items() if k not in _SCENE_EXCLUDE},
        "gs": {k: gs.get(k) for k in _GS_KEYS},
        "ai_parameters": (gs.get("ai") or {}).get("parameters"),
        "resolution": list(resolution),
        "layout": layout_params,
        "assets": dict(sorted((asset_fingerprints or {}).items())),
        "version": PREVIEW_ENGINE_VERSION,
    }
    raw = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
