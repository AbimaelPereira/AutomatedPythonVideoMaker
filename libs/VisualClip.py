import os
import requests
import io
import mimetypes
import numpy as np 
from PIL import Image, ImageDraw, ImageFont
from rembg import remove
from moviepy.editor import *
from libs.LayoutEngine import LayoutEngine

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

    def generate(self):
        el_type = self.data.get("type")
        clip = None

        if el_type == "image":
            clip = self._create_image_clip()
        elif el_type == "video":
            clip = self._create_video_clip()
        elif el_type == "text_box":
            clip = self._create_text_box_clip()

        if not clip:
            return None

        # Apply force_rgb to ALL clips to prevent shape errors
        clip = clip.fl_image(force_rgb)

        # NOVO FLUXO: Aplica rotação e PULA redimensionamento/posicionamento
        layout = self.data.get("layout", {})
        if layout.get("rotation"): clip = clip.rotate(layout["rotation"])

        clip = self._apply_animation(clip)

        return clip

    @staticmethod
    def calculate_text_box_size(data):
        """Calcula o tamanho WxH do text box, incluindo o padding."""
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


    def _get_source_file(self):
        source = self.data.get("source")
        if not source: return None
        
        local_path = source
        if source.startswith(("http:", "https:")):
            try:
                filename = os.path.basename(source.split("?")[0])
                if not filename or "." not in filename:
                    # Padroniza para .png no nome do arquivo cache se a extensão for desconhecida
                    filename = f"asset_{hash(source)}.png" 
                
                local_path = os.path.join(self.temp_dir, filename)
                if not os.path.exists(local_path):
                    response = requests.get(source)
                    response.raise_for_status()
                    if "." not in filename:
                        ext = mimetypes.guess_extension(response.headers.get('content-type'))
                        if ext: local_path += ext
                    with open(local_path, 'wb') as f:
                        f.write(response.content)
            except Exception as e:
                print(f"⚠️ Erro ao baixar asset: {e}")
                return None
        return local_path

    def _create_image_clip(self):
        path = self._get_source_file()
        if not path or not os.path.exists(path): return None
        
        try:
            pil_img = Image.open(path)
            filters = self.data.get("filters", {})
            image_was_processed = False
            
            # 1. Aplica filtros como remove_bg
            if filters.get("remove_bg"):
                print(f"  [VisualClip] Aplicando remove_bg em: {os.path.basename(path)}")
                with open(path, "rb") as i:
                    pil_img = Image.open(io.BytesIO(remove(i.read())))
                image_was_processed = True
            
            # 2. Conversão para RGBA (sempre deve ocorrer para garantir formato de vídeo)
            pil_img = pil_img.convert("RGBA")

            # 3. LÓGICA CORRIGIDA: Sobrescreve a cópia em cache (path)
            # Padroniza o caminho final para .png se o original não for.
            final_path = path
            base_name, ext = os.path.splitext(path)
            
            # Se a extensão original não for PNG, precisamos de um novo nome PNG.
            # Se for PNG, sobrescrevemos.
            if ext.lower() != '.png':
                final_path = base_name + ".png"
                # O arquivo original (ex: .jpg) permanece no cache até ser excluído. 
                # O ImageClip usará o novo .png.

            # Sobrescreve o arquivo final (o cache .png, ou cria um novo .png a partir do .jpg/.webp, etc.)
            pil_img.save(final_path, "PNG")
            
            # O clip será criado a partir do arquivo RGBA/PNG padronizado
            path = final_path 
            
        except Exception as e:
            print(f"⚠️ Erro img: {e}")
            return None

        return ImageClip(path).set_duration(self.duration)

    def _create_video_clip(self):
        path = self._get_source_file()
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
            # bbox retorna (left, top, right, bottom)
            bbox = dummy.textbbox((0,0), content, font=font)
            w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
        except Exception:
            # Fallback para versões mais antigas
            w, h = dummy.textsize(content, font=font)
            bbox = (0, 0, w, h) # Assume 0 offset
            
        pad = style.get("padding", [10, 20]) # [V_pad, H_pad]
        box_w, box_h = w + pad[1]*2, h + pad[0]*2
        
        # 2. Criar Imagem e Desenhar Fundo
        img = Image.new("RGBA", (int(box_w), int(box_h)), (0,0,0,0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([(0,0),(box_w,box_h)], radius=style.get("border_radius",0), fill=style.get("background_color","white"))
        
        # 3. Desenhar Texto (FIX: Ajuste vertical usando bbox[1])
        # X: pad[1] (margem lateral)
        # Y: pad[0] (margem superior) - bbox[1] (offset vertical que PIL/Pillow usa)
        text_y_pos = pad[0] - bbox[1] 

        draw.text((pad[1], text_y_pos), content, font=font, fill=style.get("text_color","black"))
        
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