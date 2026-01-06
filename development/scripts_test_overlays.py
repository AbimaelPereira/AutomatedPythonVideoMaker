# scripts/test_overlays.py
"""
Script de teste para a libs.Overlays.py
Gera um vídeo de teste com fundo preto (ou imagem estática) e aplica vários overlays.
"""
import os
from moviepy.editor import ColorClip, ImageClip, CompositeVideoClip
from libs.Overlays import make_bokeh_overlay, make_particles_overlay

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def test_all(duration=6.0, resolution=(720, 1280), bg_image_path=None, outname="test_overlay.mp4"):
    W, H = resolution
    if bg_image_path and os.path.exists(bg_image_path):
        bg = ImageClip(bg_image_path).resize(newsize=resolution).set_duration(duration)
    else:
        bg = ColorClip(size=resolution, color=(45, 49, 52), duration=duration)

    # Bokeh overlay
    bokeh = make_bokeh_overlay(
        duration=duration,
        resolution=resolution,
        num_blobs=6,
        base_color=(255,130,80),
        size_range=(0.12, 0.45),
        movement="orbit", # "orbit" | "drift" | "random"
        seed=123
    )

    # Particles
    particles = make_particles_overlay(
        # duration=duration,
        # resolution=resolution,
        # num_particles=800,
        # color=(255,240,220),
        # size_range=(4,18),
        # movement="float", # 'fall' (cai de topo para baixo), 'scatter' (direção aleatória), 'float' (gentle drift)
        # seed=42

        duration=6.0,
        resolution=(720, 1280),
        num_particles=400,
        color=(255,240,220),
        size_range=(4,18),
        movement="scatter",
        speed_range=(20, 180),
        opacity_range=(0.15, 0.85),
        seed=42
    )

    # Compose order: background -> bokeh (behind) -> particles -> leak (on top)
    composite = CompositeVideoClip([
        bg,
        # bokeh,
        particles,
    ],
    size=resolution).set_duration(duration)

    output_path = os.path.join(OUTPUT_DIR, outname)
    print(f"[TEST] Renderizando vídeo de teste em: {output_path}")
    composite.write_videofile(output_path, fps=24, codec="libx264", audio=False, preset="medium")

if __name__ == "__main__":
    test_all(duration=3.0, resolution=(720, 1280), bg_image_path=None)