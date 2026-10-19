"""Timeline → clipes MoviePy (paridade com o caminho ffmpeg).

Este módulo existe para que NENHUM recurso se perca quando a cena cai no
caminho legado: tudo que o `compile_ffmpeg` sabe fazer, aqui é feito igual — na
MESMA ORDEM, que é o que mantém o resultado visual equivalente:

    zoom (janela fixa) → border_radius → scale → opacity → posição/visibilidade

O `border_radius` fica no meio porque é aplicado por quem chama; por isso as
funções são granulares em vez de um `apply_timeline` monolítico.

Importa MoviePy (ao contrário do resto do pacote Motion), então só é carregado
no caminho legado.
"""

import math

from moviepy.editor import CompositeVideoClip


def has(timeline, prop: str) -> bool:
    """A timeline move essa propriedade?"""
    if timeline is None:
        return False
    track = timeline.tracks.get(prop)
    return track is not None and not track.is_static()


def apply_zoom(clip, timeline):
    """`zoom`: transborda e é recortado de volta no tamanho da caixa.

    Mesma técnica do `apply_animation_in_window` legado (e do `zoompan` do
    ffmpeg): o conteúdo cresce, o enquadramento não.
    """
    if not has(timeline, "zoom"):
        return clip

    from libs.VisualClip import force_rgb

    win_w, win_h = clip.size
    duration = clip.duration
    zoomed = clip.resize(lambda t: timeline.sample("zoom", t)).set_position("center")
    window = CompositeVideoClip([zoomed], size=(win_w, win_h)).set_duration(duration)
    # `force_rgb` achata o alpha; só vale quando não há máscara a preservar —
    # senão a opacidade do motion (aplicada depois) renderizaria sobre preto.
    if clip.mask is None and not has(timeline, "opacity"):
        window = window.fl_image(force_rgb)
    return window


def apply_scale(clip, timeline):
    """`scale`: TRANSBORDA a caixa (motion de UI: pop, punch).

    Diferente de `zoom`, que fica dentro dela. Nunca unificar as duas.
    """
    if not has(timeline, "scale"):
        return clip
    return clip.resize(lambda t: timeline.sample("scale", t))


def rotation_canvas(box: tuple) -> tuple:
    """(lado, esquerda, topo) do canvas quadrado que comporta o giro.

    Um retângulo girado ocupa até a sua DIAGONAL. As contas são IDÊNTICAS às do
    `FilterGraphBuilder.rotate_anim` (mesmo `ceil`, mesmo ajuste para par,
    mesma divisão inteira) de propósito: um pixel de diferença no tamanho do
    canvas desloca o centro de meio pixel, e num elemento com textura de grade
    isso já derruba o SSIM de paridade entre os backends.
    """
    _, _, bw, bh = box
    side = int(math.ceil(math.hypot(bw, bh)))
    side += side % 2
    return (side, (side - int(bw)) // 2, (side - int(bh)) // 2)


def apply_rotation(clip, timeline, box: tuple = None):
    """`rotation` em graus, anti-horário (igual ao filtro `rotate`).

    Não usa `vfx.rotate`: com ângulo múltiplo de 90° ele pega um atalho que faz
    `np.transpose` com 3 eixos e QUEBRA em clipe com máscara (a máscara é 2D) —
    `ValueError: axes don't match array`. Aqui a rotação é feita com PIL, no
    quadro e na máscara, dentro de um canvas de tamanho fixo.
    """
    if not has(timeline, "rotation"):
        return clip

    import numpy as np
    from PIL import Image

    box = box or (0, 0, clip.w, clip.h)
    side, left, top = rotation_canvas(box)
    if side > clip.w or side > clip.h:
        # Canvas com folga para a diagonal; `opacity=0` deixa a borda
        # transparente (e cria a máscara, se ainda não houver).
        clip = clip.margin(left=left, right=side - clip.w - left,
                           top=top, bottom=side - clip.h - top, opacity=0)

    def rotate_frame(get_frame, t):
        angle = timeline.sample("rotation", t)
        frame = get_frame(t)
        if abs(angle) < 1e-6:
            return frame
        is_mask = frame.ndim == 2
        array = np.uint8(frame * 255) if is_mask else np.uint8(frame)
        # BILINEAR (e não BICUBIC) para bater com a interpolação do filtro
        # `rotate` do ffmpeg, que é bilinear por padrão — com bicúbico a borda
        # do elemento girado fica visivelmente mais dura num backend que no
        # outro e o SSIM de paridade cai.
        rotated = Image.fromarray(array).rotate(
            angle, resample=Image.BILINEAR, expand=False)
        out = np.asarray(rotated)
        return out.astype(float) / 255.0 if is_mask else out

    clip = clip.fl(rotate_frame, apply_to=["mask"], keep_duration=True)
    return clip


def apply_blur(clip, timeline):
    """`blur` animado (sigma do gaussiano), via PIL quadro a quadro.

    O MoviePy não tem desfoque nativo; `GaussianBlur` do PIL é o equivalente
    mais próximo do `gblur` do ffmpeg (mesmo sigma, mesma família de kernel).
    """
    if not has(timeline, "blur"):
        return clip

    import numpy as np
    from PIL import Image, ImageFilter

    def blur_frame(get_frame, t):
        sigma = max(0.0, timeline.sample("blur", t))
        frame = get_frame(t)
        if sigma < 0.05:
            return frame
        # A máscara chega como float 0–1 e 2D; o quadro, como uint8 RGB.
        is_mask = frame.ndim == 2
        array = np.uint8(frame * 255) if is_mask else np.uint8(frame)
        blurred = Image.fromarray(array).filter(ImageFilter.GaussianBlur(sigma))
        out = np.asarray(blurred)
        return out.astype(float) / 255.0 if is_mask else out

    # `apply_to=["mask"]` é o que faz as BORDAS desfocarem: o `gblur` do ffmpeg
    # borra o canal alpha junto com a cor, e sem isso um backend entregaria
    # borda nítida e o outro borda suave.
    return clip.fl(blur_frame, apply_to=["mask"], keep_duration=True)


def apply_opacity(clip, timeline):
    """`opacity` animada, pela MÁSCARA.

    `set_opacity` é estático — usá-lo congelaria o fade no primeiro valor. A
    máscara é multiplicada (não substituída) para preservar o alpha próprio do
    PNG.
    """
    if not has(timeline, "opacity"):
        return clip

    if clip.mask is None:
        clip = clip.add_mask()
    sample = timeline.sample
    clip.mask = clip.mask.fl(
        lambda get_frame, t: get_frame(t) * sample("opacity", t),
        keep_duration=True,
    )
    return clip


def position(timeline, box: tuple, *, anchor=("center", "center")):
    """Posição (callable ou tupla) para `set_position`.

    Soma o deslocamento animado à caixa do layout e compensa a `scale`, igual ao
    `overlay` do ffmpeg: o clipe cresce a partir da âncora que o JSON pediu, não
    do canto superior esquerdo.
    """
    bx, by, bw, bh = box
    moves = has(timeline, "x") or has(timeline, "y")
    scaled = has(timeline, "scale")
    rotated = has(timeline, "rotation")
    if not moves and not scaled and not rotated:
        return (bx, by)

    ax = str(anchor[0]) if len(anchor) > 0 else "center"
    ay = str(anchor[1]) if len(anchor) > 1 else "center"

    def at(t):
        dx = timeline.sample("x", t) if moves else 0.0
        dy = timeline.sample("y", t) if moves else 0.0
        width, height = bw, bh
        if scaled:
            factor = timeline.sample("scale", t)
            width, height = bw * factor, bh * factor
        if rotated:
            # Canvas FIXO da rotação (ver rotation_canvas) — não varia com o
            # ângulo, então basta somá-lo ao crescimento da escala.
            side = rotation_canvas(box)[0]
            width = width + (side - bw)
            height = height + (side - bh)
        if scaled or rotated:
            grow_w, grow_h = width - bw, height - bh
            # Com rotação, a âncora é sempre o CENTRO: o quadro ampliado tem
            # margem dos dois lados, então encostar "à direita" não faria
            # sentido (mesma regra do caminho ffmpeg).
            if ax == "right" and not rotated:
                dx -= grow_w
            elif ax != "left" or rotated:
                dx -= grow_w / 2.0
            if ay == "bottom" and not rotated:
                dy -= grow_h
            elif ay != "top" or rotated:
                dy -= grow_h / 2.0
        return (bx + dx, by + dy)

    return at


def apply_visible(clip, timeline, scene_duration: float = None):
    """Janela `visible`: equivalente ao `enable=between(...)` do overlay.

    Implementada pela MÁSCARA, não por `set_start`/`set_end`. Dentro de um
    `CompositeVideoClip`, um clipe com `set_start(0.5)` passa a receber tempo
    LOCAL (t − 0,5) — e todas as curvas deste módulo são amostradas em tempo
    ABSOLUTO da cena. O resultado seria toda a animação atrasada pelo início da
    janela; medido antes da correção: 0,5 s de defasagem contra o ffmpeg.
    """
    if timeline is None or not timeline.visible:
        return clip
    start, end = timeline.visible

    if clip.mask is None:
        clip = clip.add_mask()
    clip.mask = clip.mask.fl(
        lambda get_frame, t: get_frame(t) * (1.0 if start <= t <= end else 0.0),
        keep_duration=True,
    )
    return clip
