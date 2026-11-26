"""Elementos `html` e `icon`: renderizados para PNG (Chromium headless) no prepare.

O PrepareEngine gera o PNG em `{slug}/assets/render/` e reescreve o elemento
como `type: "image"` — o resto do pipeline (layout, motion, ffmpeg, preview)
não conhece estes tipos.

    {"type": "html", "template": "quote_card",          # templates/html/<nome>.html (Jinja2)
                                                         # ou caminho: "templates/canal_x/card.html"
                                                         # (abs, ~ ou relativo a videomaker/; caminhos
                                                         # relativos DENTRO do html partem da pasta dele)
     "params": {"texto": "...", "autor": "..."},
     "width": 900,                                       # largura da página (px)
     "transparent": true, "padding": 0, "scale": 1,
     "placement": {...}, "motion": {...}}

    {"type": "html", "html": "<div class='x'>{{ t }}</div>", "css": ".x{...}", "params": {"t": "oi"}}

    {"type": "icon", "name": "noto:clown-face",           # prefixo:nome do Iconify
     "size": 600, "color": "#ff2a2a",                    # color só em ícones monocromáticos
     "glow": "#ff0000", "style": "transform: rotate(-8deg)"}

Sem `placement.width` o PNG entra no tamanho nativo (`width`/`size`).
"""
import hashlib
import json
import os
import threading

TEMPLATES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "templates", "html"))
_RENDER_VERSION = "1"
_RENDER_KEYS = ("type", "template", "html", "css", "params", "width", "height",
                "transparent", "background", "padding", "scale",
                "name", "size", "color", "glow", "style", "animated", "sync")
_lock = threading.Lock()
# file:// → file:// (fontes e imagens locais referenciadas pelo HTML).
CHROME_ARGS = ["--allow-file-access-from-files"]

# Leva animações CSS/WAAPI e `window.onFrame` ao estado final (no-op em html estático).
_FINISH_JS = """async () => {
  for (const a of document.getAnimations()) {
    try { a.pause(); const t = a.effect.getComputedTiming();
          a.currentTime = isFinite(t.endTime) ? t.endTime : (t.delay || 0) + 600000; } catch (e) {}
  }
  if (typeof window.onFrame === 'function') { try { await window.onFrame(window.DURATION || 600); } catch (e) {} }
  await new Promise(r => requestAnimationFrame(() => r()));
}"""


def template_path(name: str) -> str:
    """`template` = nome (templates/html/<nome>.html) OU caminho de arquivo.

    Caminho: tem `/` ou termina em `.html`; absoluto, `~` ou relativo a videomaker/.
    """
    if "/" in name or name.endswith((".html", ".htm")):
        path = os.path.expanduser(name)
        if not os.path.isabs(path):
            path = os.path.join(os.path.dirname(TEMPLATES_DIR.rstrip("/")), "..", path)
        return os.path.abspath(path)
    return os.path.join(TEMPLATES_DIR, f"{name}.html")


def _template_text(name: str) -> str:
    path = template_path(name)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"template html '{name}' não encontrado ({path})")
    with open(path, encoding="utf-8") as f:
        return f.read()


def render_key(el: dict) -> str:
    spec = {k: el.get(k) for k in _RENDER_KEYS if k in el}
    if el.get("type") == "html" and el.get("template"):
        spec["_tpl"] = _template_text(el["template"])
    raw = json.dumps(spec, sort_keys=True, ensure_ascii=False) + _RENDER_VERSION
    return "rn_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# ---------- montagem do HTML ----------

def _page(body: str, css: str, el: dict) -> str:
    transparent = el.get("transparent", True)
    bg = "transparent" if transparent else el.get("background", "#000")
    pad = int(el.get("padding", 0))
    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>
html,body{{margin:0;padding:0;background:{bg};}}
#__root{{display:inline-block;padding:{pad}px;box-sizing:content-box;}}
{css}
</style></head><body><div id="__root">{body}</div></body></html>"""


def _html_document(el: dict) -> str:
    from jinja2 import Environment
    env = Environment(autoescape=True)  # variável ausente = vazio
    params = el.get("params") or {}
    if el.get("template"):
        # Template completo: o próprio arquivo traz <style>; ajustamos só o fundo.
        doc = env.from_string(_template_text(el["template"])).render(**params)
        if el.get("transparent", True) is False:
            bg = el.get("background", "#000")
            doc = doc.replace("</head>", f"<style>html,body{{background:{bg} !important}}</style></head>", 1)
        if "id=\"__root\"" not in doc:
            pad = int(el.get("padding", 0))
            doc = doc.replace("<body>", f'<body><div id="__root" style="display:inline-block;padding:{pad}px">', 1)
            doc = doc.replace("</body>", "</div></body>", 1)
        return doc
    if not el.get("html"):
        raise ValueError("elemento html precisa de 'template' ou 'html'")
    body = env.from_string(el["html"]).render(**params)
    return _page(body, el.get("css", ""), el)


def _fetch_icon_svg(name: str, color: str | None) -> str:
    import requests
    if ":" not in name:
        raise ValueError(f"icon '{name}': use 'prefixo:nome' do Iconify (ex: noto:clown-face)")
    prefix, icon = name.split(":", 1)
    params = {"color": color} if color else {}
    r = requests.get(f"https://api.iconify.design/{prefix}/{icon}.svg", params=params, timeout=20)
    if r.status_code != 200 or "<svg" not in r.text:
        raise RuntimeError(f"icon '{name}' não encontrado no Iconify ({r.status_code})")
    return r.text


def _icon_document(el: dict) -> str:
    size = int(el.get("size", 512))
    svg = _fetch_icon_svg(el["name"], el.get("color"))
    glow = el.get("glow")
    filt = (f"filter:drop-shadow(0 0 {max(2, size // 50)}px {glow}) drop-shadow(0 0 {max(4, size // 18)}px {glow});"
            if glow else "")
    pad = int(el.get("padding", size // 6 if glow else 0))
    css = f"#__icon svg{{width:{size}px;height:{size}px;display:block;{filt}{el.get('style', '')}}}"
    return _page(f'<div id="__icon">{svg}</div>', css, dict(el, padding=pad))


# ---------- render ----------

VIDEOMAKER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _doc_for(el: dict) -> tuple:
    """(doc, width, height, transparent, scale, base_dir) de um elemento `html`/`icon`.

    Sem `template`, caminhos relativos no HTML (fontes, imagens) partem de
    `videomaker/` — ex.: `url('assets/fonts/Montserrat/Montserrat-Black.ttf')`.
    """
    t = el.get("type")
    base_dir = VIDEOMAKER_DIR
    if t == "html":
        doc, width = _html_document(el), int(el.get("width", 1080))
        if el.get("animated"):
            # Pose final (preview): âncoras em 0 e relógio no fim (ver _FINISH_JS).
            from libs.Graphics.animated import _inject
            doc = _inject(doc, {k: 0.0 for k in (el.get("sync") or {})}, 10.0)
        if el.get("template"):
            base_dir = os.path.dirname(template_path(el["template"]))
    elif t == "icon":
        doc = _icon_document(el)
        width = int(el.get("size", 512)) * 2 + 400
    else:
        raise ValueError(f"tipo não renderizável: {t}")
    height = int(el.get("height") or 400)
    return doc, width, height, el.get("transparent", True), float(el.get("scale", 1)), base_dir


def render_element(el: dict, **_) -> bytes:
    """PNG (bytes) de um elemento `html` ou `icon`."""
    out = render_many([el])[0]
    if isinstance(out, Exception):
        raise out
    return out


def render_many(elements: list) -> list:
    """PNG (bytes) de vários elementos num ÚNICO Chromium (bem mais rápido que um
    navegador por elemento). Erro de um elemento vira a Exception na sua posição.

    A página é aberta de um arquivo temporário (não `set_content`), para
    `file://` (fontes/imagens locais) funcionar.
    """
    import tempfile
    from pathlib import Path
    from playwright.sync_api import sync_playwright

    results = []
    with _lock, sync_playwright() as p:
        browser = p.chromium.launch(args=CHROME_ARGS)
        try:
            for el in elements:
                try:
                    doc, width, height, transparent, scale, base_dir = _doc_for(el)
                    base = Path(base_dir).as_uri() + "/"
                    doc = doc.replace("<head>", f'<head><base href="{base}">', 1) if "<head>" in doc \
                        else f'<base href="{base}">' + doc
                    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False,
                                                     encoding="utf-8") as f:
                        f.write(doc)
                    page = browser.new_page(viewport={"width": width, "height": height},
                                            device_scale_factor=scale)
                    try:
                        page.goto(Path(f.name).as_uri(), wait_until="load")
                        page.evaluate("document.fonts.ready")
                        page.evaluate(_FINISH_JS)
                        target = page.locator("#__root")
                        results.append(target.first.screenshot(omit_background=transparent)
                                       if target.count()
                                       else page.screenshot(full_page=True, omit_background=transparent))
                    finally:
                        page.close()
                        os.unlink(f.name)
                except Exception as e:  # noqa: BLE001 — devolvido na posição do elemento
                    results.append(e)
        finally:
            browser.close()
    return results
