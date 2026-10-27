"""Efeitos sonoros sincronizados com as animações (`motion`) da cena.

O Motion já sabe o instante exato de cada ação (inclusive as ancoradas numa
palavra da narração). Este módulo só junta esses instantes com um som e mistura
tudo na faixa de narração da cena ANTES do render — assim os dois caminhos
(ffmpeg e MoviePy) recebem o mesmo áudio sem saber que SFX existe.

De onde vem o som de uma ação, em ordem:

1. `sfx` declarado na própria ação (`"sfx": false` desliga só ela);
2. `global_settings.sfx.presets[<preset>]` — padrões com curinga (`slide_in_*`);
   ação sem preset casa com a chave `"custom"`.

Também aceita eventos avulsos na cena, sem animação:

    "sfx": { "events": [ { "at": {"word": "dark"}, "source": "assets/sfx/boom" } ] }

`source` é arquivo ou pasta (sorteio determinístico por cena, para o mesmo JSON
soar igual em todo render). Dois eventos da MESMA origem (arquivo ou pasta) a menos de `min_gap`
segundos viram um só — elementos que entram juntos (pílula + texto) não dobram
o volume.
"""

import fnmatch
import hashlib
import math
import os

AUDIO_EXTS = (".wav", ".mp3", ".ogg", ".m4a", ".flac", ".aac")

DEFAULTS = {
    "enabled": True,
    "volume": 0.7,       # multiplicador global, aplicado sobre o volume de cada evento
    "min_gap": 0.08,
    "presets": {},
}


def sfx_settings(effective_gs: dict = None, scene: dict = None) -> dict:
    """`sfx` efetivo: defaults < global_settings < cena."""
    from libs.utils import deep_merge

    cfg = dict(DEFAULTS)
    for layer in ((effective_gs or {}).get("sfx"), (scene or {}).get("sfx")):
        if isinstance(layer, dict):
            cfg = deep_merge(cfg, layer)
        elif layer is False:
            cfg["enabled"] = False
    return cfg


def _normalize(spec):
    """str | {source, volume, offset} → dict, ou None."""
    if not spec:
        return None
    if isinstance(spec, str):
        return {"source": spec}
    if isinstance(spec, dict) and spec.get("source"):
        return dict(spec)
    return None


def _preset_spec(preset: str, presets: dict):
    key = preset or "custom"
    if key in presets:
        return presets[key]
    for pattern, spec in presets.items():
        if fnmatch.fnmatch(key, pattern):
            return spec
    return None


def _pick_file(source: str, seed: str):
    if os.path.isfile(source):
        return source
    if not os.path.isdir(source):
        return None
    files = sorted(f for f in os.listdir(source) if f.lower().endswith(AUDIO_EXTS))
    if not files:
        return None
    index = int(hashlib.md5(seed.encode()).hexdigest(), 16) % len(files)
    return os.path.join(source, files[index])


def collect_events(*, scene: dict, effective_gs: dict, scene_duration: float,
                   words: list = None) -> list:
    """`[(t, arquivo, volume)]` da cena, ordenados e deduplicados."""
    cfg = sfx_settings(effective_gs, scene)
    if not cfg.get("enabled", True):
        return []
    presets = cfg.get("presets") or {}
    master = float(cfg.get("volume", 1.0))
    scene_id = str((scene or {}).get("id", "cena"))
    raw = []    # (t, source, volume, seed)

    elements = [el for el in (scene or {}).get("visual_elements") or [] if isinstance(el, dict)]
    if any(el.get("motion") for el in elements):
        from libs.Motion import motion_defaults, resolve_scene_motion
        # O instante de uma ação não depende da caixa (ela só converte x/y em "%"),
        # então uma caixa nominal basta e o SFX não precisa esperar o layout.
        boxes = [(0, 0, 100, 100)] * len(elements)
        timelines = resolve_scene_motion(
            scene=scene, elements=elements, boxes=boxes, resolution=(1920, 1080),
            scene_duration=float(scene_duration), words=words,
            defaults=motion_defaults(effective_gs, scene),
        )
        for i, timeline in enumerate(timelines):
            if timeline is None:
                continue
            for action in timeline.actions:
                if action.get("sfx") is False:
                    continue
                spec = _normalize(action.get("sfx")) or \
                    _normalize(_preset_spec(action.get("preset"), presets))
                if not spec:
                    continue
                t = action["start"] + float(spec.get("offset", 0.0))
                raw.append((t, spec["source"], float(spec.get("volume", 1.0)) * master,
                            f"{scene_id}:{i}:{action['index']}"))

    events = cfg.get("events") or []
    if events:
        from libs.Motion import AnchorResolver, narration_text_of
        resolver = AnchorResolver(words=words, narration_text=narration_text_of(scene),
                                  scene_duration=float(scene_duration), on_missing="skip")
        for n, ev in enumerate(events):
            spec = _normalize(ev)
            if not spec:
                continue
            t = resolver.resolve(ev.get("at", 0.0), path=f"sfx.events[{n}].at")
            if t is None:
                print(f"[SFX] ⚠️ evento {n} da cena '{scene_id}' sem âncora resolvida — ignorado")
                continue
            raw.append((t + float(spec.get("offset", 0.0)), spec["source"],
                        float(spec.get("volume", 1.0)) * master, f"{scene_id}:ev{n}"))

    kept = []    # (t, source, path, volume) — dedup pela ORIGEM: dois elementos
    gap = float(cfg.get("min_gap", 0.08))   # da mesma pasta no mesmo instante são um som só
    for t, source, volume, seed in sorted(raw):
        path = _pick_file(source, seed)
        if not path:
            print(f"[SFX] ⚠️ som não encontrado: {source}")
            continue
        t = max(0.0, min(t, float(scene_duration)))
        dup = next((k for k, e in enumerate(kept) if e[1] == source and abs(e[0] - t) < gap), None)
        if dup is not None:
            e = kept[dup]
            kept[dup] = (e[0], e[1], e[2], max(e[3], volume))
            continue
        kept.append((t, source, path, volume))
    return [(t, path, volume) for t, _, path, volume in kept]


def mix(*, narration_path: str, events: list, scene_duration: float, out_path: str) -> str:
    """Narração + eventos → WAV com a duração da cena. Devolve `out_path`."""
    from pydub import AudioSegment

    length_ms = int(math.ceil(float(scene_duration) * 1000))
    if narration_path and os.path.exists(narration_path):
        base = AudioSegment.from_file(narration_path)
    else:
        base = AudioSegment.silent(duration=length_ms, frame_rate=44100)
    if len(base) < length_ms:
        base = base + AudioSegment.silent(duration=length_ms - len(base), frame_rate=base.frame_rate)

    cache = {}
    for t, path, volume in events:
        if volume <= 0:
            continue
        if path not in cache:
            seg = AudioSegment.from_file(path)
            cache[path] = seg.set_frame_rate(base.frame_rate).set_channels(base.channels)
        seg = cache[path].apply_gain(20 * math.log10(volume))
        base = base.overlay(seg, position=int(t * 1000))

    base.export(out_path, format="wav")
    return out_path


def scene_sfx_mix(*, scene: dict, effective_gs: dict, scene_duration: float,
                  narration_path: str, words: list, scene_dir: str, scene_id: str):
    """Ponto de entrada do engine: caminho do WAV mixado, ou None se a cena não tem SFX."""
    events = collect_events(scene=scene, effective_gs=effective_gs,
                            scene_duration=scene_duration, words=words)
    if not events:
        return None
    out = os.path.join(scene_dir, f"{scene_id}_sfx_mix.wav")
    mix(narration_path=narration_path, events=events,
        scene_duration=scene_duration, out_path=out)
    resumo = ", ".join(f"{t:.2f}s {os.path.basename(p)}" for t, p, _ in events)
    print(f"[SFX] cena '{scene_id}': {len(events)} efeito(s) — {resumo}")
    return out
