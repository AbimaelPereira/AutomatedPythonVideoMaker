import copy

from libs.Preview import hashing
from libs.Preview.hashing import scene_hash

SCENE = {"id": "a", "narration": {"text": "oi"},
         "visual_elements": [{"type": "image", "source": "x.png", "placement": {"width": "30%"}}]}
GS = {"ai": {"parameters": {"model": "flux"}}}
RES, LAYOUT = (1920, 1080), {"width": 1920}


def h(scene=SCENE, gs=GS, fps=None):
    return scene_hash(scene, gs, RES, LAYOUT, fps or {"k": "k:1:10"})


def test_narracao_nao_muda():
    s = copy.deepcopy(SCENE)
    s["narration"]["text"] = "outra"
    s["duration"] = 9
    assert h(s) == h()


def test_placement_muda():
    s = copy.deepcopy(SCENE)
    s["visual_elements"][0]["placement"]["width"] = "40%"
    assert h(s) != h()


def test_modelo_do_canal_muda():
    assert h(gs={"ai": {"parameters": {"model": "turbo"}}}) != h()


def test_asset_regerado_muda():
    assert h(fps={"k": "k:2:10"}) != h()


def test_versao_muda(monkeypatch):
    before = h()
    monkeypatch.setattr(hashing, "PREVIEW_ENGINE_VERSION", hashing.PREVIEW_ENGINE_VERSION + 1)
    assert h() != before
