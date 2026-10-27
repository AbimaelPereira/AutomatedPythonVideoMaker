"""Monta a `Timeline` a partir do bloco `motion` do JSON.

Ordem do pipeline (não reordenar — cada passo depende do anterior):

    validar → expandir presets → resolver âncoras → aplicar on_missing
    → resolver `after` → converter unidades → montar tracks → mesclar
    → aplicar stagger → clampar na cena

As âncoras de fala chegam por um resolvedor injetado (`anchor_resolver`), para
este módulo não saber nada de SRT nem de Whisper.
"""

from libs.Motion import presets as presets_mod
from libs.Motion import schema
from libs.Motion.errors import MotionError
from libs.Motion.keyframes import BASES, Timeline, Track, parse_track

# `hold: false` volta à base IMEDIATAMENTE depois da ação. O keyframe de retorno
# fica uma fração de ms após o último da ação — no mesmo instante ele venceria a
# deduplicação e apagaria o valor final da própria ação.
_SNAP_EPS = 1e-3

DEFAULTS = {
    "enabled": True,
    "on_missing": "proportional",
    "default_ease": "out_cubic",
    "default_duration": 0.5,
    "fps_hint": 30,
}


def normalize(motion_cfg):
    """Aceita a forma curta `"motion": [ {ação}, … ]`."""
    if isinstance(motion_cfg, (list, tuple)):
        return {"actions": list(motion_cfg)}
    return motion_cfg


def effective_defaults(defaults: dict = None) -> dict:
    merged = dict(DEFAULTS)
    for key, value in (defaults or {}).items():
        if value is not None:
            merged[key] = value
    return merged


def _filter_comments(data: dict) -> dict:
    """Remove as chaves de comentário (`"algo/"`), como o engine faz no JSON."""
    return {k: v for k, v in data.items() if not str(k).endswith("/")}


def _merge_action(action: dict, defaults: dict, path: str) -> dict:
    """Ação + preset → dict com tracks/ease/duration/loop resolvidos.

    O que a ação declara vence PROPRIEDADE A PROPRIEDADE (§2.6): declarar
    `scale` num `pop_in` troca só o scale, o `opacity` do preset continua.
    """
    action = _filter_comments(action)
    preset_name = action.get("preset")
    merged = {"duration": None, "ease": None, "loop": False, "tracks": {}}

    if preset_name:
        merged.update(presets_mod.expand(preset_name))

    if action.get("tracks"):
        tracks = dict(merged["tracks"])
        tracks.update(_filter_comments(action["tracks"]))
        merged["tracks"] = tracks

    if action.get("duration") is not None:
        merged["duration"] = float(action["duration"])
    if action.get("ease") is not None:
        merged["ease"] = action["ease"]
    if "loop" in action:
        merged["loop"] = bool(action["loop"])

    if merged["ease"] is None:
        merged["ease"] = defaults["default_ease"]
    if merged["duration"] is None and not preset_name:
        # Sem preset, a duração default vem do `global_settings.motion`. Com
        # preset, `duration: null` é intencional (ken burns = o resto da cena).
        merged["duration"] = float(defaults["default_duration"])
    if not merged["tracks"]:
        raise MotionError("ação sem tracks após expandir o preset", path)
    return merged


def build_timeline(motion_cfg, *, box, resolution, scene_duration,
                   anchor_resolver, defaults: dict = None,
                   stagger_offset: float = 0.0, path: str = "motion") -> Timeline:
    """`motion` do JSON → `Timeline` em segundos absolutos da cena."""
    motion_cfg = normalize(motion_cfg)
    defaults = effective_defaults(defaults)

    if isinstance(motion_cfg, dict) and motion_cfg.get("enabled") is False:
        return None

    schema.check(motion_cfg, path)
    motion_cfg = _filter_comments(motion_cfg)

    on_missing = motion_cfg.get("on_missing") or defaults["on_missing"]
    anchor_resolver.on_missing = on_missing

    actions = list(motion_cfg["actions"])
    merged = [_merge_action(a, defaults, f"{path}.actions[{i}]")
              for i, a in enumerate(actions)]

    # --- 1ª passada: âncoras que não dependem de outra ação ---------------
    starts: list = [None] * len(actions)
    deferred: list = []          # índices com `at: {after: ...}`
    missed: list = []            # índices cuja âncora de fala não casou

    for i, action in enumerate(actions):
        apath = f"{path}.actions[{i}].at"
        spec = action.get("at")
        if spec is None:
            starts[i] = 0.0
            continue
        if isinstance(spec, dict) and (spec.get("after") or spec.get("at_end_of")):
            deferred.append(i)
            continue
        resolved = anchor_resolver.resolve(spec, path=apath)
        if resolved is None:
            missed.append(i)
        else:
            starts[i] = resolved

    # --- on_missing -------------------------------------------------------
    if missed:
        if on_missing == "strict":
            # O resolvedor já levantou AnchorNotFound nesse modo; chegar aqui
            # significa que ele devolveu None por outro motivo.
            raise MotionError("âncora não resolvida com on_missing=strict",
                              f"{path}.actions[{missed[0]}].at")
        if on_missing == "start":
            for i in missed:
                starts[i] = 0.0
        elif on_missing == "skip":
            pass    # fica None → a ação é descartada abaixo
        else:       # proportional (default)
            total = len(missed)
            for n, i in enumerate(missed):
                starts[i] = scene_duration * (n + 1) / (total + 1)

    # --- durações e `until` ----------------------------------------------
    def action_duration(i: int) -> float:
        """Duração efetiva da ação `i` (precisa do start já resolvido)."""
        spec_until = actions[i].get("until")
        if spec_until is not None:
            end = anchor_resolver.resolve(spec_until,
                                          path=f"{path}.actions[{i}].until")
            if end is not None:
                return max(0.001, end - starts[i])
        if merged[i]["duration"] is not None:
            return float(merged[i]["duration"])
        # Preset com `duration: null` (ken burns) = o resto da cena.
        return max(0.001, scene_duration - starts[i])

    ends: dict = {}

    def register_end(i: int):
        name = actions[i].get("name")
        if name:
            ends[name] = starts[i] + action_duration(i)

    for i in range(len(actions)):
        if starts[i] is not None and i not in deferred:
            register_end(i)

    # --- `after`: na ordem de declaração, já com os ends disponíveis -------
    for i in deferred:
        spec = actions[i]["at"]
        ref = spec.get("after") or spec.get("at_end_of")
        if ref not in ends:
            raise MotionError(
                f"'after' aponta para ação sem fim conhecido: {ref!r}",
                f"{path}.actions[{i}].at",
                "a ação referenciada precisa ter 'name' e vir antes desta")
        starts[i] = ends[ref] + float(spec.get("offset") or 0.0)
        register_end(i)

    # --- stagger ----------------------------------------------------------
    if stagger_offset:
        starts = [None if s is None else s + stagger_offset for s in starts]

    # --- tracks -----------------------------------------------------------
    timeline = Timeline(duration=float(scene_duration))
    timeline.warnings = list(getattr(anchor_resolver, "misses", []))

    for i, action in enumerate(actions):
        if starts[i] is None:
            timeline.warnings.append(
                f"{path}.actions[{i}] descartada (on_missing=skip)")
            continue

        start = max(0.0, float(starts[i]))
        duration = action_duration(i)
        cfg = merged[i]
        hold = bool(action.get("hold", True))

        for prop, raw in cfg["tracks"].items():
            keys = parse_track(
                prop, raw, duration=duration, action_start=start, box=box,
                resolution=resolution, default_ease=cfg["ease"],
                path=f"{path}.actions[{i}].tracks.{prop}",
            )
            track = timeline.tracks.get(prop)
            if track is None:
                track = Track(prop=prop, keys=[], base=BASES[prop])
                timeline.tracks[prop] = track
            track.add(keys, hold=hold,
                      base_snap_at=(start + duration + _SNAP_EPS) if not hold else None)

            if cfg["loop"]:
                period = max(0.001, duration)
                track.loop = (period, start, float(scene_duration))

        timeline.actions.append({
            "index": i,
            "name": action.get("name"),
            "preset": action.get("preset"),
            "start": start,
            "duration": duration,
            "ease": cfg["ease"],
            "props": sorted(cfg["tracks"].keys()),
            "loop": cfg["loop"],
            # Efeito sonoro da ação (cru do JSON; None = usar o default do preset).
            # Quem toca é o SfxMixer — o Motion só informa o instante.
            "sfx": action.get("sfx"),
        })

    # --- visible ----------------------------------------------------------
    visible = motion_cfg.get("visible")
    if visible:
        v_from = visible.get("from")
        v_to = visible.get("to")
        start = anchor_resolver.resolve(v_from, path=f"{path}.visible.from") \
            if v_from is not None else 0.0
        end = anchor_resolver.resolve(v_to, path=f"{path}.visible.to") \
            if v_to is not None else scene_duration
        start = 0.0 if start is None else start
        end = scene_duration if end is None else end
        start = max(0.0, min(float(start), scene_duration))
        end = max(start, min(float(end), scene_duration))
        timeline.visible = (start, end)

    # --- clamp final ------------------------------------------------------
    for track in timeline.tracks.values():
        track.clamp(0.0, float(scene_duration))

    return timeline
