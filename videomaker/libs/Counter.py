"""Elemento `counter`: número que anima de `from` até `to`.

Não tem render próprio: cada valor vira um `text_box` com sua janela
`motion.visible`, uma após a outra. Assim os dois backends (ffmpeg e MoviePy),
o preview e o SFX enxergam só `text_box`, sem caminho novo.

    {
      "type": "counter", "from": 300.51, "to": 89.90,
      "start": 1.7,                # s ou âncora ({"word": ...}); default = visible.from
      "duration": 0.7, "ease": "out_expo",
      "steps": 7,                  # nº de trocas; ausente = a cada quadro (máx. 60)
      "format": {"prefix": "R$ ", "suffix": "", "decimals": 2,
                 "decimal": ",", "thousands": "."},
      "sfx": {"source": "assets/sfx/click", "on": "start"},   # ou "each"
      "style": {...}, "placement": {...},
      "motion": {"actions": [...], "visible": {...}}   # tempos absolutos
    }

`visible`/`actions` também são aceitos na raiz do elemento (movidos p/ `motion`).
"""

import copy

from libs.Motion import easing as easing_mod
from libs.Motion.errors import MotionError

FPS = 30
MAX_VALUES = 60
_EDGE_EPS = 1e-3
_COUNTER_KEYS = {"type", "from", "to", "start", "duration", "ease", "easing",
                 "steps", "format", "sfx", "visible", "actions"}


def format_value(value: float, fmt: dict = None) -> str:
    fmt = fmt or {}
    decimals = int(fmt.get("decimals", 0))
    dec_sep = fmt.get("decimal", ",")
    th_sep = fmt.get("thousands", ".")
    text = f"{abs(value):,.{decimals}f}"               # 1,234.56
    text = text.replace(",", "\0").replace(".", dec_sep).replace("\0", th_sep)
    if value < 0 and float(text.replace(th_sep, "").replace(dec_sep, ".") or 0) != 0:
        text = "-" + text
    return f"{fmt.get('prefix', '')}{text}{fmt.get('suffix', '')}"


def _shift(anchor, delta: float, path: str):
    """`anchor` + `delta` segundos (número, "start" ou âncora dict)."""
    if delta == 0:
        return anchor
    if isinstance(anchor, (int, float)) and not isinstance(anchor, bool):
        return round(float(anchor) + delta, 4)
    if isinstance(anchor, str) and anchor.strip().lower() == "start":
        return round(delta, 4)
    if isinstance(anchor, dict):
        out = dict(anchor)
        out["offset"] = round(float(out.get("offset") or 0.0) + delta, 4)
        return out
    raise MotionError(f"counter: 'start' inválido {anchor!r} (use segundos ou âncora)", path)


def _values(el: dict, path: str) -> list:
    """`[(t_relativo, texto)]` sem repetições consecutivas."""
    try:
        v0, v1 = float(el["from"]), float(el["to"])
    except (KeyError, TypeError, ValueError):
        raise MotionError("counter precisa de 'from' e 'to' numéricos", path)
    duration = float(el.get("duration", 1.0))
    if duration < 0:
        raise MotionError("counter: 'duration' precisa ser ≥ 0", f"{path}.duration")
    ease = el.get("ease") or el.get("easing") or "linear"
    if ease not in easing_mod.NAMES:
        raise MotionError(f"counter: easing '{ease}' inexistente "
                          f"(ex.: out_expo, out_cubic, linear)", f"{path}.ease")

    steps = el.get("steps")
    if steps is None:
        steps = min(MAX_VALUES, max(1, round(duration * FPS)))
    steps = max(1, int(steps))
    if duration == 0:
        steps = 1

    out = []
    for k in range(steps + 1):
        p = k / steps
        text = format_value(v0 + (v1 - v0) * easing_mod.apply(ease, p), el.get("format"))
        if out and out[-1][1] == text:
            continue
        out.append((duration * p if k else 0.0, text))
    return out


def expand_counter(el: dict, *, counter_id: str, path: str = "counter") -> tuple:
    """`counter` → (lista de `text_box`, lista de eventos de sfx da cena)."""
    unknown = set(el) - _COUNTER_KEYS - {"style", "placement", "motion", "layout",
                                          "stagger_group", "border_radius", "id"}
    unknown = {k for k in unknown if not str(k).endswith("/")}
    if unknown:
        raise MotionError(f"counter: campos desconhecidos {sorted(unknown)}", path)

    motion = copy.deepcopy(el.get("motion") or {})
    if isinstance(motion, list):
        motion = {"actions": motion}
    if "actions" in el:
        motion["actions"] = copy.deepcopy(el["actions"])
    if "visible" in el:
        motion["visible"] = copy.deepcopy(el["visible"])
    motion.setdefault("actions", [])
    visible = motion.pop("visible", None) or {}

    start = el.get("start")
    if start is None:
        start = visible.get("from", 0.0)

    values = _values(el, path)
    base = {k: copy.deepcopy(v) for k, v in el.items() if k not in _COUNTER_KEYS}
    base["type"] = "text_box"
    base["_counter_id"] = counter_id
    # Caixa fixa + dígitos tabulares: o número não pula/escala a cada troca
    # (ver `_counter_union_bbox` em VisualClip).
    style = dict(base.get("style") or {})
    style.setdefault("tabular_nums", True)
    style.setdefault("align", "center")
    style["_counter_values"] = [text for _, text in values]
    base["style"] = style

    pieces = []
    for i, (t, text) in enumerate(values):
        piece = copy.deepcopy(base)
        piece["content"] = text
        win = {}
        if i == 0:
            if "from" in visible:
                win["from"] = visible["from"]
        else:
            win["from"] = _shift(start, t, f"{path}.start")
        if i + 1 < len(values):
            # `visible` é inclusivo nas duas pontas: sem o recuo, o quadro
            # exatamente na troca mostraria os dois valores sobrepostos.
            win["to"] = _shift(start, values[i + 1][0] - _EDGE_EPS, f"{path}.start")
        elif "to" in visible:
            win["to"] = visible["to"]
        m = copy.deepcopy(motion)
        if win:
            m["visible"] = win
        if m.get("actions") or m.get("visible"):
            piece["motion"] = m
        pieces.append(piece)

    events = []
    sfx = el.get("sfx")
    if sfx:
        if isinstance(sfx, str):
            sfx = {"source": sfx}
        source = sfx.get("source") or sfx.get("file")
        if not source:
            raise MotionError("counter: sfx precisa de 'source'", f"{path}.sfx")
        ev = {"source": source}
        for k in ("volume", "offset"):
            if k in sfx:
                ev[k] = sfx[k]
        on = sfx.get("on", "start")
        # `each` sem `steps` daria um clique por quadro: cai para `start`.
        times = [t for t, _ in values] if (on == "each" and el.get("steps")) else [0.0]
        for t in times:
            events.append({**ev, "at": _shift(start, t, f"{path}.start")})
    return pieces, events


def expand_scene_counters(scene: dict, path: str = "scene") -> None:
    """Expande os `counter` de `scene["visual_elements"]` (in-place)."""
    elements = scene.get("visual_elements")
    if not isinstance(elements, list) or not any(
            isinstance(e, dict) and e.get("type") == "counter" for e in elements):
        return
    new, events = [], []
    for i, el in enumerate(elements):
        if isinstance(el, dict) and el.get("type") == "counter":
            pieces, evs = expand_counter(el, counter_id=f"{path}:{i}",
                                         path=f"{path}.visual_elements[{i}]")
            new.extend(pieces)
            events.extend(evs)
        else:
            new.append(el)
    scene["visual_elements"] = new
    if events:
        sfx = scene.get("sfx")
        if sfx is False:
            return
        sfx = dict(sfx) if isinstance(sfx, dict) else {}
        sfx["events"] = list(sfx.get("events") or []) + events
        scene["sfx"] = sfx


def expand_video_counters(video_data: dict) -> None:
    """Expande todos os `counter` do vídeo (cenas soltas ou capítulos)."""
    for si, scene in enumerate(video_data.get("scenes") or []):
        if isinstance(scene, dict):
            expand_scene_counters(scene, f"scenes[{si}]")
    for ci, chapter in enumerate(video_data.get("chapters") or []):
        for si, scene in enumerate((chapter or {}).get("scenes") or []):
            if isinstance(scene, dict):
                expand_scene_counters(scene, f"chapters[{ci}].scenes[{si}]")
