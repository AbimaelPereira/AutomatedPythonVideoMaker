"""Impressão da timeline resolvida — o loop de iteração rápida do Motion.

Antes de renderizar (que custa segundos ou minutos), veja ONDE cada ação caiu:

    python -m libs.Motion.inspect jsons/x.json --video 0 --scene cena_02
    python -m libs.Motion.inspect jsons/x.json --no-tts     # sem gerar narração

`MOTION_DEBUG=1` imprime a mesma tabela durante o render normal.

Sem `--no-tts` o TTS da cena é executado (só a narração, nada de vídeo) para que
as âncoras de palavra sejam resolvidas contra o SRT real — é o único jeito de
conferir sincronia de verdade. Com `--no-tts`, as âncoras de fala caem no
`on_missing` e o que se valida é a estrutura.
"""

import argparse
import json
import os
import sys


def debug_enabled() -> bool:
    return os.getenv("MOTION_DEBUG", "0").strip().lower() in ("1", "true", "yes")


def format_timeline(timeline, *, label: str = "", words: list = None) -> str:
    """Tabela legível de uma `Timeline` já resolvida."""
    if timeline is None:
        return f"  {label}: sem motion"

    lines = [f"  {label}  dur={timeline.duration:.2f}s  "
             f"tracks={','.join(sorted(timeline.active())) or '—'}"]

    if timeline.visible:
        lines.append(f"      visible: {timeline.visible[0]:.2f}s → "
                     f"{timeline.visible[1]:.2f}s")

    for action in timeline.actions:
        name = action.get("name") or f"ação[{action['index']}]"
        preset = action.get("preset") or "tracks"
        loop = "  (loop)" if action.get("loop") else ""
        lines.append(f"      t={action['start']:.2f}  +{action['duration']:.2f}  "
                     f"{name:<12} {preset:<16} ease={action['ease']}"
                     f"  props={','.join(action['props'])}{loop}")
        if words:
            lines.append(f"            ↳ {_nearest_word(words, action['start'])}")

    for prop, track in sorted(timeline.tracks.items()):
        keys = ", ".join(f"{k.t:.2f}s→{k.value:.3f}" for k in track.keys[:8])
        extra = " …" if len(track.keys) > 8 else ""
        lines.append(f"      {prop:<8} [{keys}{extra}]")

    for warning in timeline.warnings:
        lines.append(f"      ⚠️ {warning}")

    return "\n".join(lines)


def _nearest_word(words: list, t: float) -> str:
    """Qual palavra está sendo falada em `t` — confere a âncora de olho."""
    for i, word in enumerate(words):
        if word["start"] <= t <= word["end"]:
            return (f"palavra #{i + 1} {word['word']!r} "
                    f"({word['start']:.2f}–{word['end']:.2f})")
    after = next((i for i, w in enumerate(words) if w["start"] > t), None)
    if after is None:
        return "depois da última palavra"
    word = words[after]
    return (f"entre palavras, antes de #{after + 1} {word['word']!r} "
            f"({word['start']:.2f})")


def print_scene(scene_id: str, timelines: list, *, words: list = None,
                duration: float = 0.0):
    """Tabela de uma cena inteira (usada pelo CLI e pelo MOTION_DEBUG)."""
    count = len(words or [])
    print(f"[Motion] {scene_id}  dur={duration:.2f}s  palavras={count}")
    for i, timeline in enumerate(timelines):
        if timeline is None:
            continue
        print(format_timeline(timeline, label=f"elemento[{i}]", words=words))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def inspect_json(json_path: str, *, video_index: int = 0, scene_filter: str = None,
                 use_tts: bool = True, validate_only: bool = False) -> int:
    """Resolve (e imprime) as timelines de um JSON de vídeo. 0 = tudo ok."""
    from libs.LayoutEngine import LayoutEngine
    from libs.Motion import (motion_defaults, resolve_scene_motion,
                             words_from_srt)
    from libs.Motion.errors import MotionError
    from libs.Motion.schema import validate
    from libs.UnifiedVideoEngine import UnifiedVideoEngine

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    videos = data if isinstance(data, list) else [data]
    video_data = videos[video_index]

    engine = UnifiedVideoEngine(video_data)
    scenes = engine._normalize_scenes()

    problems = 0
    for scene in scenes:
        scene_id = scene.get("id", "?")
        if scene_filter and scene_filter not in str(scene_id):
            continue
        elements = list(scene.get("visual_elements") or [])
        if not any(isinstance(el, dict) and el.get("motion") for el in elements):
            continue

        if validate_only:
            for i, el in enumerate(elements):
                if not el.get("motion"):
                    continue
                path = f"scenes[{scene_id}].visual_elements[{i}].motion"
                for error in validate(el["motion"], path):
                    print(f"❌ {error}")
                    problems += 1
            continue

        effective_gs = engine._resolve_scene_gs(scene)
        duration = float(scene.get("duration") or 0.0)
        words = None

        if use_tts:
            scene_dir = os.path.join(engine.output_dir, str(scene_id))
            os.makedirs(scene_dir, exist_ok=True)
            from libs.Audio.NarrationEngine import NarrationEngine
            from libs.UnifiedVideoEngine import _resolve_scene_tts
            from libs.utils import deep_merge

            tts_config = _resolve_scene_tts(
                deep_merge(engine.tts_config, effective_gs.get("tts", {})), scene)
            narration, tts_duration, srt_path = NarrationEngine(
                tts_config, engine.output_dir).process_scene_narration(scene, scene_dir)
            words = words_from_srt(srt_path)
            duration = duration or float(tts_duration or 0.0)
            if narration:
                try:
                    narration.close()
                except Exception:
                    pass

        duration = duration or 4.0

        # As caixas precisam do tamanho nativo da mídia; aqui (sem render) o
        # importante é a ORDEM DE GRANDEZA das caixas, então usa-se um tamanho
        # nominal. Tempos e easings — o que se está inspecionando — não dependem
        # dele.
        items = [{
            "original_size": (1920, 1080),
            "placement": el.get("placement"),
            "layout": el.get("layout", {}),
            "border_radius": el.get("border_radius", 0),
            "animation": el.get("animation"),
        } for el in elements]
        layout = LayoutEngine.process_stack_layout(items, engine.layout_config)
        boxes = []
        for res in layout:
            if not res:
                boxes.append((0, 0, engine.resolution_output[0],
                              engine.resolution_output[1]))
                continue
            (w, h), (x, y) = res["final_size"], res["final_position"]
            boxes.append((int(x), int(y), int(w), int(h)))

        try:
            timelines = resolve_scene_motion(
                scene=scene, elements=elements, boxes=boxes,
                resolution=engine.resolution_output, scene_duration=duration,
                words=words, defaults=motion_defaults(effective_gs, scene),
            )
        except MotionError as e:
            print(f"❌ {scene_id}: {e}")
            problems += 1
            continue

        print_scene(str(scene_id), timelines, words=words, duration=duration)

    if validate_only and not problems:
        print("✅ motion válido em todas as cenas")
    return 1 if problems else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("json_file")
    ap.add_argument("--video", type=int, default=0, help="índice do vídeo na lista")
    ap.add_argument("--scene", default=None, help="filtra pelo id da cena")
    ap.add_argument("--no-tts", action="store_true",
                    help="não gera narração (âncoras de fala caem no on_missing)")
    ap.add_argument("--validate", action="store_true",
                    help="só roda o schema, sem resolver nada")
    args = ap.parse_args(argv)

    json_file = os.path.abspath(args.json_file)
    os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))
    return inspect_json(json_file, video_index=args.video, scene_filter=args.scene,
                        use_tts=not args.no_tts, validate_only=args.validate)


if __name__ == "__main__":
    sys.exit(main())
