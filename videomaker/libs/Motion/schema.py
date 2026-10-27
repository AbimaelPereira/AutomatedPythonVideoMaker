"""Validação do bloco `motion`.

Validador manual — nenhuma dependência nova. Objetivo (princípio P3): nunca
ignorar um campo silenciosamente. Chave com typo, easing inexistente, preset
inexistente, `after` apontando para o nada: tudo vira erro com o caminho JSON e
uma sugestão por `difflib`.

`validate()` devolve a lista de erros; `check()` levanta o primeiro. Devolver em
lista permite ao `--validate` do main.py mostrar todos os problemas de um JSON
numa passada, em vez de um por execução.
"""

import difflib

from libs.Motion import easing, presets
from libs.Motion.errors import ValidationError
from libs.Motion.keyframes import PROPS

MOTION_KEYS = {
    "enabled", "on_missing", "default_ease", "default_duration", "fps_hint",
    "visible", "actions", "stagger", "stagger_group",
}
ACTION_KEYS = {"name", "at", "until", "duration", "ease", "preset", "tracks",
               "hold", "loop", "sfx"}
SFX_KEYS = {"source", "volume", "offset"}
AT_KEYS = {"word", "nth", "word_index", "phrase", "sentence", "after",
           "at_end_of", "offset", "align"}
VISIBLE_KEYS = {"from", "to"}
ON_MISSING = ("strict", "proportional", "start", "skip")
ALIGN = ("start", "end", "center")


def _hint(name, options) -> str:
    close = difflib.get_close_matches(str(name), list(options), n=5, cutoff=0.3)
    return "talvez: " + ", ".join(close) if close else \
        "válidos: " + ", ".join(sorted(options))


def _unknown_keys(data: dict, allowed: set, path: str, errors: list):
    for key in data:
        if key in allowed or str(key).endswith("/"):
            # Chave terminada em "/" é comentário — mesma convenção do
            # `_filter_comment_keys` do engine.
            continue
        errors.append(ValidationError(f"chave desconhecida '{key}'",
                                      f"{path}.{key}", _hint(key, allowed)))


def _validate_anchor(spec, path: str, errors: list):
    if spec is None:
        errors.append(ValidationError("âncora vazia", path))
        return
    if isinstance(spec, (int, float)) and not isinstance(spec, bool):
        return
    if isinstance(spec, str):
        return
    if not isinstance(spec, dict):
        errors.append(ValidationError(f"âncora inválida: {spec!r}", path,
                                      "use segundos, \"42%\", \"start\"/\"end\" "
                                      "ou {\"word\": \"...\"}"))
        return

    _unknown_keys(spec, AT_KEYS, path, errors)

    selectors = [k for k in ("word", "word_index", "phrase", "sentence",
                             "after", "at_end_of") if k in spec]
    if not selectors:
        errors.append(ValidationError(
            "âncora sem seletor", path,
            "informe word, word_index, phrase, sentence ou after"))
    elif len(selectors) > 1:
        errors.append(ValidationError(
            f"âncora com seletores conflitantes: {', '.join(selectors)}", path,
            "use apenas um"))

    if "align" in spec and spec["align"] not in ALIGN:
        errors.append(ValidationError(f"align inválido: {spec['align']!r}", path,
                                      _hint(spec["align"], ALIGN)))
    if "offset" in spec and not isinstance(spec["offset"], (int, float)):
        errors.append(ValidationError(f"offset precisa ser número: "
                                      f"{spec['offset']!r}", path))
    for key in ("nth", "word_index", "sentence"):
        if key in spec:
            value = spec[key]
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                errors.append(ValidationError(
                    f"{key} precisa ser inteiro ≥ 1 (1-based): {value!r}",
                    f"{path}.{key}"))


def _validate_tracks(tracks, path: str, errors: list):
    if not isinstance(tracks, dict):
        errors.append(ValidationError(f"tracks precisa ser objeto: {tracks!r}", path))
        return
    for prop, raw in tracks.items():
        if str(prop).endswith("/"):
            continue
        prop_path = f"{path}.{prop}"
        if prop not in PROPS:
            errors.append(ValidationError(f"propriedade não animável '{prop}'",
                                          prop_path, _hint(prop, PROPS)))
            continue
        if isinstance(raw, (list, tuple)):
            if not raw:
                errors.append(ValidationError(f"track '{prop}' vazia", prop_path))
            for i, item in enumerate(raw):
                if isinstance(item, (list, tuple)) and len(item) == 3:
                    if item[2] not in easing.EASINGS:
                        errors.append(ValidationError(
                            f"easing desconhecido: {item[2]!r}",
                            f"{prop_path}[{i}][2]", _hint(item[2], easing.NAMES)))
        _validate_range(prop, raw, prop_path, errors)


def _flat_values(raw):
    """Valores numéricos de uma track, em qualquer das 4 formas."""
    items = raw if isinstance(raw, (list, tuple)) else [raw]
    for item in items:
        if isinstance(item, (list, tuple)):
            if len(item) >= 2 and isinstance(item[1], (int, float)) \
                    and not isinstance(item[1], bool):
                yield item[1]
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            yield item


def _validate_range(prop: str, raw, path: str, errors: list):
    for value in _flat_values(raw):
        if prop == "blur" and value < 0:
            errors.append(ValidationError(f"blur não pode ser negativo: {value}",
                                          path))
        if prop == "opacity" and not (0.0 <= value <= 1.0):
            errors.append(ValidationError(f"opacity fora de 0–1: {value}", path))
        if prop in ("scale", "zoom") and value <= 0:
            errors.append(ValidationError(f"{prop} precisa ser > 0: {value}", path))


def _validate_sfx(spec, path: str, errors: list):
    """`sfx` da ação: caminho (arquivo ou pasta), objeto {source, volume, offset} ou false."""
    if spec is False or spec is None or (isinstance(spec, str) and spec.strip()):
        return
    if not isinstance(spec, dict):
        errors.append(ValidationError(f"sfx inválido: {spec!r}", path,
                                      "use um caminho, {\"source\": ...} ou false"))
        return
    _unknown_keys(spec, SFX_KEYS, path, errors)
    if not isinstance(spec.get("source"), str) or not spec["source"].strip():
        errors.append(ValidationError("sfx sem 'source'", path))
    for key in ("volume", "offset"):
        value = spec.get(key)
        if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool)):
            errors.append(ValidationError(f"{key} precisa ser número: {value!r}", f"{path}.{key}"))
    if isinstance(spec.get("volume"), (int, float)) and spec["volume"] < 0:
        errors.append(ValidationError(f"volume não pode ser negativo: {spec['volume']}", f"{path}.volume"))


def validate(motion_cfg, path: str = "motion") -> list:
    """Lista de `ValidationError` (vazia = válido)."""
    errors: list = []

    if isinstance(motion_cfg, (list, tuple)):
        motion_cfg = {"actions": list(motion_cfg)}
    if not isinstance(motion_cfg, dict):
        return [ValidationError(f"motion precisa ser objeto ou lista de ações: "
                                f"{motion_cfg!r}", path)]

    _unknown_keys(motion_cfg, MOTION_KEYS, path, errors)

    on_missing = motion_cfg.get("on_missing")
    if on_missing is not None and on_missing not in ON_MISSING:
        errors.append(ValidationError(f"on_missing inválido: {on_missing!r}",
                                      f"{path}.on_missing",
                                      _hint(on_missing, ON_MISSING)))

    default_ease = motion_cfg.get("default_ease")
    if default_ease is not None and default_ease not in easing.EASINGS:
        errors.append(ValidationError(f"easing desconhecido: {default_ease!r}",
                                      f"{path}.default_ease",
                                      _hint(default_ease, easing.NAMES)))

    for key in ("default_duration", "stagger"):
        value = motion_cfg.get(key)
        if value is not None and (not isinstance(value, (int, float))
                                  or isinstance(value, bool) or value < 0):
            errors.append(ValidationError(f"{key} precisa ser número ≥ 0: "
                                          f"{value!r}", f"{path}.{key}"))

    visible = motion_cfg.get("visible")
    if visible is not None:
        vpath = f"{path}.visible"
        if not isinstance(visible, dict):
            errors.append(ValidationError(f"visible precisa ser objeto "
                                          f"{{from, to}}: {visible!r}", vpath))
        else:
            _unknown_keys(visible, VISIBLE_KEYS, vpath, errors)
            for key in ("from", "to"):
                if key in visible:
                    _validate_anchor(visible[key], f"{vpath}.{key}", errors)

    actions = motion_cfg.get("actions")
    if actions is None:
        errors.append(ValidationError("motion sem 'actions'", path))
        return errors
    if not isinstance(actions, (list, tuple)):
        errors.append(ValidationError(f"actions precisa ser lista: {actions!r}",
                                      f"{path}.actions"))
        return errors
    if not actions:
        errors.append(ValidationError("actions vazia", f"{path}.actions"))
        return errors

    names: list = []
    for i, action in enumerate(actions):
        apath = f"{path}.actions[{i}]"
        if not isinstance(action, dict):
            errors.append(ValidationError(f"ação precisa ser objeto: {action!r}",
                                          apath))
            continue

        _unknown_keys(action, ACTION_KEYS, apath, errors)

        preset = action.get("preset")
        if preset is not None and preset not in presets.PRESETS:
            errors.append(ValidationError(f"preset inexistente: {preset!r}",
                                          f"{apath}.preset",
                                          _hint(preset, presets.NAMES)))

        tracks = action.get("tracks")
        if tracks is not None:
            _validate_tracks(tracks, f"{apath}.tracks", errors)
        elif preset is None:
            errors.append(ValidationError(
                "ação sem 'tracks' e sem 'preset'", apath,
                "declare tracks ou use um preset"))

        ease = action.get("ease")
        if ease is not None and ease not in easing.EASINGS:
            errors.append(ValidationError(f"easing desconhecido: {ease!r}",
                                          f"{apath}.ease", _hint(ease, easing.NAMES)))

        duration = action.get("duration")
        if duration is not None and (not isinstance(duration, (int, float))
                                     or isinstance(duration, bool)
                                     or duration <= 0):
            errors.append(ValidationError(f"duration precisa ser > 0: {duration!r}",
                                          f"{apath}.duration"))

        for key in ("hold", "loop"):
            if key in action and not isinstance(action[key], bool):
                errors.append(ValidationError(f"{key} precisa ser booleano: "
                                              f"{action[key]!r}", f"{apath}.{key}"))

        if "sfx" in action:
            _validate_sfx(action["sfx"], f"{apath}.sfx", errors)

        if "at" in action:
            _validate_anchor(action["at"], f"{apath}.at", errors)
        if "until" in action:
            _validate_anchor(action["until"], f"{apath}.until", errors)

        # `after`/`at_end_of` só pode apontar para uma ação JÁ declarada: olhar
        # para frente abriria ciclo (A espera B que espera A).
        for key in ("at", "until"):
            spec = action.get(key)
            if not isinstance(spec, dict):
                continue
            ref = spec.get("after") or spec.get("at_end_of")
            if ref is None:
                continue
            if ref not in names:
                known = ", ".join(n for n in names if n) or "nenhuma ainda"
                errors.append(ValidationError(
                    f"'{key}.after' aponta para ação inexistente ou posterior: "
                    f"{ref!r}", f"{apath}.{key}",
                    f"ações nomeadas antes desta: {known}"))

        name = action.get("name")
        if name is not None:
            if not isinstance(name, str) or not name.strip():
                errors.append(ValidationError(f"name inválido: {name!r}",
                                              f"{apath}.name"))
            elif name in names:
                errors.append(ValidationError(f"nome de ação duplicado: {name!r}",
                                              f"{apath}.name"))
        names.append(name)

    return errors


def check(motion_cfg, path: str = "motion"):
    """Levanta o primeiro erro encontrado (uso normal no render)."""
    errors = validate(motion_cfg, path)
    if errors:
        if len(errors) > 1:
            extra = "; ".join(str(e) for e in errors[1:4])
            raise ValidationError(f"{errors[0].message} [+{len(errors) - 1} "
                                  f"outro(s): {extra}]", errors[0].path,
                                  errors[0].hint)
        raise errors[0]
