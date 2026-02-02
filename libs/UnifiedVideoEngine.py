import os
import json
import numpy as np
import random
from moviepy.editor import *
import subprocess
import shutil
import gc
import hashlib

from libs.Config import Config
from libs.VisualClip import VisualClip, force_rgb
from libs.Subtitle import Subtitle
from libs.MediaDownloader import MediaDownloader
from libs.LayoutEngine import LayoutEngine
from libs.YouTube import YouTube
from libs.Background.BackgroundEngine import BackgroundEngine
from libs.NarrationEngine import NarrationEngine
from libs.TransitionEngine import TransitionEngine

try:
    from libs.AIProviders import ai_manager
    from libs.AIProviders.AICache import AICache
    AI_AVAILABLE = True
    print("[UVE] ✅ Sistema de IA carregado")
except ImportError as e:
    AI_AVAILABLE = False
    print(f"[UVE] ⚠️ Sistema de IA não disponível: {e}")

AVAILABLE_RESOLUTIONS = {"9:16": (1080, 1920), "16:9": (1920, 1080)}


def hex_to_rgb(hex_value):
    """Converte cor hexadecimal para tupla RGB"""
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
    """Mescla dicionários recursivamente."""
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
    VALID_AUDIO_EXTENSIONS = [".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"]
    
    def __init__(self, data_config):
        self.data_config = data_config
        self.global_settings = data_config.get("global_settings", {})
        self.output_ratio = data_config.get("output_ratio", "9:16")
        self.resolution_output = AVAILABLE_RESOLUTIONS.get(self.output_ratio, (1080, 1920))
        self.tts_config = self.global_settings.get("tts", {})

        # Caches
        self.dir_media_index = {}  # path -> list[VideoClip] (DirectoryType cache)

        if AI_AVAILABLE:
            cache_dir = os.path.join(os.getcwd(), "cache", "ai_generated")
            self.ai_cache = AICache(cache_dir)
        else:
            self.ai_cache = None

        self.config_instance = Config()

        if "padding_bottom" in self.global_settings:
            self.config_instance.padding_bottom = self.global_settings["padding_bottom"]
        if "padding_top" in self.global_settings:
            self.config_instance.padding_top = self.global_settings["padding_top"]
        if "padding_side" in self.global_settings:
            self.config_instance.padding_side = self.global_settings["padding_side"]

        self.config_instance.width = self.resolution_output[0]
        self.config_instance.height = self.resolution_output[1]

        slug = data_config.get("slug", "video_sem_slug")
        base_output_dir = getattr(self.config_instance, 'output_dir', os.path.join(os.getcwd(), "output"))
        self.output_dir = os.path.join(base_output_dir, slug)
        os.makedirs(self.output_dir, exist_ok=True)

        self.final_clips = []
        self.total_duration = 0.0

    def _create_visual_elements_clip(self, scene_data, scene_duration, scene_dir):
        """Cria elementos visuais da cena."""
        elements = scene_data.get("visual_elements", [])
        if not elements:
            return None

        print(f"[UVE] Processando {len(elements)} elementos visuais...")

        valid_clips_info = []
        valid_element_data_for_layout = []

        for i, element_data in enumerate(elements):
            try:
                config = {
                    "element_data": element_data,
                    "resolution_output": self.resolution_output,
                    "temp_dir": scene_dir,
                    "duration": scene_duration,
                }

                processor = VisualClip(config)
                raw_clip = processor.generate()

                if raw_clip: 
                    w, h = raw_clip.size
                    element_data_copy = element_data.copy()
                    element_data_copy['original_size'] = (w, h)

                    valid_clips_info.append(raw_clip)
                    valid_element_data_for_layout.append(element_data_copy)
                    print(f"[UVE] ✅ Elemento {i + 1} gerado: {w}x{h}")
                else:
                    print(f"[UVE] ⚠️ Falha ao gerar elemento {i + 1}")

            except Exception as e: 
                print(f"[UVE] ❌ Erro no elemento {i + 1}: {e}")

        if not valid_clips_info:
            print("[UVE] ❌ Nenhum elemento visual foi gerado com sucesso")
            return None

        try:
            layout_results = LayoutEngine.process_stack_layout(
                valid_element_data_for_layout,
                self.config_instance
            )

            final_clips = []

            for i, clip in enumerate(valid_clips_info):
                if i >= len(layout_results):
                    break

                layout = layout_results[i]
                final_size = layout['final_size']
                final_pos = layout['final_position']

                try:
                    clip_resized = clip.resize(newsize=final_size)
                    clip_positioned = clip_resized.set_position(final_pos)
                    final_clips.append(clip_positioned)
                    print(f"[UVE] ✅ Elemento {i + 1} posicionado: {final_size} @ {final_pos}")
                except Exception as e:
                    print(f"[UVE] ❌ Falha ao posicionar elemento {i + 1}: {e}")

            if not final_clips:
                print("[UVE] ❌ Nenhum elemento foi posicionado corretamente")
                return None

            return CompositeVideoClip(final_clips, size=self.resolution_output).set_duration(
                scene_duration).fl_image(force_rgb)

        except Exception as e: 
            print(f"[UVE] ❌ Falha no LayoutEngine: {e}")
            print("[UVE] Usando posicionamento centralizado como fallback")

            centered_clips = []
            for i, clip in enumerate(valid_clips_info):
                try:
                    clip_centered = clip.set_position('center')
                    centered_clips.append(clip_centered)
                except Exception as e:
                    print(f"[UVE] ❌ Falha no fallback do elemento {i + 1}: {e}")

            if centered_clips:
                return CompositeVideoClip(centered_clips, size=self.resolution_output).set_duration(
                    scene_duration).fl_image(force_rgb)

            return None

    def _create_subtitle_clip(self, scene_duration, subtitle_file, has_visual_elements=False):
        """Cria clip de legendas."""
        try:
            if not subtitle_file or not os.path.exists(subtitle_file):
                print("[UVE] ⚠️ Arquivo de legenda não encontrado")
                return None

            print(f"[UVE] Gerando legendas do arquivo: {subtitle_file}")

            subtitle_config = {
                "subtitle_narration_file": subtitle_file,
                "resolution_output": self.resolution_output,
                "padding_bottom": getattr(self.config_instance, 'padding_bottom', 200),
                "padding_side": getattr(self.config_instance, 'padding_side', 50),
                "padding_top":  getattr(self.config_instance, 'padding_top', 200),
                "has_visual_elements": True,
            }

            global_subtitle_config = self.global_settings.get("subtitle", {})
            subtitle_config.update(global_subtitle_config)

            subtitle_generator = Subtitle(params=subtitle_config)
            subtitle_clip = subtitle_generator.generate()

            if subtitle_clip:
                subtitle_clip = subtitle_clip.set_duration(scene_duration)
                print("[UVE] ✅ Legendas geradas com sucesso")
                return subtitle_clip
            else:
                print("[UVE] ❌ Falha na geração das legendas")
                return None

        except Exception as e:
            print(f"[UVE] ❌ Falha ao criar legendas: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _apply_background_audio_to_video(self, video_path: str, output_path: str) -> str:
        """
        Aplica áudio de fundo ao vídeo final concatenado.
        """
        bg_audio_config = self.global_settings.get("background", {}).get("audio", {})
        
        if not bg_audio_config:
            print("[UVE] Sem configuração de áudio de fundo")
            return video_path
        
        audio_type = bg_audio_config.get("type", "file")
        source = bg_audio_config.get("source")
        volume = bg_audio_config.get("volume", 0.3)
        
        if not source:
            print("[UVE] Áudio de fundo sem source configurado")
            return video_path
        
        try:
            if audio_type == "directory":
                if not os.path.isdir(source):
                    print(f"[UVE] ⚠️ Diretório de áudio não encontrado: {source}")
                    return None
                
                valid_extensions = ('.mp3', '.wav', '.ogg', '.m4a')
                audio_files = [f for f in os.listdir(source) if f.lower().endswith(valid_extensions)]
                
                if not audio_files:
                    print(f"[UVE] ⚠️ Nenhum arquivo de áudio válido encontrado em: {source}")
                    return None
                     
                audio_path = os.path.join(source, random.choice(audio_files))
            else:
                audio_path = source
            
            if not audio_path or not os.path.exists(audio_path):
                print(f"[UVE] ⚠️ Áudio de fundo não encontrado:  {audio_path}")
                return video_path
            
            print(f"[UVE] 🎵 Aplicando áudio de fundo: {os.path.basename(audio_path)}")
            
            video_clip = VideoFileClip(video_path)
            video_duration = video_clip.duration
            
            bg_audio = AudioFileClip(audio_path)
            
            if bg_audio.duration < video_duration:
                loops_needed = int(video_duration / bg_audio.duration) + 1
                bg_clips = [bg_audio] * loops_needed
                bg_audio = concatenate_audioclips(bg_clips)
            
            bg_audio = bg_audio.subclip(0, video_duration)
            bg_audio = bg_audio.volumex(volume)
            
            if video_clip.audio:
                final_audio = CompositeAudioClip([video_clip.audio, bg_audio])
            else:
                final_audio = bg_audio
            
            final_video = video_clip.set_audio(final_audio)
            
            print(f"[UVE] 🎬 Renderizando vídeo com áudio de fundo...")
            final_video.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac',
                fps=30,  # CORRIGIDO: FPS consistente
                preset='medium',
                threads=4,
                verbose=False,
                logger=None
            )
            
            video_clip.close()
            bg_audio.close()
            final_video.close()
            
            print(f"[UVE] ✅ Áudio de fundo aplicado:  {os.path.basename(output_path)}")
            return output_path
            
        except Exception as e:
            print(f"[UVE] ❌ Erro ao aplicar áudio de fundo: {e}")
            import traceback
            traceback.print_exc()
            return video_path

    def _render_scene(self, scene_index, scene_id, total_scenes, composed_clip, narration_clip, scene_dir):
        scene_clip_path = os.path.join(scene_dir, f"{scene_id}.mp4")
        temp_audiofile = os.path.join(scene_dir, f"{scene_id}.m4a")

        print(f"[UVE] 🎬 Renderizando cena {scene_index + 1}/{total_scenes}...")

        # CORREÇÃO APLICADA: FPS de 24 para 30
        composed_clip.write_videofile(
            scene_clip_path,
            codec='libx264',
            audio_codec='aac',
            temp_audiofile=temp_audiofile,
            remove_temp=True,
            fps=30,  # CORRIGIDO: Era 24, agora 30 para evitar trancos
            preset='medium',
            threads=4,
            verbose=False,
            logger=None  # Remove logs excessivos
        )

        print(f"[UVE] ✅ Cena {scene_index + 1} renderizada:  {os.path.basename(scene_clip_path)}")

        try:
            composed_clip.close()
            if narration_clip:
                narration_clip.close()
        except: 
            pass

        del composed_clip
        gc.collect()

        return scene_clip_path
    
    def run(self):
        """Método principal de renderização."""
        print("[UVE] 🚀 Iniciando processamento do vídeo...")

        scene_files = []

        scenes = self.data_config.get("scenes", [])
        total_scenes = len(scenes)

        if not scenes:
            print("[UVE] ❌ Nenhuma cena encontrada na configuração")
            return None

        # PRÉ-PROCESSAMENTO: segmentar áudio e legendas ANTES das cenas (para provider=local_file)
        try:
            scenes = NarrationEngine.preprocess_scenes({
                "provider": self.tts_config.get("provider", "edge"),
                "tts_config": self.tts_config,
                "scenes_data": scenes,
                "output_base_dir": self.output_dir
            })
        except Exception as e:
            print(f"[UVE] ⚠️ Pré-processamento de narração falhou: {e}")

        for scene_index, scene in enumerate(scenes):
            scene_id = scene.get("id", f"cena_{scene_index}")
            print(f"\n[UVE] 📝 Processando cena {scene_index + 1}/{total_scenes}:  {scene_id}")

            scene_dir = os.path.join(self.output_dir, scene_id)
            os.makedirs(scene_dir, exist_ok=True)

            # 1. Narração (usa dados pré-segmentados se local_file)
            narration_engine = NarrationEngine(self.tts_config, self.output_dir)
            narration_clip, duration_from_tts, subtitle_file = narration_engine.process_scene_narration(scene, scene_dir)

            # adicionar fixo 50ms antes e depois da narração
            # if narration_clip:
            #     # silencio inicial/final
            #     silence_duration = 0.05
            #     audio_silencio = AudioClip(lambda t: 0, duration=silence_duration)
            #     narration_clip = concatenate_audioclips([audio_silencio, narration_clip, audio_silencio])
            #     duration_from_tts = narration_clip.duration
            #     print(f"[UVE] Duração da narração: {duration_from_tts}s")
            # else:
            #     print("[UVE] Sem narração para esta cena")

            # 2. Duração
            scene_duration = scene.get("duration", duration_from_tts)
            if not scene_duration or scene_duration < 0.1:
                scene_duration = 4.0
                print(f"[UVE] Usando duração padrão: {scene_duration}s")
            else:
                print(f"[UVE] Duração da cena: {scene_duration}s")

            # 3. Componentes
            try:
                # Fundo via BackgroundEngine (visual + background.filters)
                bg_engine = BackgroundEngine(
                    resolution_output=self.resolution_output,
                    dir_clips_cache=self.dir_media_index,
                    ai_cache=self.ai_cache,
                )
                background_clip = bg_engine.build_scene_background(self.global_settings, scene, float(scene_duration), scene_dir, self.output_dir)

                visual_clip = self._create_visual_elements_clip(scene, scene_duration, scene_dir)

                subtitle_clip = None
                if scene.get("narration", {}).get("subtitles", False):
                    has_visuals = bool(scene.get("visual_elements"))
                    subtitle_clip = self._create_subtitle_clip(scene_duration, subtitle_file, has_visuals)

                # 4. Composição da cena
                final_scene_clip = [background_clip]
                if visual_clip: 
                    final_scene_clip.append(visual_clip)
                if subtitle_clip:
                    final_scene_clip.append(subtitle_clip)

                # 5. force_rgb
                safe_clips = []
                for c in final_scene_clip: 
                    try:
                        c = c.fl_image(force_rgb)
                        safe_clips.append(c)
                    except Exception as e:
                        print(f"[UVE] ⚠️ Falha ao aplicar force_rgb:  {e}")
                        safe_clips.append(c)

                # 6. Compor cena final
                composed_clip = CompositeVideoClip(safe_clips, size=self.resolution_output).set_duration(scene_duration)
                composed_clip = composed_clip.fl_image(force_rgb)

                # 7. Narração
                if narration_clip:
                    composed_clip = composed_clip.set_audio(narration_clip)

                transitions_config = self.global_settings.get("transitions")
    
                if transitions_config and transitions_config.get("enabled", False):
                    print(f"[UVE] 🎬 Aplicando transição Zoom na cena {scene_index + 1}...")
                    
                    try:
                        transition_engine = TransitionEngine({
                            "clip": composed_clip,
                            "transitions_settings": transitions_config,
                            "resolution": self.resolution_output
                        })
                        
                        composed_clip = transition_engine.apply_transition()
                        print(f"[UVE] ✅ Transição aplicada com sucesso")
                        
                    except Exception as e:
                        print(f"[UVE] ⚠️ Falha ao aplicar transição: {e}")
                        # Continua com o clip original

                scene_clip_path = self._render_scene(
                    scene_index,
                    scene_id, 
                    total_scenes, 
                    composed_clip, 
                    narration_clip, 
                    scene_dir
                )
                scene_files.append(scene_clip_path)

            except Exception as e:
                print(f"[UVE] ❌ Erro ao processar cena {scene_id + 1}: {e}")
                import traceback
                traceback.print_exc()
                continue

        # 9. Concatenar cenas
        slug = self.data_config.get("slug", "video_final")
        output_filename = f"{slug}.mp4"

        intermediate_path = os.path.join(self.output_dir, f"{slug}_no_bg_audio.mp4")
        output_path = os.path.join(self.output_dir, output_filename)

        if not scene_files:
            print("[UVE] ❌ Nenhuma cena foi renderizada com sucesso")
            return None

        try:
            print(f"[UVE] 🔗 Concatenando {len(scene_files)} cenas...")

            concat_list_path = os.path.join(self.output_dir, "concat_list.txt")
            with open(concat_list_path, "w", encoding="utf-8") as f:
                for p in scene_files:
                    f.write(f"file '{os.path.abspath(p)}'\n")

            # CORREÇÃO APLICADA: Re-encoding ao invés de -c copy para evitar trancos
            print("[UVE] 🎬 Concatenando com re-encoding para transições suaves...")
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_list_path,
                "-c:v", "libx264",  # Re-encode de vídeo (evita trancos)
                "-preset", "medium",
                "-crf", "20",  # Qualidade alta
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",  # Re-encode de áudio
                "-b:a", "192k",
                "-movflags", "+faststart",  # Otimiza para streaming
                intermediate_path
            ]

            subprocess.run(ffmpeg_cmd, check=True, capture_output=True)
            print(f"[UVE] ✅ Vídeo concatenado:  {intermediate_path}")

        except subprocess.CalledProcessError as e:
            print(f"[UVE] ❌ Falha na concatenação: {e}")
            print(f"[UVE] stderr: {e.stderr.decode() if e.stderr else 'N/A'}")
            return None
        except Exception as e:
            print(f"[UVE] ❌ Falha na concatenação: {e}")
            return None

        # 10. Áudio de fundo
        bg_audio_config = self.global_settings.get("background", {}).get("audio", {})
        if bg_audio_config and bg_audio_config.get("source"):
            final_path = self._apply_background_audio_to_video(intermediate_path, output_path)
        else:
            shutil.move(intermediate_path, output_path)
            final_path = output_path
            print("[UVE] Sem áudio de fundo configurado")

        # 11. Upload YouTube (opcional)
        if self.data_config.get("youtube") and self.data_config.get("debug") is not True:
            try:
                print("[UVE] 📤 Iniciando upload para o YouTube...")
                youtube_params = self.data_config.get("youtube", {}).copy()
                youtube_params["video_path"] = final_path
                youtube_uploader = YouTube(params=youtube_params)
                youtube_uploader.upload()
            except Exception as e:
                print(f"[UVE] ❌ Upload YouTube falhou: {e}")

        # 12. Abrir vídeo (debug)
        if self.data_config.get("debug") is True:
            try:
                print("[UVE] 🎥 Abrindo vídeo final...")
                if os.name == 'nt': 
                    os.startfile(final_path)
                elif os.name == 'posix':
                    subprocess.run(
                        ["open" if "darwin" in os.uname().sysname.lower() else "xdg-open", final_path])
            except Exception as e:
                print(f"[UVE] ⚠️ Falha ao abrir vídeo:  {e}")

        print(f"\n[UVE] 🎉 Processamento concluído com sucesso!")
        print(f"[UVE] 📁 Arquivo final:  {final_path}")

        return final_path