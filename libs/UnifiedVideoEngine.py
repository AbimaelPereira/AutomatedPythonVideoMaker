import os
import json
import numpy as np
import random
from moviepy.editor import *

# Assumed imports from user's libs based on project structure
from libs.Config import Config
from libs.BackgroundVideo import BackgroundVideo
from libs.VisualClip import VisualClip, force_rgb 
from libs.Subtitle import Subtitle
from libs.MediaDownloader import MediaDownloader 
from libs.TTS_Edge import EdgeTTS 

# Assumed standard resolution configuration
AVAILABLE_RESOLUTIONS = {"9:16": (1080, 1920), "16:9": (1920, 1080)}

# --- HELPER PARA CONVERSÃO SEGURA DE COR ---
def hex_to_rgb(hex_value):
    """Converte string hex (#RRGGBB) para tupla (R, G, B) para evitar erros no ColorClip."""
    if not isinstance(hex_value, str):
        return hex_value # Retorna como está se não for string (ex: já é tupla)
    
    hex_value = hex_value.lstrip('#')
    try:
        if len(hex_value) == 6:
            return tuple(int(hex_value[i:i+2], 16) for i in (0, 2, 4))
        else:
            print(f"[WARN] Cor inválida: {hex_value}. Usando preto.")
            return (0, 0, 0)
    except ValueError:
        print(f"[WARN] Erro ao converter cor: {hex_value}. Usando preto.")
        return (0, 0, 0)
# -------------------------------------------

class UnifiedVideoEngine:
    def __init__(self, data_config):
        self.data_config = data_config
        # Garante que global_settings existe
        self.global_settings = data_config.get("global_settings", {})
        self.output_ratio = data_config.get("output_ratio", "9:16")
        self.resolution_output = AVAILABLE_RESOLUTIONS.get(self.output_ratio, (1080, 1920))
        self.tts_config = self.global_settings.get("tts", {})
        
        # 1. Instancia a Config para pegar paths padrões se necessário
        config_instance = Config()
        
        # 2. Define o slug e caminhos.
        slug = data_config.get("slug", "video_sem_slug")
        
        # Define o diretório base de saída
        base_output_dir = config_instance.output_dir if hasattr(config_instance, 'output_dir') else os.path.join(os.getcwd(), "output")

        # Define a pasta do vídeo.
        self.output_dir = os.path.join(base_output_dir, slug)
        
        # Cria o diretório do vídeo
        os.makedirs(self.output_dir, exist_ok=True)
        
        self.final_clips = []
        self.total_duration = 0.0

    def _get_tts_engine(self):
        return EdgeTTS()

    def _process_narration(self, scene_data, target_dir):
        # target_dir será a pasta da cena
        narration_config = scene_data.get("narration", {})
        text = narration_config.get("text", "")
        
        if not text:
            print("[UVE] Cena sem narração. Duração será fixa.")
            return None, 0.0, None, None

        voice = scene_data.get("tts", {}).get("voice", self.tts_config.get("voice"))
        
        # Define o caminho base do áudio DENTRO da pasta da cena
        audio_basename = os.path.join(target_dir, f"audio_{scene_data['id']}")
        
        print(f"[UVE] Gerando áudio para cena {scene_data['id']} em {target_dir}...")
        
        try:
            tts_params = {
                "text": text,
                "voice_id": voice,
                "output_basename": audio_basename,
            }
            tts_engine = EdgeTTS(params=tts_params)
            
            tts_result = tts_engine.generate_audio_and_subtitles()
            
            final_audio_path = tts_result.get("audio_file")
            word_boundaries = tts_result.get("word_boundaries")
            subtitle_file = tts_result.get("subtitle_file")
            
            audio_clip = AudioFileClip(final_audio_path)
            duration = audio_clip.duration
            
        except Exception as e:
            print(f"[ERRO UVE] Falha ao gerar TTS: {e}")
            return None, 4.0, None, None
        
        return audio_clip, duration, word_boundaries, subtitle_file

    def _create_background_clip(self, scene_data, scene_duration, scene_dir, video_dir):
        if "background" in scene_data:
            background_config = scene_data["background"]
            storage_dir = scene_dir
            print(f"[UVE] Usando fundo específico da cena. Salvando em: {storage_dir}")
        else:
            background_config = self.global_settings.get("background", {})
            storage_dir = video_dir
            print(f"[UVE] Usando fundo global. Salvando em: {storage_dir}")

        visual_config = background_config.get("visual", {})
        
        bg_clip = None
        bg_type = visual_config.get("type", "color")
        bg_source = visual_config.get("source")

        if bg_type == "color":
            # CORREÇÃO: Converter hex para RGB
            color_source = bg_source or "#1a1a1a"
            rgb_color = hex_to_rgb(color_source)
            bg_clip = ColorClip(self.resolution_output, color=rgb_color, duration=scene_duration)
            
        elif bg_type == "image":
            image_path = bg_source

            if image_path and image_path.lower().startswith(("http:", "https:")):
                image_path = MediaDownloader.resolve_source_path(image_path, storage_dir)
            
            if image_path and os.path.exists(image_path):
                try:
                    bg_clip = ImageClip(image_path, duration=scene_duration)
                    
                    width, height = bg_clip.size
                    target_w, target_h = self.resolution_output
                    
                    if (width / height) < (target_w / target_h):
                        bg_clip = bg_clip.resize(width=target_w)
                        bg_clip = vfx.crop(bg_clip, x_center=target_w/2, y_center=target_h/2, width=target_w, height=target_h)
                    else:
                        bg_clip = bg_clip.resize(height=target_h)
                        bg_clip = vfx.crop(bg_clip, x_center=target_w/2, y_center=target_h/2, width=target_w, height=target_h)
                    
                    bg_clip = bg_clip.fx(vfx.resize, lambda t: 1.0 + 0.05 * t/scene_duration).set_pos("center")
                    bg_clip = bg_clip.subclip(0, scene_duration)

                except Exception as e:
                    print(f"[ERRO UVE] Falha ao criar ImageClip de fundo: {e}.")
                    bg_clip = ColorClip(self.resolution_output, color=(0,0,0), duration=scene_duration)
            else:
                 bg_clip = ColorClip(self.resolution_output, color=(0,0,0), duration=scene_duration)

        elif bg_type == "video":
            bg_video_processor = BackgroundVideo(params={"background_videos_dir": bg_source, "resolution_output": self.resolution_output})
            bg_clip = bg_video_processor.generate_background_video()
            
            if bg_clip and bg_clip.duration < scene_duration:
                bg_clip = vfx.loop(bg_clip, duration=scene_duration)
            elif bg_clip and bg_clip.duration > scene_duration:
                bg_clip = bg_clip.subclip(0, scene_duration)

        if bg_clip is None:
            # Fallback seguro com tupla
            bg_clip = ColorClip(self.resolution_output, color=(0,0,0), duration=scene_duration)

        # Áudio de fundo
        audio_config = background_config.get("audio", self.global_settings.get("background", {}).get("audio", {}))
        
        if audio_config.get("type") == "directory" and audio_config.get("source"):
             bg_music_dir = audio_config["source"]
             full_bg_music_dir = os.path.join(os.getcwd(), bg_music_dir) 
             
             if os.path.isdir(full_bg_music_dir):
                 music_files = [os.path.join(full_bg_music_dir, f) for f in os.listdir(full_bg_music_dir) if f.endswith(".mp3")]
                 if music_files:
                     bg_audio_clip = AudioFileClip(random.choice(music_files)).subclip(0, scene_duration)
                     bg_audio_clip = bg_audio_clip.volumex(audio_config.get("volume", 0.1))
                     
                     if bg_clip.audio is None:
                        bg_clip = bg_clip.set_audio(bg_audio_clip)
                     else:
                        bg_clip.audio = CompositeAudioClip([bg_clip.audio, bg_audio_clip])
        
        # Tratamento de áudio para arquivo único (conforme seu JSON original tinha suporte implícito)
        elif audio_config.get("type") == "file" and audio_config.get("source"):
            audio_source = MediaDownloader.resolve_source_path(audio_config["source"], storage_dir)
            if audio_source and os.path.exists(audio_source):
                bg_audio_clip = AudioFileClip(audio_source)
                # Loop se o áudio for menor que a cena
                if bg_audio_clip.duration < scene_duration:
                    bg_audio_clip = afx.audio_loop(bg_audio_clip, duration=scene_duration)
                else:
                    bg_audio_clip = bg_audio_clip.subclip(0, scene_duration)
                
                bg_audio_clip = bg_audio_clip.volumex(audio_config.get("volume", 0.1))
                if bg_clip.audio is None:
                    bg_clip = bg_clip.set_audio(bg_audio_clip)
                else:
                    bg_clip.audio = CompositeAudioClip([bg_clip.audio, bg_audio_clip])


        return bg_clip.set_duration(scene_duration)


    def _create_visual_elements_clip(self, scene_data, scene_duration, scene_dir):
        visual_elements = scene_data.get("visual_elements", [])
        
        element_clips = []
        for element_data in visual_elements:
            config = {
                "element_data": element_data,
                "resolution_output": self.resolution_output,
                "temp_dir": scene_dir, 
                "duration": scene_duration
            }
            clip_processor = VisualClip(config)
            clip = clip_processor.generate()
            if clip:
                element_clips.append(clip)
        
        if not element_clips:
            return None
            
        return CompositeVideoClip(element_clips, size=self.resolution_output).set_duration(scene_duration)


    def _create_subtitle_clip(self, scene_duration, subtitle_file):
        if not subtitle_file or not os.path.exists(subtitle_file):
            print("[UVE] Arquivo de legenda não encontrado ou inexistente.")
            return None
        
        subtitle_config = self.global_settings.get("subtitle", {}).copy()
        padding_bottom = self.global_settings.get("padding_bottom", 150)
        padding_side = self.global_settings.get("padding_side", 50)
        
        print(f"[UVE] Configurando legendas com Padding Inferior: {padding_bottom}px, Lateral: {padding_side}px")

        subtitle_config.update({
            "subtitle_narration_file": subtitle_file,
            "resolution_output": self.resolution_output,
            "padding_bottom": padding_bottom,
            "padding_side": padding_side
        })
        
        try:
            subtitle_generator = Subtitle(params=subtitle_config)
            return subtitle_generator.generate().set_duration(scene_duration)
        except Exception as e:
            print(f"[ERRO UVE] Falha ao gerar legenda: {e}")
            return None

    def run(self, output_filename="final_video.mp4"):
        print("[UVE] Iniciando processamento do vídeo...")
        all_scene_clips = []

        for scene in self.data_config.get("scenes", []):
            scene_id = scene.get("id", "cena_desconhecida")
            print(f"=========================================================")
            print(f"[UVE] Processando cena: {scene_id}")

            scene_dir = os.path.join(self.output_dir, scene_id)
            os.makedirs(scene_dir, exist_ok=True)
            print(f"[UVE] Pasta da cena: {scene_dir}")

            # 1. Narração
            audio_clip, duration_from_tts, word_timing, subtitle_file = self._process_narration(scene, scene_dir)
            
            # 2. Duração
            scene_duration = scene.get("duration", duration_from_tts)
            if not scene_duration or scene_duration < 0.1:
                scene_duration = 4.0 
            print(f"[UVE] Duração final da cena: {scene_duration:.2f} segundos.")

            # 3. Fundo
            background_clip = self._create_background_clip(scene, scene_duration, scene_dir, self.output_dir)
            
            # 4. Elementos Visuais
            visual_clip = self._create_visual_elements_clip(scene, scene_duration, scene_dir)
            
            # 5. Legendas
            subtitle_clip = None
            if scene.get("narration", {}).get("subtitles", False):
                subtitle_clip = self._create_subtitle_clip(scene_duration, subtitle_file)

            # 6. Composição
            # Empilha: Fundo -> Visual -> Legenda
            final_scene_clip = [background_clip]
            if visual_clip: final_scene_clip.append(visual_clip)
            if subtitle_clip: final_scene_clip.append(subtitle_clip)

            # --- CORREÇÃO DE SEGURANÇA ---
            # Garante que TODOS os clips sejam RGB antes de compor
            # Isso evita que o MoviePy tente misturar arrays de Strings (do ColorClip bugado) ou Máscaras com RGB
            safe_clips = []
            for c in final_scene_clip:
                try:
                    # Aplica force_rgb que foi importado do VisualClip
                    c = c.fl_image(force_rgb) 
                    safe_clips.append(c)
                except Exception as e:
                    print(f"[WARN] Falha ao sanitizar clip: {e}")
                    safe_clips.append(c)

            composed_clip = CompositeVideoClip(safe_clips, size=self.resolution_output).set_duration(scene_duration)
            
            # Reforço final
            composed_clip = composed_clip.fl_image(force_rgb)

            if audio_clip:
                composed_clip.audio = CompositeAudioClip([composed_clip.audio, audio_clip]) if composed_clip.audio else audio_clip

            all_scene_clips.append(composed_clip)
            self.total_duration += scene_duration

        if not all_scene_clips:
            print("[ERRO UVE] Nenhuma cena processada.")
            return None
            
        final_video = concatenate_videoclips(all_scene_clips, method="compose")

        slug = self.data_config.get("slug", "final_video")
        output_filename = f"{slug}.mp4"
        output_path = os.path.join(self.output_dir, output_filename)
        
        print(f"=========================================================")
        print(f"[UVE] Escrevendo vídeo final em: {output_path}")
        
        ffmpeg_audio_temp = os.path.join(self.output_dir, 'temp-audio-rendering.m4a')
        
        final_video.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            temp_audiofile=ffmpeg_audio_temp,
            remove_temp=True,
            fps=24,
            preset='medium'
        )
        print("[UVE] Processamento concluído.")
        return output_path