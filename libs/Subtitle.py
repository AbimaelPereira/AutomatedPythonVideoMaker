import os
import srt
import numpy as np
from moviepy.editor import TextClip, CompositeVideoClip, ColorClip

# Helper para garantir RGB, prevenindo erro de broadcast
def force_rgb(im):
    # Se a imagem for 2D (apenas altura e largura, sem canais de cor), empilha para criar RGB
    return np.dstack((im, im, im)) if im.ndim == 2 else im

class Subtitle:
    def __init__(self, params=None):
        defaults = {
            "subtitle_narration_file": None,
            "font_path": "./fonts/Poppins/Poppins-Black.ttf",
            "font_size": 80, 
            "color": "white",
            "stroke_color": "black",
            "stroke_width": 4,
            "resolution_output": (1080, 1920),
            "padding_side": 50,
            "padding_bottom": 150,
        }
        if params:
            defaults.update(params)

        print("=" * 10)
        print("📝 Configurações de legenda (Ativas):")
        for k, v in defaults.items():
            print(f"  {k}: {v}")
        print("=" * 10)

        for k, v in defaults.items():
            setattr(self, k, v)

        if not self.subtitle_narration_file or not os.path.exists(self.subtitle_narration_file):
            raise FileNotFoundError(f"Arquivo de legenda (.srt) não encontrado: {self.subtitle_narration_file}")
        if not os.path.exists(self.font_path):
            print(f"⚠️ Fonte não encontrada: {self.font_path}. Tentando usar fonte padrão do ImageMagick.")
            self.font_path = "Arial" 

    def generate(self):
        with open(self.subtitle_narration_file, "r", encoding="utf-8") as f:
            try:
                subtitles = list(srt.parse(f.read()))
            except srt.SRTParseError as e:
                 print(f"⚠️ Erro crítico ao analisar arquivo SRT: {e}")
                 raise RuntimeError("Falha no parsing do SRT")

        screen_width = self.resolution_output[0]
        screen_height = self.resolution_output[1]
        
        safe_width = screen_width - (2 * self.padding_side)

        subtitle_clips = []
        for sub in subtitles:
            # upper case
            txt = sub.content.replace("\n", " ").strip().upper()
            if not txt: continue 

            start, end = sub.start.total_seconds(), sub.end.total_seconds()

            try:
                txt_clip = TextClip(
                        txt,
                        font=self.font_path,
                        fontsize=self.font_size,
                        color=self.color,
                        stroke_color=self.stroke_color,
                        stroke_width=self.stroke_width,
                        size=(safe_width, None), 
                        method="caption",
                        align="center"
                    )
                
                # CORREÇÃO CRÍTICA: Força o clipe de texto a ser RGB/RGBA
                # Isso evita que textos brancos/pretos sejam otimizados como máscaras 2D
                txt_clip = txt_clip.fl_image(force_rgb)

                final_clip = (txt_clip
                    .set_position(lambda t, h=txt_clip.h: ("center", screen_height - self.padding_bottom - h))
                    .set_start(start)
                    .set_end(end)
                )
                subtitle_clips.append(final_clip)

            except Exception as e:
                print(f"⚠️  Erro ao gerar clipe de legenda para '{txt[:20]}...': {e}")
                continue

        if not subtitle_clips:
            print("⚠️ Nenhuma legenda válida foi gerada. Retornando clipe vazio.")
            return ColorClip(size=(1,1), color=(0,0,0,0), duration=0.1)

        # Retorna a composição
        return CompositeVideoClip(subtitle_clips, size=self.resolution_output)