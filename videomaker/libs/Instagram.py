"""Publicação no Instagram via Graph API (Facebook Login).

Vídeo → upload resumable direto (rupload). Imagem → JPEG → R2 → image_url → apaga do R2.
Targets independentes: "feed" (REELS / IMAGE) e "story" (STORIES).
"""
import os
import re
import subprocess
import tempfile
import time

import requests

from libs.InstagramAccount import GRAPH, InstagramAccount, load_account

VALID_TARGETS = ("feed", "story")
CAPTION_MAX = 2200
HASHTAGS_MAX = 30
IMAGE_MAX_BYTES = 8 * 1024 * 1024
REEL_MIN_S, REEL_MAX_S = 3, 15 * 60
STORY_VIDEO_MAX_S = 60
CAROUSEL_MAX = 10


def _probe(path: str) -> tuple:
    """(duração_s, largura, altura) via ffprobe; None nos campos que falharem."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height:format=duration", "-of", "default=nw=1", path],
            capture_output=True, text=True, timeout=30).stdout
        vals = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
        return (float(vals["duration"]) if vals.get("duration") not in (None, "N/A") else None,
                int(vals["width"]) if vals.get("width") else None,
                int(vals["height"]) if vals.get("height") else None)
    except Exception:
        return None, None, None


def _is_9x16(w, h) -> bool:
    return bool(w and h) and abs(w / h - 9 / 16) < 0.01


def _is_feed_image_ratio(w, h) -> bool:
    """Imagem de feed: 9:16 ou 4:5..1.91:1 (1:1 e 4:5 inclusos)."""
    return _is_9x16(w, h) or (bool(w and h) and 0.795 <= w / h <= 1.92)


class InstagramError(RuntimeError):
    pass


class Instagram:
    def __init__(self, params: dict, account: InstagramAccount | None = None, session=None):
        self.params = params or {}
        self.account = account or load_account(self.params.get("credentials_json"))
        self.http = session or requests.Session()
        self.poll_interval = float(self.params.get("poll_interval", 5))
        self.timeout = float(self.params.get("timeout", 600))

    # ------------------------------------------------------------------
    # validação
    # ------------------------------------------------------------------
    def targets(self) -> list:
        t = self.params.get("targets") or ["feed"]
        return [t] if isinstance(t, str) else list(t)

    def validar(self, path: str | None = None, kind: str = "video") -> list:
        """Lista de problemas (vazia = ok). Avisos (não bloqueiam) são impressos."""
        problemas = []
        targets = self.targets()
        invalidos = [t for t in targets if t not in VALID_TARGETS]
        if invalidos or not targets:
            problemas.append(f"targets inválidos: {invalidos or targets} (use {list(VALID_TARGETS)})")

        caption = self.params.get("caption") or ""
        if len(caption) > CAPTION_MAX:
            problemas.append(f"caption com {len(caption)} chars (máx {CAPTION_MAX})")
        n_tags = len(re.findall(r"#\w+", caption))
        if n_tags > HASHTAGS_MAX:
            problemas.append(f"caption com {n_tags} hashtags (máx {HASHTAGS_MAX})")

        if path is None:
            return problemas
        if not os.path.exists(path):
            return problemas + [f"arquivo não encontrado: {path}"]

        if kind == "image":
            from PIL import Image
            with Image.open(path) as im:
                w, h = im.size
            if not _is_feed_image_ratio(w, h):
                print(f"[Instagram] Aviso: imagem {w}x{h} fora de 9:16 / 4:5–1.91:1")
            return problemas

        dur, w, h = _probe(path)
        if not _is_9x16(w, h):
            print(f"[Instagram] Aviso: vídeo {w}x{h} não é 9:16")
        if dur is not None:
            if "feed" in targets and not (REEL_MIN_S <= dur <= REEL_MAX_S):
                problemas.append(f"reel com {dur:.1f}s (permitido {REEL_MIN_S}s–{REEL_MAX_S // 60}min)")
            if "story" in targets and dur > STORY_VIDEO_MAX_S:
                print(f"[Instagram] Aviso: story de vídeo com {dur:.1f}s (> {STORY_VIDEO_MAX_S}s)")
        return problemas

    # ------------------------------------------------------------------
    # Graph API
    # ------------------------------------------------------------------
    def _check(self, r, what: str) -> dict:
        try:
            data = r.json()
        except ValueError:
            data = {}
        if not r.ok or "error" in data:
            raise InstagramError(f"{what}: HTTP {r.status_code} {data.get('error') or r.text}")
        return data

    def _create_container(self, **fields) -> dict:
        fields = {k: v for k, v in fields.items() if v is not None}
        fields["access_token"] = self.account.token
        r = self.http.post(f"{GRAPH}/{self.account.user_id}/media", data=fields, timeout=60)
        return self._check(r, "criar container")

    def _upload_resumable(self, uri: str, path: str) -> None:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            r = self.http.post(uri, data=f, timeout=max(300, size / 200_000), headers={
                "Authorization": f"OAuth {self.account.token}",
                "offset": "0",
                "file_size": str(size),
            })
        data = self._check(r, "upload resumable")
        if data.get("success") is False:
            raise InstagramError(f"upload resumable: {data}")

    def _wait(self, container_id: str) -> None:
        deadline = time.monotonic() + self.timeout
        while True:
            r = self.http.get(f"{GRAPH}/{container_id}", timeout=30, params={
                "fields": "status_code,status", "access_token": self.account.token})
            data = self._check(r, "status do container")
            status = data.get("status_code")
            if status in ("FINISHED", "PUBLISHED"):
                return
            if status in ("ERROR", "EXPIRED"):
                raise InstagramError(f"container {container_id}: {status} {data.get('status')}")
            if time.monotonic() >= deadline:
                raise InstagramError(f"container {container_id}: timeout ({self.timeout}s), último status {status}")
            time.sleep(self.poll_interval)

    def _publish(self, container_id: str) -> dict:
        r = self.http.post(f"{GRAPH}/{self.account.user_id}/media_publish", timeout=60, data={
            "creation_id": container_id, "access_token": self.account.token})
        media_id = self._check(r, "publicar")["id"]
        permalink = None
        try:
            r = self.http.get(f"{GRAPH}/{media_id}", timeout=30, params={
                "fields": "permalink", "access_token": self.account.token})
            permalink = self._check(r, "permalink").get("permalink")
        except Exception as e:
            print(f"[Instagram] Aviso: sem permalink para {media_id}: {e}")
        return {"id": media_id, "permalink": permalink}

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def _run_one(self, target: str, fn) -> list:
        try:
            res = fn(target)
            print(f"[Instagram] ✅ {target}: {res.get('permalink') or res['id']}")
            return [{"target": target, "ok": True, **res}]
        except Exception as e:
            print(f"[Instagram] ❌ {target}: {e}")
            return [{"target": target, "ok": False, "error": str(e)}]

    def _run_targets(self, fn) -> list:
        return [r for target in self.targets() for r in self._run_one(target, fn)]

    def publish_video(self, path: str) -> list:
        caption = self.params.get("caption")
        cover = self.params.get("cover") or {}

        def one(target):
            if target == "feed":
                c = self._create_container(
                    media_type="REELS", upload_type="resumable", caption=caption,
                    share_to_feed=str(bool(self.params.get("share_to_feed", True))).lower(),
                    cover_url=cover.get("url"), thumb_offset=cover.get("thumb_offset_ms"))
            else:
                c = self._create_container(media_type="STORIES", upload_type="resumable")
            self._upload_resumable(c["uri"], path)
            self._wait(c["id"])
            return self._publish(c["id"])

        return self._run_targets(one)

    def publish_image(self, path: str, slug: str = "post", r2=None) -> list:
        return self.publish_images([path], slug=slug, r2=r2)

    def publish_images(self, paths: list, slug: str = "post", r2=None) -> list:
        """feed: 1 imagem → IMAGE; 2–10 → CAROUSEL. story: um story por imagem, em ordem."""
        from PIL import Image
        from libs.R2 import R2, ig_key

        if not paths:
            raise InstagramError("nenhuma imagem para publicar")
        if "feed" in self.targets() and len(paths) > CAROUSEL_MAX:
            raise InstagramError(f"carrossel com {len(paths)} imagens (máx {CAROUSEL_MAX})")

        r2 = r2 or R2()
        caption = self.params.get("caption")
        stamp = int(time.time())
        tmps, keys, urls = [], [], []
        try:
            for i, path in enumerate(paths, 1):
                tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                tmp.close()
                tmps.append(tmp.name)
                with Image.open(path) as im:
                    im.convert("RGB").save(tmp.name, "JPEG", quality=95)
                if os.path.getsize(tmp.name) > IMAGE_MAX_BYTES:
                    raise InstagramError(f"{os.path.basename(path)}: JPEG > 8MB")
                key = ig_key(slug, f"{slug}_{stamp}_{i:02d}.jpg")
                keys.append(key)
                urls.append(r2.upload_file(tmp.name, key))

            def feed(_):
                if len(urls) == 1:
                    c = self._create_container(image_url=urls[0], caption=caption)
                else:
                    children = []
                    for url in urls:
                        child = self._create_container(image_url=url, is_carousel_item="true")
                        self._wait(child["id"])
                        children.append(child["id"])
                    c = self._create_container(media_type="CAROUSEL", caption=caption,
                                               children=",".join(children))
                self._wait(c["id"])
                return self._publish(c["id"])

            def story_for(url):
                def one(_):
                    c = self._create_container(image_url=url, media_type="STORIES")
                    self._wait(c["id"])
                    return self._publish(c["id"])
                return one

            results = []
            for target in self.targets():
                if target == "feed":
                    results += self._run_one("feed", feed)
                else:
                    for url in urls:
                        results += self._run_one("story", story_for(url))
            return results
        finally:
            for t in tmps:
                os.remove(t)
            for key in keys:
                try:
                    r2.delete(key)
                except Exception as e:
                    print(f"[Instagram] Aviso: falha ao apagar {key} do R2 (lifecycle limpa): {e}")
