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


# Amostras p/ medir as métricas verticais de uma linha, por papel:
#   CAP    → caixa alta sem acento: define o topo "normal" e a baseline.
#   ACCENT → acento alto: o quanto a tinta pode subir acima do CAP.
#   BELOW  → o quanto pode descer abaixo da baseline (cedilha e descendentes).
# Fontes display (ex.: BebasNeue) não têm todos os glifos; por isso cada papel é
# uma união de amostras — o que faltar simplesmente não contribui.
_REF_CAP = ("HXEM", "ABCO")
_REF_ACCENT = ("ÁÀÂÃÉÊÍÓÔÕÚ", "ÇÃO")
_REF_BELOW = ("ÇÃO", "çãgy", "Ppgy Qj")


def _ink_span(text: str, style: dict):
    """(top, bottom) da tinta de `text`, ou None se não houver tinta."""
    arr = render_text(text, style)
    rows = np.where(arr[:, :, 3].any(axis=1))[0]
    if len(rows) == 0:
        return None
    return int(rows[0]), int(rows[-1])


def _union_span(samples, style: dict):
    top = bottom = None
    for s in samples:
        span = _ink_span(s, style)
        if span is None:
            continue
        t, b = span
        top = t if top is None else min(top, t)
        bottom = b if bottom is None else max(bottom, b)
    return top, bottom


def line_vertical_metrics(style: dict) -> dict:
    """Métricas verticais de uma linha renderizada com `fixed_line_box`, todas
    medidas sobre textos de REFERÊNCIA fixos (nunca sobre o texto real).

    Retorna um dict com offsets DENTRO do array de `render_text`:

      cap_top    → topo da caixa alta (onde uma linha sem acento começa)
      baseline   → base da caixa alta (onde os glifos assentam)
      accent_rise→ quanto a tinta sobe acima de `cap_top` num acento
      below_drop → quanto a tinta desce abaixo de `baseline` (cedilha etc.)
      cap_height → baseline - cap_top

    Por que referência fixa: medir a tinta real fazia `É`/`À` reportarem um topo
    ~18px acima do de uma palavra sem acento, e como o layout posicionava por
    "topo da tinta", a linha acentuada saía deslocada.

    Por que separar `accent_rise` de `cap_height`: o avanço entre linhas deve
    seguir a caixa alta (o que o olho lê como altura da linha); o acento é folga
    que só precisa caber no gap, não somar ao passo de todas as linhas.
    """
    ref = dict(style)
    ref["fixed_line_box"] = True

    cap_top, cap_bottom = _union_span(_REF_CAP, ref)
    if cap_top is None:
        arr = render_text(_REF_CAP[0], ref)
        h = arr.shape[0]
        return {"cap_top": 0, "baseline": h, "cap_height": h,
                "accent_rise": 0, "below_drop": 0}

    acc_top, _ = _union_span(_REF_ACCENT, ref)
    _, below_bottom = _union_span(_REF_BELOW, ref)

    accent_rise = max(0, cap_top - acc_top) if acc_top is not None else 0
    below_drop = max(0, below_bottom - cap_bottom) if below_bottom is not None else 0

    return {
        "cap_top": cap_top,
        "baseline": cap_bottom,
        "cap_height": cap_bottom - cap_top + 1,
        "accent_rise": accent_rise,
        "below_drop": below_drop,
    }


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

         Campos opcionais do placement:
           relative_to: "safe" (default) | "screen" — base de medida de
             `region`/`height` e das âncoras. "screen" mede contra a TELA
             INTEIRA, que é o que layouts de tela dividida precisam: a metade
             livre é uma fração da tela, não da área segura, então percentuais
             medidos contra a área segura caem assimétricos dentro dela.
           height: altura da caixa (fração ou px). Sem ele a caixa usa a altura
             inteira da base, e o texto pode descer até a borda inferior.

      2. LEGADO — sem `placement`: usa `subtitle_position` (top/center/bottom) +
         paddings, replicando o comportamento histórico.
    """
    screen_w, screen_h = resolution
    pad_side = int(style.get("padding_side", 50))
    pad_top = int(style.get("padding_top", 100))
    pad_bot = int(style.get("padding_bottom", 850))

    # Paddings verticais que somam >= altura da tela colapsam a área segura para
    # 1px (`safe_area` faz max(1, ...)), e o bloco de texto passa a ser desenhado
    # a partir desse ponto — a 1ª linha nasce colada no fundo do espaço e as
    # seguintes descem para fora do quadro. Isso acontece quando paddings
    # calibrados para outra resolução (ex.: 960/960, de um canal 9:16 legado)
    # chegam num render onde não cabem. Nesse caso os paddings verticais não
    # descrevem uma faixa utilizável, então caem para os defaults de ~5%.
    if pad_top + pad_bot >= screen_h:
        fallback = int(screen_h * 0.05)
        print(
            f"⚠️  [Subtitle] padding_top({pad_top}) + padding_bottom({pad_bot}) "
            f">= altura da tela ({screen_h}); área da legenda seria nula. "
            f"Usando {fallback}px em cima/embaixo."
        )
        pad_top = pad_bot = fallback
    if pad_side * 2 >= screen_w:
        pad_side = int(screen_w * 0.05)

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

        # Base de medida: área segura (default) ou tela inteira. Espelha o
        # `relative_to` do LayoutEngine, para que legenda e visual possam ser
        # ancorados na MESMA referência num layout de tela dividida.
        rel = str(placement.get("relative_to", "safe")).lower()
        if rel == "screen":
            bx, by, bw, bh = 0, 0, screen_w, screen_h
        else:
            bx, by, bw, bh = sx, sy, sw, sh

        region = placement.get("region")
        box_w = LayoutEngine.calculate_dimension(region, bw) if region is not None else bw
        box_w = max(1, min(box_w, bw))

        req_h = placement.get("height")
        box_h = LayoutEngine.calculate_dimension(req_h, bh) if req_h is not None else bh
        box_h = max(1, min(box_h, bh))

        # X da faixa dentro da base, conforme anchor horizontal.
        if ax == "left":
            box_x = bx
        elif ax == "right":
            box_x = bx + bw - box_w
        elif ax == "center":
            box_x = bx + (bw - box_w) // 2
        elif isinstance(ax, str) and "%" in ax:
            box_x = bx + int(bw * (float(ax.strip("%")) / 100.0))
        else:
            box_x = bx + LayoutEngine.calculate_dimension(ax, bw)

        # Y da faixa: só entra em jogo quando `height` encolhe a caixa. Sem
        # `height` a caixa cobre a base inteira e `box_y` é o topo dela, como
        # antes — `anchor_y` segue alinhando o TEXTO dentro da caixa.
        anchor_y = ay if ay in ("top", "center", "bottom") else "center"
        if ay == "top":
            box_y = by
        elif ay == "bottom":
            box_y = by + bh - box_h
        elif isinstance(ay, str) and "%" in ay:
            box_y = by + int(bh * (float(ay.strip("%")) / 100.0))
        else:  # center
            box_y = by + (bh - box_h) // 2

        return {
            "x": int(box_x), "y": int(box_y), "width": int(box_w),
            "height": int(box_h), "anchor_y": anchor_y,
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
