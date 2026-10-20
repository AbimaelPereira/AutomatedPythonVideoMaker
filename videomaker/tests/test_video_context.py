import subprocess
import sys

import pytest

from libs.VideoContext import VideoContext


FAKE_CHANNEL_CONFIG = {
    "global_settings": {
        "tts": {"provider": "edge"},
        "padding_top": 10,
    },
    "output": {"dir": "canal_dir", "ratio": "9:16"},
}


def _patch_channel_config(monkeypatch, config=FAKE_CHANNEL_CONFIG):
    monkeypatch.setattr(
        "libs.VideoContext.load_channel_config",
        lambda name: config if name else {},
    )


def test_merge_canal_x_video(monkeypatch):
    _patch_channel_config(monkeypatch)
    video_data = {
        "slug": "meu_video",
        "channel_name": "fake",
        "global_settings": {"tts": {"provider": "kokoro"}},
    }
    ctx = VideoContext.from_video_data(video_data)
    # vídeo vence o canal no campo sobrescrito, mas o canal continua presente no resto.
    assert ctx.global_settings["tts"]["provider"] == "kokoro"
    assert ctx.global_settings["padding_top"] == 10


def test_chapters_achatados_na_ordem_com_gs_mesclado(monkeypatch):
    _patch_channel_config(monkeypatch)
    video_data = {
        "slug": "video_capitulos",
        "channel_name": "fake",
        "chapters": [
            {
                "id": "cap1",
                "global_settings": {"padding_top": 999},
                "scenes": [{"id": "a"}, {"id": "b"}],
            },
            {
                "id": "cap2",
                "scenes": [{"id": "c"}],
            },
        ],
    }
    ctx = VideoContext.from_video_data(video_data)
    ids = [s["id"] for s in ctx.scenes]
    assert ids == ["a", "b", "c"]
    assert ctx.scenes[0]["_effective_gs"]["padding_top"] == 999
    assert ctx.scenes[2]["_effective_gs"]["padding_top"] == 10
    assert [s["_index"] for s in ctx.scenes] == [0, 1, 2]


def test_output_dir_video_vence_canal(monkeypatch):
    _patch_channel_config(monkeypatch)
    video_data = {
        "slug": "s1",
        "channel_name": "fake",
        "output": {"dir": "video_dir"},
    }
    ctx = VideoContext.from_video_data(video_data)
    assert ctx.output_dir.endswith("video_dir/s1")


def test_output_dir_relativo_e_home(monkeypatch):
    _patch_channel_config(monkeypatch, config={})
    video_data = {"slug": "s2", "output": {"dir": "~/minha_pasta"}}
    ctx = VideoContext.from_video_data(video_data)
    assert "~" not in ctx.output_dir
    assert ctx.output_dir.endswith("minha_pasta/s2")


def test_slug_ausente_levanta(monkeypatch):
    _patch_channel_config(monkeypatch, config={})
    with pytest.raises(ValueError):
        VideoContext.from_video_data({}, require_slug=True)


def test_slug_path_traversal_levanta(monkeypatch):
    _patch_channel_config(monkeypatch, config={})
    with pytest.raises(ValueError):
        VideoContext.from_video_data({"slug": "../x"})


def test_video_data_original_nao_mutado(monkeypatch):
    _patch_channel_config(monkeypatch, config={})
    video_data = {"slug": "s3", "scenes": [{"id": "a"}]}
    original_scene = video_data["scenes"][0]
    VideoContext.from_video_data(video_data)
    assert original_scene == {"id": "a"}
    assert "_index" not in original_scene
    assert "_effective_gs" not in original_scene


def test_import_video_context_nao_carrega_moviepy():
    code = (
        "import sys\n"
        "import libs.VideoContext\n"
        "assert 'moviepy' not in sys.modules\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
