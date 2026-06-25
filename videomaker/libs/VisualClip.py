import os
import requests
import io
import mimetypes
import numpy as np 
from PIL import Image, ImageDraw, ImageFont
from rembg import remove
from moviepy.editor import *
from libs.LayoutEngine import LayoutEngine
from libs.Filters.utils import hex_to_rgb
# Importa a nova biblioteca de download
from libs.MediaDownloader import MediaDownloader

# Helper: Force 3-channel RGB
def force_rgb(im):
    if im.ndim == 2:
        return np.dstack((im, im, im))
    if im.shape[2] == 4:
        return im[:, :, :3]
    return im

def apply_border_radius_clip(clip, radius: int):
    """Aplica máscara de cantos arredondados a um clip MoviePy. Função standalone."""
    w, h = clip.size
    mask_img = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask_img)
    draw.rounded_rectangle([(0, 0), (w - 1, h - 1)], radius=radius, fill=255)
    mask_arr = np.array(mask_img).astype(float) / 255.0
    mask_clip = ImageClip(mask_arr, ismask=True).set_duration(clip.duration)
    return clip.set_mask(mask_clip)


def _zoom_resize(clip, anim):
    """Aplica zoom dinâmico (resize lambda) — standalone, espelha _make_zoom_clip."""
    anim_type = anim.get("type")
    total = float(clip.duration or 1.0)
    if anim_type == "zoom_in":
        s, e = float(anim.get("start_scale", 1.0)), float(anim.get("end_scale", 1.15))
        return clip.resize(lambda t: s + (e - s) * min(t / total, 1.0))
    if anim_type == "zoom_out":
        s, e = float(anim.get("start_scale", 1.15)), float(anim.get("end_scale", 1.0))
        return clip.resize(lambda t: s + (e - s) * min(t / total, 1.0))
    if anim_type == "zoom_pulse":
        intensity = float(anim.get("intensity", 0.06))
        return clip.resize(lambda t: 1.0 + intensity * np.sin((t / total) * np.pi))
    if anim_type == "fade_zoom_in":
        s, e = float(anim.get("start_scale", 1.0)), float(anim.get("end_scale", 1.12))
        fd = float(anim.get("fade_duration", 0.6))
        clip = clip.resize(lambda t: s + (e - s) * min(t / total, 1.0))
        return clip.crossfadein(fd)
    return clip


def apply_animation_in_window(clip, anim):
    """Aplica animação a um clip MANTENDO seu tamanho fixo (janela).

    Usado no worker após resize+crop no modo cover: o zoom transborda e é
    recortado para o tamanho original, preservando o layout (largura/altura
    do elemento não mudam quadro a quadro). Função standalone.
    """
    if not anim:
        return clip
    anim_type = anim.get("type", "none")
    start = float(anim.get("start_at", 0))
    clip = clip.set_start(start)

    if anim_type == "fade_in":
        return clip.crossfadein(float(anim.get("duration", 1.0)))
    if anim_type in ("zoom_in", "zoom_out", "zoom_pulse", "fade_zoom_in"):
        win_w, win_h = clip.size
        duration = clip.duration
        zoomed = _zoom_resize(clip, anim).set_position("center")
        window = CompositeVideoClip([zoomed], size=(win_w, win_h)).set_duration(duration)
        return window.fl_image(force_rgb)
    return clip


# Chaves de `filters` consumidas pelo VisualClip (não pelo FilterEngine).
_NON_ENGINE_FILTERS = ("remove_bg",)


def apply_visual_filters(clip, filters_cfg):
    """Aplica filtros KIND='modifier' (brightness_pulse, …) e KIND='overlay'
    (light_leak, particles, …) a um clip de visual_element via FilterEngine.
    Ignora chaves do VisualClip (remove_bg). Standalone para ser chamável
    tanto no worker quanto no caminho sequencial."""
    if not filters_cfg or not isinstance(filters_cfg, dict):
        return clip
    engine_cfg = {k: v for k, v in filters_cfg.items() if k not in _NON_ENGINE_FILTERS}
    if not engine_cfg:
        return clip
    from libs.Filters import FilterEngine
    engine = FilterEngine(clip.size)
    clip = engine.apply(clip, engine_cfg)
    clip = engine.compose(clip, engine_cfg, clip.duration)
    return clip


class VisualClip:
    # Extensões consideradas vídeo ao resolver um remote_asset
    _VIDEO_EXTS = ('.mp4', '.mov', '.webm', '.mkv', '.avi', '.gif')

    def __init__(self, config):
        self.data = config.get("element_data", {})
        self.resolution = config.get("resolution_output", (1080, 1920))
        self.temp_dir = config.get("temp_dir", "output/temp")
        self.duration = config.get("duration", 5.0)
        self.remote_asset_manager = config.get("remote_asset_manager")
        os.makedirs(self.temp_dir, exist_ok=True)

    # [RESOLVE_SOURCE_PATH REMOVIDO DAQUI]

    def _resolve_remote_asset(self):
        """Resolve um slug de remote_asset para um caminho local, com fallback.

        O `source` é tratado como slug; o RemoteAssetManager seleciona uma URL
        válida e tenta o download — caindo para a próxima URL se falhar.
        Retorna o caminho local baixado ou None.
        """
        if not self.remote_asset_manager:
            print("[VisualClip] RemoteAssetManager não disponível para remote_asset.")
            return None

        slug = self.data.get("source")
        if not slug:
            print("[VisualClip] Slug (source) não especificado para remote_asset.")
            return None

        while True:
            selected_url = self.remote_asset_manager.select_url(slug)
            if not selected_url:
                print(f"[VisualClip] Nenhuma URL válida restante no slug '{slug}'.")
                return None

            print(f"[VisualClip] remote_asset '{slug}' → {selected_url[:60]}...")

            def on_success(url):
                self.remote_asset_manager.mark_download_success(url)

            def on_fail(url):
                self.remote_asset_manager.mark_download_failed(url)

            path = MediaDownloader.resolve_source_path(
                selected_url, self.temp_dir,
                on_success_callback=on_success,
                on_fail_callback=on_fail,
            )

            if path:
                register_slug = self.data.get("register_remote_asset_as")
                if register_slug and selected_url.startswith("http"):
                    self.remote_asset_manager.register_url(register_slug, selected_url)
                return path

            print("[VisualClip] Falha no download, tentando próxima URL...")

    def generate(self):
        el_type = self.data.get("type")
        clip = None

        if el_type == "remote_asset":
            path = self._resolve_remote_asset()
            if not path:
                return None
            # Despacha por extensão do arquivo baixado: vídeo vs imagem
            ext = os.path.splitext(path)[1].lower()
            if ext in self._VIDEO_EXTS:
                clip = self._create_video_clip(path)
            else:
                clip = self._create_image_clip(path)
        elif el_type == "image":
            clip = self._create_image_clip()
        elif el_type == "video":
            clip = self._create_video_clip()
        elif el_type == "text_box":
            clip = self._create_text_box_clip()
        elif el_type == "color":
            clip = self._create_color_clip()

        if not clip: return None

        # Apply force_rgb to ALL clips to prevent shape errors
        clip = clip.fl_image(force_rgb)

        layout = self.data.get("layout", {})
        if layout.get("rotation"): clip = clip.rotate(layout["rotation"])

        anim = self.data.get("animation", {})

        # No modo cover (placement.width+height) o worker ainda faz resize+crop sobre
        # o clip. Um resize estático posterior MATA a animação de zoom (resize(lambda t:))
        # e DESTRÓI a máscara de border_radius. Por isso, nesse modo, adiamos AMBOS para
        # o worker, que aplica na ordem: resize → crop → animation → border_radius.
        placement = self.data.get("placement", {})
        defer = (placement.get("width") is not None and placement.get("height") is not None)
        if defer:
            return clip  # animation + border_radius aplicados no worker pós-crop

        border_radius = self.data.get("border_radius", 0)

        if anim and anim.get("type", "none") not in ("none", "fade_in"):
            if border_radius and border_radius > 0:
                clip = self._apply_zoom_in_window(clip, anim, int(border_radius))
            else:
                clip = self._apply_animation(clip)
        else:
            if border_radius and border_radius > 0:
                clip = self._apply_border_radius(clip, int(border_radius))
            clip = self._apply_animation(clip)

        return clip

    def _apply_border_radius(self, clip, radius: int):
        """Aplica máscara de cantos arredondados ao clip via PIL."""
        w, h = clip.size

        mask_img = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(mask_img)
        draw.rounded_rectangle([(0, 0), (w - 1, h - 1)], radius=radius, fill=255)
        mask_arr = np.array(mask_img).astype(float) / 255.0

        mask_clip = ImageClip(mask_arr, ismask=True).set_duration(clip.duration)
        return clip.set_mask(mask_clip)

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


    def _create_image_clip(self, path=None):
        # *** CHAMADA À NOVA LIB DE DOWNLOAD ***
        # `path` pré-resolvido (ex: remote_asset) pula a resolução de source.
        if path is None:
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

    def _create_video_clip(self, path=None):
        # *** CHAMADA À NOVA LIB DE DOWNLOAD ***
        # `path` pré-resolvido (ex: remote_asset) pula a resolução de source.
        if path is None:
            path = MediaDownloader.resolve_source_path(self.data.get("source"), self.temp_dir)
        if not path or not os.path.exists(path): return None
        
        clip = VideoFileClip(path)
        
        audio_cfg = self.data.get("audio", {})
        if not audio_cfg.get("keep_audio", False):
            clip = clip.without_audio()
        else:
            clip = clip.volumex(audio_cfg.get("volume", 1.0))
            
        return clip

    def _create_color_clip(self):
        """Cria um ColorClip sólido (ex.: overlay de escurecimento). Tamanho
        é um placeholder — o worker redimensiona via placement.width/height."""
        color = hex_to_rgb(self.data.get("color", "#000000"))
        return ColorClip(size=self.resolution, color=color).set_duration(self.duration)

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

    def _make_zoom_clip(self, clip, anim_type, anim):
        """Aplica zoom suave usando resize(lambda t:) nativo do MoviePy."""
        total = float(clip.duration or 1.0)

        if anim_type == "zoom_in":
            start_scale = float(anim.get("start_scale", 1.0))
            end_scale   = float(anim.get("end_scale", 1.15))
            clip = clip.resize(lambda t: start_scale + (end_scale - start_scale) * min(t / total, 1.0))

        elif anim_type == "zoom_out":
            start_scale = float(anim.get("start_scale", 1.15))
            end_scale   = float(anim.get("end_scale", 1.0))
            clip = clip.resize(lambda t: start_scale + (end_scale - start_scale) * min(t / total, 1.0))

        elif anim_type == "zoom_pulse":
            intensity = float(anim.get("intensity", 0.06))
            clip = clip.resize(lambda t: 1.0 + intensity * np.sin((t / total) * np.pi))

        elif anim_type == "fade_zoom_in":
            start_scale   = float(anim.get("start_scale", 1.0))
            end_scale     = float(anim.get("end_scale", 1.12))
            fade_duration = float(anim.get("fade_duration", 0.6))
            clip = clip.resize(lambda t: start_scale + (end_scale - start_scale) * min(t / total, 1.0))
            clip = clip.crossfadein(fade_duration)

        return clip

    def _apply_zoom_in_window(self, clip, anim, radius: int):
        """Zoom acontece dentro de uma janela de tamanho fixo com border_radius.
        O clip escalado é centralizado e recortado para o tamanho original,
        depois a máscara arredondada é aplicada sobre o resultado fixo.
        """
        win_w, win_h = clip.size
        duration = clip.duration

        zoomed = self._make_zoom_clip(clip, anim.get("type"), anim)

        # "center" faz o MoviePy centralizar o clip escalado quadro a quadro
        zoomed = zoomed.set_position("center")

        # Janela de tamanho fixo — o zoom transborda e é cortado aqui
        window = CompositeVideoClip([zoomed], size=(win_w, win_h)).set_duration(duration)
        window = window.fl_image(force_rgb)

        # Máscara arredondada fixa sobre a janela
        return self._apply_border_radius(window, radius)

    def _apply_animation(self, clip):
        anim = self.data.get("animation", {})
        if not anim:
            return clip

        start     = float(anim.get("start_at", 0))
        anim_type = anim.get("type", "none")

        clip = clip.set_start(start)

        if anim_type == "fade_in":
            dur  = float(anim.get("duration", 1.0))
            clip = clip.crossfadein(dur)
        elif anim_type in ("zoom_in", "zoom_out", "zoom_pulse", "fade_zoom_in"):
            clip = self._make_zoom_clip(clip, anim_type, anim)

        return clip