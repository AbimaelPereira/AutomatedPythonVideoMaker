"""
FiltersEngine — aplica filtros visuais ao fundo da cena.
Substitui 'overlays' por 'background.filters'. Implementa 'particles'.
"""
from typing import Dict, Tuple, Optional
from moviepy.editor import VideoClip
import random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def _hex_to_rgb(hex_value):
    if not isinstance(hex_value, str):
        return tuple(hex_value)
    hex_value = hex_value.lstrip('#')
    try:
        if len(hex_value) == 6:
            return tuple(int(hex_value[i:i+2], 16) for i in (0, 2, 4))
    except ValueError:
        pass
    return (255, 255, 255)


def _clamp01(x: float) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except Exception:
        return 0.0


def _lerp(x01: float, a: float, b: float) -> float:
    return a + (b - a) * _clamp01(x01)


class FiltersEngine:
    def __init__(self, resolution: Tuple[int, int]):
        self.resolution = tuple(map(int, resolution))  # (W, H)

    def create_filters_clip(self, filters_config: Dict, duration: float) -> Optional[VideoClip]:
        if not filters_config or not isinstance(filters_config, dict):
            return None

        particles_cfg = filters_config.get("particles")
        if isinstance(particles_cfg, dict):
            return self._build_particles(particles_cfg, duration)

        return None

    def _build_particles(self, cfg: Dict, duration: float) -> Optional[VideoClip]:
        try:
            W, H = self.resolution

            opacity = float(cfg.get("opacity", 0.8))
            color = cfg.get("color", (255, 255, 255))
            if isinstance(color, str):
                color = _hex_to_rgb(color)
            color = tuple(int(c) for c in color)

            blur_radius = float(cfg.get("blur_radius", 3.0))
            axis_ratio_range = cfg.get("axis_ratio_range", [0.8, 1.3])
            if (not isinstance(axis_ratio_range, (list, tuple))) or len(axis_ratio_range) != 2:
                axis_ratio_range = [0.8, 1.3]
            axis_min, axis_max = float(axis_ratio_range[0]), float(axis_ratio_range[1])

            base_density = cfg.get("density")
            base_speed = cfg.get("speed")
            base_size = cfg.get("size")

            if cfg.get("intensity") is not None:
                it = _clamp01(float(cfg["intensity"]))
                if base_density is None:
                    base_density = it
                if base_speed is None:
                    base_speed = it
                if base_size is None:
                    base_size = it

            density = _clamp01(base_density if base_density is not None else 0.7)
            speed01 = _clamp01(base_speed if base_speed is not None else 0.6)
            size01 = _clamp01(base_size if base_size is not None else 0.6)

            movement = (cfg.get("movement") or "scatter").strip().lower()
            if movement not in ("scatter", "float", "fall"):
                movement = "scatter"

            min_speed_default = int(_lerp(speed01, 10, 50))
            max_speed_default = int(_lerp(speed01, 40, 160))

            min_size_default = int(_lerp(size01, 6, 18))
            max_size_default = int(_lerp(size01, 14, 48))

            area_factor = (W * H) / (1080 * 1920)
            num_default = int(_lerp(density, 80, 600) * max(0.3, area_factor))
            num_particles = int(cfg.get("num_particles", num_default))

            if "speed_range" in cfg and isinstance(cfg["speed_range"], (list, tuple)) and len(cfg["speed_range"]) == 2:
                min_speed, max_speed = int(cfg["speed_range"][0]), int(cfg["speed_range"][1])
            else:
                min_speed, max_speed = min_speed_default, max_speed_default

            if "size_range" in cfg and isinstance(cfg["size_range"], (list, tuple)) and len(cfg["size_range"]) == 2:
                min_size, max_size = int(cfg["size_range"][0]), int(cfg["size_range"][1])
            else:
                min_size, max_size = min_size_default, max_size_default

            max_opacity = max(0.1, min(1.0, float(opacity)))
            opacity_range = (0.10, max_opacity)

            seed = cfg.get("seed")
            if seed is None:
                seed = random.randint(1, 10**6)
            rng = np.random.default_rng(int(seed))

            px = rng.random(num_particles) * W
            py = rng.random(num_particles) * H

            base_sizes = rng.integers(max(1, min_size), max(min_size + 1, max_size + 1), size=num_particles)
            opas = rng.random(num_particles) * (opacity_range[1] - opacity_range[0]) + opacity_range[0]

            axis_ratios = rng.random(num_particles) * (axis_max - axis_min) + axis_min
            widths = (base_sizes * axis_ratios).astype(int)
            heights = (base_sizes / np.maximum(1e-3, axis_ratios)).astype(int)

            mags = rng.integers(max(1, min_speed), max(min_speed + 1, max_speed + 1), size=num_particles)
            angles = rng.random(num_particles) * 2.0 * np.pi

            vx = (mags * np.cos(angles)).astype(float)
            vy = (mags * np.sin(angles)).astype(float)

            phases = None
            if movement == "float":
                phases = rng.random(num_particles) * 2.0 * np.pi

            if movement == "fall":
                vy = np.abs(vy)
                vx = vx * 0.2

            def make_color_frame(t):
                # RGB (sem alpha, máscara aplicada separadamente)
                img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)

                if phases is not None:
                    sin_t = np.sin((t + np.arange(num_particles)) * 0.7 + phases)
                    cos_t = np.cos((t + np.arange(num_particles)) * 0.6 + phases)
                    xs = (px + vx * t + 20 * sin_t) % W
                    ys = (py + vy * t + 20 * cos_t) % H
                else:
                    xs = (px + vx * t) % W
                    ys = (py + vy * t) % H

                for i in range(num_particles):
                    half_w = int(max(1, widths[i] // 2))
                    half_h = int(max(1, heights[i] // 2))
                    alpha = int(opas[i] * 255)
                    bbox = [int(xs[i] - half_w), int(ys[i] - half_h), int(xs[i] + half_w), int(ys[i] + half_h)]
                    draw.ellipse(bbox, fill=(color[0], color[1], color[2], alpha))

                if blur_radius > 0:
                    img = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
                # Retorna RGB uint8
                return np.array(img.convert("RGB"), dtype=np.uint8)

            def make_mask_frame(t):
                mask_img = Image.new("L", (W, H), 0)
                draw_m = ImageDraw.Draw(mask_img)

                if phases is not None:
                    sin_t = np.sin((t + np.arange(num_particles)) * 0.7 + phases)
                    cos_t = np.cos((t + np.arange(num_particles)) * 0.6 + phases)
                    xs = (px + vx * t + 20 * sin_t) % W
                    ys = (py + vy * t + 20 * cos_t) % H
                else:
                    xs = (px + vx * t) % W
                    ys = (py + vy * t) % H

                for i in range(num_particles):
                    half_w = int(max(1, widths[i] // 2))
                    half_h = int(max(1, heights[i] // 2))
                    alpha = int(opas[i] * 255)
                    bbox = [int(xs[i] - half_w), int(ys[i] - half_h), int(xs[i] + half_w), int(ys[i] + half_h)]
                    draw_m.ellipse(bbox, fill=alpha)

                if blur_radius > 0:
                    mask_img = mask_img.filter(ImageFilter.GaussianBlur(radius=blur_radius))

                mask_arr = np.array(mask_img, dtype=np.uint8) / 255.0  # float 0..1
                return mask_arr

            color_clip = VideoClip(make_color_frame, duration=float(duration))
            mask_clip = VideoClip(make_mask_frame, duration=float(duration), ismask=True)
            return color_clip.set_mask(mask_clip)

        except Exception as e:
            print(f"[FiltersEngine] ❌ Falha ao construir partículas: {e}")
            return None