import numpy as np
import pytest
from PIL import Image

from libs.Preview.PreviewEngine import PreviewEngine
from tests.preview.conftest import scene


@pytest.mark.parametrize("anim", [
    {"type": "fade_in", "duration": 1.0},
    {"type": "zoom_in", "intensity": 0.3},
    {"type": "fade_zoom_in", "duration": 1.0},
])
def test_elemento_animado_aparece_opaco_na_posicao_final(make_ctx, red_png, anim):
    ctx = make_ctx({"scenes": [scene("ref", red_png), scene("anim", red_png, animation=anim)]})
    res = PreviewEngine(ctx, max_workers=1).run()
    ref, got = (np.asarray(Image.open(s.path).convert("RGB")).astype(int) for s in res.scenes)
    assert ref[540, 960, 0] > 200  # elemento visível no centro
    assert np.abs(ref - got).max() <= 2


def test_motion_removido(make_ctx, red_png):
    motion = {"actions": [{"preset": "fade_in", "at": 0, "duration": 1}]}
    ctx = make_ctx({"scenes": [scene("ref", red_png), scene("m", red_png, motion=motion)]})
    res = PreviewEngine(ctx, max_workers=1).run()
    ref, got = (np.asarray(Image.open(s.path).convert("RGB")).astype(int) for s in res.scenes)
    assert np.abs(ref - got).max() <= 2
