"""Renderiza os JSONs golden cena a cena e grava os MP4s para comparação.

Rede de segurança da Fase 0 do plano de Motion: antes de mexer na camada de
animação, congela-se o resultado atual dos caminhos de render; depois de mexer,
compara-se com `compare_ssim.py`. Nenhum JSON legado pode mudar um pixel.

    python tests/golden_render.py --save tests/baseline/
    RENDER_BACKEND=moviepy python tests/golden_render.py --save tests/baseline_mp/

Por que não chama `main.py`: os golden são offline e determinísticos — não têm
narração (TTS exige rede), e a legenda é alimentada por um SRT sintético
declarado na chave `_srt` do JSON. O harness reproduz os passos 4–10 de
`_process_scene_worker` (fundo, visuais, legenda, composição, encode) para poder
injetar esse SRT e escolher o backend explicitamente.
"""

import argparse
import glob
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
VIDEOMAKER = os.path.dirname(HERE)
sys.path.insert(0, VIDEOMAKER)

GOLDEN_DIR = os.path.join(HERE, "golden")


def _render_scene(engine, scene, scene_index: int, srt_path: str) -> str:
    """Renderiza uma cena isolada e devolve o caminho do MP4."""
    from libs.UnifiedVideoEngine import (
        _create_subtitle_clip_worker, _create_visual_elements_clip_worker,
        _resolve_scene_layout_params, _resolve_scene_transitions,
        _subtitles_enabled, _try_ffmpeg_scene, force_rgb,
    )
    from libs.Background.BackgroundEngine import BackgroundEngine
    from libs.Transitions.TransitionEngine import TransitionEngine
    from moviepy.editor import CompositeVideoClip

    scene_id = scene.get("id", f"cena_{scene_index}")
    scene_dir = os.path.join(engine.output_dir, scene_id)
    os.makedirs(scene_dir, exist_ok=True)
    out_path = os.path.join(scene_dir, f"{scene_id}.mp4")

    effective_gs = engine._resolve_scene_gs(scene)
    duration = float(scene.get("duration") or 4.0)
    layout_params = _resolve_scene_layout_params(engine.layout_params, scene)

    fast = _try_ffmpeg_scene(
        scene=scene, effective_gs=effective_gs, scene_dir=scene_dir,
        scene_id=scene_id, scene_duration=duration,
        resolution_output=engine.resolution_output,
        scene_quality=engine.scene_quality, layout_params=layout_params,
        subtitle_file=srt_path, remote_asset_manager=engine.remote_asset_manager,
        narration_path=None, out_path=out_path, ai_cache=engine.ai_cache,
        log_prefix="[golden]",
    )
    if fast:
        return out_path

    # --- caminho MoviePy (mesma ordem do worker) ---
    bg_engine = BackgroundEngine(
        resolution_output=engine.resolution_output, dir_clips_cache={},
        ai_cache=engine.ai_cache, remote_asset_manager=engine.remote_asset_manager,
    )
    background_clip = bg_engine.build_scene_background(
        effective_gs, scene, duration, scene_dir, engine.output_dir
    )
    visual_clip = _create_visual_elements_clip_worker(
        scene, duration, scene_dir, engine.resolution_output,
        engine.remote_asset_manager, layout_params,
    )
    layers = [background_clip]
    layers += visual_clip if isinstance(visual_clip, list) else ([visual_clip] if visual_clip else [])

    if _subtitles_enabled(effective_gs, scene):
        subtitle_clip = _create_subtitle_clip_worker(
            duration, srt_path, layout_params, engine.resolution_output,
            effective_gs, scene_data=scene,
        )
        if subtitle_clip:
            layers.append(subtitle_clip)

    composed = CompositeVideoClip(layers, size=engine.resolution_output).set_duration(duration)
    composed = composed.fl_image(force_rgb)

    trans = _resolve_scene_transitions(effective_gs, scene)
    if trans and trans.get("enabled"):
        composed = TransitionEngine({
            "clip": composed, "transitions_settings": trans,
            "resolution": engine.resolution_output,
        }).apply_transition()

    q = engine.scene_quality
    composed.write_videofile(
        out_path, codec="libx264", audio=False, fps=q["fps"], preset=q["preset"],
        verbose=False, logger=None,
        ffmpeg_params=["-crf", str(q["crf"]), "-pix_fmt", q["pix_fmt"],
                       "-vsync", "cfr", "-g", "60", "-bf", "2"],
    )
    composed.close()
    return out_path


def render_json(json_path: str, save_dir: str) -> list:
    """Renderiza todas as cenas de um golden. Devolve os arquivos salvos."""
    from libs.UnifiedVideoEngine import UnifiedVideoEngine

    with open(json_path, "r", encoding="utf-8") as f:
        video_data = json.load(f)

    name = os.path.splitext(os.path.basename(json_path))[0]
    srt_path = video_data.pop("_srt", None)
    if srt_path:
        srt_path = os.path.abspath(srt_path)
        if not os.path.exists(srt_path):
            raise FileNotFoundError(f"{name}: _srt não encontrado ({srt_path})")

    # Saída isolada por golden, fora de output/ para não poluir o diretório real.
    video_data.setdefault("output", {})["dir"] = os.path.join(HERE, "_work")
    engine = UnifiedVideoEngine(video_data)

    saved = []
    os.makedirs(save_dir, exist_ok=True)
    for i, scene in enumerate(engine._normalize_scenes()):
        scene_id = scene.get("id", f"cena_{i}")
        t0 = time.time()
        produced = _render_scene(engine, scene, i, srt_path)
        dest = os.path.join(save_dir, f"{name}__{scene_id}.mp4")
        shutil.copyfile(produced, dest)
        saved.append(dest)
        print(f"[golden] {name}/{scene_id} → {os.path.basename(dest)} "
              f"({time.time() - t0:.1f}s)")
    return saved


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--save", required=True, help="diretório de saída dos MP4s")
    ap.add_argument("--only", default=None,
                    help="renderiza só os golden cujo nome contém este texto")
    args = ap.parse_args()

    # O engine assume cwd = videomaker/ (assets, cache e tokens são relativos).
    os.chdir(VIDEOMAKER)

    from tests.fixtures.make_fixtures import build
    build()

    files = sorted(glob.glob(os.path.join(GOLDEN_DIR, "*.json")))
    if args.only:
        files = [f for f in files if args.only in os.path.basename(f)]
    if not files:
        print("[golden] nenhum JSON golden encontrado")
        return 1

    save_dir = os.path.abspath(args.save)
    failures = []
    for json_path in files:
        try:
            render_json(json_path, save_dir)
        except Exception as e:
            failures.append((os.path.basename(json_path), f"{type(e).__name__}: {e}"))
            import traceback
            traceback.print_exc()

    print(f"\n[golden] backend={os.getenv('RENDER_BACKEND', 'auto')} "
          f"→ {save_dir}")
    for name, err in failures:
        print(f"[golden] ❌ {name}: {err}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
