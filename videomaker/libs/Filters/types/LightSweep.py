"""
LightSweep — clarão de luz que VARRE a tela e sai, tipo um holofote/farol
passando pela lente da câmera por alguns segundos.

Diferente do brightness_pulse (brilho uniforme), aqui a luz é uma faixa que se
desloca de uma borda à outra: entra, atravessa o frame e sai pelo lado oposto.
Repete em loop lento a cada `period` segundos.

KIND = "modifier" → clareia o PRÓPRIO clip via screen blend (não tampa a imagem).

Parâmetros (JSON):
  intensity — brilho do clarão (0–1+, ~0.8 default)
  width     — largura da faixa de luz, fração da diagonal (~0.3 default)
  period    — segundos de um ciclo completo (entra→atravessa→sai)
  angle     — graus da direção da varredura; "random" (default) sorteia
  color     — cor do clarão (hex), default branco levemente quente
"""
import random

import numpy as np

from libs.Filters.utils import hex_to_rgb

KIND = "modifier"


def apply(clip, cfg: dict):
    intensity = float(cfg.get("intensity", 0.8))
    width = max(0.02, float(cfg.get("width", 0.3)))
    period = max(0.2, float(cfg.get("period", 4.0)))
    color = np.array(hex_to_rgb(cfg.get("color", "#FFF4E0")), dtype=np.float32) / 255.0

    raw_angle = cfg.get("angle", "random")
    if raw_angle == "random" or raw_angle is None:
        angle = random.uniform(0, 2 * np.pi)
    else:
        angle = np.deg2rad(float(raw_angle))

    w, h = clip.size
    # Projeção de cada pixel sobre o eixo da varredura (direção `angle`),
    # normalizada para [0,1] (0 = primeira borda atingida, 1 = oposta).
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = xx / max(1, w - 1)
    ny = yy / max(1, h - 1)
    proj = nx * np.cos(angle) + ny * np.sin(angle)
    proj_min, proj_max = float(proj.min()), float(proj.max())
    proj = (proj - proj_min) / max(1e-6, (proj_max - proj_min))  # [0,1]

    sigma = width
    # O centro do clarão viaja de -width a 1+width num ciclo, garantindo que
    # entre e saia totalmente da tela (off-screen nas pontas).
    span = 1.0 + 2.0 * width

    def sweep(get_frame, t):
        phase = (t % period) / period          # 0→1 ao longo do ciclo
        center = -width + phase * span          # posição do clarão no eixo
        band = np.exp(-((proj - center) ** 2) / (2.0 * sigma ** 2))  # (h,w)
        light = band[..., None] * color[None, None, :] * intensity   # (h,w,3)

        base = get_frame(t).astype(np.float32) / 255.0
        out = 1.0 - (1.0 - base) * (1.0 - light)   # screen blend
        return (np.clip(out, 0.0, 1.0) * 255.0).astype("uint8")

    return clip.fl(sweep)
