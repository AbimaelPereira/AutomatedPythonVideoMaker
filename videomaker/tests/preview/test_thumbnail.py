import os

import numpy as np
import pytest
from PIL import Image

from libs.Thumbnail.Thumbnail import build_thumbnail, validate_thumbnail


def _thumb(**extra):
    cfg = {"type": "scene", "background": {"visual": {"type": "color", "color": "#000000"}}}
    cfg.update(extra)
    return cfg


def test_tamanho_padrao_por_orientacao(make_ctx):
    for ratio, size in (("16:9", (1280, 720)), ("9:16", (720, 1280))):
        ctx = make_ctx({"slug": f"t{size[0]}", "scenes": [],
                        "output": {"dir": os.path.dirname(make_ctx({"scenes": []}).output_dir),
                                   "ratio": ratio}})
        r = build_thumbnail(_thumb(), ctx)
        assert r.path == os.path.join(ctx.output_dir, "thumbnail.png")
        assert Image.open(r.path).size == size


def test_proporcao_invalida_vira_aviso(make_ctx):
    r = build_thumbnail(_thumb(width=1000, height=1000), make_ctx({"scenes": []}))
    assert Image.open(r.path).size == (1280, 720)
    assert any("proporção" in w for w in r.warnings)


def test_animacao_ignorada_e_elemento_visivel(make_ctx, red_png):
    el = {"type": "image", "source": red_png, "animation": {"type": "fade_in", "duration": 1},
          "placement": {"anchor": ["center", "center"], "width": "30%"}}
    r = build_thumbnail(_thumb(visual_elements=[el]), make_ctx({"scenes": []}))
    assert "thumbnail: 'animation' ignorado em visual_elements[0]" in r.warnings
    assert np.asarray(Image.open(r.path).convert("RGB"))[360, 640, 0] > 200


def test_chaves_de_cena_viram_aviso(make_ctx):
    r = build_thumbnail(_thumb(narration={"text": "x"}, subtitle={}, duration=3, foo=1),
                        make_ctx({"scenes": []}))
    assert r.path and len(r.warnings) == 4


def test_nada_levanta():
    for cfg in (None, {}, {"width": "abc", "height": None}, {"visual_elements": "x"},
                {"background": 3, "visual_elements": [1, {"type": "image"}]}):
        clean, _ = validate_thumbnail(cfg, (1920, 1080))
        assert clean["width"] == 1280


def test_fundo_ruidoso_fica_abaixo_de_2mb(make_ctx, tmp_path):
    noise = (np.random.default_rng(0).random((1080, 1920, 3)) * 255).astype(np.uint8)
    path = tmp_path / "noise.png"
    Image.fromarray(noise).save(path)
    cfg = _thumb(width=1920, height=1080,
                 background={"visual": {"type": "image", "source": str(path)}})
    r = build_thumbnail(cfg, make_ctx({"scenes": []}))
    assert os.path.getsize(r.path) <= 2 * 1024 * 1024


def test_ia_do_bloco_em_assets_e_reaproveitada(make_ctx, monkeypatch):
    import io
    import libs.AIProviders as ai
    calls = []

    def gen(prompt, provider=None, **kw):
        calls.append(prompt)
        buf = io.BytesIO()
        Image.new("RGB", (kw["width"], kw["height"]), (0, 0, 255)).save(buf, "PNG")
        return {"success": True, "content": buf.getvalue()}

    monkeypatch.setattr(ai.ai_manager, "generate_image", gen)
    ctx = make_ctx({"scenes": []})
    cfg = _thumb(background={"visual": {"type": "ai", "prompt": "capa"}})
    build_thumbnail(cfg, ctx)
    r = build_thumbnail(cfg, ctx)
    assert calls == ["capa"]
    assert any(f.endswith(".png") for f in os.listdir(os.path.join(ctx.assets_dir, "ai")))
    assert np.asarray(Image.open(r.path).convert("RGB"))[360, 640, 2] > 200


def test_thumbnail_renderer_removido():
    with pytest.raises(ModuleNotFoundError):
        import libs.Thumbnail.ThumbnailRenderer  # noqa: F401
