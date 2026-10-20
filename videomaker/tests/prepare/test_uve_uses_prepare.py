import pytest


class _Stop(BaseException):
    pass


def test_prepare_roda_antes_do_tts(tmp_path, monkeypatch):
    import libs.UnifiedVideoEngine as uve
    from libs.Prepare import PrepareEngine as pe

    order = []
    monkeypatch.setattr(pe.PrepareEngine, "run", lambda self: order.append("prepare"))
    monkeypatch.setattr(pe.PrepareEngine, "apply", lambda self, scenes: scenes)

    def fake_tts(cfg):
        order.append("tts")
        raise _Stop()

    monkeypatch.setattr(uve.NarrationEngine, "preprocess_scenes", staticmethod(fake_tts))
    engine = uve.UnifiedVideoEngine({
        "slug": "t", "debug": True, "output": {"dir": str(tmp_path)},
        "scenes": [{"id": "a", "narration": {"text": "oi"}}],
    })
    with pytest.raises(_Stop):
        engine._run()
    assert order == ["prepare", "tts"]
