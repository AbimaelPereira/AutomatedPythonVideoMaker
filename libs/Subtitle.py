import os
import srt
from moviepy.editor import TextClip, CompositeVideoClip


class Subtitle:
    def __init__(self, params=None):
        defaults = {
            "subtitle_narration_file": None,
            "font_path": "./fonts/Poppins/Poppins-Black.ttf",
            "font_size": 150,
            "color": "white",
            "stroke_color": "black",
            "stroke_width": 7,
            "resolution_output": (1080, 1920),
            "position": ("center", "bottom"),
        }
        if params:
            defaults.update(params)

        for k, v in defaults.items():
            setattr(self, k, v)

        if not self.subtitle_narration_file or not os.path.exists(self.subtitle_narration_file):
            raise FileNotFoundError("Arquivo de legenda (.srt) não encontrado")
        if not os.path.exists(self.font_path):
            raise FileNotFoundError(f"Fonte TTF não encontrada: {self.font_path}")

    def generate(self):
        with open(self.subtitle_narration_file, "r", encoding="utf-8") as f:
            subtitles = list(srt.parse(f.read()))

        subtitle_clips = []
        for sub in subtitles:
            txt = sub.content.replace("\n", " ").upper()
            start, end = sub.start.total_seconds(), sub.end.total_seconds()

            clip = (TextClip(
                    txt,
                    font=self.font_path,
                    fontsize=self.font_size,
                    color=self.color,
                    stroke_color=self.stroke_color,
                    stroke_width=self.stroke_width,
                    size=(self.resolution_output[0], None),  # largura já correta
                    method="caption",
                    align="center"
                )
                .set_position(self.position)
                .set_start(start)
                .set_end(end))
            subtitle_clips.append(clip)


        return CompositeVideoClip(subtitle_clips)
