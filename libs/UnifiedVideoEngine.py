import os
import json
import numpy as np
import random
from moviepy.editor import *

# Assumed imports from user's libs based on project structure
from libs.Config import Config
from libs.BackgroundVideo import BackgroundVideo
from libs.VisualClip import VisualClip
from libs.Subtitle import Subtitle
from libs.MediaDownloader import MediaDownloader 
from libs.TTS_Edge import EdgeTTS 

# Assumed standard resolution configuration
AVAILABLE_RESOLUTIONS = {"9:16": (1080, 1920), "16:9": (1920, 1080)}

class UnifiedVideoEngine:
    def __init__(self, data_config):
        self.data_config = data_config
        self.global_settings = data_config.get("global_settings", {})
        self.output_ratio = data_config.get("output_ratio", "9:16")
        self.resolution_output = AVAILABLE_RESOLUTIONS.get(self.output_ratio, (1080, 1920))
        self.tts_config = self.global_settings.get("tts", {})
        
        # 1. Instancia a Config.
        config_instance = Config()
        
        # 2. Define o slug e caminhos.
        slug = data_config.get("slug", "video_sem_slug")
        
        # Define o diretório base de saída (usa o valor da Config ou o default)
        base_output_dir = config_instance.output_dir if hasattr(config_instance, 'output_dir') else os.path.join(os.getcwd(), "output")

        # CORREÇÃO DA ORGANIZAÇÃO DE PASTAS: Cria pasta específica por vídeo
        self.output_dir = os.path.join(base_output_dir, slug)
        self.temp_dir = os.path.join(self.output_dir, "temp")
        
        # Cria os diretórios
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)
        
        self.final_clips = []
        self.total_duration = 0.0

    def _get_tts_engine(self):
        # Este método não é mais estritamente necessário, mas mantido.
        return EdgeTTS()

    def _process_narration(self, scene_data):
        narration_config = scene_data.get("narration", {})
        text = narration_config.get("text", "")
        
        if not text:
            print("[UVE] Cena sem narração. Duração será fixa.")
            return None, 0.0, None

        # Override de voz na cena, se houver
        voice = scene_data.get("tts", {}).get("voice", self.tts_config.get("voice"))
        
        # Arquivo de áudio temporário (apenas o basename)
        audio_basename = os.path.join(self.temp_dir, f"audio_{scene_data['id']}")
        
        print(f"[UVE] Gerando áudio para cena {scene_data['id']} com voz {voice}...")
        
        try:
            # CORREÇÃO DO ERRO: Passa todos os parâmetros relevantes para o construtor EdgeTTS
            tts_params = {
                "text": text,
                "voice_id": voice,
                "output_basename": audio_basename,
                # Adicione outros parâmetros EdgeTTS se necessário, como 'rate'
            }
            tts_engine = EdgeTTS(params=tts_params)
            
            # Chama o método sem argumentos, usando self.text, self.voice_id, etc.
            final_audio_path, word_boundaries = tts_engine.generate_audio_and_subtitles()
            
            # Recalcula a duração a partir do arquivo gerado
            audio_clip = AudioFileClip(final_audio_path)
            duration = audio_clip.duration
            
        except Exception as e:
            print(f"[ERRO UVE] Falha ao gerar TTS: {e}")
            return None, 4.0, None # Fallback
        
        audio_clip = AudioFileClip(final_audio_path)
        
        return audio_clip, duration, word_boundaries

    def _create_background_clip(self, scene_data, scene_duration):
        # Prioriza a configuração da cena, senão usa a global
        background_config = scene_data.get("background", self.global_settings.get("background", {}))
        visual_config = background_config.get("visual", {})
        
        bg_clip = None
        bg_type = visual_config.get("type", "color")
        bg_source = visual_config.get("source")
        
        print(f"[UVE] Criando clipe de fundo. Tipo: {bg_type}, Fonte: {bg_source}")

        if bg_type == "color":
            color_source = bg_source or "#1a1a1a"
            bg_clip = ColorClip(self.resolution_output, color=color_source, duration=scene_duration)
            
        elif bg_type == "image":
            image_path = bg_source

            # Chamada ao MediaDownloader para resolver URLs no novo self.temp_dir
            if image_path and image_path.lower().startswith(("http:", "https:")):
                image_path = MediaDownloader.resolve_source_path(image_path, self.temp_dir)
            
            if image_path and os.path.exists(image_path):
                print(f"[UVE] Fundo de imagem local (ou baixado): {image_path}")
                try:
                    # Carrega a imagem e define a duração
                    bg_clip = ImageClip(image_path, duration=scene_duration)
                    
                    # O fundo deve preencher o quadro (resize/crop)
                    width, height = bg_clip.size
                    target_w, target_h = self.resolution_output
                    
                    if (width / height) < (target_w / target_h):
                        bg_clip = bg_clip.resize(width=target_w)
                        bg_clip = vfx.crop(bg_clip, x_center=target_w/2, y_center=target_h/2, width=target_w, height=target_h)
                    else:
                        bg_clip = bg_clip.resize(height=target_h)
                        bg_clip = vfx.crop(bg_clip, x_center=target_w/2, y_center=target_h/2, width=target_w, height=target_h)
                    
                    # Adiciona zoom_in simples como efeito visual (opcional)
                    bg_clip = bg_clip.fx(vfx.resize, lambda t: 1.0 + 0.05 * t/scene_duration).set_pos("center")
                    bg_clip = bg_clip.subclip(0, scene_duration) # Garante a duração

                except Exception as e:
                    print(f"[ERRO UVE] Falha ao criar ImageClip de fundo: {e}. Usando cor de fallback.")
                    bg_clip = ColorClip(self.resolution_output, color="#000000", duration=scene_duration)
            else:
                 print("[UVE] Falha ao obter caminho da imagem. Usando cor de fallback.")
                 bg_clip = ColorClip(self.resolution_output, color="#000000", duration=scene_duration)

        elif bg_type == "video":
            # Simplificação: assume que videos de background são resolvidos pelo BackgroundVideo
            bg_video_processor = BackgroundVideo(params={"background_videos_dir": bg_source, "resolution_output": self.resolution_output})
            bg_clip = bg_video_processor.generate_background_video()
            
            if bg_clip and bg_clip.duration < scene_duration:
                # Loop se o vídeo for muito curto
                bg_clip = vfx.loop(bg_clip, duration=scene_duration)
            elif bg_clip and bg_clip.duration > scene_duration:
                bg_clip = bg_clip.subclip(0, scene_duration)

        if bg_clip is None:
            # Fallback final se tudo falhar
            print("[UVE] Falha total ao criar clipe de fundo. Usando clipe preto.")
            return ColorClip(self.resolution_output, color="#000000", duration=scene_duration)

        # Adiciona o áudio de fundo (global ou por cena)
        audio_config = background_config.get("audio", self.global_settings.get("background", {}).get("audio", {}))
        
        if audio_config.get("type") == "directory" and audio_config.get("source"):
             bg_music_dir = audio_config["source"]
             # Adiciona o path base do projeto, assumindo que bg_music/geopolitica é relativo
             full_bg_music_dir = os.path.join(os.getcwd(), bg_music_dir) 
             
             if os.path.isdir(full_bg_music_dir):
                 music_files = [os.path.join(full_bg_music_dir, f) for f in os.listdir(full_bg_music_dir) if f.endswith(".mp3")]
                 if music_files:
                     bg_audio_clip = AudioFileClip(random.choice(music_files)).subclip(0, scene_duration)
                     bg_audio_clip = bg_audio_clip.volumex(audio_config.get("volume", 0.1))
                     
                     if bg_clip.audio is None:
                        bg_clip = bg_clip.set_audio(bg_audio_clip)
                     else:
                        # Mixa o áudio de fundo (se já houver) com a música de fundo
                        bg_clip.audio = CompositeAudioClip([bg_clip.audio, bg_audio_clip])

        return bg_clip.set_duration(scene_duration)


    def _create_visual_elements_clip(self, scene_data, scene_duration):
        # Processa os elementos visuais que se sobrepõem ao fundo
        visual_elements = scene_data.get("visual_elements", [])
        
        element_clips = []
        for element_data in visual_elements:
            config = {
                "element_data": element_data,
                "resolution_output": self.resolution_output,
                "temp_dir": self.temp_dir,
                "duration": scene_duration
            }
            clip_processor = VisualClip(config)
            clip = clip_processor.generate()
            if clip:
                element_clips.append(clip)
        
        if not element_clips:
            return None
            
        # Simplificação: compõe todos os elementos visuais
        return CompositeVideoClip(element_clips, size=self.resolution_output).set_duration(scene_duration)


    def _create_subtitle_clip(self, scene_duration, word_timing):
        # Apenas cria o clipe de legenda se houver timing
        if not word_timing:
            return None
        
        # O EdgeTTS retorna os limites de palavras para a Subtitle usar
        subtitle_config = self.global_settings.get("subtitle", {})
        
        # Assumimos que Subtitle é uma classe que retorna um TextClip/CompositeVideoClip
        subtitle_generator = Subtitle(
            word_timing=word_timing,
            resolution=self.resolution_output,
            config=subtitle_config
        )
        
        return subtitle_generator.generate().set_duration(scene_duration)

    def run(self, output_filename="final_video.mp4"):
        print("[UVE] Iniciando processamento do vídeo...")
        all_scene_clips = []

        for scene in self.data_config.get("scenes", []):
            scene_id = scene.get("id", "cena_desconhecida")
            print(f"=========================================================")
            print(f"[UVE] Processando cena: {scene_id}")

            # 1. Processar Narração (TTS)
            audio_clip, duration_from_tts, word_timing = self._process_narration(scene)
            
            # 2. Definir Duração da Cena
            scene_duration = scene.get("duration", duration_from_tts)
            if not scene_duration or scene_duration < 0.1:
                scene_duration = 4.0 # Duração de fallback
            print(f"[UVE] Duração final da cena: {scene_duration:.2f} segundos.")

            # 3. Criar Clipe de Fundo (Com a correção de URL de imagem)
            background_clip = self._create_background_clip(scene, scene_duration)
            
            # 4. Criar Clipe de Elementos Visuais
            visual_clip = self._create_visual_elements_clip(scene, scene_duration)
            
            # 5. Criar Clipe de Legendas (Subtitles)
            subtitle_clip = None
            if scene.get("narration", {}).get("subtitles", False):
                subtitle_clip = self._create_subtitle_clip(scene_duration, word_timing)

            # 6. Compor a Cena
            final_scene_clip = [background_clip]
            if visual_clip: final_scene_clip.append(visual_clip)
            if subtitle_clip: final_scene_clip.append(subtitle_clip)

            composed_clip = CompositeVideoClip(final_scene_clip, size=self.resolution_output).set_duration(scene_duration)
            
            # 7. Adicionar o Áudio da Narração
            if audio_clip:
                composed_clip.audio = CompositeAudioClip([composed_clip.audio, audio_clip]) if composed_clip.audio else audio_clip

            all_scene_clips.append(composed_clip)
            self.total_duration += scene_duration

        if not all_scene_clips:
            print("[ERRO UVE] Nenhuma cena processada.")
            return None
            
        # 8. Concatenar todas as cenas
        final_video = concatenate_videoclips(all_scene_clips, method="compose")

        # 9. Escrever o Arquivo Final
        # Garante o nome do arquivo final baseado no slug na pasta correta
        slug = self.data_config.get("slug", "final_video")
        output_filename = f"{slug}.mp4"
        output_path = os.path.join(self.output_dir, output_filename)
        
        print(f"=========================================================")
        print(f"[UVE] Escrevendo vídeo final em: {output_path}")
        final_video.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            # Usa o self.temp_dir correto para o arquivo de áudio temporário do MoviePy
            temp_audiofile=os.path.join(self.temp_dir, 'temp-audio.m4a'),
            remove_temp=True,
            fps=24,
            preset='medium'
        )
        print("[UVE] Processamento concluído.")
        return output_path