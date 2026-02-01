"""
FiltersEngine — aplica filtros visuais ao fundo da cena.
Versão "Organic Light Leak": Luzes arredondadas e difusas nas bordas.
"""
from typing import Dict, Tuple, Optional
from moviepy.editor import VideoClip
import numpy as np
import random
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
        Gera Light Leaks orgânicos: Manchas arredondadas que deslizam pelas bordas.
        """
        W, H = self.resolution
        
        # Parâmetros
        speed_mult = float(cfg.get("speed", 0.5))
        intensity_mult = float(cfg.get("intensity", 1.0))
        
        # Paleta "Burn" (Laranja, Vermelho, Dourado)
        palette = [
            (255, 60, 0),    # Vermelho Neon
            (255, 120, 20),  # Laranja
            (255, 180, 50),  # Dourado
            (200, 20, 0)     # Vermelho Sangue
        ]

        # Configuração dos "Atores" (Manchas de luz)
        # Vamos criar 4 a 6 manchas que se comportam independentemente
        num_blobs = 5
        blobs = []

        for i in range(num_blobs):
            # Escolhe uma borda aleatória: 0=Esq, 1=Dir, 2=Topo, 3=Baixo
            edge = random.choice([0, 1, 1, 2, 3]) # Leve preferência por laterais
            
            # Cor aleatória
            color = random.choice(palette)
            
            # Tamanho base (bem grande para parecer luz vazada)
            base_size = random.uniform(W * 0.4, W * 0.8)
            
            # Velocidade e Fase
            speed = random.uniform(0.1, 0.4) * speed_mult
            phase = random.uniform(0, 2 * np.pi)
            
            blobs.append({
                "edge": edge,
                "color": color,
                "base_size": base_size,
                "speed": speed,
                "phase": phase,
                # Posição inicial (offset) ao longo da borda (0.0 a 1.0)
                "offset_start": random.uniform(-0.2, 0.8) 
            })

        def draw_blobs(t, mode="rgb"):
            # Cria imagem preta (vazia)
            img = Image.new("RGB" if mode == "rgb" else "L", (W, H), (0, 0, 0) if mode == "rgb" else 0)
            draw = ImageDraw.Draw(img)

            for b in blobs:
                # Movimento contínuo ao longo do tempo
                # O movimento é linear com um pouco de oscilação senoidal
                progress = (b["offset_start"] + t * b["speed"]) % 1.5 - 0.25 # Vai de -0.25 a 1.25
                
                # Oscilação de tamanho ("respiração")
                pulse = np.sin(t * 1.5 + b["phase"]) 
                current_size = b["base_size"] * (1.0 + 0.2 * pulse)
                radius = current_size / 2

                # Define centro (cx, cy) baseado na borda
                if b["edge"] == 0:   # Esquerda (move verticalmente)
                    cx = 0 - radius * 0.4 # Parcialmente fora da tela
                    cy = H * progress
                elif b["edge"] == 1: # Direita (move verticalmente)
                    cx = W + radius * 0.4
                    cy = H * (1.0 - progress) # Inverso
                elif b["edge"] == 2: # Topo (move horizontalmente)
                    cx = W * progress
                    cy = 0 - radius * 0.4
                else:                # Baixo
                    cx = W * (1.0 - progress)
                    cy = H + radius * 0.4

                # Coordenadas do Bounding Box
                x1, y1 = cx - radius, cy - radius
                x2, y2 = cx + radius, cy + radius

                # Desenhar
                if mode == "rgb":
                    draw.ellipse([x1, y1, x2, y2], fill=b["color"])
                else:
                    # Na máscara, a opacidade varia com o pulso também
                    opacity = int(255 * intensity_mult * (0.6 + 0.4 * pulse)) # Min 60% Max 100%
                    draw.ellipse([x1, y1, x2, y2], fill=opacity)

            # Blur Pesado é o segredo do "Light Leak"
            # Reduz a resolução para o blur ser rápido e depois aumenta (opcional), 
            # mas aqui faremos direto pois são poucos objetos.
            img = img.filter(ImageFilter.GaussianBlur(radius=80)) # Blur muito forte

            return np.array(img)

        # 1. Gerador RGB
        def make_rgb(t):
            return draw_blobs(t, mode="rgb")

        # 2. Gerador Mask (Grayscale / Alpha)
        def make_mask(t):
            mask_arr = draw_blobs(t, mode="mask")
            # Normaliza para 0..1 float
            return mask_arr.astype(np.float64) / 255.0

        # Criação dos Clips Separados (Seguro contra erros de broadcast)
        clip_rgb = VideoClip(make_rgb, duration=duration)
        clip_mask = VideoClip(make_mask, duration=duration, ismask=True)
        
        final_clip = clip_rgb.set_mask(clip_mask)
        return final_clip

    def _build_particles(self, cfg: Dict, duration: float) -> VideoClip:
        # Mantendo o código de partículas original que funciona
        W, H = self.resolution
        density = float(cfg.get("density", 0.5))
        base_speed = float(cfg.get("speed", 0.5))
        size_factor = float(cfg.get("size", 0.5))
        color_hex = cfg.get("color", "#FFFFFF")
        blur_radius = float(cfg.get("blur_radius", 2.0))
        
        rgb = _hex_to_rgb(color_hex)
        num_particles = int(50 * density)
        
        xs = np.random.uniform(0, W, num_particles)
        ys = np.random.uniform(0, H, num_particles)
        vys = np.random.uniform(-50, -10, num_particles) * base_speed
        vxs = np.random.uniform(-10, 10, num_particles) * base_speed
        sizes = np.random.uniform(2, 10, num_particles) * size_factor + 2
        opacities = np.random.uniform(0.3, 0.9, num_particles)
        phases = np.random.uniform(0, 2*np.pi, num_particles)

        def make_frame_rgba(t):
            img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            
            curr_xs = (xs + vxs * t * 60 + np.sin(t * 2 + phases) * 10) % W
            curr_ys = (ys + vys * t * 60) % H
            
            for i in range(num_particles):
                x, y = curr_xs[i], curr_ys[i]
                s = sizes[i]
                o = int(opacities[i] * 255)
                bbox = [x - s, y - s, x + s, y + s]
                draw.ellipse(bbox, fill=(rgb[0], rgb[1], rgb[2], o))
            
            if blur_radius > 0:
                img = img.filter(ImageFilter.GaussianBlur(blur_radius))
            
            return np.array(img)

        clip_rgba = VideoClip(make_frame_rgba, duration=duration)
        return clip_rgba.to_RGB().set_mask(clip_rgba.to_mask())