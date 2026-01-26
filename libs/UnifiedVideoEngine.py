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
        self.dir_media_index = {}

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

        # Inicializa o gerenciador de narração
        self.narration_manager = NarrationEngine(self.tts_config, self.output_dir)
        
        # Pré-processa narração se necessário
        scenes = self.data_config.get("scenes", [])
        if scenes:
            self.narration_manager.preprocess_scenes(scenes)

    def _process_narration(self, scene_data, target_dir):
        """Delega o processamento de narração para o NarrationEngine."""
        return self.narration_manager.process_scene_narration(scene_data, target_dir)

    def process_scenes(self):
        """Processa todas as cenas do vídeo."""
        scenes = self.data_config.get("scenes", [])
        
        if not scenes:
            print("[UVE] ⚠️ Nenhuma cena encontrada no JSON!")
            return

        print(f"[UVE] Processando {len(scenes)} cenas...")

        for i, scene_data in enumerate(scenes):
            scene_id = scene_data.get("id", f"scene_{i}")
            print(f"\n[UVE] === Processando Cena {i+1}/{len(scenes)}: {scene_id} ===")
            
            try:
                clip = self._process_scene(scene_data, i)
                if clip:
                    self.final_clips.append(clip)
                    self.total_duration += clip.duration
                    print(f"[UVE] ✅ Cena {scene_id} processada (duração: {clip.duration:.1f}s)")
                else:
                    print(f"[UVE] ⚠️ Cena {scene_id} falhou")
            except Exception as e:
                print(f"[UVE] ❌ ERRO na cena {scene_id}: {e}")
                import traceback
                traceback.print_exc()

        print(f"\n[UVE] ✅ Processamento concluído. Total: {len(self.final_clips)} cenas, duração: {self.total_duration:.1f}s")

    def _process_scene(self, scene_data, scene_index):
        """Processa uma cena individual."""
        scene_id = scene_data.get("id", f"scene_{scene_index}")
        target_dir = os.path.join(self.output_dir, scene_id)
        os.makedirs(target_dir, exist_ok=True)

        # Processamento de narração
        audio_path, duration, subtitle_path, word_boundaries = self._process_narration(scene_data, target_dir)
        
        if not audio_path:
            duration = scene_data.get("duration", 4.0)
            print(f"[UVE] Cena sem áudio, usando duração fixa: {duration}s")

        # Processamento de background
        bg_config = self._merge_background_config(scene_data)
        background_engine = BackgroundEngine(
            bg_config, 
            self.resolution_output, 
            duration, 
            target_dir,
            scene_id
        )
        background_clip = background_engine.create_background()

        # Processamento de elementos visuais
        visual_clips = self._process_visual_elements(scene_data, target_dir, duration)

        # Processamento de legendas
        subtitle_clip = None
        if subtitle_path and os.path.exists(subtitle_path):
            subtitle_config = self._merge_subtitle_config(scene_data)
            subtitle_clip = self._create_subtitle_clip(subtitle_path, duration, subtitle_config)

        # Composição final da cena
        final_clip = self._compose_scene(
            background_clip, 
            visual_clips, 
            subtitle_clip, 
            audio_path, 
            duration
        )

        # Limpeza de memória
        self._cleanup_clips([background_clip] + visual_clips + ([subtitle_clip] if subtitle_clip else []))

        return final_clip

    def _merge_background_config(self, scene_data):
        """Mescla configurações de background global com da cena."""
        global_bg = self.global_settings.get("background", {})
        scene_bg = scene_data.get("background", {})
        return deep_merge(global_bg, scene_bg)

    def _merge_subtitle_config(self, scene_data):
        """Mescla configurações de legenda global com da cena."""
        global_subtitle = self.global_settings.get("subtitle", {})
        scene_subtitle = scene_data.get("subtitle", {})
        return deep_merge(global_subtitle, scene_subtitle)

    def _process_visual_elements(self, scene_data, target_dir, duration):
        """Processa elementos visuais da cena."""
        elements = scene_data.get("visual_elements", [])
        visual_clips = []

        for element in elements:
            try:
                clip = self._create_visual_element_clip(element, target_dir, duration)
                if clip:
                    visual_clips.append(clip)
            except Exception as e:
                print(f"[UVE] ⚠️ Erro ao processar elemento visual: {e}")

        return visual_clips

    def _create_visual_element_clip(self, element, target_dir, duration):
        """Cria clip para um elemento visual específico."""
        element_type = element.get("type")
        
        if element_type == "image":
            return self._create_image_clip(element, duration)
        elif element_type == "video":
            return self._create_video_clip(element, duration)
        elif element_type == "text_box":
            return self._create_text_clip(element, duration)
        else:
            print(f"[UVE] Tipo de elemento não suportado: {element_type}")
            return None

    def _create_image_clip(self, element, duration):
        """Cria clip de imagem."""
        source = element.get("source")
        if not source or not os.path.exists(source):
            print(f"[UVE] Imagem não encontrada: {source}")
            return None

        try:
            clip = ImageClip(source, duration=duration)
            clip = self._apply_layout_and_effects(clip, element)
            return clip
        except Exception as e:
            print(f"[UVE] Erro ao criar clip de imagem: {e}")
            return None

    def _create_video_clip(self, element, duration):
        """Cria clip de vídeo."""
        source = element.get("source")
        if not source or not os.path.exists(source):
            print(f"[UVE] Vídeo não encontrado: {source}")
            return None

        try:
            clip = VideoFileClip(source)
            if clip.duration > duration:
                clip = clip.subclip(0, duration)
            elif clip.duration < duration:
                clip = clip.loop(duration=duration)
            
            clip = self._apply_layout_and_effects(clip, element)
            return clip
        except Exception as e:
            print(f"[UVE] Erro ao criar clip de vídeo: {e}")
            return None

    def _create_text_clip(self, element, duration):
        """Cria clip de texto."""
        text = element.get("text", "")
        if not text:
            return None

        try:
            layout_config = element.get("layout", {})
            font_size = layout_config.get("font_size", 50)
            color = layout_config.get("color", "white")
            
            clip = TextClip(text, fontsize=font_size, color=color, duration=duration)
            clip = self._apply_layout_and_effects(clip, element)
            return clip
        except Exception as e:
            print(f"[UVE] Erro ao criar clip de texto: {e}")
            return None

    def _apply_layout_and_effects(self, clip, element):
        """Aplica layout e efeitos a um clip."""
        layout_config = element.get("layout", {})
        
        # Redimensionamento
        width = layout_config.get("width")
        height = layout_config.get("height")
        
        if width or height:
            clip = self._resize_clip(clip, width, height)

        # Posicionamento
        position = layout_config.get("position", "center")
        clip = self._position_clip(clip, position, layout_config)

        # Efeitos
        filters = element.get("filters", {})
        clip = self._apply_filters(clip, filters)

        # Animações
        animation = element.get("animation", {})
        clip = self._apply_animation(clip, animation)

        return clip

    def _resize_clip(self, clip, width, height):
        """Redimensiona um clip."""
        try:
            if isinstance(width, str) and width.endswith('%'):
                width = int(self.resolution_output[0] * float(width[:-1]) / 100)
            if isinstance(height, str) and height.endswith('%'):
                height = int(self.resolution_output[1] * float(height[:-1]) / 100)
            
            if width and height:
                return clip.resize((width, height))
            elif width:
                return clip.resize(width=width)
            elif height:
                return clip.resize(height=height)
        except Exception as e:
            print(f"[UVE] Erro ao redimensionar clip: {e}")
        
        return clip

    def _position_clip(self, clip, position, layout_config):
        """Posiciona um clip na tela."""
        try:
            if position == "center":
                return clip.set_position("center")
            elif position == "top_left":
                return clip.set_position((0, 0))
            elif position == "top_right":
                return clip.set_position(("right", 0))
            elif position == "bottom_left":
                return clip.set_position((0, "bottom"))
            elif position == "bottom_right":
                return clip.set_position(("right", "bottom"))
            elif isinstance(position, dict) and position.get("type") == "custom":
                x = position.get("x", 0)
                y = position.get("y", 0)
                return clip.set_position((x, y))
        except Exception as e:
            print(f"[UVE] Erro ao posicionar clip: {e}")
        
        return clip

    def _apply_filters(self, clip, filters):
        """Aplica filtros a um clip."""
        try:
            if filters.get("blur"):
                # Implementar blur se necessário
                pass
            
            if filters.get("brightness"):
                brightness = filters["brightness"]
                clip = clip.fx(lambda gf, t: gf(t) * brightness)
                
        except Exception as e:
            print(f"[UVE] Erro ao aplicar filtros: {e}")
        
        return clip

    def _apply_animation(self, clip, animation):
        """Aplica animações a um clip."""
        try:
            anim_type = animation.get("type")
            duration = animation.get("duration", 1.0)
            start_at = animation.get("start_at", 0)
            
            if anim_type == "fade_in":
                clip = clip.crossfadein(duration)
            elif anim_type == "fade_out":
                clip = clip.crossfadeout(duration)
            elif anim_type == "slide_left":
                # Implementar animação de slide se necessário
                pass
                
        except Exception as e:
            print(f"[UVE] Erro ao aplicar animação: {e}")
        
        return clip

    def _create_subtitle_clip(self, subtitle_path, duration, subtitle_config):
        """Cria clip de legendas."""
        try:
            subtitle = Subtitle(
                subtitle_file=subtitle_path,
                config=self.config_instance,
                subtitle_config=subtitle_config
            )
            return subtitle.create_subtitle_clip(duration)
        except Exception as e:
            print(f"[UVE] Erro ao criar legendas: {e}")
            return None

    def _compose_scene(self, background_clip, visual_clips, subtitle_clip, audio_path, duration):
        """Compõe todos os elementos da cena."""
        try:
            clips = [background_clip]
            
            # Adiciona elementos visuais
            clips.extend(visual_clips)
            
            # Adiciona legendas
            if subtitle_clip:
                clips.append(subtitle_clip)
            
            # Compõe vídeo
            final_clip = CompositeVideoClip(clips, size=self.resolution_output)
            final_clip = final_clip.set_duration(duration)
            
            # Adiciona áudio se existir
            if audio_path and os.path.exists(audio_path):
                audio_clip = AudioFileClip(audio_path)
                final_clip = final_clip.set_audio(audio_clip)
            
            return final_clip
            
        except Exception as e:
            print(f"[UVE] Erro ao compor cena: {e}")
            return None

    def _cleanup_clips(self, clips):
        """Libera memória dos clips."""
        for clip in clips:
            if clip:
                try:
                    clip.close()
                except:
                    pass

    def render_final_video(self, output_filename=None):
        """Renderiza o vídeo final."""
        if not self.final_clips:
            print("[UVE] ❌ Nenhum clip para renderizar!")
            return None

        if not output_filename:
            output_filename = f"{self.data_config.get('slug', 'video')}_final.mp4"
        
        output_path = os.path.join(self.output_dir, output_filename)
        
        try:
            print(f"[UVE] 🎬 Renderizando vídeo final: {output_path}")
            
            final_video = concatenate_videoclips(self.final_clips, method="compose")
            
            final_video.write_videofile(
                output_path,
                fps=30,
                codec='libx264',
                audio_codec='aac',
                temp_audiofile='temp-audio.m4a',
                remove_temp=True
            )
            
            print(f"[UVE] ✅ Vídeo renderizado: {output_path}")
            return output_path
            
        except Exception as e:
            print(f"[UVE] ❌ Erro ao renderizar vídeo: {e}")
            import traceback
            traceback.print_exc()
            return None
        finally:
            # Limpeza final
            self._cleanup_clips(self.final_clips)

    def upload_to_youtube(self, video_path, title, description, tags=None):
        """Faz upload do vídeo para o YouTube."""
        try:
            youtube = YouTube()
            return youtube.upload_video(video_path, title, description, tags or [])
        except Exception as e:
            print(f"[UVE] Erro no upload para YouTube: {e}")
            return None

    def cleanup_temp_files(self):
        """Remove arquivos temporários."""
        try:
            if os.path.exists(self.output_dir):
                for root, dirs, files in os.walk(self.output_dir):
                    for file in files:
                        if file.startswith("temp-") or file.endswith(".tmp"):
                            os.remove(os.path.join(root, file))
        except Exception as e:
            print(f"[UVE] Erro ao limpar arquivos temporários: {e}")

    def get_video_info(self):
        """Retorna informações do vídeo processado."""
        return {
            "scenes_count": len(self.final_clips),
            "total_duration": self.total_duration,
            "resolution": self.resolution_output,
            "output_ratio": self.output_ratio,
            "output_dir": self.output_dir
        }