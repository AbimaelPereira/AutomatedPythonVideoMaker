"""Compilador de expressões ffmpeg: escape, forma da árvore e planos.

O teste mais importante aqui é o de VÍRGULA. O `filter_complex` é um argv só; uma
vírgula não escapada dentro de `'...'` encerra o filtro e o ffmpeg devolve um
erro que não aponta para a causa. Além da contagem, cada expressão é submetida
ao avaliador real do ffmpeg — se ele aceitar e devolver o valor esperado, o
escape está certo de fato.

    pytest tests/test_compile_ffmpeg.py -q
"""

import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from libs.Motion import compile_ffmpeg as cf                     # noqa: E402
from libs.Motion.anchors import AnchorResolver                   # noqa: E402
from libs.Motion.errors import ValidationError                   # noqa: E402
from libs.Motion.timeline import build_timeline                  # noqa: E402

BOX = (100, 200, 400, 300)
RES = (1920, 1080)


def _timeline(motion, duration=4.0):
    return build_timeline(motion, box=BOX, resolution=RES,
                          scene_duration=duration,
                          anchor_resolver=AnchorResolver(scene_duration=duration))


def _bare_commas(expr: str) -> int:
    return expr.replace("\\,", "").count(",")


def _eval_at(expr: str, t: float) -> float:
    """Avalia a expressão NO FFMPEG, no instante `t`.

    O `geq` expõe o tempo como `T` (maiúsculo), ao contrário do `scale`/`overlay`
    — por isso as expressões são compiladas aqui com `t_var="T"`.
    O valor é mapeado de [-1000, 2000] para 16 bits — a faixa cobre deslocamento
    em pixels sem clampar.
    """
    import numpy as np

    lo, span = -1000.0, 3000.0
    cmd = [
        "ffmpeg", "-v", "error",
        "-f", "lavfi", "-i", "color=c=black:size=2x2:rate=100:duration=6",
        "-vf", f"format=gray16le,geq=lum='(({expr})-({lo}))/{span}*65535'",
        "-f", "rawvideo", "-pix_fmt", "gray16le", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True)
    assert proc.returncode == 0, proc.stderr.decode()[:400]
    frames = np.frombuffer(proc.stdout, dtype="<u2").reshape(-1, 4)
    index = min(int(round(t * 100)), len(frames) - 1)
    return float(frames[index][0]) / 65535 * span + lo


# ---------------------------------------------------------------------------
# ESCAPE
# ---------------------------------------------------------------------------

def test_track_expr_has_no_bare_comma():
    timeline = _timeline([{"at": 0.0, "duration": 1.0, "ease": "out_elastic",
                           "tracks": {"x": [[0, 0], [0.25, 50], [0.5, -20],
                                            [0.75, 10], [1.0, 0]]}}])
    expr = cf.track_expr(timeline.get("x"))
    assert _bare_commas(expr) == 0


def test_every_generated_expression_is_comma_safe():
    timeline = _timeline({
        "visible": {"from": 0.5, "to": 3.0},
        "actions": [{"at": 0.0, "duration": 1.0, "preset": "pop_in"},
                    {"at": 1.5, "duration": 1.0, "tracks": {"zoom": [1.0, 1.2]}}],
    })
    exprs = list(cf.position_exprs(timeline, BOX, scaled=True))
    exprs += list(cf.scale_exprs(timeline, BOX))
    exprs.append(cf.zoom_expr(timeline, t_var="(on/30)"))
    exprs.append(cf.enable_expr(timeline))
    for expr in exprs:
        assert _bare_commas(expr) == 0, expr


def test_esc_escapes_raw_text():
    assert cf.esc("a,b:c'd") == "a\\,b\\:c\\'d"


# ---------------------------------------------------------------------------
# VALORES (avaliados pelo ffmpeg de verdade)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("t,expected", [
    (0.0, 100.0),    # antes do 1º keyframe: segura
    (0.5, 100.0),
    (1.0, 150.0),    # metade do caminho, easing linear
    (1.5, 200.0),
    (2.5, 200.0),    # depois do último: segura
])
def test_position_expr_matches_python(t, expected):
    timeline = _timeline([{"at": 0.5, "duration": 1.0, "ease": "linear",
                           "tracks": {"x": [0, 100]}}])
    expr = cf.position_exprs(timeline, BOX, t_var="T")[0]
    assert _eval_at(expr, t) == pytest.approx(expected, abs=0.2)
    assert BOX[0] + timeline.sample("x", t) == pytest.approx(expected)


def test_eased_expr_matches_python_sample():
    timeline = _timeline([{"at": 0.0, "duration": 1.0, "ease": "out_back",
                           "tracks": {"y": [0, 200]}}])
    expr = cf.position_exprs(timeline, BOX, t_var="T")[1]
    for t in (0.1, 0.3, 0.5, 0.9):
        expected = BOX[1] + timeline.sample("y", t)
        assert _eval_at(expr, t) == pytest.approx(expected, abs=0.5), t


def test_loop_expr_folds_time():
    timeline = _timeline([{"at": 0.0, "duration": 2.0, "loop": True,
                           "ease": "linear",
                           "tracks": {"y": [[0, 0], [0.5, 100], [1.0, 0]]}}],
                         duration=6.0)
    expr = cf.position_exprs(timeline, BOX, t_var="T")[1]
    assert _eval_at(expr, 1.0) == pytest.approx(_eval_at(expr, 3.0), abs=0.5)


def test_static_track_compiles_to_a_constant():
    timeline = _timeline([{"at": 0.0, "duration": 1.0, "tracks": {"x": [25, 25]}}])
    expr = cf.track_expr(timeline.get("x"), t_var="T", offset=100.0)
    assert "if(" not in expr
    assert float(expr) == pytest.approx(125.0)


# ---------------------------------------------------------------------------
# PLANOS
# ---------------------------------------------------------------------------

def test_scale_exprs_force_even_dimensions():
    timeline = _timeline([{"preset": "pop_in"}])
    w_expr, h_expr = cf.scale_exprs(timeline, BOX, t_var="T")
    assert w_expr.startswith("trunc(") and "/2)*2" in w_expr
    assert h_expr.startswith("trunc(") and "/2)*2" in h_expr
    # 0.82 × 400 = 328 (par) no início da curva
    assert _eval_at(w_expr, 0.0) == pytest.approx(328.0, abs=2.0)


def test_scale_compensation_uses_overlay_size():
    timeline = _timeline([{"preset": "punch"}])
    x_expr, y_expr = cf.position_exprs(timeline, BOX, scaled=True)
    assert "overlay_w" in x_expr and "overlay_h" in y_expr


@pytest.mark.parametrize("anchor,fragment", [
    (("left", "top"), None),
    (("right", "center"), "-overlay_w"),
    (("center", "bottom"), "-overlay_h"),
])
def test_scale_compensation_respects_anchor(anchor, fragment):
    timeline = _timeline([{"preset": "punch"}])
    x_expr, y_expr = cf.position_exprs(timeline, BOX, anchor=anchor, scaled=True)
    joined = x_expr + y_expr
    if fragment is None:
        assert "overlay_w" not in joined and "overlay_h" not in joined
    else:
        assert fragment in joined


def test_opacity_linear_uses_cheap_fade_chain():
    timeline = _timeline([{"at": 0.2, "duration": 0.5, "preset": "fade_in"},
                          {"at": 3.0, "duration": 0.5, "preset": "fade_out"}])
    plan = cf.opacity_plan(timeline)
    assert plan["kind"] == "fade"
    kinds = [segment[0] for segment in plan["segments"]]
    assert kinds == ["in", "out"]
    assert plan["segments"][0][1] == pytest.approx(0.2)


def test_opacity_partial_range_falls_back_to_geq():
    """0,3 → 0,8 não é um `fade` nativo (que só faz 0↔1)."""
    timeline = _timeline([{"at": 0.0, "duration": 1.0, "ease": "linear",
                           "tracks": {"opacity": [0.3, 0.8]}}])
    assert cf.opacity_plan(timeline)["kind"] == "geq"


def test_opacity_nonlinear_ease_falls_back_to_geq():
    timeline = _timeline([{"at": 0.0, "duration": 1.0, "ease": "out_bounce",
                           "tracks": {"opacity": [0, 1]}}])
    assert cf.opacity_plan(timeline)["kind"] == "geq"


def test_enable_expr_from_visible():
    timeline = _timeline({"visible": {"from": 1.0, "to": 2.5},
                          "actions": [{"preset": "fade_in"}]})
    assert cf.enable_expr(timeline) == "between(t\\,1\\,2.5)"


def test_no_plan_when_nothing_moves():
    timeline = _timeline([{"at": 0.0, "duration": 1.0, "tracks": {"x": [0, 0]}}])
    assert cf.scale_exprs(timeline, BOX) is None
    assert cf.position_exprs(timeline, BOX) is None
    assert cf.opacity_plan(timeline) is None
    assert cf.zoom_expr(timeline, t_var="t") is None


# ---------------------------------------------------------------------------
# GATE
# ---------------------------------------------------------------------------

def test_check_refuses_too_many_keyframes():
    keys = [[i / 40.0, (i % 2) * 10] for i in range(40)]
    timeline = _timeline([{"at": 0.0, "duration": 2.0, "tracks": {"x": keys}}])
    ok, why = cf.check(timeline)
    assert not ok and "keyframes" in why


def test_rotation_compiles_to_radians():
    """O JSON declara graus; o filtro `rotate` só entende radianos."""
    import math

    timeline = _timeline([{"at": 0.0, "duration": 1.0, "ease": "linear",
                           "tracks": {"rotation": [0, 90]}}])
    expr = cf.rotation_expr(timeline, t_var="T")
    assert _bare_commas(expr) == 0
    # `_eval_at` quantiza em 16 bits sobre uma faixa de 3000 px → passo de
    # ~0,046; por isso a tolerância é folgada aqui (o valor em si é exato).
    assert _eval_at(expr, 1.0) == pytest.approx(math.pi / 2, abs=0.06)


def test_blur_constant_is_supported_animated_is_not():
    """`gblur` só aceita sigma fixo — blur animado vai para o MoviePy."""
    constant = _timeline([{"at": 0.0, "duration": 1.0, "tracks": {"blur": [6, 6]}}])
    assert cf.blur_sigma(constant) == pytest.approx(6.0)
    assert cf.check(constant)[0]

    animated = _timeline([{"at": 0.0, "duration": 1.0, "tracks": {"blur": [8, 0]}}])
    ok, why = cf.check(animated)
    assert not ok and "blur" in why


def test_check_accepts_rotation_and_blur():
    assert cf.check_element({"motion": [{"duration": 0.5,
                                         "tracks": {"rotation": [0, 90]}}]}) == (True, "")
    assert cf.check_element({"motion": [{"duration": 0.5,
                                         "tracks": {"blur": [6, 6]}}]}) == (True, "")


def test_check_element_rejects_animation_and_motion_together():
    with pytest.raises(ValidationError):
        cf.check_element({"animation": {"type": "zoom_in"},
                          "motion": [{"preset": "fade_in"}]})


def test_check_element_passes_plain_motion():
    assert cf.check_element({"motion": [{"preset": "pop_in"}]}) == (True, "")
    assert cf.check_element({"type": "image"}) == (True, "")
