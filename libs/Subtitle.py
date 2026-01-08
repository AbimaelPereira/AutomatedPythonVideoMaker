import os
import srt
import numpy as np
from moviepy.editor import TextClip, CompositeVideoClip, ColorClip
from scipy import ndimage
from PIL import ImageColor

def force_rgb(im):
    return np.dstack((im, im, im)) if im.ndim == 2 else im

class Subtitle:
    def __init__(self, params=None):
        defaults = {
            # Arquivo SRT
            "subtitle_narration_file": None,

            # Fonte e texto
            "font_path": "./assets/fonts/Poppins/Poppins-Black.ttf",
            "font_size": 70,
            "color": "white",

            # Contorno (stroke)
            "stroke_enabled": True,
            "stroke_color": "black",
            "stroke_width": 3,  # será dobrado na renderização

            # Sombra (scipy_gaussian)
            "shadow_enabled": False,
            "shadow_color": "black",
            "shadow_opacity": 0.8,   # 0..1
            "blur_radius": 6.0,      # sigma do gaussiano
            "shadow_offset": (4, 4), # (dx, dy)

            # Layout/saída
            "resolution_output": (1080, 1920),
            "padding_side": 50,
            "padding_bottom": 850,
        }
        if params:
            defaults.update(params)

        for k, v in defaults.items():
            setattr(self, k, v)

        if not self.subtitle_narration_file or not os.path.exists(self.subtitle_narration_file):
            raise FileNotFoundError(f"Arquivo de legenda (.srt) não encontrado: {self.subtitle_narration_file}")

        if not os.path.exists(self.font_path):
            print(f"⚠️ Fonte não encontrada em {self.font_path}. Tentando fonte do sistema.")
            self.font_path = "Arial"

    def _make_shadow_clip(self, txt, duration, size, position, blur_radius, offset, color, opacity):
        """
        Gera um ColorClip na forma da máscara desfocada (sombra) usando scipy.ndimage.gaussian_filter.
        - txt: string do texto
        - duration: duração do sub
        - size: (w, h) caixa do texto
        - position: (x, y) posição base do texto
        - blur_radius: sigma do gaussiano
        - offset: (dx, dy) deslocamento da sombra
        - color: cor da sombra ("black", "#000", etc)
        - opacity: 0..1
        """
        if blur_radius <= 0:
            return None

        # 1) TextClip apenas para obter a máscara (branco sobre transparente)
        mask_source = TextClip(
            txt,
            font=self.font_path,
            fontsize=self.font_size,
            color="white",
            size=size,
            method="caption",
            align="center"
        ).set_duration(duration)

        mask = mask_source.mask  # MoviePy mask [0..1]

        # 2) Aplica desfoque gaussiano via SciPy na máscara
        def blur_mask_frame(im):
            # im é float 0..1; aplicamos gaussian_filter e normalizamos
            blurred = ndimage.gaussian_filter(im.astype(float), sigma=blur_radius)
            mx = blurred.max()
            if mx > 0:
                blurred = blurred / mx
            # aplica opacidade
            blurred = np.clip(blurred * float(opacity), 0.0, 1.0)
            return blurred

        blurred_mask = mask.fl_image(blur_mask_frame)

        # 3) ColorClip com a cor desejada e a máscara desfocada
        try:
            rgb = ImageColor.getrgb(color)
        except Exception:
            rgb = (0, 0, 0)

        shadow_clip = ColorClip(size=size, color=rgb).set_duration(duration)
        shadow_clip = shadow_clip.set_mask(blurred_mask)

        # 4) Posição com deslocamento
        x, y = position
        dx, dy = int(offset[0]), int(offset[1])
        return shadow_clip.set_position((x + dx, y + dy))

    def generate(self):
        # Lê SRT
        with open(self.subtitle_narration_file, "r", encoding="utf-8") as f:
            try:
                subtitles = list(srt.parse(f.read()))
            except Exception as e:
                print(f"❌ Erro ao ler SRT: {e}")
                return ColorClip(size=(1, 1), color=(0, 0, 0, 0), duration=0.1)

        screen_width, screen_height = self.resolution_output
        safe_width = screen_width - (2 * self.padding_side)
        # Altura da caixa de texto (mantém compatibilidade com layout atual)
        box_height = self.padding_bottom - 20

        subtitle_clips = []
        for sub in subtitles:
            txt = sub.content.replace("\n", " ").strip().upper()
            if not txt:
                continue

            start, end = sub.start.total_seconds(), sub.end.total_seconds()
            duration = max(0.01, end - start)

            try:
                comps = []

                # Posição base da caixa de legenda
                box_y_pos = screen_height - self.padding_bottom
                left_x = int((screen_width - safe_width) / 2)
                base_position = (left_x, box_y_pos)
                box_size = (safe_width, box_height)

                # 1) Sombra (opcional)
                if self.shadow_enabled:
                    try:
                        shadow_clip = self._make_shadow_clip(
                            txt=txt,
                            duration=duration,
                            size=box_size,
                            position=base_position,
                            blur_radius=float(self.blur_radius),
                            offset=self.shadow_offset,
                            color=self.shadow_color,
                            opacity=float(self.shadow_opacity),
                        )
                        if shadow_clip is not None:
                            comps.append(shadow_clip)
                    except Exception as e:
                        print(f"⚠️ Erro ao criar sombra: {e}")

                # 2) Contorno (opcional)
                if self.stroke_enabled and self.stroke_width > 0:
                    stroke_clip = TextClip(
                        txt,
                        font=self.font_path,
                        fontsize=self.font_size,
                        color=self.stroke_color,
                        stroke_color=self.stroke_color,
                        stroke_width=self.stroke_width * 2,
                        size=box_size,
                        method="caption",
                        align="center"
                    ).set_duration(duration).fl_image(force_rgb).set_position(base_position)
                    comps.append(stroke_clip)

                # 3) Preenchimento (sempre)
                fill_clip = TextClip(
                    txt,
                    font=self.font_path,
                    fontsize=self.font_size,
                    color=self.color,
                    size=box_size,
                    method="caption",
                    align="center"
                ).set_duration(duration).fl_image(force_rgb).set_position(base_position)
                comps.append(fill_clip)

                # Composição final deste intervalo
                combined_txt = CompositeVideoClip(comps, size=self.resolution_output).set_start(start).set_end(end)
                subtitle_clips.append(combined_txt)

            except Exception as e:
                print(f"⚠️ Erro ao criar clip de legenda: {e}")
                continue

        if not subtitle_clips:
            return ColorClip(size=(1, 1), color=(0, 0, 0, 0), duration=0.1)

        return CompositeVideoClip(subtitle_clips, size=self.resolution_output)