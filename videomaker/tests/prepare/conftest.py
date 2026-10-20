import pytest

from libs.Prepare import RateLimiter


@pytest.fixture(autouse=True)
def _limiters_rapidos(monkeypatch):
    """Sem RPM nos testes: o singleton por provider acumularia chamadas entre testes."""
    fast = {k: {"max_concurrent": 8, "rpm": None} for k in RateLimiter.DEFAULT_LIMITS}
    monkeypatch.setattr(RateLimiter, "DEFAULT_LIMITS", fast)
    monkeypatch.setattr(RateLimiter, "FALLBACK_LIMIT", {"max_concurrent": 8, "rpm": None})
    RateLimiter.reset_limiters()
    yield
    RateLimiter.reset_limiters()


@pytest.fixture
def make_ctx(tmp_path, monkeypatch):
    monkeypatch.setattr("libs.VideoContext.load_channel_config", lambda name: {})

    def _make(video):
        from libs.VideoContext import VideoContext
        video = dict(video)
        video.setdefault("slug", "v")
        video.setdefault("output", {"dir": str(tmp_path / "out")})
        return VideoContext.from_video_data(video)
    return _make
