import math
import numpy as np
from PIL import Image, ImageFilter
from moviepy.editor import *

# ==========================================
# CONFIGURAÇÕES
# ==========================================
IMG_1 = "1.png"
IMG_2 = "2.png"
OUTPUT_FILE = "zoom.mp4"

# Tipo de Zoom: "IN"
ZOOM_TYPE = "IN"
ZOOM_MAX_SCALE = 10.0     

# Configuração do Desfoque (Plate)
BLUR_RADIUS = 30         # Quanto maior, mais borrado o fundo fica

# Resolução Vertical
WIDTH, HEIGHT = 720, 1280

# --- TEMPOS ---
T_STATIC_1    = 0.5   
T_IMPULSE     = 0.4   
T_ZOOM_FLIGHT = 0.5   
T_RETURN      = 0.5   
T_SHAKE       = 1.5   

# --- FÍSICA ---
# No impulso (recuo), a imagem diminui para 0.9 (90%), revelando 10% de fundo
IMPULSE_SCALE  = 0.1     
SHAKE_AMP      = 0.15    
SHAKE_FREQ     = 10.0    
SHAKE_DECAY    = 6.0     

# ==========================================
# LÓGICA DE ANIMAÇÃO
# ==========================================

def ease_in_cubic(t): return t * t * t
def ease_out_cubic(t): return 1 - (1 - t) ** 3

def get_scale_clip1(t):
    t1 = T_STATIC_1
    t2 = t1 + T_IMPULSE
    t3 = t2 + T_ZOOM_FLIGHT
    
    if t < t1:
        return 1.0
    elif t < t2:
        # Fase de Impulso (Encolhe revelando o fundo borrado)
        progress = (t - t1) / T_IMPULSE
        val = math.sin(progress * (math.pi / 2))
        factor = 1.0 - IMPULSE_SCALE if ZOOM_TYPE == "IN" else 1.0 + IMPULSE_SCALE
        return 1.0 + (factor - 1.0) * val
    elif t <= t3:
        # Zoom Disparo
        progress = (t - t2) / T_ZOOM_FLIGHT
        progress = ease_in_cubic(progress)
        start_scale = 1.0 - IMPULSE_SCALE if ZOOM_TYPE == "IN" else 1.0 + IMPULSE_SCALE
        end_scale   = ZOOM_MAX_SCALE      if ZOOM_TYPE == "IN" else 0.1
        return start_scale + (end_scale - start_scale) * progress
    else:
        return ZOOM_MAX_SCALE if ZOOM_TYPE == "IN" else 0.1

def get_scale_clip2(t):
    t_return_end = T_RETURN
    t_shake_end  = T_RETURN + T_SHAKE
    
    if t < t_return_end:
        progress = t / T_RETURN
        progress = ease_out_cubic(progress)
        start_scale = ZOOM_MAX_SCALE if ZOOM_TYPE == "IN" else 0.1
        target_scale = 1.0
        return start_scale + (target_scale - start_scale) * progress
    elif t < t_shake_end:
        dt = t - t_return_end
        direction = -1 if ZOOM_TYPE == "IN" else 1
        oscillation = SHAKE_AMP * math.sin(dt * SHAKE_FREQ) * math.exp(-SHAKE_DECAY * dt)
        return 1.0 + (direction * oscillation)
    else:
        return 1.0

# ==========================================
# GERAÇÃO DO FUNDO BORRADO
# ==========================================

def create_blurred_backdrop(image_path, width, height, radius):
    """
    Abre a imagem, redimensiona para o tamanho do vídeo,
    aplica um Blur pesado e retorna como um ImageClip.
    """
    print("Gerando 'Plate' (Backdrop) com desfoque...")
    
    # 1. Abrir com PIL
    pil_img = Image.open(image_path)
    
    # 2. Redimensionar para o tamanho do vídeo (para garantir cobertura total)
    # Usamos LANCZOS para alta qualidade antes de borrar
    pil_img = pil_img.resize((width, height), Image.LANCZOS)
    
    # 3. Aplicar filtro Gaussiano
    blurred_pil = pil_img.filter(ImageFilter.GaussianBlur(radius=radius))
    
    # 4. Converter para array numpy (formato do MoviePy)
    img_array = np.array(blurred_pil)
    
    return ImageClip(img_array)

# ==========================================
# MONTAGEM
# ==========================================

def create_video():
    print(f"Iniciando vídeo ZOOM com Plate Desfocado (Radius={BLUR_RADIUS})...")

    # Tempos
    cut_point = T_STATIC_1 + T_IMPULSE + T_ZOOM_FLIGHT
    start_clip2_time = cut_point
    duration_clip2 = T_RETURN + T_SHAKE + 0.5
    total_duration = start_clip2_time + duration_clip2

    try:
        # 1. CRIAR O BACKDROP (PLATE)
        # Usamos a IMG_1 como base, já que é ela que vai encolher primeiro.
        backdrop = create_blurred_backdrop(IMG_1, WIDTH, HEIGHT, BLUR_RADIUS)
        backdrop = backdrop.set_duration(total_duration)

        # 2. CLIP 1 (Animado)
        clip1 = ImageClip(IMG_1).resize(newsize=(WIDTH, HEIGHT))
        clip1 = clip1.resize(get_scale_clip1).set_position("center")
        clip1 = clip1.set_duration(cut_point)

        # 3. CLIP 2 (Animado)
        clip2 = ImageClip(IMG_2).resize(newsize=(WIDTH, HEIGHT))
        clip2 = clip2.resize(get_scale_clip2).set_position("center")
        clip2 = clip2.set_start(start_clip2_time).set_duration(duration_clip2)

        # 4. COMPOSIÇÃO
        # O segredo: backdrop fica na camada 0 (fundo), clip1 na camada 1, clip2 na camada 2.
        # Quando clip1 encolher (scale < 1.0), veremos o backdrop atrás.
        final_video = CompositeVideoClip([backdrop, clip1, clip2], size=(WIDTH, HEIGHT))
        
        print("Renderizando vídeo...")
        final_video.write_videofile(OUTPUT_FILE, fps=30, codec="libx264")
        print(f"Sucesso! {OUTPUT_FILE}")

    except Exception as e:
        print(f"ERRO: {e}")

if __name__ == "__main__":
    create_video()