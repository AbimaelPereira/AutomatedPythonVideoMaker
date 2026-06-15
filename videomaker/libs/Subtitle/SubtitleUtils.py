"""
Utilitários compartilhados de renderização de legendas.

Centraliza a renderização PIL pura (texto → array RGBA), medição, carregamento
de fontes, resolução de cores e parsing de SRT. Extraído do antigo `Subtitle.py`
para que todos os tipos de legenda (`ClassicSubtitle`, `KaraokeSubtitle`, ...)
reutilizem a mesma base sem duplicar código.

A renderização aqui opera sobre um "estilo" arbitrário (dict), em vez de ler
atributos de uma instância específica — assim a mesma função serve para a
legenda clássica (estilo único) e para o karaokê (um estilo por palavra).
"""

import os
import srt
import hashlib
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageColor, ImageFilter

from libs.LayoutEngine import LayoutEngine


# Pontuação removida do texto das legendas (idêntico ao comportamento anterior).
_PUNCTUATION = ",.?!;:\"()[]{}<>-—_"

# Cache de fontes por (path, size) — evita reabrir o TTF repetidamente.
_font_cache: dict = {}

# Cache de palavras renderizadas (texto + estilo) → numpy array RGBA.
_render_cache: dict = {}


def force_rgb(im):
    return np.dstack((im, im, im)) if im.ndim == 2 else im


# ----------------------------------------------------------------------
# FONTE
# ----------------------------------------------------------------------

def load_font(font_path: str, font_size: int) -> ImageFont.FreeTypeFont:
    """Carrega fonte TTF (com cache); faz fallback para fonte do sistema."""
    key = (font_path, int(font_size))
    cached = _font_cache.get(key)
    if cached is not None:
        return cached

    font = None
    if font_path and os.path.exists(font_path):
        try:
            font = ImageFont.truetype(font_path, font_size)
        except Exception as e:
            print(f"⚠️ Falha ao carregar fonte '{font_path}': {e}. Usando fonte padrão.")
    elif font_path:
        print(f"⚠️ Fonte não encontrada em '{font_path}'. Usando fonte padrão.")

    if font is None:
        for fallback in ("Arial.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"):
            try:
                font = ImageFont.truetype(fallback, font_size)
                break
            except Exception:
                continue

    if font is None:
        font = ImageFont.load_default()

    _font_cache[key] = font
    return font


# ----------------------------------------------------------------------
# COR
# ----------------------------------------------------------------------

def resolve_color(color_value) -> tuple:
    """Converte qualquer formato de cor para RGBA."""
    try:
        rgb = ImageColor.getrgb(color_value)
        if len(rgb) == 3:
            return rgb + (255,)
        return rgb
    except Exception:
        return (255, 255, 255, 255)


# ----------------------------------------------------------------------
# MEDIÇÃO
# ----------------------------------------------------------------------

def measure(text: str, font: ImageFont.FreeTypeFont, stroke_width: int) -> tuple:
    """
    Retorna (width, height, offset_x, offset_y) do bounding box do texto
    incluindo stroke. Usa textbbox (Pillow >= 8.0) com fallback para textsize.
    """
    dummy = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(dummy)
    try:
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        offset_x = -bbox[0]
        offset_y = -bbox[1]
    except AttributeError:
        w, h = draw.textsize(text, font=font)
        offset_x, offset_y = 0, 0
    return w, h, offset_x, offset_y


def fit_font_size(
    text: str,
    font_path: str,
    max_width: int,
    stroke_width: int = 0,
    max_size: int = 300,
    min_size: int = 20,
) -> int:
    """
    Acha o maior font_size cuja largura renderizada (incluindo stroke) caiba em
    `max_width`. Busca binária no intervalo [min_size, max_size].

    Usado pelo karaokê: cada palavra é dimensionada para preencher a largura
    disponível. A altura é ignorada de propósito (decisão de projeto).
    """
    if not text:
        return min_size

    lo, hi = min_size, max_size
    best = min_size
    while lo <= hi:
        mid = (lo + hi) // 2
        font = load_font(font_path, mid)
        w, _, _, _ = measure(text, font, stroke_width)
        if w <= max_width:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


# ----------------------------------------------------------------------
# RENDER DE TEXTO
# ----------------------------------------------------------------------

def _style_cache_key(text: str, style: dict) -> str:
    params = (
        text,
        style.get("font_path"),
        style.get("font_size"),
        style.get("fill"),
        style.get("stroke_enabled"),
        style.get("stroke_color"),
        style.get("stroke_width"),
        style.get("shadow_enabled"),
        style.get("shadow_color"),
        style.get("shadow_opacity"),
        style.get("blur_radius"),
        str(style.get("shadow_offset")),
        style.get("fixed_line_box"),
    )
    return hashlib.md5(str(params).encode()).hexdigest()


def render_text(text: str, style: dict) -> np.ndarray:
    """
    Renderiza uma string como imagem RGBA usando PIL puro, a partir de um dict
    de estilo. Equivalente visual a stroke + fill + sombra compostos.

    `style` aceita as chaves:
      font_path, font_size, fill,
      stroke_enabled, stroke_color, stroke_width   (stroke_width já é o efetivo),
      shadow_enabled, shadow_color, shadow_opacity, blur_radius, shadow_offset,
      fixed_line_box  (bool) → ver abaixo.

    `fixed_line_box`: quando True, a altura do array não é "cropada" ao glifo —
    usa a caixa da FONTE (ascent + descent), constante para um mesmo font/size.
    O texto é desenhado numa baseline fixa, de modo que palavras diferentes da
    MESMA linha (ex.: "a" e "todos") compartilhem a mesma baseline e a mesma
    altura. Sem isso, cada palavra fica cropada ao seu próprio glifo e palavras
    curtas "flutuam" desalinhadas ao serem empilhadas lado a lado.
    """
    cache_key = _style_cache_key(text, style)
    cached = _render_cache.get(cache_key)
    if cached is not None:
        return cached

    font = load_font(style["font_path"], style["font_size"])

    stroke_enabled = style.get("stroke_enabled", False)
    sw = int(style.get("stroke_width", 0)) if stroke_enabled else 0

    shadow_enabled = style.get("shadow_enabled", False)
    blur_radius = float(style.get("blur_radius", 0.0))
    shadow_dx, shadow_dy = style.get("shadow_offset", (0, 0)) if shadow_enabled else (0, 0)

    w, h, off_x, off_y = measure(text, font, sw)

    extra_x = abs(shadow_dx) + sw + 10
    extra_y = abs(shadow_dy) + sw + 10

    fixed_line_box = bool(style.get("fixed_line_box", False))
    if fixed_line_box:
        # Caixa de altura constante (métricas da fonte), baseline fixa.
        ascent, descent = font.getmetrics()
        box_h = ascent + descent + 2 * sw
        img_w = max(1, w + extra_x * 2)
        img_h = max(1, box_h + extra_y * 2)
        # Texto desenhado no topo da caixa (sem off_y por-glifo) → baseline
        # comum a todas as palavras do mesmo font/size.
        text_x = off_x + extra_x
        text_y = extra_y + sw
    else:
        img_w = max(1, w + extra_x * 2)
        img_h = max(1, h + extra_y * 2)
        text_x = off_x + extra_x
        text_y = off_y + extra_y

    # --- Sombra ---
    shadow_layer = None
    if shadow_enabled and blur_radius > 0:
        shadow_layer = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow_layer)
        shadow_rgba = resolve_color(style.get("shadow_color", "black"))
        shadow_rgba = shadow_rgba[:3] + (int(255 * float(style.get("shadow_opacity", 0.8))),)
        sd.text((text_x + shadow_dx, text_y + shadow_dy), text, font=font, fill=shadow_rgba)
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    # --- Stroke ---
    stroke_layer = None
    if stroke_enabled and sw > 0:
        stroke_layer = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
        stk = ImageDraw.Draw(stroke_layer)
        stroke_rgba = resolve_color(style.get("stroke_color", "black"))
        stk.text(
            (text_x, text_y), text, font=font,
            fill=stroke_rgba, stroke_width=sw, stroke_fill=stroke_rgba,
        )

    # --- Fill ---
    fill_layer = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    fl = ImageDraw.Draw(fill_layer)
    fl.text((text_x, text_y), text, font=font, fill=resolve_color(style.get("fill", "white")))

    # --- Composição ---
    result = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    if shadow_layer:
        result = Image.alpha_composite(result, shadow_layer)
    if stroke_layer:
        result = Image.alpha_composite(result, stroke_layer)
    result = Image.alpha_composite(result, fill_layer)

    arr = np.array(result)
    _render_cache[cache_key] = arr
    return arr


# ----------------------------------------------------------------------
# CAIXA DE LEGENDA (posicionamento)
# ----------------------------------------------------------------------

def resolve_subtitle_box(style: dict, resolution: tuple) -> dict:
    """Resolve a "caixa" onde o texto da legenda é centralizado.

    Retorna dict {x, y, width, height, anchor_y} onde:
      - x, y       → canto superior-esquerdo da caixa
      - width      → largura disponível p/ o texto (quebra/centralização)
      - height     → altura disponível da caixa
      - anchor_y   → "top" | "center" | "bottom": como alinhar o bloco de texto
                     verticalmente DENTRO da caixa

    Dois modos:
      1. NOVO — `style["placement"]` = {"anchor":[x,y], "region": "30%"}:
         a caixa é uma faixa de largura `region` (default = área segura inteira),
         ancorada via `anchor[0]`; o `anchor[1]` define anchor_y.
      2. LEGADO — sem `placement`: usa `subtitle_position` (top/center/bottom) +
         paddings, replicando o comportamento histórico.
    """
    screen_w, screen_h = resolution
    pad_side = int(style.get("padding_side", 50))
    pad_top = int(style.get("padding_top", 100))
    pad_bot = int(style.get("padding_bottom", 850))

    safe_rect = LayoutEngine.safe_area(
        (screen_w, screen_h),
        {"padding_side": pad_side, "padding_top": pad_top, "padding_bottom": pad_bot},
    )
    sx, sy, sw, sh = safe_rect

    placement = style.get("placement")
    if isinstance(placement, dict) and placement.get("anchor") is not None:
        anchor = placement["anchor"]
        if isinstance(anchor, str):
            ax, ay = anchor, "center"
        else:
            ax = anchor[0] if len(anchor) > 0 else "center"
            ay = anchor[1] if len(anchor) > 1 else "center"

        region = placement.get("region")
        box_w = LayoutEngine.calculate_dimension(region, sw) if region is not None else sw
        box_w = max(1, min(box_w, sw))

        # X da faixa dentro da área segura, conforme anchor horizontal.
        if ax == "left":
            box_x = sx
        elif ax == "right":
            box_x = sx + sw - box_w
        elif ax == "center":
            box_x = sx + (sw - box_w) // 2
        elif isinstance(ax, str) and "%" in ax:
            box_x = sx + int(sw * (float(ax.strip("%")) / 100.0))
        else:
            box_x = sx + LayoutEngine.calculate_dimension(ax, sw)

        anchor_y = ay if ay in ("top", "center", "bottom") else "center"
        return {
            "x": int(box_x), "y": int(sy), "width": int(box_w),
            "height": int(sh), "anchor_y": anchor_y,
        }

    # --- Modo legado (subtitle_position + paddings) ---
    pos = style.get("subtitle_position", "bottom")
    has_visual = style.get("has_visual_elements", False)
    box_height = pad_bot - 20  # mesma fórmula histórica do ClassicSubtitle

    if pos == "top":
        box_y = pad_top
    elif pos == "center":
        box_y = (screen_h - box_height) // 2
    elif has_visual:
        box_y = screen_h - pad_bot
    else:
        box_y = (screen_h - box_height) // 2

    return {
        "x": sx, "y": int(box_y), "width": sw,
        "height": int(box_height), "anchor_y": "center",
    }


# ----------------------------------------------------------------------
# SRT
# ----------------------------------------------------------------------

def parse_srt_words(path: str, uppercase: bool = True) -> list:
    """
    Lê o SRT (gerado palavra-a-palavra pelo NarrationEngine) e retorna uma lista
    de dicts {word, start, end} (tempos em segundos), já com uppercase e remoção
    de pontuação aplicados — idêntico ao tratamento do Subtitle clássico.
    """
    with open(path, "r", encoding="utf-8") as f:
        try:
            subtitles = list(srt.parse(f.read()))
        except Exception as e:
            print(f"❌ Erro ao ler SRT: {e}")
            return []

    words = []
    trans = str.maketrans("", "", _PUNCTUATION)
    for sub in subtitles:
        txt = sub.content.replace("\n", " ").strip()
        if uppercase:
            txt = txt.upper()
        txt = txt.translate(trans).strip()
        if not txt:
            continue
        words.append({
            "word":  txt,
            "start": sub.start.total_seconds(),
            "end":   sub.end.total_seconds(),
        })
    return words
