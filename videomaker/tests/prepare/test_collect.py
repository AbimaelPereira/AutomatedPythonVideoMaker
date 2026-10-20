import pytest

from libs.Prepare.collect import THUMBNAIL_INDEX, collect_tasks


def _scene(sid, bg_prompt=None, elements=()):
    s = {"id": sid, "visual_elements": list(elements)}
    if bg_prompt:
        s["background"] = {"visual": {"type": "ai", "prompt": bg_prompt}}
    return s


def test_fundo_ia_mais_dois_elementos(make_ctx):
    ctx = make_ctx({"scenes": [_scene("a", "fundo", [
        {"type": "image", "source": {"type": "ai", "prompt": "gato"}},
        {"type": "image", "source": "https://x.com/a.png"},
    ])]})
    tasks = collect_tasks(ctx)
    assert sorted(t.kind for t in tasks) == ["ai", "ai", "download"]


def test_mesmo_prompt_em_duas_cenas_deduplica(make_ctx):
    ctx = make_ctx({"scenes": [_scene("a", "igual"), _scene("b", "igual")]})
    tasks = collect_tasks(ctx)
    assert len(tasks) == 1
    assert tasks[0].refs == ((0, "background"), (1, "background"))


def test_filtro_por_indice(make_ctx):
    ctx = make_ctx({"scenes": [_scene("a", "p1"), _scene("b", "p2")]})
    tasks = collect_tasks(ctx, scene_indexes=[1])
    assert [t.refs for t in tasks] == [((1, "background"),)]


def test_thumbnail_so_com_flag(make_ctx):
    ctx = make_ctx({"scenes": [_scene("a")], "youtube": {"thumbnail": {
        "type": "scene", "background": {"visual": {"type": "ai", "prompt": "capa"}}}}})
    assert collect_tasks(ctx) == []
    tasks = collect_tasks(ctx, include_thumbnail=True)
    assert tasks[0].refs == ((THUMBNAIL_INDEX, "background"),)
    assert tasks[0].spec["resolution"] == (720, 1280)


def test_chave_solta_no_bloco_ia_levanta(make_ctx):
    ctx = make_ctx({"scenes": [{"id": "a", "background": {"visual": {
        "type": "ai", "prompt": "x", "model": "flux"}}}]})
    with pytest.raises(ValueError):
        collect_tasks(ctx)


def test_chapters(make_ctx):
    ctx = make_ctx({"chapters": [
        {"scenes": [_scene("a", "p1")]},
        {"global_settings": {"background": {"visual": {"type": "ai", "prompt": "cap2"}}},
         "scenes": [{"id": "b"}]},
    ]})
    tasks = {t.spec["prompt"]: t.refs for t in collect_tasks(ctx)}
    assert tasks == {"p1": ((0, "background"),), "cap2": ((1, "background"),)}


def test_fundo_ia_inclui_resolucao_e_directory_ignorado(make_ctx):
    ctx = make_ctx({"output_ratio": "16:9", "scenes": [
        _scene("a", "p", [{"type": "directory", "source": "/tmp"}])]})
    tasks = collect_tasks(ctx)
    assert len(tasks) == 1 and tasks[0].spec["resolution"] == (1920, 1080)
