"""
BrightnessPulse — pulsação suave e contínua de brilho, tipo luz de estádio.

KIND = "modifier" → modifica o PRÓPRIO clip frame a frame (não é uma camada
sobreposta). O brilho oscila por uma senoide ao longo do tempo, indo de `min`
a `max` num ciclo de `period` segundos.

Parâmetros (JSON):
  min    — brilho mínimo do ciclo (1.0 = original; 0.7 = 30% mais escuro)
  max    — brilho máximo do ciclo (1.0 = original; 1.2 = 20% mais claro)
  period — duração em segundos de um ciclo completo da pulsação
"""
import numpy as np

KIND = "modifier"


def apply(clip, cfg: dict):
    lo = float(cfg.get("min", 0.8))
    hi = float(cfg.get("max", 1.15))
    period = max(0.05, float(cfg.get("period", 2.5)))

    mid = (hi + lo) / 2.0
    amp = (hi - lo) / 2.0
    omega = 2.0 * np.pi / period

    def scale_frame(get_frame, t):
        # Senoide começa no meio do ciclo subindo, oscila suavemente lo↔hi.
        factor = mid + amp * np.sin(omega * t)
        frame = get_frame(t).astype(np.float32) * factor
        return np.clip(frame, 0, 255).astype("uint8")

    return clip.fl(scale_frame)
