"""
FiltersEngine — aplica filtros visuais ao fundo da cena.
Versão "Organic Light Leak": Luzes arredondadas e difusas nas bordas.
"""
from typing import Dict, Tuple, Optional
from moviepy.editor import VideoClip
import numpy as np
import random
from PIL import Image, ImageDraw, ImageFilter

# Fator de downscale para processamento interno dos filtros.
# O blur é aplicado em resolução reduzida e depois o frame é upscalado,
# reduzindo o custo do GaussianBlur em ~16x sem perda visual perceptível.
_FILTER_SCALE = 0.25

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

class FiltersEngine:
    def __init__(self, resolution: Tuple[int, int]):
        self.resolution = tuple(map(int, resolution))  # (W, H)

    def create_filters_clip(self, filters_config: Dict, duration: float) -> Optional[VideoClip]:
        if not filters_config or not isinstance(filters_config, dict):
            return None

        if "particles" in filters_config:
            return self._build_particles(filters_config["particles"], duration)
        
        if "light_leak" in filters_config:
            return self._build_light_leak(filters_config["light_leak"], duration)

        return None

    def _build_light_leak(self, cfg: Dict, duration: float) -> VideoClip:
        """
        Light leak cinematográfico estilo filme analógico: a luz vaza a partir de
        UMA BORDA da moldura e decai em direção ao centro (gradiente direcional),
        não como manchas/bolas radiais. Ao longo da borda há um "morro" de luz suave
        que desliza devagar, dando vida sem parecer uma bolha. Pensado para blend
        "screen" (ver BackgroundEngine._apply_filters): a cor desenhada É a luz.

        Parâmetros (JSON):
          intensity — brilho geral da luz
          size      — quão FUNDO a luz entra a partir da borda (profundidade)
          speed     — velocidade do deslize/pulsação
          count     — quantos vazamentos (cada um numa borda)
          palette   — cores da luz
        """
        W, H = self.resolution
        sw, sh = max(1, int(W * _FILTER_SCALE)), max(1, int(H * _FILTER_SCALE))

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
        palette = [_hex_to_rgb(c) for c in raw_palette] if raw_palette else default_palette

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

        # Sem máscara: o RGB é a luz. Composição via blend "screen" no BackgroundEngine.
        return VideoClip(draw_leak, duration=duration)

    def _build_particles(self, cfg: Dict, duration: float) -> VideoClip:
        W, H = self.resolution

        # Resolução interna reduzida para o processamento das partículas
        sw, sh = max(1, int(W * _FILTER_SCALE)), max(1, int(H * _FILTER_SCALE))

        density = float(cfg.get("density", 0.5))
        base_speed = float(cfg.get("speed", 0.5))
        size_factor = float(cfg.get("size", 0.5))
        color_hex = cfg.get("color", "#FFFFFF")
        blur_radius = float(cfg.get("blur_radius", 2.0)) * _FILTER_SCALE

        rgb = _hex_to_rgb(color_hex)
        num_particles = int(50 * density)

        xs = np.random.uniform(0, sw, num_particles)
        ys = np.random.uniform(0, sh, num_particles)
        vys = np.random.uniform(-50, -10, num_particles) * base_speed * _FILTER_SCALE
        vxs = np.random.uniform(-10, 10, num_particles) * base_speed * _FILTER_SCALE
        sizes = (np.random.uniform(2, 10, num_particles) * size_factor + 2) * _FILTER_SCALE
        opacities = np.random.uniform(0.3, 0.9, num_particles)
        phases = np.random.uniform(0, 2 * np.pi, num_particles)

        def draw_particles(t, mode="rgb"):
            img = Image.new('RGBA', (sw, sh), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            curr_xs = (xs + vxs * t * 60 + np.sin(t * 2 + phases) * 10 * _FILTER_SCALE) % sw
            curr_ys = (ys + vys * t * 60) % sh

            for i in range(num_particles):
                x, y = curr_xs[i], curr_ys[i]
                s = sizes[i]
                o = int(opacities[i] * 255)
                bbox = [x - s, y - s, x + s, y + s]
                draw.ellipse(bbox, fill=(rgb[0], rgb[1], rgb[2], o))

            if blur_radius > 0:
                img = img.filter(ImageFilter.GaussianBlur(blur_radius))

            img = img.resize((W, H), Image.BILINEAR)

            if mode == "rgb":
                return np.array(img.convert("RGB"))
            else:
                return np.array(img.split()[3])  # canal alpha

        def make_rgb(t):
            return draw_particles(t, mode="rgb")

        def make_mask(t):
            return draw_particles(t, mode="mask").astype(np.float64) / 255.0

        clip_rgb = VideoClip(make_rgb, duration=duration)
        clip_mask = VideoClip(make_mask, duration=duration, ismask=True)
        return clip_rgb.set_mask(clip_mask)