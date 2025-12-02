import os
import srt
from moviepy.editor import TextClip, CompositeVideoClip


class Subtitle:
    def __init__(self, params=None):
        defaults = {
            "subtitle_narration_file": None,
            "font_path": "./fonts/Poppins/Poppins-Black.ttf",
            "font_size": 80, # Reduzi um pouco o padrão, 150 é muito grande
            "color": "white",
            "stroke_color": "black",
            "stroke_width": 4,
            "resolution_output": (1080, 1920),
            # Novos parâmetros de padding com valores seguros padrão
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
            # Fallback para uma fonte do sistema se a específica não existir, para evitar crash
            print(f"⚠️ Fonte não encontrada: {self.font_path}. Tentando usar fonte padrão do ImageMagick.")
            self.font_path = "Arial" # Tenta uma fonte comum

    def generate(self):
        with open(self.subtitle_narration_file, "r", encoding="utf-8") as f:
            try:
                subtitles = list(srt.parse(f.read()))
            except srt.SRTParseError as e:
                 print(f"⚠️ Erro crítico ao analisar arquivo SRT: {e}")
                 raise RuntimeError("Falha no parsing do SRT")

        # ---------------------------------------------------------------------
        # CÁLCULO DA ÁREA SEGURA (O "PALCO")
        # ---------------------------------------------------------------------
        screen_width = self.resolution_output[0]
        screen_height = self.resolution_output[1]
        
        # Largura segura = Largura total - (padding esquerdo + padding direito)
        safe_width = screen_width - (2 * self.padding_side)

        subtitle_clips = []
        for sub in subtitles:
            txt = sub.content.replace("\n", " ").strip()
            if not txt: continue # Pula legendas vazias

            start, end = sub.start.total_seconds(), sub.end.total_seconds()

            try:
                # Cria o clipe de texto com quebra de linha automática (caption)
                # restrito à largura segura.
                txt_clip = TextClip(
                        txt,
                        font=self.font_path,
                        fontsize=self.font_size,
                        color=self.color,
                        stroke_color=self.stroke_color,
                        stroke_width=self.stroke_width,
                        size=(safe_width, None), # Define largura máxima exata, altura automática
                        method="caption",
                        align="center"
                    )
                
                # ---------------------------------------------------------------------
                # POSICIONAMENTO EXATO RESPEITANDO O PADDING INFERIOR
                # ---------------------------------------------------------------------
                # Usamos uma função lambda para definir a posição (x, y).
                # X: "center" (centralizado horizontalmente)
                # Y: Altura da tela - Padding Inferior - Altura do próprio texto.
                # Isso garante que a base do texto fique exatamente na linha do padding.
                
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
             # Se não conseguiu gerar nada, retorna um clipe vazio transparente para não quebrar a composição
            print("⚠️ Nenhuma legenda válida foi gerada. Retornando clipe vazio.")
            return ColorClip(size=(1,1), color=(0,0,0,0), duration=0.1)

        # Retorna a composição de todas as legendas posicionadas
        return CompositeVideoClip(subtitle_clips, size=self.resolution_output)