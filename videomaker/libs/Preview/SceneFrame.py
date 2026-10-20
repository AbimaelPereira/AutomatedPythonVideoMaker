"""Render de 1 quadro de cena (pose de repouso) — núcleo do preview e da thumbnail."""
import copy
import os
import tempfile

from libs.utils import _resolve_scene_layout_params

# Chaves de timeline removidas na pose de repouso. `motion` concentra keyframes,
# `visible` e as ações de libs/Motion (ver libs/Motion/schema.py: MOTION_KEYS);
# `animation` é o formato legado. Rotação estática fica em `layout.rotation`.
REST_POSE_STRIP_KEYS = ("animation", "motion")

# Duração nominal: nada é encodado, as engines só exigem uma duração.
FRAME_DURATION = 1.0


def _strip(d: dict) -> dict:
    return {k: v for k, v in d.items() if k not in REST_POSE_STRIP_KEYS}


def make_rest_pose(scene: dict, effective_gs: dict) -> tuple:
    """Cópias de (cena, gs) sem animação/motion nos elementos e no fundo."""
    scene = copy.deepcopy(scene)
    gs = copy.deepcopy(effective_gs or {})
    scene["visual_elements"] = [_strip(el) for el in (scene.get("visual_elements") or [])]
    for holder in (scene, gs):
        bg = holder.get("background")
        if isinstance(bg, dict) and isinstance(bg.get("visual"), dict):
            bg["visual"] = _strip(bg["visual"])
    return scene, gs


def render_frame(scene: dict, effective_gs: dict, resolution: tuple, layout_params: dict,
                 output_path: str, *, work_dir: str, asset_store=None,
                 remote_asset_manager=None, rest_pose: bool = True,
                 log_prefix: str = "[Preview]") -> str:
    from libs.Background.BackgroundEngine import BackgroundEngine
    from libs.Preview import Compositor

    if rest_pose:
        scene, effective_gs = make_rest_pose(scene, effective_gs)
    else:
        scene, effective_gs = copy.deepcopy(scene), copy.deepcopy(effective_gs or {})
    effective_gs.pop("subtitle", None)
    effective_gs.pop("transitions", None)
    scene["subtitle"] = {"enabled": False}
    scene["transitions"] = {"enabled": False}
    layout_params = _resolve_scene_layout_params(layout_params, scene)
    resolution = tuple(resolution)

    os.makedirs(work_dir, exist_ok=True)
    clips = []
    try:
        bg_engine = BackgroundEngine(resolution_output=resolution, dir_clips_cache={},
                                     asset_store=asset_store,
                                     remote_asset_manager=remote_asset_manager)
        background = bg_engine.build_scene_background(
            effective_gs, scene, FRAME_DURATION, work_dir, work_dir)
        clips.append(background)
        visuals = Compositor.build_visual_layer(
            scene.get("visual_elements") or [], FRAME_DURATION, work_dir, resolution,
            layout_params, remote_asset_manager, rest_pose=rest_pose)
        clips.extend(visuals)
        composed = Compositor.compose(background, visuals, resolution, FRAME_DURATION)
        clips.append(composed)

        out_dir = os.path.dirname(os.path.abspath(output_path)) or "."
        os.makedirs(out_dir, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=out_dir, suffix=".png")
        os.close(fd)
        try:
            composed.save_frame(tmp, t=0)
            os.replace(tmp, output_path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        print(f"{log_prefix} quadro salvo: {output_path}")
        return output_path
    finally:
        for clip in clips:
            try:
                clip.close()
            except Exception:
                pass
