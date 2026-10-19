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
    if not moves and not scaled:
        return (bx, by)

    ax = str(anchor[0]) if len(anchor) > 0 else "center"
    ay = str(anchor[1]) if len(anchor) > 1 else "center"

    def at(t):
        dx = timeline.sample("x", t) if moves else 0.0
        dy = timeline.sample("y", t) if moves else 0.0
        if scaled:
            factor = timeline.sample("scale", t)
            grow_w, grow_h = bw * factor - bw, bh * factor - bh
            if ax == "right":
                dx -= grow_w
            elif ax != "left":
                dx -= grow_w / 2.0
            if ay == "bottom":
                dy -= grow_h
            elif ay != "top":
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
