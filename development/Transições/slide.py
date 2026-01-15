import math
import numpy as np
from PIL import Image, ImageFilter
from moviepy.editor import *

# ==========================================
# CONFIGURAÇÕES
# ==========================================
IMG_1 = "1.png"
IMG_2 = "2.png"
OUTPUT_FILE = "slide.mp4"

# Escolha a direção: "up", "down", "left", "right"
DIRECTION = "left"

# Configuração do Desfoque (Backdrop)
BLUR_RADIUS = 30         # Intensidade do borrão no fundo

# Resolução do vídeo
WIDTH, HEIGHT = 720, 1280

# Tempos
DURATION_IMG = 0.5       # Tempo estático inicial
IMPULSE_TIME = 0.3       # Estágio 1: Tempo do "Recuo/Impulso"
TRANSITION_TIME = 0.15   # Estágio 2: Tempo do Slide rápido
SHAKE_TIME = 3.0         # Estágio 3: Tempo balançando

# Configuração da Física
IMPULSE_AMPLITUDE = 100   # Pixels de recuo (impulso)
SHAKE_AMPLITUDE = 150     # Pixels de overshoot (balanço)
SHAKE_FREQ = 10          # Frequência da vibração
SHAKE_DECAY = 4          # Rapidez com que o balanço para, quanto maior, mais rápido para      

# ==========================================
# LÓGICA MATEMÁTICA (Movimento)
# ==========================================

def get_motion_offset(t, target_size):
    t_impulse_start = DURATION_IMG
    t_slide_start   = t_impulse_start + IMPULSE_TIME
    t_shake_start   = t_slide_start + TRANSITION_TIME
    
    if t < t_impulse_start:
        return 0
    elif t < t_slide_start:
        # Fase de Impulso
        local_t = t - t_impulse_start
        progress = local_t / IMPULSE_TIME
        return -IMPULSE_AMPLITUDE * math.sin(progress * (math.pi / 2))
    elif t < t_shake_start:
        # Fase de Slide
        local_t = t - t_slide_start
        progress = local_t / TRANSITION_TIME
        start_pos = -IMPULSE_AMPLITUDE
        end_pos = target_size
        return start_pos + (end_pos - start_pos) * progress
    else:
        # Fase de Balanço
        dt = t - t_shake_start
        if dt > SHAKE_TIME:
            return target_size
        shake_offset = SHAKE_AMPLITUDE * math.sin(dt * SHAKE_FREQ) * math.exp(-SHAKE_DECAY * dt)
        return target_size + shake_offset

# ==========================================
# GERAÇÃO DO FUNDO BORRADO
# ==========================================

def create_blurred_backdrop(image_path, width, height, radius):
    """
    Cria um ImageClip estático e borrado para servir de fundo.
    """
    print(f"Gerando fundo desfocado (Radius={radius})...")
    
    # 1. Abrir imagem com PIL
    pil_img = Image.open(image_path)
    
    # 2. Redimensionar (LANCZOS para qualidade)
    pil_img = pil_img.resize((width, height), Image.LANCZOS)
    
    # 3. Aplicar Blur
    blurred_pil = pil_img.filter(ImageFilter.GaussianBlur(radius=radius))
    
    # 4. Converter para array numpy para o MoviePy
    img_array = np.array(blurred_pil)
    
    return ImageClip(img_array)

# ==========================================
# MONTAGEM
# ==========================================

def create_video():
    print(f"Iniciando Slide Direcional ({DIRECTION}) com Plate Desfocado...")
    
    total_duration = DURATION_IMG + IMPULSE_TIME + TRANSITION_TIME + SHAKE_TIME + 0.5

    # Lógica de Direção (Física)
    if DIRECTION == "down":
        pos_func_out = lambda t: ("center", get_motion_offset(t, HEIGHT))
        pos_func_in  = lambda t: ("center", get_motion_offset(t, HEIGHT) - HEIGHT)
    elif DIRECTION == "up":
        pos_func_out = lambda t: ("center", -get_motion_offset(t, HEIGHT))
        pos_func_in  = lambda t: ("center", -get_motion_offset(t, HEIGHT) + HEIGHT)
    elif DIRECTION == "right":
        pos_func_out = lambda t: (get_motion_offset(t, WIDTH), "center")
        pos_func_in  = lambda t: (get_motion_offset(t, WIDTH) - WIDTH, "center")
    elif DIRECTION == "left":
        pos_func_out = lambda t: (-get_motion_offset(t, WIDTH), "center")
        pos_func_in  = lambda t: (-get_motion_offset(t, WIDTH) + WIDTH, "center")
    else:
        print("Direção inválida.")
        return

    try:
        # 1. Criar Fundo (PLATE) Desfocado
        # Usamos IMG_1 pois é ela que sai e revela o fundo
        bg_blurred = create_blurred_backdrop(IMG_1, WIDTH, HEIGHT, BLUR_RADIUS)
        bg_blurred = bg_blurred.set_duration(total_duration)

        # 2. Criar Clipes Animados (Frente)
        clip1 = ImageClip(IMG_1).resize(newsize=(WIDTH, HEIGHT)).set_duration(total_duration)
        clip2 = ImageClip(IMG_2).resize(newsize=(WIDTH, HEIGHT)).set_duration(total_duration)
        
        # Aplicar movimento
        clip1 = clip1.set_position(pos_func_out)
        clip2 = clip2.set_position(pos_func_in)

        # 3. Compor as camadas
        # [FUNDO BORRADO, IMG_1 (Móvel), IMG_2 (Móvel)]
        final_video = CompositeVideoClip([bg_blurred, clip1, clip2], size=(WIDTH, HEIGHT))
        
        final_video = final_video.set_duration(total_duration)

        print("Renderizando...")
        final_video.write_videofile(OUTPUT_FILE, fps=30, codec="libx264")
        print(f"Vídeo salvo: {OUTPUT_FILE}")
        
    except Exception as e:
        print(f"ERRO: {e}")

if __name__ == "__main__":
    create_video()