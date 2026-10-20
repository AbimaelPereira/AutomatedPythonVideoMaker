import copy
import itertools
import os

import pytest

from libs.Prepare.PrepareEngine import PrepareEngine

VIDEOMAKER_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def fake_ai(monkeypatch):
    import libs.AIProviders as ai
    calls = []

    def gen(prompt, provider=None, **kw):
        calls.append(prompt)
        if prompt == "quebra":
            return {"success": False, "error": "prompt inválido"}
        return {"success": True, "content": f"img:{prompt}".encode()}

    monkeypatch.setattr(ai.ai_manager, "generate_image", gen)
    return calls


@pytest.fixture
def fake_download(monkeypatch):
    from libs.MediaDownloader import MediaDownloader
    calls = []

    def resolve(source, temp_dir="output/temp", on_success_callback=None, on_fail_callback=None):
        calls.append(source)
        os.makedirs(temp_dir, exist_ok=True)
        path = os.path.join(temp_dir, f"asset_{abs(hash(source))}.png")
        with open(path, "wb") as f:
            f.write(source.encode())
        if on_success_callback:
            on_success_callback(source)
        return path

    monkeypatch.setattr(MediaDownloader, "resolve_source_path", staticmethod(resolve))
    return calls


def _video(prompts=("a", "b")):
    return {"scenes": [
        {"id": f"s{i}", "background": {"visual": {"type": "ai", "prompt": p}},
         "visual_elements": [{"type": "image", "source": f"https://x.com/{p}.png"}]}
        for i, p in enumerate(prompts)]}


def test_segunda_execucao_100_cache(make_ctx, fake_ai, fake_download):
    ctx = make_ctx(_video())
    r1 = PrepareEngine(ctx).run()
    assert len(r1.resolved) == 4 and r1.skipped == 0 and not r1.failed
    n_ai, n_dl = len(fake_ai), len(fake_download)
    r2 = PrepareEngine(ctx).run()
    assert r2.skipped == 4
    assert (len(fake_ai), len(fake_download)) == (n_ai, n_dl)


def test_force_regera(make_ctx, fake_ai, fake_download):
    ctx = make_ctx(_video())
    PrepareEngine(ctx).run()
    PrepareEngine(ctx, force=True).run()
    assert len(fake_ai) == 4


def test_ai_cache_false_regera_ia(make_ctx, fake_ai, fake_download):
    ctx = make_ctx(dict(_video(), ai_cache=False))
    PrepareEngine(ctx).run()
    PrepareEngine(ctx).run()
    assert len(fake_ai) == 4 and len(fake_download) == 2


def test_falha_isolada(make_ctx, fake_ai, fake_download):
    ctx = make_ctx(_video(("ok", "quebra")))
    r = PrepareEngine(ctx).run()
    assert len(r.failed) == 1 and len(r.resolved) == 3


def test_apply_nao_muta_e_reescreve(make_ctx, fake_ai, fake_download):
    ctx = make_ctx(_video(("ok", "quebra")))
    eng = PrepareEngine(ctx)
    eng.run()
    original = copy.deepcopy(ctx.scenes)
    out = eng.apply(ctx.scenes)
    assert ctx.scenes == original
    bg0 = out[0]["background"]["visual"]
    assert bg0["type"] == "ai" and os.path.isfile(bg0["_resolved_path"])
    assert "_resolved_path" not in out[1]["background"]["visual"]  # falhou: intocado
    assert os.path.isfile(out[0]["visual_elements"][0]["source"])
    assert out[0]["visual_elements"][0]["type"] == "image"


def test_ve_ia_vira_caminho(make_ctx, fake_ai):
    ctx = make_ctx({"scenes": [{"id": "a", "visual_elements": [
        {"type": "image", "source": {"type": "ai", "prompt": "gato"}}]}]})
    eng = PrepareEngine(ctx)
    eng.run()
    src = eng.apply(ctx.scenes)[0]["visual_elements"][0]["source"]
    assert isinstance(src, str) and open(src, "rb").read() == b"img:gato"


def test_remote_asset_fixado(make_ctx, fake_download):
    urls = itertools.count()

    class FakeRAM:
        def select_url(self, slug):
            return f"https://cdn/{slug}/{next(urls)}.png"
        def mark_download_success(self, url): pass
        def mark_download_failed(self, url): pass
        def register_url(self, *a): pass

    video = {"global_settings": {"remote_assets": {"selection_mode": "random"}},
             "scenes": [{"id": "a", "visual_elements": [{"type": "remote_asset", "source": "gatos"}]}]}
    ctx = make_ctx(video)
    e1 = PrepareEngine(ctx, remote_asset_manager=FakeRAM())
    e1.run()
    url1 = next(iter(e1.store.entries().values()))["meta"]["url"]
    path = e1.apply(ctx.scenes)[0]["visual_elements"][0]["source"]
    os.remove(path)  # força nova resolução: deve usar a URL fixada
    e2 = PrepareEngine(ctx, remote_asset_manager=FakeRAM())
    e2.run()
    assert next(iter(e2.store.entries().values()))["meta"]["url"] == url1
    assert e2.apply(ctx.scenes)[0]["visual_elements"][0]["type"] == "remote_asset"


def test_nada_fora_da_pasta_do_video(make_ctx, fake_ai, fake_download, tmp_path):
    cache_dir = os.path.join(VIDEOMAKER_DIR, "cache")
    before = sorted(os.listdir(cache_dir)) if os.path.isdir(cache_dir) else None
    ctx = make_ctx(_video())
    PrepareEngine(ctx).run()
    for root, _, files in os.walk(tmp_path):
        for f in files:
            assert os.path.join(root, f).startswith(os.path.join(ctx.output_dir, "assets"))
    after = sorted(os.listdir(cache_dir)) if os.path.isdir(cache_dir) else None
    assert before == after
