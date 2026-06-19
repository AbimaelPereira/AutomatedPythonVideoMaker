"""
FilterEngine — despachante de filtros visuais (espelha TransitionEngine /
SubtitleEngine). Cada tipo vive em `libs/Filters/types/` e declara um `KIND`:

  - "overlay"  — gera um clip de luz/partículas composto POR CIMA do clip base
                 (screen blend p/ luz, alpha p/ partículas). Usado no fundo.
  - "modifier" — modifica o PRÓPRIO clip frame a frame (brilho, cor, …).
                 Usado nos visual_elements.

Config no JSON (bloco "filters", um dict tipo→params, mesclável via deep_merge):

  "filters": {
    "light_leak":      { "intensity": 0.8, "count": 2 },   # overlay
    "brightness_pulse":{ "min": 0.75, "max": 1.2, "period": 2.5 }  # modifier
  }

Vários filtros podem coexistir; cada método aplica só os do seu KIND, na ordem
em que aparecem no dict.
"""
from typing import Dict, Optional

import numpy as np
from moviepy.editor import CompositeVideoClip, VideoClip

from libs.Filters.types import BrightnessPulse, LightLeak, LightSweep, Particles

# Registro nome→módulo. Cada módulo expõe KIND e build()/apply().
_FILTERS = {
    "light_leak": LightLeak,
    "particles": Particles,
    "brightness_pulse": BrightnessPulse,
    "light_sweep": LightSweep,
}


def _force_rgb(im):
    if im.ndim == 2:
        return np.dstack((im, im, im))
    if im.shape[2] == 4:
        return im[:, :, :3]
    return im


class FilterEngine:
    def __init__(self, resolution):
        self.resolution = tuple(map(int, resolution))  # (W, H)

    def _items(self, cfg: Dict, kind: str):
        """Filtros válidos de um KIND, na ordem do dict."""
        if not cfg or not isinstance(cfg, dict):
            return []
        out = []
        for name, params in cfg.items():
            mod = _FILTERS.get(name)
            if mod is None:
                print(f"[FilterEngine] ⚠️ Filtro desconhecido '{name}'. Ignorando.")
                continue
            if getattr(mod, "KIND", None) != kind:
                continue
            out.append((name, mod, params if isinstance(params, dict) else {}))
        return out

    def apply(self, clip, cfg: Dict):
        """Aplica filtros KIND='modifier' diretamente no clip (visual_elements)."""
        for name, mod, params in self._items(cfg, "modifier"):
            print(f"[FilterEngine] Aplicando filtro '{name}' (modifier)...")
            clip = mod.apply(clip, params)
        return clip

    def compose(self, bg_clip, cfg: Dict, duration: float):
        """Compõe filtros KIND='overlay' por cima do clip base (fundo).

        Light leak / glow é composto com blend "screen": a luz SEMPRE clareia o
        fundo e nunca o tampa. Partículas usam alpha "over" (CompositeVideoClip).
        """
        overlays = self._items(cfg, "overlay")
        if not overlays:
            return bg_clip.fl_image(_force_rgb)

        for name, mod, params in overlays:
            print(f"[FilterEngine] Compondo filtro '{name}' (overlay)...")
            fclip: Optional[VideoClip] = mod.build(params, self.resolution, float(duration))
            if fclip is None:
                continue

            if name in ("light_leak",):
                bg_clip = bg_clip.fl_image(_force_rgb)

                def screen_blend(get_frame, t, _f=fclip):
                    base = get_frame(t).astype(np.float32) / 255.0
                    leak = _f.get_frame(t).astype(np.float32) / 255.0
                    out = 1.0 - (1.0 - base) * (1.0 - leak)
                    return (np.clip(out, 0.0, 1.0) * 255.0).astype("uint8")

                bg_clip = bg_clip.fl(screen_blend).set_duration(duration)
            else:
                bg_clip = CompositeVideoClip(
                    [bg_clip, fclip], size=self.resolution
                ).set_duration(duration)

        return bg_clip.fl_image(_force_rgb)
