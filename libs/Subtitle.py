import os
import srt
import hashlib
import numpy as np
from moviepy.editor import ImageClip, CompositeVideoClip, ColorClip
from scipy import ndimage
from PIL import Image, ImageDraw, ImageFont, ImageColor, ImageFilter


def force_rgb(im):
    return np.dstack((im, im, im)) if im.ndim == 2 else im


class Subtitle:
    """
    Gerador de legendas otimizado.

    MUDANÇA PRINCIPAL: substituímos TextClip (ImageMagick via subprocess) por
    renderização 100% PIL in-process. Isso elimina centenas de chamadas externas
    ao ImageMagick por cena, reduzindo drasticamente o tempo de renderização.

    Interface pública idêntica à versão anterior — o UnifiedVideoEngine não
    precisa de nenhuma alteração.
    """

    # Cache de imagens renderizadas: chave → numpy array RGBA
    # Evita re-renderizar a mesma palavra (ex: "DE", "E", "O") múltiplas vezes.
    _render_cache: dict = {}

    def __init__(self, params=None):
        defaults = {
            # Arquivo SRT
            "subtitle_narration_file": None,

            # Fonte e texto
            "font_path": "./assets/fonts/Poppins/Poppins-Black.ttf",
            "font_size": 70,
            "color": "white",

            "uppercase": True,
            "has_visual_elements": False,

            # Contorno (stroke)
            "stroke_enabled": True,
            "stroke_color": "black",
            "stroke_width": 3,          # será dobrado internamente, igual à versão anterior

            # Sombra
            "shadow_enabled": False,
            "shadow_color": "black",
            "shadow_opacity": 0.8,      # 0..1
            "blur_radius": 6.0,
            "shadow_offset": (4, 4),    # (dx, dy)

            # Layout/saída
            "resolution_output": (1080, 1920),
            "padding_side": 50,
            "padding_bottom": 850,
            "padding_top": 100,
        }
        if params:
            defaults.update(params)

        for k, v in defaults.items():
            setattr(self, k, v)

        if not self.subtitle_narration_file or not os.path.exists(self.subtitle_narration_file):
            raise FileNotFoundError(
                f"Arquivo de legenda (.srt) não encontrado: {self.subtitle_narration_file}"
            )

        # Carrega a fonte TTF uma única vez para reutilizar em todos os clips
        self._font = self._load_font(self.font_path, self.font_size)

        # Stroke efetivo (dobrado, igual ao comportamento da versão anterior)
        self._stroke_width_effective = self.stroke_width * 2 if self.stroke_enabled else 0

    # ------------------------------------------------------------------
    # FONTE
    # ------------------------------------------------------------------

    def _load_font(self, font_path: str, font_size: int) -> ImageFont.FreeTypeFont:
        """Carrega fonte TTF; faz fallback para fonte do sistema se não encontrar."""
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, font_size)
            except Exception as e:
                print(f"⚠️ Falha ao carregar fonte '{font_path}': {e}. Usando fonte padrão.")
        else:
            print(f"⚠️ Fonte não encontrada em '{font_path}'. Usando fonte padrão.")

        # Tenta fontes comuns do sistema como fallback
        for fallback in ("Arial.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"):
            try:
                return ImageFont.truetype(fallback, font_size)
            except Exception:
                continue

        return ImageFont.load_default()

    # ------------------------------------------------------------------
    # CORE: renderização PIL de uma palavra/texto
    # ------------------------------------------------------------------

    def _cache_key(self, text: str) -> str:
        """Gera chave de cache baseada no texto e nas configurações visuais."""
        params = (
            text,
            self.font_path,
            self.font_size,
            self.color,
            self.stroke_enabled,
            self.stroke_color,
            self._stroke_width_effective,
            self.shadow_enabled,
            self.shadow_color,
            self.shadow_opacity,
            self.blur_radius,
            str(self.shadow_offset),
        )
        return hashlib.md5(str(params).encode()).hexdigest()

    def _resolve_color(self, color_value) -> tuple:
        """Converte qualquer formato de cor para RGBA."""
        try:
            rgb = ImageColor.getrgb(color_value)
            if len(rgb) == 3:
                return rgb + (255,)
            return rgb
        except Exception:
            return (255, 255, 255, 255)

    def _measure_text(self, text: str, font: ImageFont.FreeTypeFont, stroke_width: int) -> tuple:
        """
        Retorna (width, height) do bounding box do texto incluindo stroke.
        Usa textbbox se disponível (Pillow >= 8.0), senão textsize como fallback.
        """
        dummy = Image.new("RGBA", (1, 1))
        draw = ImageDraw.Draw(dummy)

        try:
            # Pillow >= 8.0
            bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            offset_x = -bbox[0]
            offset_y = -bbox[1]
        except AttributeError:
            # Pillow < 8.0 — fallback
            w, h = draw.textsize(text, font=font)
            offset_x, offset_y = 0, 0

        return w, h, offset_x, offset_y

    def _render_text_to_array(self, text: str) -> np.ndarray:
        """
        Renderiza uma string como imagem RGBA usando PIL puro.

        Processo:
          1. Mede o texto para determinar o tamanho exato da imagem
          2. Desenha o stroke (contorno) se habilitado
          3. Desenha o fill (texto principal)
          4. Aplica sombra gaussiana se habilitada
          5. Retorna numpy array RGBA

        Equivalente visual ao que era feito com:
          TextClip(stroke) + TextClip(fill) + CompositeVideoClip
        """
        cache_key = self._cache_key(text)
        if cache_key in self._render_cache:
            return self._render_cache[cache_key]

        # Medição do texto para determinar o tamanho da imagem necessária
        sw = self._stroke_width_effective
        w, h, off_x, off_y = self._measure_text(text, self._font, sw)

        # Margem extra para acomodar sombra e stroke sem cortar
        shadow_dx, shadow_dy = self.shadow_offset if self.shadow_enabled else (0, 0)
        # A margem extra é a soma do deslocamento da sombra, a largura do stroke e um pequeno buffer
        extra_x = abs(shadow_dx) + sw + 10
        extra_y = abs(shadow_dy) + sw + 10

        img_w = w + extra_x * 2
        img_h = h + extra_y * 2
        if img_w < 1: img_w = 1
        if img_h < 1: img_h = 1

        # Posição base do texto dentro da imagem
        text_x = off_x + extra_x
        text_y = off_y + extra_y

        # --- Sombra ---
        if self.shadow_enabled and self.blur_radius > 0:
            shadow_layer = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
            sd = ImageDraw.Draw(shadow_layer)
            shadow_rgba = self._resolve_color(self.shadow_color)
            # Opacidade da sombra aplicada via alpha
            shadow_rgba = shadow_rgba[:3] + (int(255 * self.shadow_opacity),)

            sd.text(
                (text_x + shadow_dx, text_y + shadow_dy),
                text,
                font=self._font,
                fill=shadow_rgba,
            )
            # Blur gaussiano na camada de sombra
            shadow_layer = shadow_layer.filter(
                ImageFilter.GaussianBlur(radius=self.blur_radius)
            )
        else:
            shadow_layer = None

        # --- Stroke (contorno) ---
        stroke_layer = None
        if self.stroke_enabled and sw > 0:
            stroke_layer = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
            stk = ImageDraw.Draw(stroke_layer)
            stroke_rgba = self._resolve_color(self.stroke_color)
            stk.text(
                (text_x, text_y),
                text,
                font=self._font,
                fill=stroke_rgba,
                stroke_width=sw,
                stroke_fill=stroke_rgba,
            )

        # --- Fill (texto principal) ---
        fill_layer = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
        fl = ImageDraw.Draw(fill_layer)
        fill_rgba = self._resolve_color(self.color)
        fl.text(
            (text_x, text_y),
            text,
            font=self._font,
            fill=fill_rgba,
        )

        # --- Composição das camadas ---
        result = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))

        if shadow_layer:
            result = Image.alpha_composite(result, shadow_layer)
        if stroke_layer:
            result = Image.alpha_composite(result, stroke_layer)
        result = Image.alpha_composite(result, fill_layer)

        arr = np.array(result)

        # Armazena no cache
        self._render_cache[cache_key] = arr
        return arr

    # ------------------------------------------------------------------
    # POSICIONAMENTO
    # ------------------------------------------------------------------

    def _make_subtitle_clip(self, text: str, duration: float, position: tuple) -> ImageClip:
        """
        Cria um ImageClip de legenda a partir de um array PIL RGBA.

        O clip é posicionado na tela com set_position, exatamente como a versão
        anterior fazia com CompositeVideoClip([stroke_clip, fill_clip]).
        """
        arr = self._render_text_to_array(text)

        # Extrai canais RGB e mask separadamente para o MoviePy
        rgb  = arr[:, :, :3]
        alpha = arr[:, :, 3].astype(float) / 255.0

        clip = (
            ImageClip(rgb, ismask=False)
            .set_duration(duration)
        )

        # Aplica máscara de transparência
        mask_clip = ImageClip(alpha, ismask=True).set_duration(duration)
        clip = clip.set_mask(mask_clip)

        # Centraliza horizontalmente dentro da box de legenda
        screen_w, screen_h = self.resolution_output
        safe_w = screen_w - (2 * self.padding_side)
        clip_w, clip_h = clip.size

        # Centraliza o texto na área segura
        x = self.padding_side + max(0, (safe_w - clip_w) // 2)
        y = position[1] + max(0, (self._box_height - clip_h) // 2)

        return clip.set_position((x, y))

    # ------------------------------------------------------------------
    # GERAÇÃO PRINCIPAL
    # ------------------------------------------------------------------

    def generate(self):
        """
        Lê o SRT e retorna um CompositeVideoClip com todas as legendas.

        Interface idêntica à versão anterior.
        """
        with open(self.subtitle_narration_file, "r", encoding="utf-8") as f:
            try:
                subtitles = list(srt.parse(f.read()))
            except Exception as e:
                print(f"❌ Erro ao ler SRT: {e}")
                return ColorClip(size=(1, 1), color=(0, 0, 0, 0), duration=0.1)

        if not subtitles:
            return ColorClip(size=(1, 1), color=(0, 0, 0, 0), duration=0.1)

        screen_w, screen_h = self.resolution_output
        safe_w = screen_w - (2 * self.padding_side)
        self._box_height = self.padding_bottom - 20

        subtitle_clips = []

        for sub in subtitles:
            txt = sub.content.replace("\n", " ").strip()
            if self.uppercase:
                txt = txt.upper()
            if not txt:
                continue

            txt = txt.translate(str.maketrans("", "", ",.?!;:\"()[]{}<>-—_"))

            start    = sub.start.total_seconds()
            end      = sub.end.total_seconds()
            duration = max(0.01, end - start)

            try:
                # Posição Y da box de legenda (mesmo cálculo da versão anterior)
                if self.has_visual_elements:
                    box_y = screen_h - self.padding_bottom
                else:
                    box_y = (screen_h - self._box_height) // 2

                clip = self._make_subtitle_clip(
                    text=txt,
                    duration=duration,
                    position=(self.padding_side, box_y),
                )

                clip = (
                    clip
                    .fl_image(force_rgb)
                    .set_start(start)
                    .set_end(end)
                )

                subtitle_clips.append(clip)

            except Exception as e:
                print(f"⚠️ Erro ao criar clip de legenda para '{txt[:30]}': {e}")
                continue

        if not subtitle_clips:
            return ColorClip(size=(1, 1), color=(0, 0, 0, 0), duration=0.1)

        return CompositeVideoClip(subtitle_clips, size=self.resolution_output)
