"""Sintetiza a parte própria da biblioteca de SFX em assets/sfx/ (whoosh, chime, swell, paper).
Determinístico (seed fixa): rodar de novo gera os mesmos arquivos. Uso: python3 tools/gerar_sfx.py"""
import os
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt

SR = 44100
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "sfx")
rng = np.random.default_rng(7)


def save(cat, name, x, peak=0.8):
    x = x / (np.max(np.abs(x)) + 1e-9) * peak
    fade = int(0.004 * SR)
    x[:fade] *= np.linspace(0, 1, fade)
    x[-fade:] *= np.linspace(1, 0, fade)
    st = np.stack([x, x], axis=1)
    wavfile.write(os.path.join(OUT, cat, name + ".wav"), SR, (st * 32767).astype(np.int16))


def env_ar(n, attack, release_curve=3.0):
    a = int(n * attack)
    return np.concatenate([np.linspace(0, 1, a) ** 2, np.linspace(1, 0, n - a) ** release_curve])


def bandpass_sweep(noise, f0, f1, q=1.2):
    """Ruído filtrado com centro varrendo de f0 a f1 (blocos de 256 amostras)."""
    out = np.zeros_like(noise)
    blk = 256
    centers = np.geomspace(f0, f1, len(noise) // blk + 1)
    for i, c in enumerate(centers):
        lo, hi = c / (1 + 1 / q), min(c * (1 + 1 / q), SR / 2 - 100)
        sos = butter(2, [lo, hi], btype="band", fs=SR, output="sos")
        seg = noise[max(0, i * blk - 512):(i + 1) * blk]
        out[i * blk:(i + 1) * blk] = sosfilt(sos, seg)[-len(out[i * blk:(i + 1) * blk]):]
    return out


# whoosh — ar passando: ruído com filtro varrendo e envelope suave
for k, (dur, f0, f1, att) in enumerate([(0.45, 400, 3500, 0.55), (0.6, 300, 2500, 0.5), (0.35, 800, 5000, 0.6)], 1):
    n = int(dur * SR)
    x = bandpass_sweep(rng.standard_normal(n), f0, f1) * env_ar(n, att, 2.0)
    save("whoosh", f"whoosh_{k:02d}", x, 0.7)

# chime — sino suave (parciais inarmônicos com decaimento exponencial)
for k, f in enumerate([880.0, 1046.5, 1318.5], 1):
    dur = 2.2
    t = np.arange(int(dur * SR)) / SR
    parts = [(1, 1.0, 1.6), (2.76, 0.35, 2.4), (5.4, 0.18, 3.5), (8.93, 0.08, 5.0)]
    x = sum(a * np.sin(2 * np.pi * f * r * t) * np.exp(-d * t) for r, a, d in parts)
    x *= np.minimum(1, t / 0.004)
    save("chime", f"chime_{k:02d}", x, 0.6)

# swell — subida grave e macia (seno com vibrato + ruído grave), para palavra de impacto
for k, (f, dur) in enumerate([(55.0, 1.4), (73.4, 1.1)], 1):
    n = int(dur * SR)
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * f * t + 0.3 * np.sin(2 * np.pi * 5 * t)) + 0.5 * np.sin(2 * np.pi * 2 * f * t)
    sos = butter(2, 400, btype="low", fs=SR, output="sos")
    rumble = sosfilt(sos, rng.standard_normal(n)) * 0.6
    e = np.concatenate([np.linspace(0, 1, int(n * 0.7)) ** 2, np.linspace(1, 0, n - int(n * 0.7)) ** 1.5])
    save("swell", f"swell_{k:02d}", (tone + rumble) * e, 0.75)

# paper — folha deslizando: ruído rosado agudo em rajadas curtas
for k, dur in enumerate([0.35, 0.5], 1):
    n = int(dur * SR)
    white = rng.standard_normal(n)
    sos = butter(2, [1500, 9000], btype="band", fs=SR, output="sos")
    grain = sosfilt(sos, white) * (0.6 + 0.4 * np.abs(sosfilt(butter(1, 30, fs=SR, output="sos"), rng.standard_normal(n))) * 8)
    save("paper", f"paper_{k:02d}", grain * env_ar(n, 0.3, 1.5), 0.55)
print("ok", OUT)
