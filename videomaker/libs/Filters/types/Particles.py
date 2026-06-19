"""
Particles — partículas suaves flutuando (poeira/brilhos) sobre o fundo.

KIND = "overlay" → o engine compõe o clip (com máscara alpha) por cima.

Parâmetros (JSON):
  density     — quantidade de partículas (0–1, ~50 partículas em 1.0)
  speed       — velocidade do movimento
  size        — tamanho das partículas
  color       — cor (hex)
  blur_radius — desfoque das partículas
"""
import numpy as np
from moviepy.editor import VideoClip
from PIL import Image, ImageDraw, ImageFilter

from libs.Filters.utils import FILTER_SCALE, hex_to_rgb

KIND = "overlay"


def build(cfg: dict, resolution, duration: float) -> VideoClip:
    W, H = resolution

    # Resolução interna reduzida para o processamento das partículas
    sw, sh = max(1, int(W * FILTER_SCALE)), max(1, int(H * FILTER_SCALE))

    density = float(cfg.get("density", 0.5))
    base_speed = float(cfg.get("speed", 0.5))
    size_factor = float(cfg.get("size", 0.5))
    color_hex = cfg.get("color", "#FFFFFF")
    blur_radius = float(cfg.get("blur_radius", 2.0)) * FILTER_SCALE

    rgb = hex_to_rgb(color_hex)
    num_particles = int(50 * density)

    xs = np.random.uniform(0, sw, num_particles)
    ys = np.random.uniform(0, sh, num_particles)
    vys = np.random.uniform(-50, -10, num_particles) * base_speed * FILTER_SCALE
    vxs = np.random.uniform(-10, 10, num_particles) * base_speed * FILTER_SCALE
    sizes = (np.random.uniform(2, 10, num_particles) * size_factor + 2) * FILTER_SCALE
    opacities = np.random.uniform(0.3, 0.9, num_particles)
    phases = np.random.uniform(0, 2 * np.pi, num_particles)

    def draw_particles(t, mode="rgb"):
        img = Image.new('RGBA', (sw, sh), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        curr_xs = (xs + vxs * t * 60 + np.sin(t * 2 + phases) * 10 * FILTER_SCALE) % sw
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
