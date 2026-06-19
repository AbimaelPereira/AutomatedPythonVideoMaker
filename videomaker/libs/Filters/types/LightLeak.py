"""
LightLeak — light leak cinematográfico estilo filme analógico.

A luz vaza a partir de UMA BORDA da moldura e decai em direção ao centro
(gradiente direcional), não como manchas/bolas radiais. Ao longo da borda há um
"morro" de luz suave que desliza devagar, dando vida sem parecer uma bolha.
Pensado para blend "screen" (a cor desenhada É a luz).

KIND = "overlay" → o engine compõe o clip gerado por cima via screen blend.

Parâmetros (JSON):
  intensity — brilho geral da luz
  size      — quão FUNDO a luz entra a partir da borda (profundidade)
  speed     — velocidade do deslize/pulsação
  count     — quantos vazamentos (cada um numa borda)
  palette   — cores da luz
"""
import random

import numpy as np
from moviepy.editor import VideoClip
from PIL import Image

from libs.Filters.utils import FILTER_SCALE, hex_to_rgb

KIND = "overlay"


def build(cfg: dict, resolution, duration: float) -> VideoClip:
    W, H = resolution
    sw, sh = max(1, int(W * FILTER_SCALE)), max(1, int(H * FILTER_SCALE))

    speed_mult = float(cfg.get("speed", 1.0))
    intensity_mult = float(cfg.get("intensity", 0.8))
    size_mult = float(cfg.get("size", 1.0))
    num_leaks = int(cfg.get("count", 2))

    default_palette = [
        (255, 150, 40),
        (255, 190, 80),
        (255, 120, 20),
    ]
    raw_palette = cfg.get("palette")
    palette = [hex_to_rgb(c) for c in raw_palette] if raw_palette else default_palette

    # Coordenadas normalizadas [0,1] da grade de baixa-res.
    yy, xx = np.mgrid[0:sh, 0:sw].astype(np.float32)
    nx = xx / max(1, sw - 1)
    ny = yy / max(1, sh - 1)

    leaks = []
    for i in range(num_leaks):
        edge = random.choice(["left", "right", "top", "bottom"])
        color = np.array(random.choice(palette), dtype=np.float32)
        # Profundidade: fração da tela que a luz penetra a partir da borda.
        # size_mult escala isso. ~0.25–0.45 da tela por padrão.
        depth = random.uniform(0.25, 0.45) * size_mult
        speed = random.uniform(0.15, 0.4) * speed_mult
        phase = random.uniform(0, 2 * np.pi)
        # Centro do "morro" de luz ao longo da borda e sua largura.
        band_center = random.uniform(0.3, 0.7)
        band_width = random.uniform(0.35, 0.6)
        # Direção e velocidade da DERIVA ao longo da borda: o morro percorre a
        # borda de uma ponta à outra (não só oscila no lugar).
        drift_dir = random.choice([1.0, -1.0])
        drift_speed = random.uniform(0.06, 0.14) * speed_mult
        leaks.append({
            "edge": edge, "color": color, "depth": max(0.05, depth),
            "speed": speed, "phase": phase,
            "band_center": band_center, "band_width": band_width,
            "drift_dir": drift_dir, "drift_speed": drift_speed,
        })

    def draw_leak(t):
        light = np.zeros((sh, sw, 3), dtype=np.float32)

        for lk in leaks:
            pulse = 0.55 + 0.45 * np.sin(t * lk["speed"] * 4 + lk["phase"])
            brightness = intensity_mult * 0.7 * pulse
            if brightness <= 0.01:
                continue

            # 1) Gradiente de PROFUNDIDADE: forte na borda → 0 rumo ao centro.
            #    depth_axis vai de 0 (na borda) a 1 (na borda oposta).
            if lk["edge"] == "left":
                depth_axis = nx
            elif lk["edge"] == "right":
                depth_axis = 1.0 - nx
            elif lk["edge"] == "top":
                depth_axis = ny
            else:  # bottom
                depth_axis = 1.0 - ny
            # Decaimento exponencial: luz concentrada perto da borda.
            depth_falloff = np.exp(-depth_axis / lk["depth"])

            # 2) Variação ao longo da borda: um "morro" gaussiano que SE MOVE
            #    com direção (deriva contínua de uma ponta à outra) + uma leve
            #    oscilação por cima, pra dar vida sem ficar mecânico.
            if lk["edge"] in ("left", "right"):
                along = ny
            else:
                along = nx
            # Deriva direcional: percorre [-0.3, 1.3] em loop e reentra suave.
            drift = (lk["band_center"] + lk["drift_dir"] * t * lk["drift_speed"]) % 1.6 - 0.3
            center = drift + 0.12 * np.sin(t * lk["speed"] * 2 + lk["phase"])
            band = np.exp(-((along - center) ** 2) / (2.0 * lk["band_width"] ** 2))

            falloff = depth_falloff * band
            light += falloff[..., None] * lk["color"][None, None, :] * brightness

        # Clamp translúcido: nunca estoura para branco sólido.
        light = np.clip(light, 0, 190).astype(np.uint8)

        img = Image.fromarray(light, "RGB")
        img = img.resize((W, H), Image.BILINEAR)
        return np.array(img)

    # Sem máscara: o RGB é a luz. Composição via blend "screen" no engine.
    return VideoClip(draw_leak, duration=duration)
