"""
OverlayEngine
Engine de overlays (efeitos) para o AutomatedPythonVideoMaker.

- Estrutura semelhante às classes existentes (BackgroundVideo, VisualClip)
- Constrói clipes de overlay baseados em configuração JSON em global_settings ou por cena
- Respeita override: cena sobrescreve global

Implementa: 'particles'

Parâmetros em overlays.particles:
- opacity: float (0..1) controla a opacidade máxima por partícula (default: 0.8)
- density: float (0..1) controla quantidade de partículas (default: 0.7)
- speed: float (0..1) controla a velocidade das partículas (default: 0.6)
- size: float (0..1) controla o tamanho geral das partículas (default: 0.6)
- movement: 'scatter' | 'float' | 'fall' (padrão 'scatter')
- color: hex "#RRGGBB" ou tuple (r,g,b) (default: branco)
- blur_radius: float (px), GaussianBlur por frame (default: 3.0)
- axis_ratio_range: [min, max] para ovais (ex.: [0.7, 1.4]) (default: [0.8, 1.3])

Avançado (sobrescreve os mapeamentos automáticos):
- num_particles: int
- speed_range: [min_px_per_s, max_px_per_s]
- size_range: [min_px, max_px]

Compatibilidade:
- intensity (0..1) se presente e density/speed/size ausentes, é usado para os três.
"""
from typing import Dict, Tuple, Optional
from moviepy.editor import VideoClip
import random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

def _hex_to_rgb(hex_value):
    if not isinstance(hex_value, str):
        return hex_value
    hex_value = hex_value.lstrip('#')
    try:
        if len(hex_value) == 6:
            return tuple(int(hex_value[i:i+2], 16) for i in (0, 2, 4))
        else:
            return (255, 255, 255)
    except ValueError:
        return (255, 255, 255)

def _clamp01(x: float) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except Exception:
        return 0.0

def _lerp(x01: float, a: float, b: float) -> float:
    return a + (b - a) * _clamp01(x01)

class OverlayEngine:
    def __init__(self, resolution: Tuple[int, int]):
        self.resolution = tuple(map(int, resolution))  # (W, H)

    def create_overlays_clip(self, overlays_config: Dict, duration: float) -> Optional[VideoClip]:
        """
        Recebe overlays_config (pode conter várias chaves, por enquanto 'particles')
        e retorna um único clip overlay a ser composto sobre o fundo.

        Caso não haja overlays, retorna None.
        """
        if not overlays_config or not isinstance(overlays_config, dict):
            return None

        particles_cfg = overlays_config.get("particles")
        if isinstance(particles_cfg, dict):
            return self._build_particles(particles_cfg, duration)

        return None

    def _build_particles(self, cfg: Dict, duration: float) -> Optional[VideoClip]:
        """
        Constrói o efeito de partículas como VideoClip com máscara de transparência.
        Desenha elipses (ovais) com bordas suavizadas aplicando GaussianBlur por frame.
        """
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
            if axis_min <= 0: axis_min = 0.5
            if axis_max < axis_min: axis_max = axis_min + 0.1

            movement = cfg.get("movement", "scatter")

            # Compat: se intensity for passado e density/speed/size não forem, usamos intensity
            intensity = cfg.get("intensity")
            density = _clamp01(cfg.get("density", intensity if intensity is not None else 0.7))
            speed01 = _clamp01(cfg.get("speed", intensity if intensity is not None else 0.6))
            size01 = _clamp01(cfg.get("size", intensity if intensity is not None else 0.6))

            # Mapeamentos padrão
            # Partículas: 60..1500
            default_num_particles = int(round(_lerp(density, 60, 1500)))
            # Velocidade (px/s)
            min_speed_default = int(round(_lerp(speed01, 10, 120)))      # 10..120
            max_speed_default = int(round(min_speed_default + _lerp(speed01, 60, 200)))  # +60..+200 => ~70..320
            # Tamanho (px)
            min_size_default = int(round(_lerp(size01, 2, 12)))          # 2..12
            max_size_default = int(round(_lerp(size01, 6, 34)))          # 6..34

            # Sobrescritas avançadas (se fornecidas)
            num_particles = int(cfg.get("num_particles", default_num_particles))
            if "speed_range" in cfg and isinstance(cfg["speed_range"], (list, tuple)) and len(cfg["speed_range"]) == 2:
                min_speed, max_speed = int(cfg["speed_range"][0]), int(cfg["speed_range"][1])
            else:
                min_speed, max_speed = min_speed_default, max_speed_default
            if "size_range" in cfg and isinstance(cfg["size_range"], (list, tuple)) and len(cfg["size_range"]) == 2:
                min_size, max_size = int(cfg["size_range"][0]), int(cfg["size_range"][1])
            else:
                min_size, max_size = min_size_default, max_size_default

            # Opacidade por partícula (min 0.10, max=opacity)
            max_opacity = max(0.1, min(1.0, float(opacity)))
            opacity_range = (0.10, max_opacity)

            seed = cfg.get("seed")
            if seed is None:
                seed = random.randint(1, 10**6)
            rng = np.random.default_rng(int(seed))

            # Inicializa partículas: posição, velocidade, tamanho, opacidade, proporção dos eixos
            px = rng.random(num_particles) * W
            py = rng.random(num_particles) * H

            base_sizes = rng.integers(max(1, min_size), max(min_size + 1, max_size + 1), size=num_particles)
            opas = rng.random(num_particles) * (opacity_range[1] - opacity_range[0]) + opacity_range[0]

            axis_ratios = rng.random(num_particles) * (axis_max - axis_min) + axis_min  # ex.: 0.8..1.3
            # Mantém área aproximadamente consistente: width = s * r, height = s / r
            widths = base_sizes * axis_ratios
            heights = np.maximum(2, (base_sizes / axis_ratios))

            # Direções/velocidades
            if movement == "fall":
                vx = rng.normal(0, 10, size=num_particles)           # leve drift horizontal
                vy = rng.integers(max(1, min_speed), max(min_speed + 1, max_speed + 1), size=num_particles)
                phases = None
            elif movement == "float":
                vx = rng.normal(0, 30, size=num_particles)
                vy = rng.normal(0, 30, size=num_particles)
                phases = rng.random(num_particles) * 2 * np.pi
            else:  # scatter (aleatório)
                angles = rng.random(num_particles) * 2 * np.pi
                speeds = rng.integers(max(1, min_speed), max(min_speed + 1, max_speed + 1), size=num_particles)
                vx = np.cos(angles) * speeds
                vy = np.sin(angles) * speeds
                phases = None

            def make_color_frame(t):
                # RGBA transparente
                img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)

                # Atualiza posições e desenha ovais preenchidos
                if phases is not None:
                    # movement == "float"
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

                # Desfoque nas cores (bordas menos definidas)
                if blur_radius > 0:
                    img = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))

                arr = np.array(img, dtype=np.uint8)
                return arr[..., :3]  # RGB sem alpha; alpha virá da máscara

            def make_mask_frame(t):
                # Máscara (L) 0..255
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

                # Desfoque também na máscara para suavizar bordas (soft alpha)
                if blur_radius > 0:
                    mask_img = mask_img.filter(ImageFilter.GaussianBlur(radius=blur_radius))

                mask_arr = np.array(mask_img, dtype=np.uint8) / 255.0
                return mask_arr

            color_clip = VideoClip(make_color_frame, duration=duration).set_fps(24)
            mask_clip = VideoClip(make_mask_frame, ismask=True, duration=duration).set_fps(24)
            return color_clip.set_mask(mask_clip)

        except Exception as e:
            print(f"[OverlayEngine] Falha ao criar partículas: {e}")
            return None