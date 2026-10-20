import os

import pytest
from PIL import Image

import libs.Preview.PreviewEngine as pe
from libs.Preview.PreviewEngine import PreviewEngine
from tests.preview.conftest import scene


@pytest.fixture
def spy(monkeypatch):
    calls = []
    real = pe._render_scene_job

    def wrapped(job):
        calls.append(job["index"])
        return real(job)

    monkeypatch.setattr(pe, "_render_scene_job", wrapped)
    return calls


def _video(src, n=3):
    return {"scenes": [scene(c, src) for c in "abc"[:n]]}


def test_tres_cenas_tres_pngs_e_cache(make_ctx, red_png, spy):
    ctx = make_ctx(_video(red_png))
    r1 = PreviewEngine(ctx, max_workers=1).run()
    names = [os.path.basename(s.path) for s in r1.scenes]
    assert names == ["01-a.png", "02-b.png", "03-c.png"]
    assert all(Image.open(s.path).size == (1920, 1080) for s in r1.scenes)
    assert os.path.dirname(r1.scenes[0].path) == ctx.previews_dir
    spy.clear()
    r2 = PreviewEngine(ctx, max_workers=1).run()
    assert [s.status for s in r2.scenes] == ["cached"] * 3 and spy == []


def test_so_cena_alterada_renderiza(make_ctx, red_png, spy):
    video = _video(red_png)
    PreviewEngine(make_ctx(video), max_workers=1).run()
    video["scenes"][1]["visual_elements"][0]["placement"]["width"] = "50%"
    spy.clear()
    r = PreviewEngine(make_ctx(video), max_workers=1).run()
    assert spy == [1] and [s.status for s in r.scenes] == ["cached", "rendered", "cached"]


def test_selecao_por_id_e_indice(make_ctx, red_png):
    ctx = make_ctx(_video(red_png))
    a = PreviewEngine(ctx, scenes=["b"], max_workers=1).run()
    b = PreviewEngine(ctx, scenes=[2], max_workers=1).run()
    assert [s.scene_id for s in a.scenes] == [s.scene_id for s in b.scenes] == ["b"]
    with pytest.raises(ValueError):
        PreviewEngine(ctx, scenes=["zzz"]).run()


def test_force(make_ctx, red_png, spy):
    ctx = make_ctx(_video(red_png))
    PreviewEngine(ctx, max_workers=1).run()
    spy.clear()
    PreviewEngine(ctx, force=True, max_workers=1).run()
    assert spy == [0, 1, 2]


def test_erro_isolado(make_ctx, red_png, monkeypatch):
    real = pe._render_scene_job

    def boom(job):
        if job["index"] == 1:
            return {"index": 1, "error": "RuntimeError: x", "warnings": []}
        return real(job)

    monkeypatch.setattr(pe, "_render_scene_job", boom)
    r = PreviewEngine(make_ctx(_video(red_png)), max_workers=1).run()
    assert [s.status for s in r.scenes] == ["rendered", "error", "rendered"]
    assert r.scenes[1].path is None


def test_chapters_indices_continuos(make_ctx, red_png):
    ctx = make_ctx({"chapters": [{"scenes": [scene("a", red_png)]},
                                 {"scenes": [scene("b", red_png)]}]})
    r = PreviewEngine(ctx, max_workers=1).run()
    assert [s.index for s in r.scenes] == [1, 2]
    assert os.path.basename(r.scenes[1].path) == "02-b.png"


def test_orfaos_so_em_execucao_completa(make_ctx, red_png):
    video = _video(red_png)
    PreviewEngine(make_ctx(video), max_workers=1).run()
    video["scenes"] = video["scenes"][:2]
    ctx = make_ctx(video)
    PreviewEngine(ctx, scenes=["a"], max_workers=1).run()
    assert os.path.exists(os.path.join(ctx.previews_dir, "03-c.png"))
    PreviewEngine(ctx, max_workers=1).run()
    assert not os.path.exists(os.path.join(ctx.previews_dir, "03-c.png"))


def test_nada_fora_do_slug(make_ctx, red_png, tmp_path):
    ctx = make_ctx(_video(red_png, 1))
    PreviewEngine(ctx, max_workers=1).run()
    for root, dirs, files in os.walk(tmp_path / "out"):
        for f in files:
            assert os.path.join(root, f).startswith(ctx.output_dir)
    assert not [d for d in os.listdir(ctx.previews_dir) if d.startswith(".work")]


def test_pool_de_processos(make_ctx, red_png):
    r = PreviewEngine(make_ctx(_video(red_png)), max_workers=2).run()
    assert all(s.status == "rendered" for s in r.scenes)
