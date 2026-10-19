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
    "resolve_motion", "has_motion", "motion_defaults",
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
