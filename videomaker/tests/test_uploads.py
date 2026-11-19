from unittest.mock import MagicMock

import pytest

from libs.Uploads import resolve_uploads, upload_config, upload_r2, validate_r2

ENV = {"R2_ACCOUNT_ID": "acc", "R2_ACCESS_KEY_ID": "k", "R2_SECRET_ACCESS_KEY": "s",
       "R2_BUCKET": "b", "R2_PUBLIC_URL": "https://pub.example"}


def test_bloco_uploads():
    r = resolve_uploads({}, {"uploads": {"youtube": {"title": "t"}, "r2": {}}})
    assert r == {"youtube": {"title": "t"}, "r2": {}}


def test_legado_na_raiz():
    r = resolve_uploads({"youtube": {"token_file_name": "x"}}, {"youtube": {"title": "t"}})
    assert r == {"youtube": {"token_file_name": "x", "title": "t"}}


def test_canal_uploads_mais_video_legado():
    r = resolve_uploads({"uploads": {"youtube": {"token_file_name": "x"}}},
                        {"youtube": {"title": "t"}})
    assert r["youtube"] == {"token_file_name": "x", "title": "t"}


def test_enabled_false_desliga_destino_do_canal():
    canal = {"uploads": {"youtube": {"token_file_name": "x"}, "r2": True}}
    r = resolve_uploads(canal, {"uploads": {"youtube": {"enabled": False}, "r2": False}})
    assert r == {}


def test_vazio_so_vale_para_r2():
    assert resolve_uploads({}, {"uploads": {"youtube": {}, "r2": True}}) == {"r2": {}}


def test_tiktok_legado_em_global_settings():
    r = resolve_uploads({}, {}, {"tiktok": {"a": 1}})
    assert r == {"tiktok": {"a": 1}}


def test_upload_config_ignora_enabled():
    cfg = upload_config("youtube", {}, {"uploads": {"youtube": {"enabled": False, "thumbnail": {"x": 1}}}})
    assert cfg["thumbnail"] == {"x": 1}


def test_validate_r2(monkeypatch):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    assert validate_r2({}, slug="s", channel_name="c") == []
    assert validate_r2({"prefix": "ig/{slug}"}, slug="s", channel_name="c")
    assert validate_r2({"prefix": "{nada}"}, slug="s", channel_name="c")
    monkeypatch.delenv("R2_BUCKET")
    assert any("R2_BUCKET" in p for p in validate_r2({}, slug="s", channel_name="c"))


def test_upload_r2(tmp_path):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"x")
    r2 = MagicMock()
    r2.upload_file.side_effect = lambda path, key: f"https://pub/{key}"
    out = upload_r2({"prefix": "videos/{channel}/{slug}"}, [str(f), None, str(tmp_path / "nao_existe")],
                    slug="meu", channel_name="canal", r2=r2)
    assert out == [{"key": "videos/canal/meu/v.mp4", "url": "https://pub/videos/canal/meu/v.mp4"}]
