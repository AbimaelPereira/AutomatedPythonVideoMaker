import os
import srt
import numpy as np
from moviepy.editor import TextClip, CompositeVideoClip, ColorClip

def force_rgb(im):
    return np.dstack((im, im, im)) if im.ndim == 2 else im

class Subtitle:
    def __init__(self, params=None):
        defaults = {
            "subtitle_narration_file": None,
            "font_path": "./fonts/Poppins/Poppins-Black.ttf",
            "font_size": 70, # Levemente menor para caber melhor na box fixa
            "color": "white",
            "stroke_color": "black",
            "stroke_width": 4,
            "resolution_output": (1080, 1920),
            "padding_side": 50,
            "padding_bottom": 250, # Deve bater com o Config
        }
        if params:
            defaults.update(params)

        for k, v in defaults.items():
            setattr(self, k, v)

        if not self.subtitle_narration_file or not os.path.exists(self.subtitle_narration_file):
            raise FileNotFoundError(f"Arquivo de legenda (.srt) não encontrado")
        if not os.path.exists(self.font_path):
            self.font_path = "Arial" 

    def generate(self):
        with open(self.subtitle_narration_file, "r", encoding="utf-8") as f:
            try:
                subtitles = list(srt.parse(f.read()))
            except:
                 return ColorClip(size=(1,1), color=(0,0,0,0), duration=0.1)

        screen_width = self.resolution_output[0]
        screen_height = self.resolution_output[1]
        
        # Largura útil da caixa de legenda
        safe_width = screen_width - (2 * self.padding_side)
        
        # Altura útil da caixa de legenda (Box Azul)
        # Vamos usar o padding_bottom como a altura total da área reservada
        # Mas damos uma margem interna de 20px
        box_height = self.padding_bottom - 20 

        subtitle_clips = []
        for sub in subtitles:
            txt = sub.content.replace("\n", " ").strip().upper()
            if not txt: continue 

            start, end = sub.start.total_seconds(), sub.end.total_seconds()

            try:
                # TextClip com 'method="caption"' e 'size' definido obriga o texto
                # a quebrar linha e ficar dentro da caixa.
                txt_clip = TextClip(
                        txt,
                        font=self.font_path,
                        fontsize=self.font_size,
                        color=self.color,
                        stroke_color=self.stroke_color,
                        stroke_width=self.stroke_width,
                        size=(safe_width, box_height), # Tamanho Fixo da Box
                        method="caption",
                        align="center" # Centraliza o texto dentro da box
                    )
                
                txt_clip = txt_clip.fl_image(force_rgb)

                # Posiciona a box no rodapé
                # Y = Altura Tela - Padding Bottom (início da área azul)
                box_y_pos = screen_height - self.padding_bottom

                final_clip = (txt_clip
                    .set_position(("center", box_y_pos)) # Fixa na área azul
                    .set_start(start)
                    .set_end(end)
                )
                subtitle_clips.append(final_clip)

            except Exception as e:
                print(f"⚠️ Erro legenda: {e}")
                continue

        if not subtitle_clips:
            return ColorClip(size=(1,1), color=(0,0,0,0), duration=0.1)

        return CompositeVideoClip(subtitle_clips, size=self.resolution_output)