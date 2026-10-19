"""Núcleo do Motion: easing, keyframes, schema, presets e timeline.

Roda em milissegundos — nada aqui renderiza vídeo. A única parte que chama o
ffmpeg é a paridade das curvas, e mesmo ela não decodifica frame: avalia a
expressão num `geq` de 200×2 e lê os valores crus.

    pytest tests/test_motion_core.py -q
"""

import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from libs.Motion import easing, presets, resolve_motion, schema          # noqa: E402
from libs.Motion.anchors import AnchorResolver                            # noqa: E402
from libs.Motion.errors import MotionError, ValidationError               # noqa: E402
from libs.Motion.keyframes import Track, parse_track, resolve_time, resolve_value  # noqa: E402
from libs.Motion.timeline import build_timeline                           # noqa: E402

BOX = (100, 200, 400, 300)      # x, y, w, h
RES = (1920, 1080)


def _timeline(motion, *, duration=4.0, words=None, text="", defaults=None,
              box=BOX):
    resolver = AnchorResolver(words=words, narration_text=text,
                              scene_duration=duration,
                              on_missing=(defaults or {}).get("on_missing",
                                                              "proportional"))
    return build_timeline(motion, box=box, resolution=RES,
                          scene_duration=duration, anchor_resolver=resolver,
                          defaults=defaults)


# ---------------------------------------------------------------------------
# EASING — paridade Python ↔ expressão ffmpeg (o teste que impede divergência
# entre os dois backends; ver §5 do plano)
# ---------------------------------------------------------------------------

_N = 200
_TOLERANCE = 0.004      # 1/255: o limite do plano


def _ffmpeg_samples(name: str):
    """Avalia a expressão da curva no ffmpeg em `_N` pontos de p ∈ [0,1].

    X (a coluna) carrega o progresso; o valor é mapeado de [-1,2] para 16 bits
    porque `out_back`/`out_elastic` passam de 1 e ficam abaixo de 0 — clampar
    esconderia justamente o overshoot que caracteriza essas curvas.
    """
    import numpy as np

    expr = easing.expr(name, f"(X/{_N - 1})")
    cmd = [
        "ffmpeg", "-v", "error",
        "-f", "lavfi", "-i", f"color=c=black:size={_N}x2:rate=1:duration=1",
        "-frames:v", "1",
        "-vf", f"format=gray16le,geq=lum='(({expr})+1)/3*65535'",
        "-f", "rawvideo", "-pix_fmt", "gray16le", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True)
    assert proc.returncode == 0, proc.stderr.decode()[:400]
    raw = np.frombuffer(proc.stdout, dtype="<u2").astype(float)[:_N]
    return raw / 65535 * 3 - 1


@pytest.mark.parametrize("name", easing.NAMES)
def test_easing_parity_python_vs_ffmpeg(name):
    samples = _ffmpeg_samples(name)
    for i, got in enumerate(samples):
        expected = easing.apply(name, i / (_N - 1))
        assert abs(got - expected) < _TOLERANCE, \
            f"{name} divergiu em p={i / (_N - 1):.3f}: py={expected} ff={got}"


def test_easing_endpoints():
    for name in easing.NAMES:
        assert abs(easing.apply(name, 0.0)) < 1e-6, name
        assert abs(easing.apply(name, 1.0) - 1.0) < 1e-6, name


def test_easing_expr_has_no_bare_comma():
    """Vírgula não escapada encerraria o filtro e o ffmpeg daria erro críptico."""
    for name in easing.NAMES:
        expr = easing.expr(name, "(t)")
        assert expr.replace("\\,", "").count(",") == 0, name


# ---------------------------------------------------------------------------
# UNIDADES
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("prop,raw,expected", [
    ("x", 40, 40.0),
    ("x", "40px", 40.0),
    ("x", "50%", 200.0),        # 50% da largura da caixa (400)
    ("y", "50%", 150.0),        # 50% da altura da caixa (300)
    ("x", "-30%", -120.0),
    ("x", "10vw", 192.0),       # 10% da largura da tela
    ("y", "10vh", 108.0),
    ("scale", 1.08, 1.08),
    ("opacity", "50%", 0.5),    # adimensional: % é só /100
])
def test_resolve_value_units(prop, raw, expected):
    assert resolve_value(prop, raw, box=BOX, resolution=RES) == pytest.approx(expected)


def test_resolve_value_rejects_garbage():
    with pytest.raises(ValidationError):
        resolve_value("x", "quarenta", box=BOX, resolution=RES)


@pytest.mark.parametrize("raw,expected", [
    (0.0, 0.0), (0.5, 1.0), (1.0, 2.0),      # fração da duração (2 s)
    ("50%", 1.0), ("0.3s", 0.3), (1.4, 1.4),  # > 1 é lido como segundos
])
def test_resolve_time_forms(raw, expected):
    assert resolve_time(raw, duration=2.0) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# TRACKS
# ---------------------------------------------------------------------------

def _keys(prop, raw, duration=1.0, start=0.0, ease="linear"):
    return parse_track(prop, raw, duration=duration, action_start=start,
                       box=BOX, resolution=RES, default_ease=ease)


def test_track_from_pair():
    keys = _keys("opacity", [0, 1])
    assert [(k.t, k.value) for k in keys] == [(0.0, 0.0), (1.0, 1.0)]


def test_track_equally_spaced():
    keys = _keys("scale", [1.0, 1.08, 1.0], duration=0.6)
    assert [round(k.t, 4) for k in keys] == [0.0, 0.3, 0.6]


def test_track_explicit_keyframes():
    keys = _keys("y", [["0%", 40], ["100%", 0]], duration=0.5)
    assert [(k.t, k.value) for k in keys] == [(0.0, 40.0), (0.5, 0.0)]


def test_track_per_keyframe_ease_overrides():
    keys = _keys("x", [[0, "-30%", "out_cubic"], [1, 0]], ease="linear")
    assert keys[0].ease == "out_cubic"
    assert keys[1].ease == "linear"


def test_track_scalar_is_constant():
    keys = _keys("opacity", 0.4, duration=2.0)
    assert [k.value for k in keys] == [0.4, 0.4]


def test_track_action_start_offsets_absolute_time():
    keys = _keys("x", [0, 100], duration=0.5, start=2.0)
    assert [k.t for k in keys] == [2.0, 2.5]


def test_track_rejects_mixed_forms():
    with pytest.raises(ValidationError):
        _keys("x", [0, [1, 20]])


def test_track_rejects_unknown_ease_in_keyframe():
    with pytest.raises(ValidationError):
        _keys("x", [[0, 0, "ease_inexistente"], [1, 10]])


def test_track_sample_interpolates_with_ease():
    track = Track(prop="opacity", keys=_keys("opacity", [0, 1]), base=1.0)
    assert track.sample(-1.0) == 0.0          # antes: segura o primeiro
    assert track.sample(0.5) == pytest.approx(0.5)
    assert track.sample(2.0) == 1.0           # depois: segura o último


def test_track_is_static_detects_no_movement():
    static = Track(prop="scale", keys=_keys("scale", [1.0, 1.0]), base=1.0)
    moving = Track(prop="scale", keys=_keys("scale", [1.0, 1.2]), base=1.0)
    assert static.is_static() and not moving.is_static()


def test_track_hold_between_actions_has_no_phantom_move():
    """Entre duas ações o valor FICA parado — sem interpolar o intervalo morto."""
    track = Track(prop="x", keys=[], base=0.0)
    track.add(_keys("x", [0, 100], duration=0.5, start=0.0))
    track.add(_keys("x", [100, 0], duration=0.5, start=3.0))
    assert track.sample(1.5) == pytest.approx(100.0)
    assert track.sample(3.25) == pytest.approx(50.0)


def test_track_clamp_keeps_edge_values():
    track = Track(prop="x", keys=_keys("x", [0, 100], duration=4.0, start=0.0),
                  base=0.0)
    track.clamp(0.0, 2.0)
    assert track.keys[-1].t == pytest.approx(2.0)
    assert track.keys[-1].value == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# SCHEMA
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("motion,fragment", [
    ({"actions": [{"ease": "out_cubic"}]}, "tracks"),
    ({"actions": [{"preset": "pop_inn"}]}, "preset"),
    ({"actions": [{"ease": "out_cubik", "tracks": {"x": [0, 1]}}]}, "easing"),
    ({"actions": [{"tracks": {"girar": [0, 1]}}]}, "não animável"),
    ({"actions": [{"tracks": {"opacity": [0, 2]}}]}, "opacity"),
    ({"actions": [{"tracks": {"scale": [0, 1]}}]}, "scale"),
    ({"actions": [{"duration": 0, "tracks": {"x": [0, 1]}}]}, "duration"),
    ({"actions": [{"tracks": {"x": [0, 1]}, "atx": 1}]}, "desconhecida"),
    ({"actions": [{"at": {"palavra": "x"}, "tracks": {"x": [0, 1]}}]}, "desconhecida"),
    ({"actions": [{"at": {}, "tracks": {"x": [0, 1]}}]}, "seletor"),
    ({"actions": [{"at": {"word": "a", "phrase": "b"}, "tracks": {"x": [0, 1]}}]},
     "conflitantes"),
    ({"actions": [{"at": {"word": "a", "align": "meio"}, "tracks": {"x": [0, 1]}}]},
     "align"),
    ({"actions": [{"at": {"after": "nada"}, "tracks": {"x": [0, 1]}}]}, "after"),
    ({"actions": []}, "vazia"),
    ({"on_missing": "talvez", "actions": [{"tracks": {"x": [0, 1]}}]}, "on_missing"),
    ({"default_ease": "nope", "actions": [{"tracks": {"x": [0, 1]}}]}, "easing"),
    ({"actions": [{"name": "a", "tracks": {"x": [0, 1]}},
                  {"name": "a", "tracks": {"x": [0, 1]}}]}, "duplicado"),
])
def test_schema_rejects(motion, fragment):
    errors = schema.validate(motion)
    assert errors, f"deveria falhar: {motion}"
    assert any(fragment in str(e) for e in errors), \
        f"mensagem sem {fragment!r}: {[str(e) for e in errors]}"
    with pytest.raises(ValidationError):
        schema.check(motion)


def test_schema_accepts_short_form_list():
    assert schema.validate([{"preset": "fade_in"}]) == []


def test_schema_ignores_comment_keys():
    assert schema.validate({"actions": [{"preset": "fade_in", "nota/": "ignorar"}],
                            "desligado/": True}) == []


def test_schema_error_suggests_close_match():
    errors = schema.validate({"actions": [{"ease": "out_cubik",
                                           "tracks": {"x": [0, 1]}}]})
    assert "out_cubic" in errors[0].hint


def test_schema_error_carries_json_path():
    errors = schema.validate({"actions": [{"tracks": {"x": [0, 1]}},
                                          {"ease": "xx", "tracks": {"x": [0, 1]}}]},
                             path="scenes[2].visual_elements[0].motion")
    assert errors[0].path == "scenes[2].visual_elements[0].motion.actions[1].ease"


# ---------------------------------------------------------------------------
# PRESETS
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", presets.NAMES)
def test_every_preset_builds_a_timeline(name):
    timeline = _timeline([{"preset": name}])
    assert timeline is not None
    assert timeline.tracks, name


def test_preset_tracks_can_be_overridden_per_property():
    timeline = _timeline([{"preset": "pop_in", "tracks": {"scale": [0.5, 1.0]}}])
    assert timeline.sample("scale", 0.0) == pytest.approx(0.5)
    assert timeline.sample("opacity", 0.0) == pytest.approx(0.0)   # veio do preset


def test_preset_with_null_duration_fills_the_scene():
    timeline = _timeline([{"preset": "ken_burns_in"}], duration=6.0)
    assert timeline.sample("zoom", 6.0) == pytest.approx(1.15)
    assert timeline.sample("zoom", 3.0) == pytest.approx(1.075, abs=1e-3)


def test_slide_preset_uses_box_relative_offset():
    timeline = _timeline([{"preset": "slide_in_right"}])
    assert timeline.sample("x", 0.0) == pytest.approx(0.6 * BOX[2])
    assert timeline.sample("x", 0.55) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# TIMELINE
# ---------------------------------------------------------------------------

def test_timeline_none_when_disabled():
    assert _timeline({"enabled": False, "actions": [{"preset": "fade_in"}]}) is None


def test_resolve_motion_returns_none_without_motion_key():
    assert resolve_motion(element={"type": "image"}, box=BOX, resolution=RES,
                          scene_duration=4.0) is None


def test_timeline_numeric_and_percent_anchors():
    timeline = _timeline([
        {"at": 1.0, "duration": 0.5, "tracks": {"x": [0, 10]}},
        {"at": "50%", "duration": 0.5, "tracks": {"y": [0, 10]}},
    ], duration=4.0)
    assert timeline.actions[0]["start"] == pytest.approx(1.0)
    assert timeline.actions[1]["start"] == pytest.approx(2.0)


def test_timeline_after_chains_to_previous_action_end():
    timeline = _timeline([
        {"name": "entrada", "at": 1.0, "duration": 0.5, "preset": "fade_in"},
        {"at": {"after": "entrada", "offset": 0.2}, "duration": 0.3,
         "tracks": {"scale": [1.0, 1.1]}},
    ])
    assert timeline.actions[1]["start"] == pytest.approx(1.7)


def test_timeline_until_defines_duration():
    timeline = _timeline([{"at": 1.0, "until": 2.5, "tracks": {"x": [0, 100]}}])
    assert timeline.actions[0]["duration"] == pytest.approx(1.5)


def test_timeline_hold_false_returns_to_base():
    timeline = _timeline([{"at": 0.0, "duration": 0.5, "hold": False, "ease": "linear",
                           "tracks": {"x": [0, 100]}}], duration=3.0)
    assert timeline.sample("x", 0.5) == pytest.approx(100.0)
    assert timeline.sample("x", 1.0) == pytest.approx(0.0)


def test_timeline_loop_repeats_block():
    timeline = _timeline([{"preset": "float"}], duration=8.0)
    track = timeline.get("y")
    assert track.loop is not None
    # período de 2 s: t=1,0 e t=3,0 caem no mesmo ponto do bloco
    assert track.sample(1.0) == pytest.approx(track.sample(3.0))


def test_timeline_visible_window():
    timeline = _timeline({"visible": {"from": 1.0, "to": 3.0},
                          "actions": [{"preset": "fade_in"}]}, duration=4.0)
    assert timeline.visible == (1.0, 3.0)


def test_timeline_clamps_outside_the_scene():
    timeline = _timeline([{"at": 3.5, "duration": 2.0, "ease": "linear",
                           "tracks": {"x": [0, 100]}}],
                         duration=4.0)
    track = timeline.get("x")
    assert track.keys[-1].t == pytest.approx(4.0)
    assert track.keys[-1].value == pytest.approx(25.0)


def test_timeline_defaults_apply_ease_and_duration():
    timeline = _timeline([{"tracks": {"x": [0, 10]}}],
                         defaults={"default_ease": "out_bounce",
                                   "default_duration": 1.25})
    assert timeline.actions[0]["ease"] == "out_bounce"
    assert timeline.actions[0]["duration"] == pytest.approx(1.25)


def test_timeline_stagger_offsets_every_action():
    timeline = _timeline([{"at": 1.0, "preset": "fade_in"}])
    staggered = build_timeline(
        [{"at": 1.0, "preset": "fade_in"}], box=BOX, resolution=RES,
        scene_duration=4.0,
        anchor_resolver=AnchorResolver(scene_duration=4.0), stagger_offset=0.24,
    )
    assert staggered.actions[0]["start"] - timeline.actions[0]["start"] \
        == pytest.approx(0.24)


def test_timeline_later_action_overwrites_overlapping_track():
    timeline = _timeline([
        {"at": 0.0, "duration": 2.0, "ease": "linear", "tracks": {"x": [0, 200]}},
        {"at": 1.0, "duration": 1.0, "ease": "linear", "tracks": {"x": [0, 50]}},
    ], duration=3.0)
    assert timeline.sample("x", 1.5) == pytest.approx(25.0)


def test_timeline_rejects_after_pointing_forward():
    with pytest.raises((MotionError, ValidationError)):
        _timeline([
            {"at": {"after": "depois"}, "preset": "fade_in"},
            {"name": "depois", "at": 1.0, "preset": "fade_in"},
        ])
