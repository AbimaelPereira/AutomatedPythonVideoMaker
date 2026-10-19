"""Motion — movimento declarativo ancorado na narração.

API pública: `resolve_motion()`. É a ÚNICA função que os dois backends de render
chamam; toda a complexidade (schema, presets, easing, âncoras, keyframes) fica
atrás dela. O pacote é Python puro — não importa MoviePy nem chama ffmpeg — o que
o torna testável em milissegundos.

    from libs.Motion import resolve_motion

    timeline = resolve_motion(element=el, box=box, resolution=(1920, 1080),
                              scene_duration=7.4, words=words)
    if timeline:                      # None = elemento sem `motion` (caminho legado)
        dx = timeline.sample("x", t)

Ver `docs/PLANO_MOTION_SYNC.md` para a superfície JSON completa.
"""

from libs.Motion.anchors import AnchorResolver
from libs.Motion.errors import AnchorNotFound, MotionError, ValidationError
from libs.Motion.keyframes import BASES, Keyframe, Timeline, Track
from libs.Motion.timeline import DEFAULTS, build_timeline, effective_defaults

__all__ = [
    "resolve_motion", "resolve_scene_motion", "resolve_background_motion",
    "has_motion", "motion_defaults",
    "words_from_srt", "narration_text_of",
    "AnchorResolver", "AnchorNotFound", "MotionError", "ValidationError",
    "Timeline", "Track", "Keyframe", "BASES", "DEFAULTS",
]


def has_motion(element: dict) -> bool:
    """True se o elemento declara `motion` (vazio/False conta como ausente)."""
    if not isinstance(element, dict):
        return False
    motion = element.get("motion")
    if not motion:
        return False
    if isinstance(motion, dict) and motion.get("enabled") is False:
        return False
    return True


def motion_defaults(effective_gs: dict = None, scene: dict = None) -> dict:
    """`global_settings.motion` efetivo (global < cena), sem as ações.

    A cadeia canal < global < capítulo já foi resolvida pelo `deep_merge` do
    engine quando `effective_gs` chega aqui; falta só a sobrescrita da cena.
    """
    from libs.utils import deep_merge

    def settings_only(data):
        motion = (data or {}).get("motion")
        if not isinstance(motion, dict):
            return {}
        return {k: v for k, v in motion.items() if k not in ("actions", "visible")}

    return deep_merge(settings_only(effective_gs), settings_only(scene))


def resolve_motion(*, element: dict, box: tuple, resolution: tuple,
                   scene_duration: float, words: list = None,
                   narration_text: str = "", defaults: dict = None,
                   stagger_offset: float = 0.0, json_path: str = ""):
    """`visual_element` cru → `Timeline`, ou None se não há `motion` novo.

    Levanta `MotionError`/`ValidationError` em JSON inválido (princípio P3) e
    `AnchorNotFound` apenas com `on_missing: "strict"` (P4).
    """
    if not has_motion(element):
        return None

    defaults = effective_defaults(defaults)
    if defaults.get("enabled") is False:
        return None

    path = f"{json_path}.motion" if json_path else "motion"
    resolver = AnchorResolver(
        words=words, narration_text=narration_text,
        scene_duration=float(scene_duration),
        on_missing=defaults["on_missing"],
    )
    timeline = build_timeline(
        element["motion"], box=box, resolution=resolution,
        scene_duration=float(scene_duration), anchor_resolver=resolver,
        defaults=defaults, stagger_offset=stagger_offset, path=path,
    )
    if timeline is None:
        return None
    return timeline


# ---------------------------------------------------------------------------
# PONTE COM O ENGINE
# ---------------------------------------------------------------------------

def words_from_srt(srt_path: str):
    """`[{word, start, end}]` do SRT palavra-a-palavra, ou None.

    O arquivo é o mesmo que alimenta a legenda (`{scene_dir}/{scene_id}.srt`),
    já remapeado pelo corte de silêncio. Falha de leitura NUNCA derruba o
    render: devolve None e o `on_missing` assume (princípio P4).
    """
    import os

    if not srt_path or not os.path.exists(srt_path):
        return None
    try:
        from libs.Subtitle.SubtitleUtils import parse_srt_words
        return parse_srt_words(srt_path, uppercase=False) or None
    except Exception as e:
        print(f"[Motion] ⚠️ falha ao ler o SRT para âncoras ({e})")
        return None


def narration_text_of(scene: dict) -> str:
    """Texto escrito da narração — base das âncoras `{"sentence": n}`."""
    return ((scene or {}).get("narration") or {}).get("text") or ""


def _stagger_offsets(scene: dict, elements: list) -> list:
    """Offset de stagger de cada elemento (0 quando não há grupo).

    `motion.stagger` no nível da CENA define o passo; os elementos entram no
    grupo por `stagger_group` (aceito na raiz do elemento ou dentro do seu
    `motion`). A ordem é a de declaração.
    """
    scene_motion = (scene or {}).get("motion")
    if not isinstance(scene_motion, dict):
        return [0.0] * len(elements)

    step = scene_motion.get("stagger")
    if not step:
        return [0.0] * len(elements)
    step = float(step)
    target_group = scene_motion.get("stagger_group")

    def group_of(el):
        if not isinstance(el, dict):
            return None
        motion = el.get("motion")
        inner = motion.get("stagger_group") if isinstance(motion, dict) else None
        return el.get("stagger_group") or inner

    offsets, counters = [], {}
    for el in elements:
        group = group_of(el)
        # Sem `stagger_group` na cena, qualquer grupo declarado vale; com ele,
        # só o grupo nomeado é escalonado.
        if group is None or (target_group is not None and group != target_group):
            offsets.append(0.0)
            continue
        index = counters.get(group, 0)
        counters[group] = index + 1
        offsets.append(index * step)
    return offsets


def resolve_scene_motion(*, scene: dict, elements: list, boxes: list,
                         resolution: tuple, scene_duration: float,
                         words: list = None, defaults: dict = None) -> list:
    """Uma `Timeline` (ou None) por elemento visual da cena.

    Ponto único de entrada dos DOIS backends: o que divergir aqui divergiria
    nos dois juntos. As caixas (`boxes`) já vêm do LayoutEngine, porque `x`/`y`
    em `%` são fração da caixa e `scale` precisa do tamanho base.
    """
    narration_text = narration_text_of(scene)
    offsets = _stagger_offsets(scene, elements)

    # MotionError (JSON inválido) sobe: o autor do JSON precisa ver (P3).
    timelines = [
        resolve_motion(
            element=el, box=box, resolution=resolution,
            scene_duration=scene_duration, words=words,
            narration_text=narration_text, defaults=defaults,
            stagger_offset=offsets[i], json_path=f"visual_elements[{i}]",
        )
        for i, (el, box) in enumerate(zip(elements, boxes))
    ]

    from libs.Motion.inspect import debug_enabled, print_scene
    if debug_enabled() and any(timelines):
        print_scene(str((scene or {}).get("id", "?")), timelines,
                    words=words, duration=float(scene_duration))
    return timelines


def resolve_background_motion(*, bg_cfg: dict, resolution: tuple,
                              scene_duration: float, scene: dict = None,
                              words: list = None, defaults: dict = None):
    """`Timeline` do `background.visual.motion`, ou None.

    A caixa é a TELA inteira — num fundo não existe caixa de layout. As
    propriedades que fazem sentido aqui são `zoom` (ken burns com keyframes),
    `x`/`y` (pan direcional) e `blur`; `scale`/`opacity` também funcionam, mas
    num fundo que cobre a tela só revelariam o preto por baixo.
    """
    if not has_motion(bg_cfg):
        return None
    return resolve_motion(
        element=bg_cfg, box=(0, 0, int(resolution[0]), int(resolution[1])),
        resolution=resolution, scene_duration=float(scene_duration),
        words=words, narration_text=narration_text_of(scene),
        defaults=defaults, json_path="background.visual",
    )
