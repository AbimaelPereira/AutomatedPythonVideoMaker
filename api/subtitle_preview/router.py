"""
Preview de legendas — compõe um FRAME inteiro na resolução real do vídeo
(9:16 ou 16:9), com o texto já posicionado (placement / paddings / área segura),
reusando a engine real do videomaker para máxima fidelidade.

Funções puras reusadas de `libs/Subtitle/SubtitleUtils` (carregado via importlib
para não disparar o `__init__` do pacote, que puxaria MoviePy):
  - render_text        → texto → array RGBA (mesmo stroke/shadow/fill do vídeo)
  - resolve_subtitle_box → resolve a caixa (placement novo OU paddings legado)
  - fit_font_size      → dimensiona a palavra/linha p/ caber na faixa (karaokê)
  - measure / load_font

A composição do frame aqui espelha a lógica de `ClassicSubtitle` e
`KaraokeSubtitle`, porém desenhando num único frame PIL em vez de gerar ImageClips.
O preview do karaokê é um FRAME ESTÁTICO do primeiro grupo (todas as palavras
visíveis), sem animação temporal.
"""

import io
import os
import sys
import importlib.util
from typing import List, Optional, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from middleware.auth import get_current_user
from auth.models import User

router = APIRouter()

_VIDEOMAKER_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "videomaker")
)
_FONTS_DIR = os.path.join(_VIDEOMAKER_DIR, "assets", "fonts")

_DEFAULT_FONT = "./assets/fonts/Montserrat/Montserrat-Black.ttf"


def _load_subtitle_utils():
    """Carrega SubtitleUtils.py isoladamente (sem o __init__ do pacote)."""
    if _VIDEOMAKER_DIR not in sys.path:
        sys.path.insert(0, _VIDEOMAKER_DIR)
    spec = importlib.util.spec_from_file_location(
        "subtitle_utils_standalone",
        os.path.join(_VIDEOMAKER_DIR, "libs", "Subtitle", "SubtitleUtils.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_utils = _load_subtitle_utils()

_PUNCTUATION = ",.?!;:\"()[]{}<>-—_"


# ----------------------------------------------------------------------
# Resoluções / paddings default por orientação (espelha _default_safe_paddings)
# ----------------------------------------------------------------------

_RESOLUTIONS = {
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
}


def _default_paddings(resolution: tuple) -> dict:
    w, h = resolution
    if w >= h:  # paisagem — ~5% simétrico
        return {"padding_side": int(w * 0.05), "padding_top": int(h * 0.05), "padding_bottom": int(h * 0.05)}
    return {"padding_side": 50, "padding_top": 100, "padding_bottom": 850}


def _resolve_font_path(font_path: Optional[str]) -> str:
    if not font_path:
        return ""
    if os.path.isabs(font_path):
        return font_path
    return os.path.normpath(os.path.join(_VIDEOMAKER_DIR, font_path))


# ----------------------------------------------------------------------
# Schemas
# ----------------------------------------------------------------------

class Placement(BaseModel):
    anchor: List[str] = ["center", "bottom"]   # [x, y]
    region: Optional[str] = None               # ex.: "30%" (faixa do texto)


class PaletteItem(BaseModel):
    fill: str = "#FFFFFF"
    stroke_enabled: bool = True
    stroke: str = "#000000"
    stroke_width: int = 3
    shadow_enabled: bool = False
    shadow_color: str = "#000000"
    shadow_opacity: float = 0.85
    shadow_blur: float = 6.0
    shadow_offset: List[int] = [4, 4]
    font_path: str = _DEFAULT_FONT
    # None = herda o uppercase global; True/False = sobrescreve só para este estilo.
    uppercase: Optional[bool] = None


class SubtitlePreviewRequest(BaseModel):
    type: Literal["classic", "karaoke"] = "classic"
    text: str = "O segredo que ninguém te contou"
    output_ratio: Literal["9:16", "16:9"] = "9:16"
    uppercase: bool = True

    # Paddings (área segura). None → default por orientação.
    padding_side: Optional[int] = None
    padding_top: Optional[int] = None
    padding_bottom: Optional[int] = None

    # Posicionamento. Se use_placement=False, usa subtitle_position (legado).
    use_placement: bool = False
    placement: Placement = Placement()
    subtitle_position: Literal["top", "center", "bottom"] = "bottom"

    background_color: str = "#101418"

    # --- CLASSIC ---
    font_path: str = "./assets/fonts/Poppins/Poppins-Black.ttf"
    font_size: int = 70
    color: str = "white"
    stroke_enabled: bool = True
    stroke_color: str = "black"
    stroke_width: int = 3
    shadow_enabled: bool = False
    shadow_color: str = "black"
    shadow_opacity: float = 0.8
    blur_radius: float = 6.0
    shadow_offset: List[int] = [4, 4]

    # --- KARAOKE ---
    palette: List[PaletteItem] = [PaletteItem()]
    words_per_group: int = 4
    layout: Literal["one_per_line", "fill_line"] = "one_per_line"
    min_chars_per_line: Optional[int] = None
    line_fill_ratio: Optional[float] = None
    lines_per_group: int = 3
    max_font_size: int = 300
    min_font_size: int = 24
    line_gap_ratio: float = 0.12


# ----------------------------------------------------------------------
# Composição do frame
# ----------------------------------------------------------------------

def _clean_words(text: str) -> List[str]:
    """Limpa pontuação e devolve palavras CRUAS (a caixa é aplicada no render,
    podendo variar por item de paleta)."""
    trans = str.maketrans("", "", _PUNCTUATION)
    out = []
    for w in text.split():
        t = w.translate(trans).strip()
        if t:
            out.append(t)
    return out


def _box(req: SubtitlePreviewRequest, resolution: tuple) -> dict:
    pads = _default_paddings(resolution)
    style = {
        "placement": (
            {"anchor": req.placement.anchor, "region": req.placement.region}
            if req.use_placement else None
        ),
        "subtitle_position": req.subtitle_position,
        "has_visual_elements": False,
        "padding_side": req.padding_side if req.padding_side is not None else pads["padding_side"],
        "padding_top": req.padding_top if req.padding_top is not None else pads["padding_top"],
        "padding_bottom": req.padding_bottom if req.padding_bottom is not None else pads["padding_bottom"],
    }
    return _utils.resolve_subtitle_box(style, resolution)


def _paste(frame, arr, x, y):
    """Cola um array RGBA sobre o frame (PIL) com alpha."""
    from PIL import Image
    overlay = Image.fromarray(arr)
    frame.alpha_composite(overlay, (int(x), int(y)))


def _render_classic(frame, req: SubtitlePreviewRequest, box: dict):
    text = req.text.upper() if req.uppercase else req.text
    text = text.translate(str.maketrans("", "", _PUNCTUATION))
    eff_stroke = req.stroke_width * 2 if req.stroke_enabled else 0
    style = {
        "font_path": _resolve_font_path(req.font_path),
        "font_size": max(1, int(req.font_size)),
        "fill": req.color,
        "stroke_enabled": req.stroke_enabled,
        "stroke_color": req.stroke_color,
        "stroke_width": eff_stroke,
        "shadow_enabled": req.shadow_enabled,
        "shadow_color": req.shadow_color,
        "shadow_opacity": req.shadow_opacity,
        "blur_radius": req.blur_radius,
        "shadow_offset": tuple(req.shadow_offset),
    }
    arr = _utils.render_text(text or " ", style)
    ch, cw = arr.shape[0], arr.shape[1]
    x = box["x"] + max(0, (box["width"] - cw) // 2)
    anchor_y = box.get("anchor_y", "center")
    if anchor_y == "top":
        y = box["y"]
    elif anchor_y == "bottom":
        y = box["y"] + max(0, box["height"] - ch)
    else:
        y = box["y"] + max(0, (box["height"] - ch) // 2)
    _paste(frame, arr, x, y)


def _palette_style(item: PaletteItem, font_size: int) -> dict:
    sw = int(item.stroke_width)
    eff = sw * 2 if (item.stroke_enabled and sw > 0) else 0
    return {
        "font_path": _resolve_font_path(item.font_path),
        "font_size": font_size,
        "fill": item.fill,
        "stroke_enabled": eff > 0,
        "stroke_color": item.stroke,
        "stroke_width": eff,
        "shadow_enabled": item.shadow_enabled,
        "shadow_color": item.shadow_color,
        "shadow_opacity": item.shadow_opacity,
        "blur_radius": item.shadow_blur if item.shadow_enabled else 0.0,
        "shadow_offset": tuple(item.shadow_offset),
        "fixed_line_box": True,
    }


def _cased_word(word: str, item: PaletteItem, global_upper: bool) -> str:
    """Aplica a caixa: item.uppercase sobrescreve o global se não for None."""
    up = item.uppercase if item.uppercase is not None else global_upper
    return word.upper() if up else word


def _line_mode(req: SubtitlePreviewRequest) -> bool:
    return req.min_chars_per_line is not None or req.line_fill_ratio is not None


def _first_group_lines(req: SubtitlePreviewRequest, words: List[str], box_w: int) -> List[List[str]]:
    """Retorna as linhas do PRIMEIRO grupo (o que aparece na tela ao limpar)."""
    if not _line_mode(req):
        wpg = max(1, int(req.words_per_group))
        chunk = words[:wpg]
        if req.layout == "fill_line":
            return [chunk]            # uma linha lógica; quebra por largura no render
        return [[w] for w in chunk]   # one_per_line

    # Modo LINHAS: agrupa palavras em linhas e pega lines_per_group.
    ref = req.palette[0] if req.palette else PaletteItem()
    ref_font = _resolve_font_path(ref.font_path)

    def tw(t: str) -> int:
        f = _utils.load_font(ref_font, 100)
        w, _, _, _ = _utils.measure(t, f, 0)
        return w

    target = int(box_w * float(req.line_fill_ratio)) if req.line_fill_ratio is not None else None
    min_chars = req.min_chars_per_line
    lines, cur = [], []
    for w in words:
        chars_ok = (min_chars is None) or (sum(len(x) for x in cur) >= int(min_chars))
        over = False
        if target is not None and cur:
            over = tw(" ".join(cur + [w])) > target
        close = cur and chars_ok and (over if target is not None else True)
        if close:
            lines.append(cur); cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(cur)
    if len(lines) > 1 and min_chars is not None and sum(len(x) for x in lines[-1]) < int(min_chars):
        lines[-2].extend(lines[-1]); lines.pop()
    lpg = max(1, int(req.lines_per_group))
    return lines[:lpg]


def _render_karaoke(frame, req: SubtitlePreviewRequest, box: dict):
    words = _clean_words(req.text)
    if not words:
        return
    safe_w = box["width"]
    palette = req.palette or [PaletteItem()]
    line_mode = _line_mode(req)
    lines = _first_group_lines(req, words, safe_w)

    # Renderiza cada linha → lista de arrays (um por palavra).
    rendered = []  # [(arrays:[np], )]
    for li, line in enumerate(lines):
        if line_mode:
            item = palette[li % len(palette)]
            font_path = _resolve_font_path(item.font_path)
            sw = int(item.stroke_width); eff = sw * 2 if (item.stroke_enabled and sw > 0) else 0
            cased = [_cased_word(w, item, req.uppercase) for w in line]
            joined = " ".join(cased)
            fs = _utils.fit_font_size(joined, font_path, max_width=safe_w, stroke_width=eff,
                                      max_size=int(req.max_font_size), min_size=int(req.min_font_size))
            style = _palette_style(item, fs); style["stroke_width"] = eff
            arrs = [_utils.render_text(w, style) for w in cased]
        else:
            arrs = []
            for i, w in enumerate(line):
                item = palette[i % len(palette)]
                font_path = _resolve_font_path(item.font_path)
                sw = int(item.stroke_width); eff = sw * 2 if (item.stroke_enabled and sw > 0) else 0
                cw = _cased_word(w, item, req.uppercase)
                fs = _utils.fit_font_size(cw, font_path, max_width=safe_w, stroke_width=eff,
                                          max_size=int(req.max_font_size), min_size=int(req.min_font_size))
                style = _palette_style(item, fs); style["stroke_width"] = eff
                style["fixed_line_box"] = False
                arrs.append(_utils.render_text(cw, style))
        rendered.append(arrs)

    # fill_line (modo legado): quebra a linha lógica em linhas visuais por largura.
    if not line_mode and req.layout == "fill_line":
        visual = []
        for arrs in rendered:
            cur, cur_w = [], 0
            for a in arrs:
                w = a.shape[1]
                if cur and cur_w + w > safe_w:
                    visual.append(cur); cur, cur_w = [], 0
                cur.append(a); cur_w += w
            if cur:
                visual.append(cur)
        rendered = visual

    # Layout vertical: altura por tinta, gap, alinhamento na caixa.
    def ink_bounds(arrs):
        import numpy as np
        top = bot = None
        for a in arrs:
            rows = np.where(a[:, :, 3].any(axis=1))[0] if a.shape[2] >= 4 else np.where(a.any(axis=(1, 2)))[0]
            if len(rows) == 0:
                continue
            t, b = int(rows[0]), int(rows[-1])
            top = t if top is None else min(top, t)
            bot = b if bot is None else max(bot, b)
        if top is None:
            h = max((a.shape[0] for a in arrs), default=1)
            return 0, h
        return top, (bot - top + 1)

    bounds = [ink_bounds(a) for a in rendered]
    vis_h = [h for (_, h) in bounds]
    gap = int(max(vis_h) * float(req.line_gap_ratio)) if vis_h else 0
    total_h = sum(vis_h) + gap * (len(rendered) - 1)

    anchor_y = box.get("anchor_y", "center")
    if anchor_y == "top":
        block_top = box["y"]
    elif anchor_y == "bottom":
        block_top = box["y"] + max(0, box["height"] - total_h)
    else:
        block_top = box["y"] + max(0, (box["height"] - total_h) // 2)

    y = block_top
    for arrs, (ink_top, vh) in zip(rendered, bounds):
        line_w = sum(a.shape[1] for a in arrs)
        x = box["x"] + max(0, (safe_w - line_w) // 2)
        for a in arrs:
            _paste(frame, a, x, y - ink_top)
            x += a.shape[1]
        y += vh + gap


# ----------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------

@router.post("")
def preview_subtitle(
    body: SubtitlePreviewRequest,
    current_user: User = Depends(get_current_user),
):
    from PIL import Image, ImageColor

    resolution = _RESOLUTIONS[body.output_ratio]
    try:
        bg = ImageColor.getrgb(body.background_color)
    except Exception:
        bg = (16, 20, 24)
    frame = Image.new("RGBA", resolution, bg + (255,))

    try:
        box = _box(body, resolution)
        if body.type == "karaoke":
            _render_karaoke(frame, body, box)
        else:
            _render_classic(frame, body, box)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao renderizar legenda: {e}")

    buf = io.BytesIO()
    frame.convert("RGB").save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


@router.get("/fonts")
def list_fonts(current_user: User = Depends(get_current_user)):
    fonts = []
    if os.path.isdir(_FONTS_DIR):
        for root, _dirs, files in os.walk(_FONTS_DIR):
            for f in files:
                if f.lower().endswith(".ttf"):
                    abs_path = os.path.join(root, f)
                    rel = os.path.relpath(abs_path, _VIDEOMAKER_DIR)
                    family = os.path.basename(os.path.dirname(abs_path))
                    fonts.append({
                        "path": "./" + rel.replace(os.sep, "/"),
                        "label": os.path.splitext(f)[0],
                        "family": family,
                    })
    fonts.sort(key=lambda x: (x["family"], x["label"]))
    return fonts


@router.get("/defaults")
def get_defaults(current_user: User = Depends(get_current_user)):
    """Resoluções e paddings default por orientação (para o front pré-preencher)."""
    return {
        ratio: {"resolution": list(res), "paddings": _default_paddings(res)}
        for ratio, res in _RESOLUTIONS.items()
    }
