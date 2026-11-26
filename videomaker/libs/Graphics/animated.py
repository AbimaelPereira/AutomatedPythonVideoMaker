"""`html` com `"animated": true`: vídeo sincronizado com a narração.

Roda no worker da cena DEPOIS do TTS (os tempos das palavras só existem aí).
O elemento é reescrito como `type: "video"` — o resto do pipeline só vê um vídeo.

    {"type": "html", "animated": true, "template": "templates/html/x/barra.html",
     "params": {...}, "width": 1080, "fps": 30,
     "transparent": false,          # opaco (ex: cena inteira em HTML) → H.264, MUITO mais rápido
     "sync": {"cresce": {"word": "oitenta"}, "fim": "end", "meio": "50%", "t0": 1.2}}

Na página:
  - CSS: `--cresce: 2.340s` em `:root` → `animation-delay: var(--cresce)`
  - JS:  `window.SYNC = {cresce: 2.34, ...}`, `window.DURATION` (s)
  - JS:  `window.WORDS = [{w, s, e}, ...]` — palavras da narração com tempo (legenda no HTML)
  - JS opcional: `window.onFrame = t => {...}` é chamado a cada quadro (t em s)
    — use para GSAP (`gsap.globalTimeline.seek(t)`), canvas, contadores, legenda etc.

O relógio é virtual: animações CSS/WAAPI ficam pausadas e são posicionadas em
`t` a cada quadro. Por isso os quadros são independentes e a captura é dividida
entre vários Chromium em paralelo (`HTML_ANIM_WORKERS`, default 4).

Velocidade (1080×1920): opaco ≈ 0,12 s/quadro (JPEG via CDP); transparente ≈ 0,6 s/quadro
(PNG com alfa). Prefira uma camada opaca de tela cheia a várias camadas transparentes.
"""
import base64
import hashlib
import json
import math
import os
import subprocess
import tempfile
import threading
from pathlib import Path

from libs.Graphics import CHROME_ARGS, _html_document, _template_text, template_path

_VERSION = "2"

_CLOCK_JS = """
window.__setTime = async (t) => {
  for (const a of document.getAnimations()) { a.pause(); a.currentTime = t * 1000; }
  if (typeof window.onFrame === 'function') { await window.onFrame(t); }
  await new Promise(r => requestAnimationFrame(() => r()));
};
"""


def is_animated(el: dict) -> bool:
    return isinstance(el, dict) and el.get("type") == "html" and bool(el.get("animated"))


def resolve_sync(sync: dict, words, narration_text: str, duration: float) -> dict:
    """`{"nome": âncora}` → `{"nome": segundos}` (mesmas âncoras do `motion`)."""
    from libs.Motion.anchors import AnchorResolver
    resolver = AnchorResolver(words=words, narration_text=narration_text,
                              scene_duration=duration, on_missing="proportional")
    out = {}
    for name, spec in (sync or {}).items():
        t = resolver.resolve(spec, path=f"sync.{name}")
        if t is None:
            print(f"[HTML animado] ⚠️ âncora '{name}' ({spec}) não encontrada; usando 0s")
            t = 0.0
        out[name] = round(float(t), 3)
    return out


def _words_js(words) -> list:
    return [{"w": w.get("word", ""), "s": round(float(w.get("start", 0)), 3),
             "e": round(float(w.get("end", 0)), 3)} for w in (words or [])]


def _inject(doc: str, sync: dict, duration: float, words: list | None = None) -> str:
    css_vars = ";".join(f"--{k}:{v}s" for k, v in sync.items())
    head = (f"<style>:root{{{css_vars};--duration:{duration}s}}</style>"
            f"<script>window.SYNC={json.dumps(sync)};window.DURATION={duration};"
            f"window.WORDS={json.dumps(words or [], ensure_ascii=False)};</script>")
    if "<head>" in doc:
        return doc.replace("<head>", "<head>" + head, 1)
    return head + doc


def _cache_key(el: dict, sync: dict, duration: float, fps: int, words: list) -> str:
    spec = {k: el.get(k) for k in ("template", "html", "css", "params", "width", "height",
                                    "scale", "transparent", "background", "padding")}
    if el.get("template"):
        spec["_tpl"] = _template_text(el["template"])
    raw = json.dumps([spec, sync, round(duration, 3), fps, words, _VERSION],
                     sort_keys=True, ensure_ascii=False)
    return "anim_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _capture(uri: str, *, width: int, height: int, scale: float, duration: float, fps: int,
             frames: range, transparent: bool, out: dict) -> None:
    """Um Chromium capturando `frames` (índices) para `out[i] = bytes`."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(args=CHROME_ARGS)
        try:
            page = browser.new_page(viewport={"width": width, "height": height},
                                    device_scale_factor=scale)
            page.add_init_script(_CLOCK_JS)
            page.goto(uri, wait_until="networkidle")
            page.evaluate("document.fonts.ready")

            # Caixa fixa = união do #__root no início e no fim (o conteúdo pode crescer).
            # Determinística: todos os workers chegam na mesma caixa.
            def root_box():
                return page.evaluate("""() => { const e = document.getElementById('__root') || document.body;
                    const r = e.getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; }""")
            page.evaluate("t => window.__setTime(t)", 0.0)
            b0 = root_box()
            page.evaluate("t => window.__setTime(t)", duration)
            b1 = root_box()
            x0, y0 = min(b0[0], b1[0]), min(b0[1], b1[1])
            w = int((max(b0[0] + b0[2], b1[0] + b1[2]) - x0) // 2 * 2) or 2   # yuv exige par
            h = int((max(b0[1] + b0[3], b1[1] + b1[3]) - y0) // 2 * 2) or 2
            clip = {"x": x0, "y": y0, "width": w, "height": h}
            cdp = None if transparent else page.context.new_cdp_session(page)

            for i in frames:
                page.evaluate("t => window.__setTime(t)", i / fps)
                if transparent:
                    out[i] = page.screenshot(clip=clip, omit_background=True)
                else:
                    r = cdp.send("Page.captureScreenshot", {
                        "format": "jpeg", "quality": 90, "optimizeForSpeed": True,
                        "clip": {**clip, "scale": 1}})
                    out[i] = base64.b64decode(r["data"])
        finally:
            browser.close()


def render_animated(el: dict, *, sync: dict, duration: float, out_path: str,
                    words: list | None = None) -> str:
    """Grava `out_path` (.mov PNG+alfa ou .mp4 H.264) com a animação de 0 a `duration`."""
    fps = int(el.get("fps", 30))
    width = int(el.get("width", 1080))
    height = int(el.get("height") or 1920)
    transparent = el.get("transparent", True) is not False
    doc = _inject(_html_document(el), sync, duration, words)
    n_frames = max(1, int(round(duration * fps)))

    if el.get("template"):
        base = Path(os.path.dirname(template_path(el["template"]))).as_uri() + "/"
        doc = doc.replace("<head>", f'<head><base href="{base}">', 1) if "<head>" in doc \
            else f'<base href="{base}">' + doc

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp_out = out_path + ".tmp" + os.path.splitext(out_path)[1]
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(doc)
    uri = Path(f.name).as_uri()

    n_workers = max(1, min(int(os.getenv("HTML_ANIM_WORKERS", "4")), math.ceil(n_frames / 24)))
    chunk = math.ceil(n_frames / n_workers)
    frames, errors = {}, []

    def run(r):
        try:
            _capture(uri, width=width, height=height, scale=float(el.get("scale", 1)),
                     duration=duration, fps=fps, frames=r, transparent=transparent, out=frames)
        except Exception as e:  # noqa: BLE001 — repassado depois do join
            errors.append(e)

    try:
        threads = [threading.Thread(target=run, args=(range(k * chunk, min(n_frames, (k + 1) * chunk)),))
                   for k in range(n_workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        os.unlink(f.name)
    if errors:
        raise errors[0]

    if transparent:
        enc_in, enc_out = ["-c:v", "png"], ["-c:v", "png", "-pix_fmt", "rgba"]
    else:
        enc_in = ["-c:v", "mjpeg"]
        enc_out = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p"]
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps),
         *enc_in, "-i", "-", *enc_out, tmp_out], stdin=subprocess.PIPE)
    try:
        for i in range(n_frames):
            ff.stdin.write(frames[i])
    finally:
        ff.stdin.close()
        if ff.wait() != 0:
            raise RuntimeError("ffmpeg falhou ao montar o vídeo do html animado")
    os.replace(tmp_out, out_path)
    return out_path


def render_scene_animated(scene: dict, *, scene_dir: str, duration: float,
                          subtitle_file: str | None, assets_dir: str | None = None) -> None:
    """Reescreve (in-place) os `html` animados da cena como `video`. Nunca levanta."""
    elements = scene.get("visual_elements") or []
    if not any(is_animated(e) for e in elements):
        return
    import time
    from libs.Motion import narration_text_of, words_from_srt
    words = words_from_srt(subtitle_file)
    words_js = _words_js(words)
    text = narration_text_of(scene)
    cache_dir = os.path.join(assets_dir, "render") if assets_dir else os.path.join(scene_dir, "anim")
    for i, el in enumerate(elements):
        if not is_animated(el):
            continue
        try:
            sync = resolve_sync(el.get("sync"), words, text, float(duration))
            fps = int(el.get("fps", 30))
            opaque = el.get("transparent", True) is False
            out = os.path.join(cache_dir, _cache_key(el, sync, float(duration), fps, words_js)
                               + (".mp4" if opaque else ".mov"))
            if not (os.path.isfile(out) and os.path.getsize(out) > 0):
                t0 = time.monotonic()
                render_animated(el, sync=sync, duration=float(duration), out_path=out, words=words_js)
                print(f"[HTML animado] elemento {i}: {duration:.2f}s de vídeo em "
                      f"{time.monotonic() - t0:.1f}s ({'opaco' if opaque else 'alfa'})")
            el["_rendered_from"] = "html_animated"
            el["type"] = "video"
            el["source"] = out
            el["_native_size"] = True
            el["_alpha"] = not opaque
        except Exception as e:
            print(f"[HTML animado] ❌ elemento {i}: {type(e).__name__}: {e}")
