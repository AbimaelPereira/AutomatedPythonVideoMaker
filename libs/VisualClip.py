import os
import requests
import io
import mimetypes
import numpy as np 
from PIL import Image, ImageDraw, ImageFont
from rembg import remove
from moviepy.editor import *
from libs.LayoutEngine import LayoutEngine
# Importa a nova biblioteca de download
from libs.MediaDownloader import MediaDownloader 

# Helper: Force 3-channel RGB
def force_rgb(im):
    return np.dstack((im, im, im)) if im.ndim == 2 else im

class VisualClip:
    def __init__(self, config):
        self.data = config.get("element_data", {})
        self.resolution = config.get("resolution_output", (1080, 1920))
        self.temp_dir = config.get("temp_dir", "output/temp")
        self.duration = config.get("duration", 5.0)
        os.makedirs(self.temp_dir, exist_ok=True)
    
    # [RESOLVE_SOURCE_PATH REMOVIDO DAQUI]

    def generate(self):
        el_type = self.data.get("type")
        clip = None

        if el_type == "image":
            clip = self._create_image_clip()
        elif el_type == "video":
            clip = self._create_video_clip()
        elif el_type == "text_box":
            clip = self._create_text_box_clip()

        if not clip: return None

        # Apply force_rgb to ALL clips to prevent shape errors
        clip = clip.fl_image(force_rgb)

        layout = self.data.get("layout", {})
        if layout.get("rotation"): clip = clip.rotate(layout["rotation"])

        clip = self._apply_animation(clip)

        return clip

    @staticmethod
    def calculate_text_box_size(data):
        # ... (mantido inalterado) ...
        content = data.get("content", "")
        style = data.get("style", {})
        font_family = style.get("font_family", "Arial")
        font_size = style.get("font_size", 50)
        
        font_path = f"fonts/{font_family.split('-')[0]}/{font_family}.ttf"
        if not os.path.exists(font_path): font_path = "fonts/Lato/Lato-Bold.ttf"
        try: font = ImageFont.truetype(font_path, font_size)
        except: font = ImageFont.load_default()

        dummy = ImageDraw.Draw(Image.new("RGBA", (1,1)))
        
        try:
            bbox = dummy.textbbox((0,0), content, font=font)
            w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
        except Exception:
            w, h = dummy.textsize(content, font=font)
            
        pad = style.get("padding", [10, 20]) # [V_pad, H_pad]
        
        box_w, box_h = w + pad[1]*2, h + pad[0]*2
        
        if box_w < 1: box_w = 1 
        if box_h < 1: box_h = 1
        
        return (int(box_w), int(box_h))


    def _create_image_clip(self):
        # *** CHAMADA À NOVA LIB DE DOWNLOAD ***
        path = MediaDownloader.resolve_source_path(self.data.get("source"), self.temp_dir)
        
        print(f"[DEBUG_VC: _create_image_clip] Tentando criar clip a partir de: {path}")
        if not path or not os.path.exists(path): 
            print("[DEBUG_VC: _create_image_clip] Caminho não é válido ou arquivo não existe.")
            return None
        
        try:
            pil_img = Image.open(path)
            filters = self.data.get("filters", {})
            image_was_processed = False
            
            # 1. Aplica filtros como remove_bg
            if filters.get("remove_bg"):
                print(f"[DEBUG_VC] Aplicando remove_bg em: {os.path.basename(path)}")
                with open(path, "rb") as i:
                    pil_img = Image.open(io.BytesIO(remove(i.read())))
                image_was_processed = True
            
            # 2. Conversão para RGBA
            pil_img = pil_img.convert("RGBA")

            # 3. Sobrescreve/Cria cópia PNG para compatibilidade MoviePy
            final_path = path
            base_name, ext = os.path.splitext(path)
            
            if ext.lower() != '.png' or image_was_processed:
                final_path = base_name + ".png"
                
            pil_img.save(final_path, "PNG")
            path = final_path 
            
        except Exception as e:
            print(f"[ERRO DEBUG_VC]: Falha no processamento/ImageClip: {e}")
            return None

        return ImageClip(path).set_duration(self.duration)

    def _create_video_clip(self):
        # *** CHAMADA À NOVA LIB DE DOWNLOAD ***
        path = MediaDownloader.resolve_source_path(self.data.get("source"), self.temp_dir)
        if not path or not os.path.exists(path): return None
        
        clip = VideoFileClip(path)
        
        audio_cfg = self.data.get("audio", {})
        if not audio_cfg.get("keep_audio", False):
            clip = clip.without_audio()
        else:
            clip = clip.volumex(audio_cfg.get("volume", 1.0))
            
        return clip

    def _create_text_box_clip(self):
        content = self.data.get("content", "")
        style = self.data.get("style", {})
        font_family = style.get("font_family", "Arial")
        font_size = style.get("font_size", 50)
        
        font_path = f"fonts/{font_family.split('-')[0]}/{font_family}.ttf"
        if not os.path.exists(font_path): font_path = "fonts/Lato/Lato-Bold.ttf"
        try: font = ImageFont.truetype(font_path, font_size)
        except: font = ImageFont.load_default()

        dummy = ImageDraw.Draw(Image.new("RGBA", (1,1)))
        
        # 1. Calcular BBox e Dimensões
        try:
            bbox = dummy.textbbox((0,0), content, font=font)
            w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
        except Exception:
            w, h = dummy.textsize(content, font=font)
            bbox = (0, 0, w, h) 
            
        pad = style.get("padding", [10, 20]) 
        box_w, box_h = w + pad[1]*2, h + pad[0]*2
        
        # 2. Criar Imagem e Desenhar Fundo
        img = Image.new("RGBA", (int(box_w), int(box_h)), (0,0,0,0))
        draw = ImageDraw.Draw(img)
        
        background_color = style.get("background_color", "white")
        
        if background_color != "transparent":
            draw.rounded_rectangle([(0,0),(box_w,box_h)], radius=style.get("border_radius",0), fill=background_color)
        
        # 3. Desenhar Texto
        # bbox[1] é geralmente negativo ou pequeno, ajustamos para desenhar na linha correta
        text_x_pos = pad[1]
        text_y_pos = pad[0] - bbox[1] 

        text_color = style.get("text_color","black")
        draw.text((text_x_pos, text_y_pos), content, font=font, fill=text_color)
        
        # --- [NOVO] Lógica de Riscado (Strikethrough) ---
        if style.get("strikethrough", False):
            # Calcula a posição Y da linha (aproximadamente no meio da altura visual do texto)
            # O fator 0.6 costuma alinhar melhor visualmente com a 'cintura' das letras
            line_y = pad[0] + (h * 0.6)
            
            # Espessura da linha proporcional ao tamanho da fonte
            line_width = max(2, int(font_size / 15))
            
            # Desenha a linha
            draw.line(
                [(text_x_pos, line_y), (text_x_pos + w, line_y)], 
                fill=text_color, 
                width=line_width
            )
        # -----------------------------------------------
        
        temp_path = os.path.join(self.temp_dir, f"textbox_{id(self)}.png")
        img.save(temp_path)
        return ImageClip(temp_path).set_duration(self.duration)

    def _apply_layout(self, clip):
        layout = self.data.get("layout", {})
        if layout.get("width"):
            w_px = LayoutEngine.calculate_dimension(layout["width"], self.resolution[0])
            clip = clip.resize(width=w_px)
        if layout.get("rotation"): clip = clip.rotate(layout["rotation"])
        
        pos = layout.get("position", "center")
        fx, fy = LayoutEngine.get_position(pos, clip.size, self.resolution, layout.get("margin", 0))
        return clip.set_position((fx, fy))

    def _apply_animation(self, clip):
        anim = self.data.get("animation", {})
        start = float(anim.get("start_at", 0))
        dur = float(anim.get("duration", 1.0)) if anim.get("duration") != "full" else 1.0
        
        clip = clip.set_start(start)
        if anim.get("type") == "fade_in": clip = clip.crossfadein(dur)
        elif anim.get("type") == "zoom_in": clip = clip.resize(lambda t: 1 + 0.1*t)
        
        return clip