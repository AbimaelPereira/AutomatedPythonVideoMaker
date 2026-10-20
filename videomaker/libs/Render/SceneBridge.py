"""SceneBridge — prepara os dados de uma cena para o caminho ffmpeg.

Faz a ponte entre o mundo "JSON + engines existentes" e o
`FFmpegSceneRenderer`, que só sabe lidar com caminhos de arquivo e caixas em
pixels já resolvidos.

Reaproveita deliberadamente a lógica já existente e testada:
  - resolução de `remote_asset` → `MediaDownloader` (mesmo caminho do VisualClip)
  - posicionamento → `LayoutEngine.process_stack_layout` (idêntico ao MoviePy)
  - agrupamento/fit do karaokê → `KaraokeSubtitle` (só o RENDER muda p/ ASS)

Assim o resultado visual do caminho rápido acompanha o do caminho MoviePy sem
duplicar regra de negócio.
"""

import os

from PIL import Image, ImageDraw

from libs.LayoutEngine import LayoutEngine
from libs.Render.FilterGraphBuilder import Unsupported
from libs.Subtitle.AssBuilder import AssBuilder


_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


# ---------------------------------------------------------------------------
# MÍDIA
# ---------------------------------------------------------------------------

def render_text_box_png(element: dict, scene_dir: str, resolution: tuple) -> str:
    """PNG de um `text_box`, pelo MESMO desenho do caminho MoviePy.

    Delega para `VisualClip.render_text_box_png` (com cache em disco), em vez de
    reimplementar o layout de texto — qualquer divergência apareceria como texto
    em posição/tamanho diferente entre os dois backends.
    """
    from libs.VisualClip import render_text_box_png as _render

    return _render(element, resolution, scene_dir)


def resolve_element_path(element: dict, scene_dir: str, remote_asset_manager,
                         resolution: tuple = None) -> str:
    """Caminho local do arquivo de um visual_element (baixa se remoto)."""
    from libs.MediaDownloader import MediaDownloader

    el_type = element.get("type")

    if el_type == "image":
        path = element.get("source")
        if path and os.path.exists(path):
            return path
        # `source` pode ser URL
        if path and str(path).startswith(("http://", "https://")):
            return MediaDownloader.resolve_source_path(path, scene_dir)
        raise Unsupported(f"imagem não encontrada: {path}")

    if el_type == "text_box":
        # Vira um PNG em disco e segue como qualquer imagem daqui para a frente.
        return render_text_box_png(element, scene_dir, resolution or (1920, 1080))

    if el_type == "color":
        # Não há arquivo: o clip é uma cor sólida dimensionada pelo placement.
        # Quem chama detecta isso pelo retorno None e usa lavfi `color`.
        return None

    if el_type == "remote_asset":
        if not remote_asset_manager:
            raise Unsupported("remote_asset sem RemoteAssetManager")
        slug = element.get("source")
        last_error = None
        for _ in range(3):
            url = remote_asset_manager.select_url(slug)
            if not url:
                break
            try:
                path = MediaDownloader.resolve_source_path(
                    url, scene_dir,
                    on_success_callback=remote_asset_manager.mark_download_success,
                    on_fail_callback=remote_asset_manager.mark_download_failed,
                )
                if path and os.path.exists(path):
                    return path
            except Exception as e:
                last_error = e
                continue
        suffix = f" ({last_error})" if last_error else ""
        raise Unsupported(f"remote_asset '{slug}' não resolvido{suffix}")

    raise Unsupported(f"tipo de elemento não suportado: {el_type}")


def _image_size(path: str) -> tuple:
    with Image.open(path) as im:
        return im.size


def _video_size(path: str) -> tuple:
    """Dimensões de um vídeo via ffprobe (PIL não abre vídeo)."""
    from libs.Background.MediaProbe import MediaProbe

    info = MediaProbe().probe(path)
    w, h = int(info.get("width") or 0), int(info.get("height") or 0)
    if w <= 0 or h <= 0:
        raise Unsupported(f"dimensões ilegíveis em {path}")
    return (w, h)


def resolve_directory_segments(cfg: dict, scene_duration: float) -> list:
    """Plano de preenchimento de um `type: "directory"`.

    Delega ao mesmo `DirectorySelector` que o BackgroundEngine usa, para que os
    dois caminhos de render escolham os mesmos arquivos e compartilhem o
    histórico anti-repetição. Aqui não se abre mídia nenhuma — só metadados.
    """
    from libs.Background.DirectorySelector import DirectorySelector

    segments = DirectorySelector().build_plan(cfg, float(scene_duration))
    if not segments:
        raise Unsupported(f"diretório sem mídia utilizável: {cfg.get('source')}")
    return segments


def video_segment(path: str, scene_duration: float) -> list:
    """Plano de um segmento só, para um arquivo de vídeo avulso.

    Deixa o vídeo único percorrer o mesmo código de normalização/concat da
    pasta, em vez de ter um caminho paralelo só para ele.
    """
    from libs.Background.MediaProbe import MediaProbe

    probe = MediaProbe()
    info = probe.probe(path)
    probe.save()

    file_duration = info.get("duration")
    if not file_duration or file_duration <= 0:
        raise Unsupported(f"vídeo sem duração legível: {path}")

    # Mais curto que a cena → loop; mais longo → corta no início (mesmo
    # comportamento do `_build_video` no BackgroundEngine).
    return [{
        "path": path,
        "start": 0.0,
        "duration": float(scene_duration),
        "is_video": True,
        "width": info.get("width", 0),
        "height": info.get("height", 0),
        "loop": file_duration < float(scene_duration),
    }]


# ---------------------------------------------------------------------------
# LAYOUT
# ---------------------------------------------------------------------------

def resolve_visual_boxes(elements: list, paths: list, layout_params: dict,
                         segments: list = None) -> list:
    """Resolve o plano de composição de cada elemento reusando o LayoutEngine.

    Retorna lista de dicts alinhada com `elements`:
        {box: (x,y,w,h), resize_to: (w,h), crop: (x1,y1,w,h)|None,
         deferred_animation: dict|None}

    `resize_to`/`crop` reproduzem o modo cover do worker MoviePy: a imagem é
    redimensionada para cobrir a caixa e o excesso é recortado — com o início do
    recorte vindo do focus point (centro ou rosto).
    """
    if not elements:
        return []

    items = []
    segments = segments or [None] * len(elements)
    for el, path, segs in zip(elements, paths, segments):
        if path is None:
            # `type: "color"` não tem arquivo. O ColorClip do caminho MoviePy usa
            # um tamanho placeholder que o placement sobrescreve; 1:1 aqui deixa
            # o LayoutEngine decidir a caixa pelo placement, sem aspect ratio
            # herdado de imagem nenhuma.
            w = h = 1000
        elif segs:
            # Pasta: dimensões já vêm do ffprobe (o primeiro segmento define o
            # aspect ratio). Abrir com PIL falharia em arquivo de vídeo.
            w, h = int(segs[0].get("width") or 0), int(segs[0].get("height") or 0)
            if w <= 0 or h <= 0:
                raise Unsupported(f"dimensões ilegíveis em {segs[0].get('path')}")
        elif os.path.splitext(path)[1].lower() in _VIDEO_EXTS:
            w, h = _video_size(path)
        elif el.get("type") == "text_box":
            # O PNG em disco é supersampled (até 4x, ver draw_text_box) para o
            # downscale do LayoutEngine sair nítido — não é o tamanho lógico do
            # texto. Quando não há `width` no placement (sem downscale previsto),
            # o tamanho de exibição tem que ser o lógico, senão o texto satura
            # 4x maior que o `font_size` pedido.
            from libs.VisualClip import VisualClip
            w, h = VisualClip.calculate_text_box_size(el)
        else:
            w, h = _image_size(path)
        items.append({
            "type": el.get("type"),
            "original_size": (w, h),
            "placement": el.get("placement"),
            "layout": el.get("layout", {}),
            "border_radius": el.get("border_radius", 0),
            "animation": el.get("animation"),
        })

    # O LayoutEngine lê atributos do config; completa com os mesmos defaults do
    # engine para não estourar AttributeError se algum vier ausente.
    cfg_dict = {
        "width": 1920, "height": 1080,
        "padding_top": 54, "padding_bottom": 160, "padding_side": 96,
        "stack_gap_percent": 0.02,
    }
    cfg_dict.update(layout_params or {})
    config = type("Cfg", (), cfg_dict)()
    results = LayoutEngine.process_stack_layout(items, config)

    plans = []
    for i, res in enumerate(results):
        if not res:
            raise Unsupported(f"layout não resolvido p/ visual_elements[{i}]")

        (fw, fh) = res["final_size"]
        (fx, fy) = res["final_position"]
        resize_to = tuple(res.get("_resize_to") or res["final_size"])

        crop = None
        crop_h = res.get("crop_height")
        crop_w = res.get("crop_width")
        if crop_h or crop_w:
            rw, rh = int(resize_to[0]), int(resize_to[1])
            focus = elements[i].get("focus", "center")
            # Ordem idêntica ao worker: crop vertical e depois horizontal, cada
            # um com offset resolvido pelo focus point.
            ch = int(crop_h) if (crop_h and crop_h < rh) else rh
            cw = int(crop_w) if (crop_w and crop_w < rw) else rw
            y1 = _crop_offset(paths[i], (rw, rh), rh, ch, focus, "y")
            x1 = _crop_offset(paths[i], (rw, rh), rw, cw, focus, "x")
            crop = (x1, y1, cw, ch)

        plans.append({
            "box": (int(fx), int(fy), int(fw), int(fh)),
            "resize_to": (int(resize_to[0]), int(resize_to[1])),
            "crop": crop,
            "deferred_animation": res.get("deferred_animation"),
        })
    return plans


def _crop_offset(path: str, resized_size: tuple, axis_size: int, crop_size: int,
                 focus: str, axis: str) -> int:
    """Início do crop no eixo, replicando `_cover_crop_offset` do engine.

    Diferença de implementação: lá o focus point é detectado no frame do clip
    MoviePy já redimensionado; aqui detectamos na imagem redimensionada com PIL.
    O resultado é o mesmo ponto, em pixels da imagem redimensionada.
    """
    center = axis_size / 2
    # `focus: "face"` só vale para imagem: a detecção roda uma vez no arquivo,
    # e um vídeo teria um rosto diferente a cada frame. Em vídeo, cai no centro.
    if focus == "face" and path and os.path.splitext(path)[1].lower() not in _VIDEO_EXTS:
        point = _detect_face_center(path, resized_size)
        if point:
            center = point[0] if axis == "x" else point[1]
    offset = int(center - crop_size / 2)
    return min(max(offset, 0), max(0, axis_size - crop_size))


_face_cache: dict = {}


def _detect_face_center(path: str, resized_size: tuple):
    """Centro do maior rosto, em pixels da imagem REDIMENSIONADA (ou None).

    Roda uma vez por (arquivo, tamanho) — fora de qualquer loop de frames, que é
    o que torna `focus: "face"` viável no caminho rápido.
    """
    key = (os.path.abspath(path), int(resized_size[0]), int(resized_size[1]))
    if key in _face_cache:
        return _face_cache[key]

    result = None
    try:
        import numpy as np
        from libs.FaceDetector import detect_focus_point

        with Image.open(path) as im:
            im = im.convert("RGB").resize(
                (int(resized_size[0]), int(resized_size[1])), Image.LANCZOS
            )
            result = detect_focus_point(np.asarray(im))
    except Exception as e:
        print(f"[SceneBridge] Detecção de rosto falhou ({e}); usando centro.")
        result = None

    _face_cache[key] = result
    return result


def resolve_ai_background(cfg: dict, resolution: tuple, asset_store, storage_dir: str,
                          global_settings: dict = None) -> str:
    """Caminho local da imagem de fundo gerada por IA.

    `type: "ai"` termina como arquivo em disco (via AssetStore) e, no
    BackgroundEngine, é apenas redimensionado para a resolução de saída — sem
    cover/crop. Aqui só resolvemos o CAMINHO: se estiver em cache, usa; se não,
    gera pelo mesmo `ai_manager` e grava com o mesmo nome, para os dois caminhos
    compartilharem o cache.

    Levanta Unsupported se a IA não estiver disponível ou o content_type for
    vídeo (aí a cena vai para o MoviePy).
    """
    content_type = cfg.get("content_type", "image")
    if content_type != "image":
        raise Unsupported(f"background ai content_type '{content_type}' não suportado")

    prompt = cfg.get("prompt", "")
    if not prompt:
        raise Unsupported("background ai sem prompt")

    provider = cfg.get("provider", "pollinations")
    # Mesma resolução e mesma chave do BackgroundEngine._build_ai — é o que faz
    # os dois caminhos dividirem o cache. Ver AIProviders/params.py.
    from libs.AIProviders.params import resolve_parameters
    from libs.Prepare.keys import ai_key
    parameters = resolve_parameters(cfg, global_settings, "background.visual")
    asset_key = ai_key(cfg, parameters, resolution)

    cached = asset_store.get(asset_key) if asset_store else None
    if cached:
        return cached

    # Não está no store: gera pelo mesmo caminho do BackgroundEngine.
    try:
        from libs.AIProviders import ai_manager
    except Exception as e:
        raise Unsupported(f"sistema de IA indisponível: {e}")

    parameters["width"] = int(resolution[0])
    parameters["height"] = int(resolution[1])
    result = ai_manager.generate_image(prompt=prompt, provider=provider, **parameters)
    if not result.get("success"):
        raise Unsupported(f"geração IA falhou: {result.get('error')}")

    if asset_store:
        return asset_store.put(asset_key, result["content"], kind="ai", ext="png",
                               meta={"provider": provider, "prompt": prompt})

    os.makedirs(storage_dir, exist_ok=True)
    file_path = os.path.join(storage_dir, f"ai_bg_{asset_key}.png")
    with open(file_path, "wb") as f:
        f.write(result["content"])
    return file_path


def resolve_background_cover(path: str, target: tuple, focus: str = "center") -> tuple:
    """Plano de cover do fundo: (resize_w, resize_h, crop_x, crop_y).

    Replica `BackgroundEngine._apply_cover` — escala pelo maior fator para cobrir
    o alvo e recorta centrado no focus point, com o mesmo clamp de bordas.
    """
    target_w, target_h = int(target[0]), int(target[1])
    w, h = _image_size(path)
    scale = max(target_w / w, target_h / h)
    new_w, new_h = int(w * scale), int(h * scale)

    cx, cy = new_w / 2, new_h / 2
    if focus == "face":
        point = _detect_face_center(path, (new_w, new_h))
        if point:
            cx, cy = point[0], point[1]

    # Mesmo clamp do BackgroundEngine: a janela nunca sai do clipe redimensionado.
    cx = min(max(cx, target_w / 2), new_w - target_w / 2)
    cy = min(max(cy, target_h / 2), new_h - target_h / 2)
    return (new_w, new_h, int(cx - target_w / 2), int(cy - target_h / 2))


def build_corner_mask(width: int, height: int, radius: int, out_dir: str) -> str:
    """Gera (com cache em disco) a máscara PNG de cantos arredondados."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"_mask_{width}x{height}_r{radius}.png")
    if os.path.exists(path):
        return path
    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, width - 1, height - 1], radius=radius, fill=255
    )
    mask.save(path)
    return path


# ---------------------------------------------------------------------------
# LEGENDAS
# ---------------------------------------------------------------------------

def build_ass_from_subtitle_config(subtitle_cfg: dict, srt_path: str,
                                   resolution: tuple, out_path: str) -> tuple:
    """Gera o .ass reusando o layout do KaraokeSubtitle/ClassicSubtitle.

    Retorna (ass_path, fontsdir) ou (None, None) se não houver legenda.
    Levanta Unsupported se algum estilo não for fiel em ASS.
    """
    if not subtitle_cfg or not subtitle_cfg.get("enabled"):
        return (None, None)
    if not srt_path or not os.path.exists(srt_path):
        return (None, None)

    sub_type = (subtitle_cfg.get("type") or "classic").lower()
    if sub_type == "karaoke":
        return _ass_from_karaoke(subtitle_cfg, srt_path, resolution, out_path)
    return _ass_from_classic(subtitle_cfg, srt_path, resolution, out_path)


def _params_for_subtitle(subtitle_cfg: dict, srt_path: str, resolution: tuple) -> dict:
    params = dict(subtitle_cfg)
    params.pop("enabled", None)
    params.pop("type", None)
    params["subtitle_narration_file"] = srt_path
    params["resolution_output"] = resolution
    return params


def _ass_from_karaoke(subtitle_cfg: dict, srt_path: str, resolution: tuple,
                      out_path: str) -> tuple:
    """Reusa o agrupamento/fit/layout do KaraokeSubtitle, trocando só o render.

    O KaraokeSubtitle calcula posições no canto SUPERIOR-ESQUERDO de cada
    palavra; o ASS posiciona pelo CENTRO (\\an5), então convertemos usando as
    dimensões da tinta de cada palavra.
    """
    from libs.Subtitle.types.KaraokeSubtitle import KaraokeSubtitle
    from libs.Subtitle import SubtitleUtils as utils

    params = _params_for_subtitle(subtitle_cfg, srt_path, resolution)
    kar = KaraokeSubtitle(params=params)

    words = utils.parse_srt_words(kar.subtitle_narration_file, uppercase=False)
    if not words:
        return (None, None)

    kar._box = utils.resolve_subtitle_box(
        {
            "placement": kar.placement,
            "subtitle_position": kar.subtitle_position,
            "has_visual_elements": kar.has_visual_elements,
            "padding_side": kar.padding_side,
            "padding_top": kar.padding_top,
            "padding_bottom": kar.padding_bottom,
        },
        kar.resolution_output,
    )

    groups = (kar._build_line_groups(words) if kar._line_mode_active()
              else kar._build_legacy_groups(words))

    builder = AssBuilder(resolution)
    fontsdir = None

    for group in groups:
        group_end = max(w["end"] for line in group for w in line)
        safe_w = kar._box["width"]

        rendered_lines = []
        styles_per_line = []
        for li, line in enumerate(group):
            if kar._line_mode_active():
                palette_item = kar.palette[li % len(kar.palette)]
                rendered = kar._render_line_uniform(line, palette_item, safe_w)
                styles_per_line.append([_style_for(kar, palette_item, r, line, safe_w, True)
                                        for r in rendered])
            else:
                rendered = kar._render_line_per_word(line, safe_w)
                styles_per_line.append([
                    _style_for(kar, kar.palette[i % len(kar.palette)], r, line, safe_w, False)
                    for i, r in enumerate(rendered)
                ])
            rendered_lines.append(rendered)

        positions = kar._layout_lines(rendered_lines, kar._box)

        # `_layout_lines` devolve pares (item, (x,y)) na ordem das palavras;
        # reconstruímos o estilo correspondente na mesma ordem.
        flat_styles = [s for line in styles_per_line for s in line]
        if len(flat_styles) != len(positions):
            raise Unsupported("divergência entre estilos e posições no karaokê")

        for (item, (x, y)), style in zip(positions, flat_styles):
            ok, why = AssBuilder.can_handle_style(style)
            if not ok:
                raise Unsupported(f"estilo de legenda não suportado: {why}")

            arr = item["arr"]
            ink = _ink_bbox(arr)
            if ink is None:
                continue
            ix0, iy0, ix1, iy1 = ink
            # X: centro da tinta real (a largura do glifo é o que importa).
            cx = x + (ix0 + ix1) / 2.0
            # Y: o \an5 do ASS ancora no centro da caixa de linha do libass, que
            # é `ascent + descent` da fonte — NÃO a tinta do glifo. Então:
            #   1. converte-se a posição do layout para a BASELINE em tela;
            #   2. a baseline vira o centro daquela caixa.
            # Usar o centro da tinta (como antes) deslocava toda palavra
            # acentuada, porque o acento estica a tinta só para cima; e usar a
            # caixa alta desalinhava linhas de tamanhos diferentes, já que a
            # relação caixa-alta/ascent varia com o font_size.
            baseline_y = item.get("baseline_y")
            if baseline_y is not None:
                font = utils.load_font(style["font_path"], style["font_size"])
                ascent, descent = font.getmetrics()
                cy = baseline_y - ascent + (ascent + descent) / 2.0
            else:
                cy = y + (iy0 + iy1) / 2.0

            text = kar._cased(item["word"]["word"], style.get("_palette_item", {}))
            builder.add_text(text, style, (cx, cy), item["word"]["start"], group_end)

            if fontsdir is None and style.get("font_path"):
                fontsdir = os.path.dirname(os.path.abspath(style["font_path"]))

    if builder.is_empty():
        return (None, None)

    builder.write(out_path)
    return (out_path, fontsdir)


def _style_for(kar, palette_item: dict, rendered: dict, line: list,
               safe_w: int, line_mode: bool) -> dict:
    """Reconstrói o dict de estilo usado no render de uma palavra."""
    from libs.Subtitle import SubtitleUtils as utils

    font_path = palette_item.get("font_path")
    stroke_width = int(palette_item.get("stroke_width", 0))
    eff_stroke = stroke_width * 2 if stroke_width > 0 else 0

    if line_mode:
        joined = " ".join(kar._cased(w["word"], palette_item) for w in line)
        font_size = utils.fit_font_size(
            joined, font_path, max_width=safe_w, stroke_width=eff_stroke,
            max_size=int(kar.max_font_size), min_size=int(kar.min_font_size),
        )
    else:
        cased = kar._cased(rendered["word"]["word"], palette_item)
        font_size = utils.fit_font_size(
            cased, font_path, max_width=safe_w, stroke_width=eff_stroke,
            max_size=int(kar.max_font_size), min_size=int(kar.min_font_size),
        )

    style = kar._build_style(palette_item, font_size)
    style["stroke_width"] = eff_stroke
    style["_palette_item"] = palette_item
    return style


def _ink_bbox(arr):
    """Bounding box dos pixels com alpha > 0 (a "tinta" real do array)."""
    import numpy as np
    if arr.shape[2] < 4:
        mask = arr.any(axis=2)
    else:
        mask = arr[:, :, 3] > 0
    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    if len(rows) == 0 or len(cols) == 0:
        return None
    return (int(cols[0]), int(rows[0]), int(cols[-1]), int(rows[-1]))


def _ass_from_classic(subtitle_cfg: dict, srt_path: str, resolution: tuple,
                      out_path: str) -> tuple:
    """Legenda clássica: uma entrada de SRT por evento, centralizada na caixa."""
    import srt as srt_lib
    from libs.Subtitle import SubtitleUtils as utils

    params = _params_for_subtitle(subtitle_cfg, srt_path, resolution)

    font_path = params.get("font_path")
    if not font_path:
        raise Unsupported("legenda clássica sem font_path")

    box = utils.resolve_subtitle_box(
        {
            "placement": params.get("placement"),
            "subtitle_position": params.get("subtitle_position", "bottom"),
            "has_visual_elements": params.get("has_visual_elements", False),
            "padding_side": params.get("padding_side", 50),
            "padding_top": params.get("padding_top", 100),
            "padding_bottom": params.get("padding_bottom", 850),
        },
        resolution,
    )

    shadow = params.get("shadow") or {}
    style = {
        "font_path": font_path,
        "font_size": int(params.get("font_size", 60)),
        "fill": params.get("color", "white"),
        "stroke_enabled": bool(params.get("stroke_width", 0)),
        "stroke_color": params.get("stroke_color", "black"),
        "stroke_width": int(params.get("stroke_width", 0)),
        "shadow_enabled": bool(shadow),
        "shadow_color": shadow.get("color", "black"),
        "shadow_opacity": shadow.get("opacity", 0.8),
        "blur_radius": shadow.get("blur", 0.0),
        "shadow_offset": tuple(shadow.get("offset", (0, 0))),
    }

    ok, why = AssBuilder.can_handle_style(style)
    if not ok:
        raise Unsupported(f"estilo de legenda não suportado: {why}")

    with open(srt_path, "r", encoding="utf-8") as f:
        entries = list(srt_lib.parse(f.read()))
    if not entries:
        return (None, None)

    builder = AssBuilder(resolution)
    cx = box["x"] + box["width"] // 2

    # `anchor_y` diz onde o texto se alinha DENTRO da caixa; ignorá-lo fazia
    # `placement.anchor: [_, "bottom"]` (e "top") renderizar sempre no meio
    # vertical. O ASS ancora pelo centro (\an5), então convertemos o alinhamento
    # da caixa no centro da linha, reservando metade da altura do texto para ele
    # não sair pela borda.
    anchor_y = box.get("anchor_y", "center")
    line_h = int(style["font_size"] * 1.2)
    if anchor_y == "top":
        cy = box["y"] + line_h // 2
    elif anchor_y == "bottom":
        cy = box["y"] + box["height"] - line_h // 2
    else:
        cy = box["y"] + box["height"] // 2

    for entry in entries:
        text = entry.content.replace("\n", " ").strip()
        if params.get("uppercase", True):
            text = text.upper()
        if not text:
            continue
        builder.add_text(text, style, (cx, cy),
                         entry.start.total_seconds(), entry.end.total_seconds())

    if builder.is_empty():
        return (None, None)

    builder.write(out_path)
    return (out_path, os.path.dirname(os.path.abspath(font_path)))
