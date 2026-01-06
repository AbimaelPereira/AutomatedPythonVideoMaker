# libs/Overlays.py
"""
Overlays.py
Biblioteca para gerar overlays tipo bokeh, light-leak, blobs radiais e partículas usando MoviePy, NumPy e Pillow.

Funções principais:
- create_radial_blob(...)
- make_bokeh_overlay(...)
- make_light_leak(...)
- make_particles_overlay(...)

Cada função retorna um MoviePy clip (CompositeVideoClip / ImageClip) sem mixar áudio.
"""
from moviepy.editor import ImageClip, CompositeVideoClip, VideoClip
import numpy as np
from PIL import Image, ImageFilter
import math
import random
import os

# Simple cache for generated blob arrays to avoid re-rendering same sizes/colors
_BLOB_CACHE = {}

def _ensure_resolution(resolution):
    if isinstance(resolution, (list, tuple)) and len(resolution) == 2:
        return tuple(map(int, resolution))
    raise ValueError("resolution must be (width, height)")

def create_radial_blob(size_px,
                       color=(255, 200, 150),
                       falloff=3.0,
                       inner_strength=1.0,
                       blur_radius=0,
                       premultiplied=False):
    """
    Cria um ImageClip contendo um blob radial RGBA (com canal alpha suave).
    Retorna um ImageClip (sem duration) que pode ser .set_duration(...) e posicionado.

    Parâmetros:
    - size_px: int, dimensão do quadrado do blob (px). Será garantido ímpar para centralização.
    - color: (r,g,b) 0-255
    - falloff: float - potência do decaimento (maior -> mais concentrado)
    - inner_strength: float (0..1) - controla 'núcleo' (1.0 padrão)
    - blur_radius: float - aplica GaussianBlur (PIL) para suavizar bordas
    - premultiplied: bool - se True, multiplica RGB por alpha (útil para certos blends)
    """
    # Chave de cache
    key = (int(size_px), tuple(color), float(falloff), float(inner_strength), float(blur_radius), bool(premultiplied))
    if key in _BLOB_CACHE:
        arr = _BLOB_CACHE[key]
        return ImageClip(arr, ismask=False, transparent=True)

    # Força tamanho inteiro e ímpar
    res = int(round(size_px))
    if res < 3: res = 3
    if res % 2 == 0: res += 1

    # Coordenadas normalizadas -1..1
    x = np.linspace(-1, 1, res)
    y = np.linspace(-1, 1, res)
    X, Y = np.meshgrid(x, y)
    R = np.sqrt(X**2 + Y**2)  # 0..~1.414 (mas limparemos)

    # Normaliza raio para 0..1
    Rn = np.clip(R / R.max(), 0.0, 1.0)

    # Alpha mask base (1 - r)^power, opcional inner_strength
    alpha = np.clip(1.0 - Rn, 0.0, 1.0)
    alpha = alpha ** falloff
    alpha = alpha * float(inner_strength)
    alpha = np.clip(alpha, 0.0, 1.0)

    # Converte alpha para imagem 0..255
    alpha_u8 = (alpha * 255).astype(np.uint8)

    # Cria imagem RGBA via PIL para aplicar blur se necessário
    rgb_arr = np.zeros((res, res, 3), dtype=np.uint8)
    rgb_arr[:, :, 0] = int(color[0])
    rgb_arr[:, :, 1] = int(color[1])
    rgb_arr[:, :, 2] = int(color[2])

    rgba = np.dstack([rgb_arr, alpha_u8])

    img = Image.fromarray(rgba, mode="RGBA")

    if blur_radius and blur_radius > 0:
        img = img.filter(ImageFilter.GaussianBlur(radius=float(blur_radius)))

    arr_final = np.array(img)  # RGBA

    # Optionally premultiply alpha (may help some blend modes)
    if premultiplied:
        a = (arr_final[:, :, 3:4].astype(np.float32) / 255.0)
        arr_final[:, :, :3] = (arr_final[:, :, :3].astype(np.float32) * a).astype(np.uint8)

    # Cache
    _BLOB_CACHE[key] = arr_final

    return ImageClip(arr_final, ismask=False, transparent=True)

def make_bokeh_overlay(
    duration,
    resolution,
    num_blobs=4,
    base_color=(255, 120, 50),
    color_jitter=30,
    size_range=(0.12, 0.45),
    size_jitter=0.15,
    speed_range=(0.3, 1.2),
    opacity_range=(0.35, 0.85),
    falloff=3.0,
    blur_mean=6.0,
    movement="orbit",
    orbit_radius_factor=(0.45, 0.9),
    seed=None
):
    """
    Gera um CompositeVideoClip contendo múltiplos blobs (bokeh) animados.

    Parâmetros relevantes:
    - duration: float (s)
    - resolution: (w,h)
    - num_blobs: int
    - base_color: RGB tuple
    - color_jitter: int (max variação por canal ±)
    - size_range: (min_frac, max_frac) - fração da largura para dimensionar blob
    - speed_range: factor multiplicador de velocidade
    - opacity_range: (min, max)
    - falloff, blur_mean: para create_radial_blob
    - movement: "orbit" | "drift" | "random"
    - orbit_radius_factor: (min, max) fração das dimensões para determinar órbita
    """
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)

    W, H = _ensure_resolution(resolution)
    clips = []

    for i in range(num_blobs):
        # tamanho em px baseado na largura
        frac = random.uniform(size_range[0], size_range[1])
        size_px = max(8, int(W * frac * (1.0 + random.uniform(-size_jitter, size_jitter))))

        # cor com jitter
        r = int(np.clip(base_color[0] + random.randint(-color_jitter, color_jitter), 0, 255))
        g = int(np.clip(base_color[1] + random.randint(-color_jitter, color_jitter), 0, 255))
        b = int(np.clip(base_color[2] + random.randint(-color_jitter, color_jitter), 0, 255))

        # opacidade
        opacity = random.uniform(opacity_range[0], opacity_range[1])

        # blur
        blur_r = max(0.5, abs(random.gauss(blur_mean, blur_mean * 0.3)))

        blob = create_radial_blob(size_px=size_px,
                                  color=(r, g, b),
                                  falloff=falloff,
                                  inner_strength=1.0,
                                  blur_radius=blur_r)
        blob = blob.set_duration(duration).set_opacity(opacity)

        # movement params
        speed = random.uniform(speed_range[0], speed_range[1])
        phase = random.uniform(0, 2 * math.pi)

        if movement == "orbit":
            # órbita elíptica central com raios proporcionais
            rx = random.uniform(orbit_radius_factor[0], orbit_radius_factor[1]) * W
            ry = random.uniform(orbit_radius_factor[0], orbit_radius_factor[1]) * H
            cx = W / 2.0
            cy = H / 2.0
            # função de posição (top-left do blob)
            def make_orbit(cx, cy, rx, ry, phase, speed, bs):
                return lambda t: (
                    int((cx + rx * math.cos(speed * t + phase)) - bs / 2),
                    int((cy + ry * math.sin(speed * t + phase)) - bs / 2)
                )
            blob = blob.set_position(make_orbit(cx, cy, rx, ry, phase, speed * 0.6, size_px))

        elif movement == "drift":
            # drift linear de um ponto A para B
            start_x = random.uniform(-0.2, 1.2) * W
            start_y = random.uniform(-0.2, 1.2) * H
            end_x = random.uniform(-0.2, 1.2) * W
            end_y = random.uniform(-0.2, 1.2) * H
            def make_drift(sx, sy, ex, ey, dur):
                return lambda t, sx=sx, sy=sy, ex=ex, ey=ey, dur=duration: (
                    int(sx + (ex - sx) * (t / dur)),
                    int(sy + (ey - sy) * (t / dur))
                )
            blob = blob.set_position(make_drift(start_x - size_px/2, start_y - size_px/2, end_x - size_px/2, end_y - size_px/2, duration))

        else:  # random (perlin-like via multi-sin)
            amp_x = random.uniform(0.05, 0.5) * W
            amp_y = random.uniform(0.05, 0.5) * H
            fx = random.uniform(0.2, 1.4) * speed
            fy = random.uniform(0.2, 1.4) * speed
            ox = random.uniform(0, 2 * math.pi)
            oy = random.uniform(0, 2 * math.pi)
            cx = random.uniform(0.2, 0.8) * W
            cy = random.uniform(0.2, 0.8) * H
            def make_random(cx, cy, amp_x, amp_y, fx, fy, ox, oy, bs):
                return lambda t: (
                    int((cx + math.cos(fx * t + ox) * amp_x) - bs/2),
                    int((cy + math.sin(fy * t + oy) * amp_y) - bs/2)
                )
            blob = blob.set_position(make_random(cx, cy, amp_x, amp_y, fx, fy, ox, oy, size_px))

        clips.append(blob)

    if not clips:
        return None
    overlay = CompositeVideoClip(clips, size=(W, H)).set_duration(duration)
    return overlay

def make_particles_overlay(duration,
                           resolution,
                           num_particles=120,
                           color=(255, 220, 200),
                           size_range=(6, 28),
                           speed_range=(10, 120),
                           falloff=2.5,
                           blur_mean=2.5,
                           opacity_range=(0.2, 0.9),
                           movement="fall",
                           seed=None):
    """
    Gera muitas partículas pequenas (cada uma um blob) com movimento simples.
    movement: 'fall' (cai de topo para baixo), 'scatter' (direção aleatória), 'float' (gentle drift)
    """
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)

    W, H = _ensure_resolution(resolution)
    clips = []

    for i in range(num_particles):
        size_px = int(random.uniform(size_range[0], size_range[1]))
        r = int(np.clip(color[0] + random.randint(-20, 20), 0, 255))
        g = int(np.clip(color[1] + random.randint(-20, 20), 0, 255))
        b = int(np.clip(color[2] + random.randint(-20, 20), 0, 255))
        opacity = random.uniform(opacity_range[0], opacity_range[1])
        blur_r = max(0.0, abs(random.gauss(blur_mean, blur_mean*0.5)))

        blob = create_radial_blob(size_px=size_px, color=(r,g,b), falloff=falloff, blur_radius=blur_r)
        blob = blob.set_duration(duration).set_opacity(opacity)

        # initial position
        if movement == "fall":
            start_x = random.uniform(0, W)
            start_y = random.uniform(-0.3 * H, -0.05 * H)
            speed = random.uniform(speed_range[0], speed_range[1])
            def pos_fn(t, sx=start_x, sy=start_y, sp=speed, bs=size_px):
                return (int(sx), int(sy + sp * t))
        elif movement == "scatter":
            sx = random.uniform(0, W)
            sy = random.uniform(0, H)
            angle = random.uniform(0, 2*math.pi)
            sp = random.uniform(speed_range[0], speed_range[1]) * 0.3
            vx = math.cos(angle) * sp
            vy = math.sin(angle) * sp
            def pos_fn(t, sx=sx, sy=sy, vx=vx, vy=vy):
                return (int(sx + vx * t), int(sy + vy * t))
        else:  # float
            sx = random.uniform(0.2*W, 0.8*W)
            sy = random.uniform(0.2*H, 0.8*H)
            ax = random.uniform(10, 60)
            ay = random.uniform(10, 60)
            fx = random.uniform(0.2, 1.0)
            fy = random.uniform(0.2, 1.0)
            def pos_fn(t, sx=sx, sy=sy, ax=ax, ay=ay, fx=fx, fy=fy, bs=size_px):
                return (int(sx + math.sin(fx * t) * ax - bs/2), int(sy + math.cos(fy * t) * ay - bs/2))

        blob = blob.set_position(pos_fn)
        clips.append(blob)

    if not clips:
        return None
    overlay = CompositeVideoClip(clips, size=(W, H)).set_duration(duration)
    return overlay