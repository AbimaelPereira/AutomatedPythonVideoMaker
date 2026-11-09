from unittest.mock import MagicMock

import pytest

from libs.R2 import R2, ig_key

ENV = {"R2_ACCOUNT_ID": "acc", "R2_ACCESS_KEY_ID": "k", "R2_SECRET_ACCESS_KEY": "s",
       "R2_BUCKET": "b", "R2_PUBLIC_URL": "https://pub.example/"}


@pytest.fixture
def env(monkeypatch):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)


def test_upload_e_delete(env, tmp_path):
    f = tmp_path / "a.jpg"
    f.write_bytes(b"x")
    client = MagicMock()
    r2 = R2(client=client)
    key = ig_key("slug", "a.jpg")
    assert r2.upload_file(str(f), key) == "https://pub.example/ig/slug/a.jpg"
    client.upload_file.assert_called_once_with(str(f), "b", key, ExtraArgs={"ContentType": "image/jpeg"})
    r2.delete(key)
    client.delete_object.assert_called_once_with(Bucket="b", Key=key)


def test_env_faltando(monkeypatch):
    for k in ENV:
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ValueError, match="R2_BUCKET"):
        R2(client=MagicMock())
