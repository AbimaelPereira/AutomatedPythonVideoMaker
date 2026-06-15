"""
ClassicSubtitle — o estilo de legenda original do projeto (type "classic").

Lê um SRT (gerado palavra-a-palavra pelo NarrationEngine) e renderiza cada
entrada como uma única imagem PIL, com stroke e sombra opcionais, posicionada
de acordo com `subtitle_position`/paddings.

Comportamento idêntico ao antigo `libs/Subtitle.py`. A renderização PIL foi
movida para `SubtitleUtils` para ser compartilhada com os demais tipos.
"""

import os
import srt
from moviepy.editor import ImageClip, CompositeVideoClip, ColorClip

from libs.Subtitle import SubtitleUtils as utils


class ClassicSubtitle:
    def __init__(self, params=None):
        defaults = {
            "subtitle_narration_file": None,

            "font_path": "./assets/fonts/Poppins/Poppins-Black.ttf",
            "font_size": 70,
            "color": "white",

            "uppercase": True,
            "has_visual_elements": False,

            "stroke_enabled": True,
            "stroke_color": "black",
            "stroke_width": 3,          # dobrado internamente (comportamento legado)

            "shadow_enabled": False,
            "shadow_color": "black",
            "shadow_opacity": 0.8,
            "blur_radius": 6.0,
            "shadow_offset": (4, 4),

            "resolution_output": (1080, 1920),
            "padding_side": 50,
            "padding_bottom": 850,
            "padding_top": 100,
            "subtitle_position": "bottom",
            "placement": None,   # novo: {"anchor":[x,y], "region": "30%"}
        }
        if params:
            defaults.update(params)

        for k, v in defaults.items():
            setattr(self, k, v)

        if not self.subtitle_narration_file or not os.path.exists(self.subtitle_narration_file):
            raise FileNotFoundError(
                f"Arquivo de legenda (.srt) não encontrado: {self.subtitle_narration_file}"
            )

        # Stroke efetivo (dobrado, igual ao comportamento da versão anterior)
        self._stroke_width_effective = self.stroke_width * 2 if self.stroke_enabled else 0

    # ------------------------------------------------------------------

    def _style(self) -> dict:
        return {
            "font_path": self.font_path,
            "font_size": self.font_size,
            "fill": self.color,
            "stroke_enabled": self.stroke_enabled,
            "stroke_color": self.stroke_color,
            "stroke_width": self._stroke_width_effective,
            "shadow_enabled": self.shadow_enabled,
            "shadow_color": self.shadow_color,
            "shadow_opacity": self.shadow_opacity,
            "blur_radius": self.blur_radius,
            "shadow_offset": self.shadow_offset,
        }

    def _make_subtitle_clip(self, text: str, duration: float, box: dict) -> ImageClip:
        arr = utils.render_text(text, self._style())

        rgb = arr[:, :, :3]
        alpha = arr[:, :, 3].astype(float) / 255.0

        clip = ImageClip(rgb, ismask=False).set_duration(duration)
        clip = clip.set_mask(ImageClip(alpha, ismask=True).set_duration(duration))

        clip_w, clip_h = clip.size

        # X: centraliza o texto dentro da largura da caixa.
        x = box["x"] + max(0, (box["width"] - clip_w) // 2)

        # Y: alinha o bloco dentro da altura da caixa conforme anchor_y.
        anchor_y = box.get("anchor_y", "center")
        if anchor_y == "top":
            y = box["y"]
        elif anchor_y == "bottom":
            y = box["y"] + max(0, box["height"] - clip_h)
        else:
            y = box["y"] + max(0, (box["height"] - clip_h) // 2)

        return clip.set_position((int(x), int(y)))

    # ------------------------------------------------------------------

    def generate(self):
        with open(self.subtitle_narration_file, "r", encoding="utf-8") as f:
            try:
                subtitles = list(srt.parse(f.read()))
            except Exception as e:
                print(f"❌ Erro ao ler SRT: {e}")
                return ColorClip(size=(1, 1), color=(0, 0, 0, 0), duration=0.1)

        if not subtitles:
            return ColorClip(size=(1, 1), color=(0, 0, 0, 0), duration=0.1)

        # Resolve a caixa de posicionamento uma vez (placement novo OU legado).
        box = utils.resolve_subtitle_box(
            {
                "placement": self.placement,
                "subtitle_position": self.subtitle_position,
                "has_visual_elements": self.has_visual_elements,
                "padding_side": self.padding_side,
                "padding_top": self.padding_top,
                "padding_bottom": self.padding_bottom,
            },
            self.resolution_output,
        )

        subtitle_clips = []

        for sub in subtitles:
            txt = sub.content.replace("\n", " ").strip()
            if self.uppercase:
                txt = txt.upper()
            if not txt:
                continue

            txt = txt.translate(str.maketrans("", "", utils._PUNCTUATION))

            start = sub.start.total_seconds()
            end = sub.end.total_seconds()
            duration = max(0.01, end - start)

            try:
                clip = self._make_subtitle_clip(text=txt, duration=duration, box=box)
                clip = clip.fl_image(utils.force_rgb).set_start(start).set_end(end)
                subtitle_clips.append(clip)

            except Exception as e:
                print(f"⚠️ Erro ao criar clip de legenda para '{txt[:30]}': {e}")
                continue

        if not subtitle_clips:
            return ColorClip(size=(1, 1), color=(0, 0, 0, 0), duration=0.1)

        return CompositeVideoClip(subtitle_clips, size=self.resolution_output)
