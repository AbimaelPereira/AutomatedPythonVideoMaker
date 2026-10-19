import os
import requests
import io
import mimetypes
import numpy as np 
from PIL import Image, ImageDraw, ImageFont
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

def _apply_cover_size(clip, target_size):
    """Leva um clipe a `target_size` cobrindo a área e cortando o excesso.

    Usado para uniformizar segmentos de uma pasta antes de concatenar
    (`concatenate_videoclips` exige tamanhos iguais). Cover em vez de resize
    puro para não distorcer arquivos com proporção diferente do primeiro.
    """
    from moviepy.video.fx.all import crop as _crop, resize as _resize

    target_w, target_h = int(target_size[0]), int(target_size[1])
    w, h = clip.size
    scale = max(target_w / w, target_h / h)
    new_w, new_h = max(int(w * scale), target_w), max(int(h * scale), target_h)

    clip = _resize(clip, newsize=(new_w, new_h))
    x_center, y_center = new_w / 2, new_h / 2
    return _crop(
        clip,
        x1=int(x_center - target_w / 2), y1=int(y_center - target_h / 2),
        x2=int(x_center + target_w / 2), y2=int(y_center + target_h / 2),
    )


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
        elif el_type == "directory":
            clip = self._create_directory_clip()
        elif el_type == "text_box":
            clip = self._create_text_box_clip()
        elif el_type == "color":
            clip = self._create_color_clip()
        elif el_type == "gradient":
            clip = self._create_gradient_clip()

        if not clip: return None

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
        anim_type = anim.get("type", "none") if anim else "none"
        uses_fade = anim_type in ("fade_in", "fade_zoom_in")

        # O degradê É a máscara alpha: todo o efeito vive na transparência
        # variável. Entra na mesma exceção do fade. O text_box sem fundo
        # depende do alpha pelo mesmo motivo (senão vira retângulo opaco).
        if el_type == "gradient":
            uses_fade = True
        elif el_type == "text_box" and \
                (self.data.get("style") or {}).get("background_color") == "transparent":
            uses_fade = True

        # force_rgb apenas quando não há fade — fade_in/fade_zoom_in dependem da
        # máscara alpha para compor corretamente; removê-la antes causa fade sobre preto.
        if not uses_fade:
            clip = clip.fl_image(force_rgb)

        if anim and anim_type not in ("none", "fade_in"):
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
    def _resolve_font(style, font_size):
        """Resolve a fonte de um text_box: `style.font_path` (caminho direto ao
        .ttf) tem prioridade; `style.font_family` é mantido como fallback legado
        (lookup em fonts/{familia}/{familia}.ttf, raramente presente no projeto)."""
        font_path = style.get("font_path")
        if not font_path:
            font_family = style.get("font_family", "Arial")
            font_path = f"fonts/{font_family.split('-')[0]}/{font_family}.ttf"
            if not os.path.exists(font_path):
                font_path = "fonts/Lato/Lato-Bold.ttf"

        try:
            return ImageFont.truetype(font_path, font_size)
        except Exception:
            return ImageFont.load_default()

    @staticmethod
    def calculate_text_box_size(data):
        # ... (mantido inalterado) ...
        content = data.get("content", "")
        style = data.get("style", {})
        font_size = style.get("font_size", 50)
        font = VisualClip._resolve_font(style, font_size)

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
                # Import preguiçoso: `rembg` puxa torch/onnxruntime e custa ~3s
                # de import. Só `filters.remove_bg` precisa dele, então carregar
                # no topo penalizava TODO import de VisualClip (incluindo o
                # render de thumbnail, que nunca usa remoção de fundo).
                from rembg import remove

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

    def _create_directory_clip(self):
        """Elemento visual montado a partir de uma pasta.

        Usa o mesmo `DirectorySelector` do fundo — inclusive o histórico
        anti-repetição —, então uma pasta compartilhada entre fundo e overlay
        não mostra o mesmo arquivo nos dois ao mesmo tempo.

        Diferença importante em relação ao fundo: aqui NÃO se aplica cover para
        a resolução de saída. O tamanho final do elemento é decidido depois pelo
        LayoutEngine (via `placement`), então os segmentos são apenas
        normalizados entre si — o menor denominador comum — e concatenados.
        """
        from libs.Background.DirectorySelector import DirectorySelector

        plan = DirectorySelector().build_plan(self.data, float(self.duration))
        if not plan:
            print(f"[VisualClip] Pasta sem mídia utilizável: {self.data.get('source')}")
            return None

        segments = []
        for seg in plan:
            try:
                segments.append(self._clip_from_segment(seg))
            except Exception as e:
                print(f"[VisualClip] ⚠️ Falha ao carregar {seg['path']}: {e}")

        if not segments:
            return None
        if len(segments) == 1:
            return segments[0]

        # `concatenate_videoclips` exige tamanho igual entre as partes. Os
        # arquivos da pasta têm resoluções variadas, então todos são levados ao
        # tamanho do primeiro segmento (preservando proporção via cover), que é
        # quem define o aspect ratio que o layout vai posicionar.
        target = segments[0].size
        normalized = [
            seg if seg.size == target else _apply_cover_size(seg, target)
            for seg in segments
        ]
        return concatenate_videoclips(normalized, method="compose")

    def _clip_from_segment(self, seg: dict):
        """Materializa um segmento do plano (sem redimensionar para a saída)."""
        duration = float(seg["duration"])

        if seg["is_video"]:
            clip = VideoFileClip(seg["path"])
            audio_cfg = self.data.get("audio", {})
            if not audio_cfg.get("keep_audio", False):
                clip = clip.without_audio()
            else:
                clip = clip.volumex(audio_cfg.get("volume", 1.0))

            if seg.get("loop"):
                clip = clip.loop(duration=duration)
            else:
                start = float(seg.get("start", 0.0))
                clip = clip.subclip(start, min(start + duration, clip.duration))
                if clip.duration < duration:
                    clip = clip.loop(duration=duration)
            return clip.set_duration(duration)

        return ImageClip(seg["path"]).set_duration(duration)

    def _create_color_clip(self):
        """Cria um ColorClip sólido (ex.: overlay de escurecimento). Tamanho
        é um placeholder — o worker redimensiona via placement.width/height."""
        color = hex_to_rgb(self.data.get("color", "#000000"))
        return ColorClip(size=self.resolution, color=color).set_duration(self.duration)

    def _create_gradient_clip(self):
        """Degradê linear com alpha, renderizado via PIL.

        Irmão do `_create_color_clip`: mesma função de overlay, mas com opacidade
        variável ao longo de um eixo — o recurso mais usado em thumbnail para
        escurecer só a faixa onde o texto entra, sem apagar a imagem inteira.

        `stops` é uma lista de {color, opacity, at}, com `at` em 0..1 medido na
        direção do degradê. Cada canal (RGB e alpha) é interpolado linearmente
        entre os stops vizinhos. Sem `stops`, cai num preto 0→1 (o caso comum).

        O bitmap nasce no tamanho da tela e é redimensionado pelo LayoutEngine
        via `placement`, exatamente como o ColorClip sólido.
        """
        direction = str(self.data.get("direction", "to_top")).lower()
        stops = self.data.get("stops") or [
            {"color": "#000000", "opacity": 0.0, "at": 0.0},
            {"color": "#000000", "opacity": 1.0, "at": 1.0},
        ]

        # Normaliza e ordena — um `stops` fora de ordem no JSON não deve inverter
        # o degradê silenciosamente.
        parsed = []
        for s in stops:
            try:
                at = min(1.0, max(0.0, float(s.get("at", 0.0))))
                rgb = hex_to_rgb(s.get("color", "#000000"))
                alpha = min(1.0, max(0.0, float(s.get("opacity", 1.0))))
                parsed.append((at, rgb, alpha))
            except Exception:
                continue
        if not parsed:
            parsed = [(0.0, (0, 0, 0), 0.0), (1.0, (0, 0, 0), 1.0)]
        parsed.sort(key=lambda item: item[0])

        w, h = int(self.resolution[0]), int(self.resolution[1])

        # O degradê só varia em UM eixo: gera-se uma faixa 1-D e depois estica-se
        # para a tela inteira. Bem mais barato que preencher w*h ponto a ponto.
        vertical = direction in ("to_top", "to_bottom")
        steps = h if vertical else w

        positions = np.linspace(0.0, 1.0, max(steps, 1))
        stop_ats = np.array([p[0] for p in parsed], dtype=float)
        ramp = np.zeros((max(steps, 1), 4), dtype=float)
        for channel in range(4):
            if channel < 3:
                values = np.array([p[1][channel] for p in parsed], dtype=float)
            else:
                values = np.array([p[2] * 255.0 for p in parsed], dtype=float)
            # np.interp já faz clamp nas pontas (antes do 1º stop / após o último).
            ramp[:, channel] = np.interp(positions, stop_ats, values)

        # `at=0` é o INÍCIO da direção declarada: "to_top" cresce de baixo p/ cima,
        # "to_left" da direita p/ esquerda.
        if direction in ("to_top", "to_left"):
            ramp = ramp[::-1]

        if vertical:
            arr = np.repeat(ramp[:, np.newaxis, :], w, axis=1)
        else:
            arr = np.repeat(ramp[np.newaxis, :, :], h, axis=0)

        arr = arr.astype("uint8")

        temp_path = os.path.join(self.temp_dir, f"gradient_{id(self)}.png")
        Image.fromarray(arr, mode="RGBA").save(temp_path)

        # ImageClip com transparent=True preserva o alpha como máscara MoviePy —
        # sem isso o degradê viraria um retângulo opaco.
        return ImageClip(temp_path, transparent=True).set_duration(self.duration)

    def _create_text_box_clip(self):
        path = render_text_box_png(self.data, self.resolution, self.temp_dir)
        # transparent=True preserva o alpha como máscara MoviePy. Sem isso,
        # `background_color: "transparent"` virava um retângulo preto opaco.
        return ImageClip(path, transparent=True).set_duration(self.duration)

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

def draw_text_box(data: dict, resolution: tuple):
    """Desenha um `text_box` e devolve a imagem PIL.

    Era o corpo de `VisualClip._create_text_box_clip`; virou função de módulo
    para o caminho ffmpeg poder gerar o MESMO bitmap (ver `render_text_box_png`).
    Nada do desenho mudou.
    """
    content = data.get("content", "")
    style = data.get("style", {})
    font_size = style.get("font_size", 50)
    pad = style.get("padding", [10, 20])  # [V_pad, H_pad]

    # Supersampling: o LayoutEngine redimensiona o clip para caber em
    # `placement.width` (área segura), o que frequentemente faz UPSCALE do
    # bitmap PIL → texto borrado. Renderizamos numa escala maior (SS) para
    # que o resize do LayoutEngine seja sempre DOWNSCALE (nítido). O fator é
    # limitado para a largura supersampleada não passar da largura da tela.
    canvas_w = resolution[0]
    ss = 4
    # Estima a largura nativa para limitar o SS dentro do canvas
    base_font = VisualClip._resolve_font(style, font_size)
    dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    try:
        bb = dummy.textbbox((0, 0), content, font=base_font)
        native_w = (bb[2] - bb[0]) + pad[1] * 2
    except Exception:
        native_w = dummy.textsize(content, font=base_font)[0] + pad[1] * 2
    if native_w > 0:
        ss = max(1, min(ss, int(canvas_w / native_w)))

    font_size_ss = font_size * ss
    pad_ss = [pad[0] * ss, pad[1] * ss]
    font = VisualClip._resolve_font(style, font_size_ss)

    # Contorno e sombra (usados em thumbnail para destacar o texto sobre
    # imagem). Ambos crescem a caixa: sem folga extra o traço e a sombra
    # seriam cortados na borda do bitmap.
    stroke_width = int(round(float(style.get("stroke_width", 0) or 0) * ss))
    stroke_color = style.get("stroke_color", "black")

    shadow = style.get("shadow") or {}
    shadow_offset = shadow.get("offset", [0, 0])
    try:
        sh_dx = int(round(float(shadow_offset[0]) * ss))
        sh_dy = int(round(float(shadow_offset[1]) * ss))
    except Exception:
        sh_dx = sh_dy = 0
    sh_blur = float(shadow.get("blur", 0) or 0) * ss
    sh_color = shadow.get("color", "black")
    sh_opacity = min(1.0, max(0.0, float(shadow.get("opacity", 1.0))))
    has_shadow = bool(shadow) and (sh_dx or sh_dy or sh_blur)

    align = str(style.get("align", "left")).lower()
    line_spacing = float(style.get("line_spacing", 1.0) or 1.0)
    # PIL mede o espaçamento entre linhas em pixels absolutos; o JSON o
    # expressa como multiplicador do tamanho da fonte (mais intuitivo e
    # independente da escala de supersampling).
    spacing_px = int(round(font_size_ss * (line_spacing - 1.0)))

    # 1. Calcular BBox e Dimensões (na escala SS)
    # `multiline_textbbox` cobre também o caso de uma linha só, então
    # substitui o textbbox anterior sem mudar o resultado do caso legado.
    try:
        bbox = dummy.multiline_textbbox(
            (0, 0), content, font=font, spacing=spacing_px, align=align,
            stroke_width=stroke_width,
        )
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        try:
            bbox = dummy.textbbox((0, 0), content, font=font)
            w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        except Exception:
            w, h = dummy.textsize(content, font=font)
            bbox = (0, 0, w, h)

    # Folga para a sombra deslocada/borrada não estourar a caixa.
    blur_pad = int(round(sh_blur * 3)) if has_shadow else 0
    extra_x = (abs(sh_dx) + blur_pad) if has_shadow else 0
    extra_y = (abs(sh_dy) + blur_pad) if has_shadow else 0

    box_w = w + pad_ss[1] * 2 + extra_x * 2
    box_h = h + pad_ss[0] * 2 + extra_y * 2

    # 2. Criar Imagem e Desenhar Fundo
    img = Image.new("RGBA", (int(box_w), int(box_h)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    background_color = style.get("background_color", "white")

    if background_color != "transparent":
        draw.rounded_rectangle([(0, 0), (box_w, box_h)], radius=style.get("border_radius", 0) * ss, fill=background_color)

    # 3. Desenhar Texto
    # bbox[0]/bbox[1] compensam o offset interno da fonte (bearing), que em
    # geral é negativo ou pequeno.
    text_x_pos = pad_ss[1] + extra_x - bbox[0]
    text_y_pos = pad_ss[0] + extra_y - bbox[1]

    text_color = style.get("text_color", "black")

    draw_kwargs = {"font": font, "spacing": spacing_px, "align": align}

    # 3a. Sombra — desenhada ANTES do texto, numa camada própria para poder
    # ser borrada sem afetar o texto nítido por cima.
    if has_shadow:
        shadow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_layer)
        shadow_draw.multiline_text(
            (text_x_pos + sh_dx, text_y_pos + sh_dy), content,
            fill=sh_color, stroke_width=stroke_width, stroke_fill=sh_color,
            **draw_kwargs,
        )
        if sh_blur > 0:
            from PIL import ImageFilter
            shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(sh_blur))
        if sh_opacity < 1.0:
            alpha = shadow_layer.getchannel("A").point(
                lambda v: int(v * sh_opacity))
            shadow_layer.putalpha(alpha)
        img = Image.alpha_composite(img, shadow_layer)
        draw = ImageDraw.Draw(img)

    # 3b. Texto (com contorno, quando houver)
    if stroke_width > 0:
        draw_kwargs["stroke_width"] = stroke_width
        draw_kwargs["stroke_fill"] = stroke_color

    draw.multiline_text((text_x_pos, text_y_pos), content,
                        fill=text_color, **draw_kwargs)

    # --- [NOVO] Lógica de Riscado (Strikethrough) ---
    if style.get("strikethrough", False):
        # Calcula a posição Y da linha (aproximadamente no meio da altura visual do texto)
        # O fator 0.6 costuma alinhar melhor visualmente com a 'cintura' das letras
        line_y = pad_ss[0] + extra_y + (h * 0.6)

        # Espessura da linha proporcional ao tamanho da fonte
        line_width = max(2, int(font_size_ss / 15))

        # Desenha a linha
        draw.line(
            [(text_x_pos, line_y), (text_x_pos + w, line_y)],
            fill=text_color,
            width=line_width
        )
    # -----------------------------------------------
    return img


def render_text_box_png(data: dict, resolution: tuple, out_dir: str) -> str:
    """Caminho de um PNG com o `text_box` desenhado (com cache em disco).

    Os DOIS caminhos de render usam este bitmap: o MoviePy embrulha num
    ImageClip, o ffmpeg usa como input. Sem isso, um `text_box` derrubava a cena
    inteira para o MoviePy — e texto é justamente o elemento que mais se anima.

    O nome é o hash de conteúdo+estilo+resolução: o mesmo text_box não é
    redesenhado a cada cena, e o resultado é determinístico (princípio P6 — o
    `id(self)` de antes mudava a cada execução).
    """
    import hashlib
    import json as _json

    key = hashlib.sha1(
        _json.dumps([data.get("content"), data.get("style"), list(resolution)],
                    sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()[:16]
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"textbox_{key}.png")
    if not os.path.exists(path):
        draw_text_box(data, resolution).save(path)
    return path
