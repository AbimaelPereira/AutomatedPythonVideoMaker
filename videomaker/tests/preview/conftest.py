import numpy as np
import pytest
from PIL import Image

from libs.Prepare import RateLimiter


@pytest.fixture(autouse=True)
def _limiters_rapidos(monkeypatch):
    fast = {k: {"max_concurrent": 8, "rpm": None} for k in RateLimiter.DEFAULT_LIMITS}
    monkeypatch.setattr(RateLimiter, "DEFAULT_LIMITS", fast)
    RateLimiter.reset_limiters()
    yield
    RateLimiter.reset_limiters()


@pytest.fixture
def red_png(tmp_path):
    path = tmp_path / "red.png"
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    img[:] = (255, 0, 0)
    Image.fromarray(img).save(path)
    return str(path)


@pytest.fixture
def make_ctx(tmp_path, monkeypatch):
    monkeypatch.setattr("libs.VideoContext.load_channel_config", lambda name: {})

    def _make(video):
        from libs.VideoContext import VideoContext
        video = dict(video)
        video.setdefault("slug", "v")
        video.setdefault("output", {"dir": str(tmp_path / "out"), "ratio": "16:9"})
        return VideoContext.from_video_data(video)
    return _make


def element(src, **extra):
    el = {"type": "image", "source": src,
          "placement": {"anchor": ["center", "center"], "width": "30%"}}
    el.update(extra)
    return el


def scene(sid, src, **extra):
    return {"id": sid, "narration": {"text": "oi"},
            "background": {"visual": {"type": "color", "color": "#000000"}},
            "visual_elements": [element(src, **extra)]}
