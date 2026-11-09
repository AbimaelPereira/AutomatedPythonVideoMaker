import json
from unittest.mock import MagicMock

import pytest

from libs import InstagramAccount as IA
from libs.Instagram import Instagram
from libs.InstagramAccount import InstagramAccount, load_account

ACC = InstagramAccount(user_id="U", token="T")


def resp(data, ok=True, status=200):
    r = MagicMock(ok=ok, status_code=status, text=json.dumps(data))
    r.json.return_value = data
    return r


class FakeHttp:
    def __init__(self, fail_target=None):
        self.calls, self.n, self.fail_target = [], 0, fail_target

    def post(self, url, data=None, **kw):
        self.calls.append(("POST", url, data if isinstance(data, dict) else "<bytes>", kw.get("headers")))
        if url.endswith("/media"):
            self.n += 1
            if self.fail_target and data.get("media_type") == self.fail_target:
                return resp({"error": {"message": "boom"}}, ok=False, status=400)
            return resp({"id": f"C{self.n}", "uri": f"https://rupload/C{self.n}"})
        if url.startswith("https://rupload"):
            return resp({"success": True})
        if url.endswith("/media_publish"):
            return resp({"id": "M" + data["creation_id"]})
        raise AssertionError(url)

    def get(self, url, params=None, **kw):
        self.calls.append(("GET", url, params, None))
        if params["fields"].startswith("status_code"):
            return resp({"status_code": "FINISHED"})
        return resp({"permalink": f"https://ig/{url.rsplit('/', 1)[1]}"})


def test_publish_video_feed_e_story(tmp_path):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"123")
    http = FakeHttp()
    ig = Instagram({"targets": ["feed", "story"], "caption": "oi", "cover": {"thumb_offset_ms": 1000}},
                   account=ACC, session=http)
    res = ig.publish_video(str(f))
    assert [r["ok"] for r in res] == [True, True]
    assert res[0]["permalink"] == "https://ig/MC1"
    feed = http.calls[0][2]
    assert feed["media_type"] == "REELS" and feed["upload_type"] == "resumable"
    assert feed["thumb_offset"] == 1000 and "cover_url" not in feed
    upload = http.calls[1]
    assert upload[3]["file_size"] == "3" and upload[3]["Authorization"] == "OAuth T"
    story = [c for c in http.calls if c[1].endswith("/media")][1][2]
    assert story["media_type"] == "STORIES" and "caption" not in story


def test_targets_independentes(tmp_path):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"1")
    res = Instagram({"targets": ["feed", "story"]}, account=ACC,
                    session=FakeHttp(fail_target="REELS")).publish_video(str(f))
    assert [r["ok"] for r in res] == [False, True]


def test_publish_image_usa_r2_e_apaga(tmp_path):
    from PIL import Image
    p = tmp_path / "i.png"
    Image.new("RGBA", (90, 160)).save(p)
    r2 = MagicMock()
    r2.upload_file.return_value = "https://pub/ig/s/x.jpg"
    http = FakeHttp()
    res = Instagram({"targets": ["story"]}, account=ACC, session=http).publish_image(str(p), "s", r2=r2)
    assert res[0]["ok"]
    assert http.calls[0][2]["image_url"] == "https://pub/ig/s/x.jpg"
    key = r2.upload_file.call_args[0][1]
    assert key.startswith("ig/s/") and key.endswith(".jpg")
    r2.delete.assert_called_once_with(key)


def test_validar():
    ig = Instagram({"targets": ["feed", "x"], "caption": "#a " * 31}, account=ACC, session=FakeHttp())
    probs = ig.validar()
    assert any("targets" in p for p in probs) and any("hashtags" in p for p in probs)
    assert Instagram({"caption": "ok"}, account=ACC).validar() == []


def test_credentials_json(tmp_path, monkeypatch):
    monkeypatch.setattr(IA, "_BASE_DIR", str(tmp_path))
    (tmp_path / "c.json").write_text(json.dumps({"user_id": 1, "token": "abc"}))
    acc = load_account("c.json")
    assert (acc.user_id, acc.token) == ("1", "abc")
    assert load_account(str(tmp_path / "c.json")).token == "abc"
    (tmp_path / "sem_token.json").write_text(json.dumps({"user_id": "2"}))
    with pytest.raises(ValueError, match="token"):
        load_account(str(tmp_path / "sem_token.json"))
    with pytest.raises(ValueError, match="não encontradas"):
        load_account("lojao")


def test_sem_credentials_nao_usa_env(monkeypatch):
    monkeypatch.setenv("IG_USER_ID", "9")
    monkeypatch.setenv("IG_TOKEN", "t")
    with pytest.raises(ValueError, match="credentials_json ausente"):
        load_account(None)


def _pngs(tmp_path, n):
    from PIL import Image
    paths = []
    for i in range(n):
        p = tmp_path / f"{i}.png"
        Image.new("RGB", (90, 160)).save(p)
        paths.append(str(p))
    return paths


def test_carrossel_feed_e_stories(tmp_path):
    r2 = MagicMock()
    r2.upload_file.side_effect = lambda path, key: f"https://pub/{key}"
    http = FakeHttp()
    res = Instagram({"targets": ["feed", "story"], "caption": "c"}, account=ACC, session=http) \
        .publish_images(_pngs(tmp_path, 3), "s", r2=r2)
    assert [r["target"] for r in res] == ["feed", "story", "story", "story"]
    assert all(r["ok"] for r in res)
    media = [c[2] for c in http.calls if c[1].endswith("/media")]
    assert [m.get("is_carousel_item") for m in media[:3]] == ["true"] * 3
    assert media[3]["media_type"] == "CAROUSEL" and media[3]["children"] == "C1,C2,C3"
    assert media[3]["caption"] == "c"
    assert [m["media_type"] for m in media[4:]] == ["STORIES"] * 3
    assert r2.delete.call_count == 3


def test_carrossel_limite(tmp_path):
    from libs.Instagram import InstagramError
    with pytest.raises(InstagramError, match="máx 10"):
        Instagram({"targets": ["feed"]}, account=ACC, session=FakeHttp()) \
            .publish_images(["x"] * 11, "s", r2=MagicMock())
