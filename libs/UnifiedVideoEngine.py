import os
import json
import numpy as np
import random
from moviepy.editor import *
import subprocess
import shutil
import gc

from libs.Config import Config
from libs.BackgroundVideo import BackgroundVideo
from libs.VisualClip import VisualClip, force_rgb 
from libs.Subtitle import Subtitle
from libs.MediaDownloader import MediaDownloader 
from libs.TTS_Edge import EdgeTTS
from libs.LayoutEngine import LayoutEngine 
from libs.YouTube import YouTube
from libs.OverlayEngine import OverlayEngine  # ADICIONADO

AVAILABLE_RESOLUTIONS = {"9:16": (1080, 1920), "16:9": (1920, 1080)}

def hex_to_rgb(hex_value):
    if not isinstance(hex_value, str):
        return hex_value 
    hex_value = hex_value.lstrip('#')
    try:
        if len(hex_value) == 6:
            return tuple(int(hex_value[i:i+2], 16) for i in (0, 2, 4))
        else:
            return (0, 0, 0)
    except ValueError:
        return (0, 0, 0)

def deep_merge(a, b):
    """
    Retorna um dicionário resultante da mescla de 'a' (base) com 'b' (overrides).
    - Valores escalares são sobrescritos por b quando presentes.
    - Dicionários aninhados são mesclados recursivamente.
    """
    if not isinstance(a, dict):
        return b
    result = dict(a)
    for k, v in (b or {}).items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result

class UnifiedVideoEngine:
    def __init__(self, data_config):
        self.data_config = data_config
        self.global_settings = data_config.get("global_settings", {})
        self.output_ratio = data_config.get("output_ratio", "9:16")
        self.resolution_output = AVAILABLE_RESOLUTIONS.get(self.output_ratio, (1080, 1920))
        self.tts_config = self.global_settings.get("tts", {})
        self.bg_cache = {} # Dicionário para guardar os clipes: { "caminho": [lista_de_clips] }

        self.config_instance = Config()
        
        if "padding_bottom" in self.global_settings:
            self.config_instance.padding_bottom = self.global_settings["padding_bottom"]
        if "padding_top" in self.global_settings:
            self.config_instance.padding_top = self.global_settings["padding_top"]
        
        self.config_instance.width = self.resolution_output[0]
        self.config_instance.height = self.resolution_output[1]

        slug = data_config.get("slug", "video_sem_slug")
        base_output_dir = self.config_instance.output_dir if hasattr(self.config_instance, 'output_dir') else os.path.join(os.getcwd(), "output")
        self.output_dir = os.path.join(base_output_dir, slug)
        os.makedirs(self.output_dir, exist_ok=True)
        
        self.final_clips = []
        self.total_duration = 0.0

    def _get_tts_engine(self):
        return EdgeTTS()

    def _process_narration(self, scene_data, target_dir):
        narration_config = scene_data.get("narration", {})
        text = narration_config.get("text", "")
        
        if not text:
            print("[UVE] Cena sem narração. Duração será fixa.")
            return None, 0.0, None, None

        voice = scene_data.get("tts", {}).get("voice", self.tts_config.get("voice"))
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
        """
        Faz merge entre global background e scene background (scene sobrescreve global)
        e aplica overlays (global e/ou por cena) sobre o fundo, respeitando override.
        """
        # Merge de background
        global_background = self.global_settings.get("background", {}) or {}
        scene_background = scene_data.get("background", None)

        if scene_background is not None:
            background_config = deep_merge(global_background, scene_background)
            storage_dir = scene_dir
        else:
            background_config = dict(global_background)
            storage_dir = video_dir

        visual_config = background_config.get("visual", {})
        bg_type = visual_config.get("type", "color")
        bg_clip = None

        try:
            if bg_type == "color":
                color = visual_config.get("source", "#000000")
                if isinstance(color, str):
                    color = hex_to_rgb(color)
                bg_clip = ColorClip(size=self.resolution_output, color=color).set_duration(scene_duration)

            elif bg_type == "image":
                src = visual_config.get("source")
                path = MediaDownloader.resolve_source_path(src, storage_dir)
                bg_clip = ImageClip(path).resize(newsize=self.resolution_output).set_duration(scene_duration)

            elif bg_type == "video":
                src = visual_config.get("source")
                path = MediaDownloader.resolve_source_path(src, storage_dir)
                bg_clip = VideoFileClip(path, audio=False)
                bg_clip = bg_clip.resize(newsize=self.resolution_output).set_duration(scene_duration).without_audio()

            elif bg_type == "directory":
                source_dir = visual_config.get("source")
                if source_dir not in self.bg_cache:
                    loader = BackgroundVideo({
                        "background_videos_dir": source_dir,
                        "resolution_output": self.resolution_output,
                        "output_ratio": self.output_ratio,
                        "crossfade_duration": self.global_settings.get("crossfade_duration", 0.8),
                        "enable_crossfade": self.global_settings.get("enable_crossfade", True),
                        "shuffle_clips": self.global_settings.get("shuffle_clips", True),
                        "loop_background": self.global_settings.get("loop_background", True),
                        "max_clips": self.global_settings.get("max_clips")
                    })
                    # Se a implementação possuir get_all_processed_clips:
                    if hasattr(loader, "get_all_processed_clips"):
                        self.bg_cache[source_dir] = loader.get_all_processed_clips()
                    else:
                        self.bg_cache[source_dir] = []
                if self.bg_cache.get(source_dir):
                    bg_clip = self.bg_cache[source_dir][0].set_duration(scene_duration)
                else:
                    bg_clip = ColorClip(size=self.resolution_output, color=(0,0,0)).set_duration(scene_duration)

            else:
                bg_clip = ColorClip(size=self.resolution_output, color=(0,0,0)).set_duration(scene_duration)
        except Exception as e:
            print(f"[UVE] Falha ao criar fundo: {e}")
            bg_clip = ColorClip(size=self.resolution_output, color=(0,0,0)).set_duration(scene_duration)

        # Overlays (merge global <- scene, cena sobrescreve)
        global_overlays = self.global_settings.get("overlays", {}) or {}
        scene_overlays = scene_data.get("overlays", None)

        if scene_overlays is not None:
            overlays_config = deep_merge(global_overlays, scene_overlays)
        else:
            overlays_config = dict(global_overlays)

        overlay_clip = None
        if overlays_config:
            try:
                ov_engine = OverlayEngine(resolution=self.resolution_output)
                overlay_clip = ov_engine.create_overlays_clip(overlays_config, scene_duration)
            except Exception as e:
                print(f"[UVE] Falha ao gerar overlays: {e}")

        # Se houver overlays, compor sobre o fundo
        if overlay_clip is not None:
            try:
                composed = CompositeVideoClip([bg_clip, overlay_clip], size=self.resolution_output).set_duration(scene_duration)
                return composed.fl_image(force_rgb)
            except Exception as e:
                print(f"[UVE] Falha ao compor overlay sobre fundo: {e}")

        return bg_clip.fl_image(force_rgb)

    def _create_visual_elements_clip(self, scene_data, scene_duration, scene_dir):
        elements = scene_data.get("visual_elements", [])
        if not elements:
            return None
        clips = []
        for el in elements:
            vc = VisualClip({
                "element_data": el,
                "resolution_output": self.resolution_output,
                "temp_dir": scene_dir,
                "duration": scene_duration,
            }).generate()
            if vc:
                clips.append(vc)
        if not clips:
            return None
        return CompositeVideoClip(clips, size=self.resolution_output).set_duration(scene_duration).fl_image(force_rgb)

    def _create_subtitle_clip(self, scene_duration, subtitle_file, has_visual_elements=False):  # ADICIONAR parâmetro
        try:
            if not subtitle_file or not os.path. exists(subtitle_file):
                return None
            sub = Subtitle({
                "subtitle_file": subtitle_file,
                "duration": scene_duration,
                "resolution_output": self.resolution_output,
                "has_visual_elements": has_visual_elements,  # ADICIONAR
                # Pegar configurações do global_settings se existirem
                **self.global_settings.get("subtitle", {})  # ADICIONAR
            })
            return sub.generate()
        except Exception as e:
            print(f"[UVE] Falha ao criar legendas: {e}")
            return None

    def run(self, output_filename="final_video.mp4"):
        print("[UVE] Iniciando processamento do vídeo...")
        scene_files = []
        temp_dir = os.path.join(self.output_dir, "_temp")
        os.makedirs(temp_dir, exist_ok=True)

        for scene in self.data_config.get("scenes", []):
            scene_id = scene.get("id", "cena_desconhecida")
            print(f"[UVE] Processando cena: {scene_id}")

            scene_dir = os.path.join(self.output_dir, scene_id)
            os.makedirs(scene_dir, exist_ok=True)

            audio_clip, duration_from_tts, word_timing, subtitle_file = self._process_narration(scene, scene_dir)
            scene_duration = scene.get("duration", duration_from_tts)
            if not scene_duration or scene_duration < 0.1:
                scene_duration = 4.0 

            background_clip = self._create_background_clip(scene, scene_duration, scene_dir, self.output_dir)
            visual_clip = self._create_visual_elements_clip(scene, scene_duration, scene_dir)

            subtitle_clip = None
            if scene. get("narration", {}).get("subtitles", False):
                has_visuals = bool(scene.get("visual_elements"))  # verificar se há elementos visuais
                subtitle_clip = self._create_subtitle_clip(scene_duration, subtitle_file, has_visuals)

            final_scene_clip = [background_clip]
            if visual_clip: final_scene_clip.append(visual_clip)
            if subtitle_clip: final_scene_clip.append(subtitle_clip)

            safe_clips = []
            for c in final_scene_clip:
                try:
                    c = c.fl_image(force_rgb) 
                    safe_clips.append(c)
                except Exception:
                    safe_clips.append(c)

            composed_clip = CompositeVideoClip(safe_clips, size=self.resolution_output).set_duration(scene_duration)
            composed_clip = composed_clip.fl_image(force_rgb)

            if audio_clip:
                composed_clip.audio = CompositeAudioClip([composed_clip.audio, audio_clip]) if composed_clip.audio else audio_clip

            scene_index = len(scene_files)
            temp_scene_path = os.path.join(temp_dir, f"scene_{scene_index:04d}.mp4")
            temp_audiofile = os.path.join(temp_dir, f"temp-audio-{scene_index}.m4a")
            try:
                print(f"[UVE] Renderizando cena {scene_index} para {temp_scene_path} ...")
                composed_clip.write_videofile(
                    temp_scene_path,
                    codec='libx264',
                    audio_codec='aac',
                    temp_audiofile=temp_audiofile,
                    remove_temp=True,
                    fps=24,
                    preset='medium',
                    threads=1
                )
                scene_files.append(temp_scene_path)
                print(f"[UVE] Cena {scene_index} renderizada: {temp_scene_path}")
            except Exception as e:
                print(f"[UVE] Erro ao renderizar cena {scene_index}: {e}")

        output_path = os.path.join(self.output_dir, output_filename)
        if scene_files:
            try:
                concat_list_path = os.path.join(temp_dir, "concat_list.txt")
                with open(concat_list_path, "w", encoding="utf-8") as f:
                    for p in scene_files:
                        f.write(f"file '{os.path.abspath(p)}'\n")

                subprocess.run([
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", concat_list_path, "-c", "copy", output_path
                ], check=True)
                print(f"[UVE] Vídeo final concatenado: {output_path}")
            except Exception as e:
                print(f"[UVE] Falha ao concatenar vídeo final: {e}")

        # (mantém lógica existente para áudio global, upload e debug)
        try:
            bg_config = self.global_settings.get("background", {})
        except Exception as e:
            print(f"[UVE] Aviso: falha ao aplicar audio de fundo global: {e}")

        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass

        if self.data_config.get("youtube") and self.data_config.get("debug") is not True:
            try:
                print("[UVE] Iniciando upload para o YouTube...")
                youtube_params = self.data_config.get("youtube", {})
                youtube_params["video_path"] = output_path
                youtube_uploader = YouTube(params=youtube_params)
                youtube_uploader.upload()
            except Exception as e:
                print(f"[UVE] Upload YouTube falhou: {e}")

        if self.data_config.get("debug") is True:
            try:
                if os.name == 'nt':
                    os.startfile(output_path)
                elif os.name == 'posix':
                    subprocess.run(["open", output_path])
            except Exception:
                pass