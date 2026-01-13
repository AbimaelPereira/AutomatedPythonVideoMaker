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
from libs.BackgroundVideo import BackgroundVideo
from libs.VisualClip import VisualClip, force_rgb
from libs.Subtitle import Subtitle
from libs.MediaDownloader import MediaDownloader
from libs.TTS_Edge import EdgeTTS
from libs.LayoutEngine import LayoutEngine
from libs.YouTube import YouTube
from libs.OverlayEngine import OverlayEngine
from libs.SceneAudioManager import SceneAudioManager

try:
    from libs.AIProviders import ai_manager
    from libs.AIProviders.AICache import AICache
    AI_AVAILABLE = True
    print("[UVE] ✅ Sistema de IA carregado")
except ImportError as e:
    AI_AVAILABLE = False
    print(f"[UVE] ⚠️ Sistema de IA não disponível: {e}")

AVAILABLE_RESOLUTIONS = {"9: 16": (1080, 1920), "16:9": (1920, 1080)}


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

        self.bg_cache = {}
        self.last_used_videos = []
        self.max_history = 3

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

    def _get_tts_engine(self):
        return EdgeTTS()

    def _process_narration(self, scene_data, target_dir):
        """Processa narração da cena gerando áudio e legendas."""
        narration_config = scene_data.get("narration", {})
        text = narration_config.get("text", "")

        if not text:
            print("[UVE] Cena sem narração.  Duração será fixa.")
            return None, narration_config.get("duration", 4.0), None, None

        voice = (scene_data.get("tts", {}).get("voice") or
                 self.tts_config.get("voice") or
                 "pt-BR-AntonioNeural")

        audio_basename = os.path.join(target_dir, f"audio_{scene_data.get('id', 'unknown')}")

        print(f"[UVE] Gerando áudio para cena {scene_data.get('id')} em {target_dir}...")

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

            if not final_audio_path or not os.path.exists(final_audio_path):
                print(f"[ERRO UVE] Arquivo de áudio não foi criado: {final_audio_path}")
                return None, 4.0, None, None

            audio_clip = AudioFileClip(final_audio_path)
            duration = audio_clip.duration

            print(f"[UVE] ✅ Áudio gerado com sucesso - Duração: {duration:.2f}s")
            return audio_clip, duration, word_boundaries, subtitle_file

        except Exception as e:
            print(f"[ERRO UVE] Falha ao gerar TTS: {e}")
            import traceback
            traceback.print_exc()
            return None, 4.0, None, None

    def _select_random_videos_for_duration(self, available_clips, target_duration, scene_id):
        """Seleciona vídeos aleatórios para cobrir a duração necessária."""
        if not available_clips:
            return []

        selected_clips = []
        current_duration = 0.0
        attempts = 0
        max_attempts = len(available_clips) * 3

        available_for_selection = []
        for clip in available_clips:
            clip_path = getattr(clip, 'filename', str(hash(str(clip))))
            if clip_path not in self.last_used_videos:
                available_for_selection.append(clip)

        if not available_for_selection: 
            print(f"[UVE] Resetando histórico de vídeos para evitar deadlock")
            available_for_selection = available_clips.copy()
            self.last_used_videos = []

        print(f"[UVE] Selecionando vídeos para duração:  {target_duration:.2f}s")
        print(f"[UVE] Vídeos disponíveis: {len(available_for_selection)} (histórico: {len(self.last_used_videos)})")

        while current_duration < target_duration and attempts < max_attempts:
            attempts += 1

            if not available_for_selection:
                break

            selected_clip = random.choice(available_for_selection)
            clip_duration = getattr(selected_clip, 'duration', 4.0)

            remaining_duration = target_duration - current_duration
            actual_duration = min(clip_duration, remaining_duration)

            if actual_duration < clip_duration:
                start_time = random.uniform(0, max(0, clip_duration - actual_duration))
                clip_segment = selected_clip.subclip(start_time, start_time + actual_duration)
            else:
                clip_segment = selected_clip.copy()

            selected_clips.append(clip_segment)
            current_duration += actual_duration

            clip_path = getattr(selected_clip, 'filename', str(hash(str(selected_clip))))
            if clip_path not in self.last_used_videos:
                self.last_used_videos.append(clip_path)

            available_for_selection.remove(selected_clip)

            print(f"[UVE] Vídeo selecionado: duração {actual_duration:.2f}s (total: {current_duration:.2f}s)")

            if not available_for_selection and current_duration < target_duration:
                print(f"[UVE] ⚠️ Acabaram os vídeos únicos.  Duração atual: {current_duration:.2f}s")
                break

        if len(self.last_used_videos) > self.max_history:
            self.last_used_videos = self.last_used_videos[-self.max_history:]

        print(f"[UVE] ✅ {len(selected_clips)} vídeos selecionados para duração total: {current_duration:.2f}s")
        return selected_clips

    def _create_ai_background_clip(self, ai_config, scene_duration, storage_dir):
        """Cria fundo usando IA"""
        if not AI_AVAILABLE or not self.ai_cache:
            raise ValueError("Sistema de IA não está disponível")

        try:
            provider = ai_config.get("provider", "pollinations")
            content_type = ai_config.get("content_type", "image")
            prompt = ai_config.get("prompt", "")
            parameters = ai_config.get("parameters", {})
            cache_key = ai_config.get("cache_key")

            if not prompt:
                raise ValueError("Prompt não especificado para IA background")

            print(f"[UVE] 🤖 Processando background IA:  {content_type}")
            print(f"[UVE] Prompt: {prompt[: 100]}...")

            if not cache_key:
                cache_data = {
                    "provider": provider,
                    "type": content_type,
                    "prompt": prompt,
                    "parameters": parameters
                }
                cache_key = hashlib.md5(json.dumps(cache_data, sort_keys=True).encode()).hexdigest()[:12]
                print(f"[UVE] Cache key gerado: {cache_key}")

            cached_file = self.ai_cache.get(cache_key, content_type)
            if cached_file:
                print(f"[UVE] ✅ IA background encontrado no cache:  {os.path.basename(cached_file)}")
                file_path = cached_file
            else:
                print(f"[UVE] 🎨 Gerando {content_type} background com {provider}...")

                if not parameters.get("width") and not parameters.get("height"):
                    parameters["width"] = self.resolution_output[0]
                    parameters["height"] = self.resolution_output[1]

                if content_type == "image":
                    result = ai_manager.generate_image(prompt=prompt, provider=provider, **parameters)
                elif content_type == "video": 
                    result = ai_manager.generate_video(prompt=prompt, provider=provider, **parameters)
                else:
                    raise ValueError(f"Tipo de conteúdo IA inválido: {content_type}")

                if not result.get("success"):
                    raise ValueError(f"Falha na geração IA: {result.get('error')}")

                extension = "png" if content_type == "image" else "mp4"
                filename = f"ai_bg_{cache_key}.{extension}"
                file_path = os.path.join(storage_dir, filename)

                with open(file_path, "wb") as f:
                    f.write(result["content"])

                print(f"[UVE] ✅ IA background salvo:  {filename} ({result['size']} bytes)")

                self.ai_cache.store(cache_key, file_path, content_type, {
                    "prompt": prompt,
                    "provider": provider,
                    "parameters": parameters,
                    "size": result["size"]
                })

            if content_type == "image":
                bg_clip = (ImageClip(file_path)
                           .resize(newsize=self.resolution_output)
                           .set_duration(scene_duration))
                print(f"[UVE] ✅ IA background (imagem) criado: {scene_duration:.2f}s")

            elif content_type == "video":
                bg_clip = VideoFileClip(file_path, audio=False)
                bg_clip = bg_clip.resize(newsize=self.resolution_output)

                if bg_clip.duration < scene_duration:
                    bg_clip = bg_clip.loop(duration=scene_duration)
                else:
                    bg_clip = bg_clip.subclip(0, scene_duration)

                bg_clip = bg_clip.without_audio()
                print(f"[UVE] ✅ IA background (vídeo) criado: {scene_duration:.2f}s")

            return bg_clip

        except Exception as e:
            print(f"[UVE] ❌ Erro ao criar IA background: {e}")
            import traceback
            traceback.print_exc()
            return ColorClip(size=self.resolution_output, color=(0, 0, 0)).set_duration(scene_duration)

    def _create_background_clip(self, scene_data, scene_duration, scene_dir, video_dir):
        """Cria clip de fundo com merge de configurações global/cena."""
        print(f"[UVE] Criando fundo para duração: {scene_duration:.2f}s")

        global_background = self.global_settings.get("background", {}) or {}
        scene_background = scene_data.get("background", None)

        if scene_background is not None:
            background_config = deep_merge(global_background, scene_background)
            storage_dir = scene_dir
            print("[UVE] Usando configuração de fundo mesclada (global + cena)")
        else:
            background_config = dict(global_background)
            storage_dir = video_dir
            print("[UVE] Usando configuração de fundo global")

        visual_config = background_config.get("visual", {})
        bg_type = visual_config.get("type", "color")
        bg_clip = None

        try:
            if bg_type == "color":
                color = visual_config.get("source", "#000000")
                if isinstance(color, str):
                    color = hex_to_rgb(color)
                print(f"[UVE] Criando fundo colorido: {color}")
                bg_clip = ColorClip(size=self.resolution_output, color=color).set_duration(scene_duration)

            elif bg_type == "image":
                src = visual_config.get("source")
                if not src:
                    raise ValueError("Source da imagem não especificada")

                path = MediaDownloader.resolve_source_path(src, storage_dir)
                print(f"[UVE] Carregando imagem de fundo: {path}")

                bg_clip = (ImageClip(path)
                           .resize(newsize=self.resolution_output)
                           .set_duration(scene_duration))

            elif bg_type == "video":
                src = visual_config.get("source")
                if not src:
                    raise ValueError("Source do vídeo não especificada")

                path = MediaDownloader.resolve_source_path(src, storage_dir)
                print(f"[UVE] Carregando vídeo de fundo: {path}")

                bg_clip = VideoFileClip(path, audio=False)
                bg_clip = bg_clip.resize(newsize=self.resolution_output)

                if bg_clip.duration < scene_duration:
                    bg_clip = bg_clip.loop(duration=scene_duration)
                else:
                    bg_clip = bg_clip.subclip(0, scene_duration)

                bg_clip = bg_clip.without_audio()

            elif bg_type == "ai":
                bg_clip = self._create_ai_background_clip(visual_config, scene_duration, storage_dir)

            elif bg_type == "directory":
                source_dir = visual_config.get("source")
                if not source_dir: 
                    raise ValueError("Diretório source não especificado")

                print(f"[UVE] Processando vídeos do diretório: {source_dir}")

                if source_dir not in self.bg_cache:
                    print(f"[UVE] Carregando vídeos do diretório para cache...")
                    loader = BackgroundVideo({
                        "background_videos_dir": source_dir,
                        "resolution_output": self.resolution_output,
                        "output_ratio": self.output_ratio,
                        "crossfade_duration": self.global_settings.get("crossfade_duration", 0.8),
                        "enable_crossfade": self.global_settings.get("enable_crossfade", True),
                        "shuffle_clips": self.global_settings.get("shuffle_clips", True),
                        "loop_background":  self.global_settings.get("loop_background", True),
                        "max_clips":  self.global_settings.get("max_clips")
                    })

                    if hasattr(loader, "get_all_processed_clips"):
                        self.bg_cache[source_dir] = loader.get_all_processed_clips()
                    elif hasattr(loader, "get_processed_clips"):
                        self.bg_cache[source_dir] = loader.get_processed_clips()
                    else:
                        print("[UVE] ⚠️ BackgroundVideo não tem método de cache conhecido")
                        self.bg_cache[source_dir] = []

                cached_clips = self.bg_cache.get(source_dir, [])
                if cached_clips:
                    print(f"[UVE] Cache contém {len(cached_clips)} vídeos processados")

                    scene_id = scene_data.get('id', 'unknown')
                    selected_clips = self._select_random_videos_for_duration(
                        cached_clips, scene_duration, scene_id
                    )

                    if selected_clips:
                        if len(selected_clips) == 1:
                            bg_clip = selected_clips[0]
                            if bg_clip.duration < scene_duration:
                                bg_clip = bg_clip.loop(duration=scene_duration)
                            elif bg_clip.duration > scene_duration:
                                bg_clip = bg_clip.subclip(0, scene_duration)
                        else:
                            print(f"[UVE] Concatenando {len(selected_clips)} vídeos para o fundo")

                            enable_crossfade = self.global_settings.get("enable_crossfade", False)
                            crossfade_duration = self.global_settings.get("crossfade_duration", 0.5)

                            if enable_crossfade and len(selected_clips) > 1:
                                bg_clip = selected_clips[0]
                                for next_clip in selected_clips[1:]:
                                    bg_clip = concatenate_videoclips(
                                        [bg_clip, next_clip],
                                        method="compose"
                                    )
                                    if bg_clip.duration > crossfade_duration:
                                        bg_clip = bg_clip.crossfadein(crossfade_duration)
                            else:
                                bg_clip = concatenate_videoclips(selected_clips, method="compose")

                            if bg_clip.duration > scene_duration:
                                bg_clip = bg_clip.subclip(0, scene_duration)
                            elif bg_clip.duration < scene_duration:
                                remaining = scene_duration - bg_clip.duration
                                if remaining > 0 and selected_clips:
                                    last_clip = selected_clips[-1]
                                    if last_clip.duration >= remaining:
                                        extra_clip = last_clip.subclip(0, remaining)
                                    else:
                                        extra_clip = last_clip.loop(duration=remaining)
                                    bg_clip = concatenate_videoclips([bg_clip, extra_clip])

                        print(f"[UVE] ✅ Fundo criado com duração final: {bg_clip.duration:.2f}s")
                    else:
                        print("[UVE] ⚠️ Nenhum vídeo selecionado, usando fundo preto")
                        bg_clip = ColorClip(size=self.resolution_output, color=(0, 0, 0)).set_duration(scene_duration)
                else:
                    print("[UVE] ⚠️ Cache vazio, usando fundo preto")
                    bg_clip = ColorClip(size=self.resolution_output, color=(0, 0, 0)).set_duration(scene_duration)

            else:
                print(f"[UVE] ⚠️ Tipo de fundo desconhecido: {bg_type}, usando preto")
                bg_clip = ColorClip(size=self.resolution_output, color=(0, 0, 0)).set_duration(scene_duration)

        except Exception as e:
            print(f"[UVE] ❌ Falha ao criar fundo: {e}")
            import traceback
            traceback.print_exc()
            print(f"[UVE] Usando fundo preto como fallback")
            bg_clip = ColorClip(size=self.resolution_output, color=(0, 0, 0)).set_duration(scene_duration)

        return self._apply_overlays_to_background(bg_clip, scene_data, scene_duration)

    def _apply_overlays_to_background(self, bg_clip, scene_data, scene_duration):
        """Aplica overlays ao fundo"""
        global_overlays = self.global_settings.get("overlays", {}) or {}
        scene_overlays = scene_data.get("overlays", None)

        if scene_overlays is not None: 
            overlays_config = deep_merge(global_overlays, scene_overlays)
        else:
            overlays_config = dict(global_overlays)

        overlay_clip = None
        if overlays_config:
            try:
                print("[UVE] Processando overlays...")
                ov_engine = OverlayEngine(resolution=self.resolution_output)
                overlay_clip = ov_engine.create_overlays_clip(overlays_config, scene_duration)
            except Exception as e:
                print(f"[UVE] ⚠️ Falha ao gerar overlays: {e}")

        if overlay_clip is not None:
            try:
                print("[UVE] Compondo fundo + overlays")
                composed = CompositeVideoClip([bg_clip, overlay_clip],
                                              size=self.resolution_output).set_duration(scene_duration)
                return composed.fl_image(force_rgb)
            except Exception as e: 
                print(f"[UVE] ❌ Falha ao compor overlay sobre fundo: {e}")

        return bg_clip.fl_image(force_rgb)
    
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
                "has_visual_elements": has_visual_elements,
            }

            global_subtitle_config = self.global_settings.get("subtitle", {})
            subtitle_config.update(global_subtitle_config)

            print(f"[UVE] Configurações de legenda:  posição={'centro' if not has_visual_elements else 'inferior'}")

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

    def _get_transition_effect_config(self, scene_data):
        """Obtém configuração de efeito de transição com merge global/cena."""
        global_effect = self.global_settings.get("transition_effect_audio", {})
        scene_effect = scene_data.get("transition_effect_audio", {})

        if scene_effect:
            return deep_merge(global_effect, scene_effect)
        return dict(global_effect) if global_effect else None

    def _select_random_audio_from_dir(self, directory:  str) -> str:
        """Seleciona áudio aleatório de um diretório."""
        if not os.path.isdir(directory):
            return None

        files = [
            os.path.join(directory, f) for f in os.listdir(directory)
            if os.path.splitext(f.lower())[1] in self.VALID_AUDIO_EXTENSIONS
        ]

        return random.choice(files) if files else None

    def _apply_background_audio_to_video(self, video_path: str, output_path: str) -> str:
        """
        Aplica áudio de fundo ao vídeo final concatenado.
        
        Args:
            video_path: caminho do vídeo sem áudio de fundo
            output_path:  caminho de saída do vídeo com áudio de fundo
        
        Returns:
            caminho do vídeo final ou video_path original se falhar
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
            # Seleciona arquivo de áudio
            if audio_type == "directory":
                audio_path = self._select_random_audio_from_dir(source)
            else:  # file
                audio_path = source
            
            if not audio_path or not os.path.exists(audio_path):
                print(f"[UVE] ⚠️ Áudio de fundo não encontrado:  {audio_path}")
                return video_path
            
            print(f"[UVE] 🎵 Aplicando áudio de fundo: {os.path.basename(audio_path)}")
            
            # Carrega vídeo para obter duração
            video_clip = VideoFileClip(video_path)
            video_duration = video_clip.duration
            
            # Carrega áudio de fundo
            bg_audio = AudioFileClip(audio_path)
            
            # Loop se necessário
            if bg_audio.duration < video_duration:
                loops_needed = int(video_duration / bg_audio.duration) + 1
                bg_clips = [bg_audio] * loops_needed
                bg_audio = concatenate_audioclips(bg_clips)
            
            # Ajusta duração e volume
            bg_audio = bg_audio.subclip(0, video_duration)
            bg_audio = bg_audio.volumex(volume)
            
            # Mixa com áudio existente do vídeo
            if video_clip.audio:
                final_audio = CompositeAudioClip([video_clip.audio, bg_audio])
            else:
                final_audio = bg_audio
            
            # Aplica ao vídeo
            final_video = video_clip.set_audio(final_audio)
            
            # Exporta
            print(f"[UVE] 🎬 Renderizando vídeo com áudio de fundo...")
            final_video.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac',
                fps=24,
                preset='medium',
                threads=4,
                verbose=False,
                logger=None
            )
            
            # Limpeza
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

    def run(self, output_filename="final_video.mp4"):
        """Método principal de renderização."""
        print("[UVE] 🚀 Iniciando processamento do vídeo...")

        scene_files = []
        temp_dir = os.path.join(self.output_dir, "_temp")
        os.makedirs(temp_dir, exist_ok=True)

        scenes = self.data_config.get("scenes", [])
        total_scenes = len(scenes)

        if not scenes:
            print("[UVE] ❌ Nenhuma cena encontrada na configuração")
            return None

        for scene_index, scene in enumerate(scenes):
            scene_id = scene.get("id", f"cena_{scene_index}")
            print(f"\n[UVE] 📝 Processando cena {scene_index + 1}/{total_scenes}:  {scene_id}")

            scene_dir = os.path.join(self.output_dir, scene_id)
            os.makedirs(scene_dir, exist_ok=True)

            # 1. Processar narração
            narration_clip, duration_from_tts, word_timing, subtitle_file = self._process_narration(scene, scene_dir)

            # 2. Definir duração da cena
            scene_duration = scene.get("duration", duration_from_tts)
            if not scene_duration or scene_duration < 0.1:
                scene_duration = 4.0
                print(f"[UVE] Usando duração padrão: {scene_duration}s")
            else:
                print(f"[UVE] Duração da cena: {scene_duration}s")

            # 3. Criar componentes da cena
            try:
                background_clip = self._create_background_clip(scene, scene_duration, scene_dir, self.output_dir)
                visual_clip = self._create_visual_elements_clip(scene, scene_duration, scene_dir)

                subtitle_clip = None
                if scene.get("narration", {}).get("subtitles", False):
                    has_visuals = bool(scene.get("visual_elements"))
                    subtitle_clip = self._create_subtitle_clip(scene_duration, subtitle_file, has_visuals)

                # 4. Composição da cena
                final_scene_clip = [background_clip]
                if visual_clip: 
                    final_scene_clip.append(visual_clip)
                    print("[UVE] ✅ Elementos visuais adicionados")
                if subtitle_clip:
                    final_scene_clip.append(subtitle_clip)
                    print("[UVE] ✅ Legendas adicionadas")

                # 5. Aplicar force_rgb em todos os clips
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

                # 7. Processar áudio da cena (narração + efeito de transição)
                effect_config = self._get_transition_effect_config(scene)

                audio_manager = SceneAudioManager({
                    "scene_duration": scene_duration,
                    "output_dir": scene_dir,
                })

                scene_audio = audio_manager.create_scene_audio(
                    narration_clip=narration_clip,
                    transition_effect_config=effect_config,
                    scene_duration=scene_duration
                )

                if scene_audio:
                    composed_clip = composed_clip.set_audio(scene_audio)
                    print("[UVE] ✅ Áudio da cena composto (narração + efeito)")
                elif narration_clip:
                    composed_clip = composed_clip.set_audio(narration_clip)
                    print("[UVE] ✅ Áudio da narração adicionado")

                # 8. Renderizar cena para arquivo temporário
                temp_scene_path = os.path.join(temp_dir, f"scene_{scene_index:04d}.mp4")
                temp_audiofile = os.path.join(temp_dir, f"temp-audio-{scene_index}.m4a")

                print(f"[UVE] 🎬 Renderizando cena {scene_index + 1}/{total_scenes}...")

                composed_clip.write_videofile(
                    temp_scene_path,
                    codec='libx264',
                    audio_codec='aac',
                    temp_audiofile=temp_audiofile,
                    remove_temp=True,
                    fps=24,
                    preset='medium',
                    threads=4,
                    verbose=False,
                    logger=None
                )

                scene_files.append(temp_scene_path)
                print(f"[UVE] ✅ Cena {scene_index + 1} renderizada:  {os.path.basename(temp_scene_path)}")

                # Limpeza de memória
                try:
                    composed_clip.close()
                    if narration_clip:
                        narration_clip.close()
                except: 
                    pass

                del composed_clip
                gc.collect()

            except Exception as e:
                print(f"[UVE] ❌ Erro ao processar cena {scene_index + 1}: {e}")
                import traceback
                traceback.print_exc()
                continue

        # 9. Concatenar cenas em vídeo final
        slug = self.data_config.get("slug", "video_final")
        if not output_filename.endswith('.mp4'):
            output_filename = f"{slug}.mp4"

        # Vídeo intermediário (sem áudio de fundo)
        intermediate_path = os.path.join(temp_dir, f"{slug}_no_bg_audio.mp4")
        output_path = os.path.join(self.output_dir, output_filename)

        if not scene_files:
            print("[UVE] ❌ Nenhuma cena foi renderizada com sucesso")
            return None

        try:
            print(f"[UVE] 🔗 Concatenando {len(scene_files)} cenas...")

            concat_list_path = os.path.join(temp_dir, "concat_list.txt")
            with open(concat_list_path, "w", encoding="utf-8") as f:
                for p in scene_files:
                    f.write(f"file '{os.path.abspath(p)}'\n")

            ffmpeg_cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_list_path, "-c", "copy", intermediate_path
            ]

            subprocess.run(ffmpeg_cmd, check=True, capture_output=True)
            print(f"[UVE] ✅ Vídeo concatenado:  {intermediate_path}")

        except subprocess.CalledProcessError as e:
            print("[UVE] ⚠️ Concatenação rápida falhou, tentando re-encoding...")
            try:
                ffmpeg_cmd_reencode = [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", concat_list_path,
                    "-c: v", "libx264", "-preset", "medium", "-crf", "20",
                    "-c:a", "aac", "-b: a", "128k",
                    intermediate_path
                ]
                subprocess.run(ffmpeg_cmd_reencode, check=True, capture_output=True)
                print(f"[UVE] ✅ Vídeo concatenado (re-encoded): {intermediate_path}")
            except Exception as e: 
                print(f"[UVE] ❌ Falha na concatenação: {e}")
                return None
        except Exception as e:
            print(f"[UVE] ❌ Falha na concatenação: {e}")
            return None

        # 10. Aplicar áudio de fundo ao vídeo final
        bg_audio_config = self.global_settings.get("background", {}).get("audio", {})
        if bg_audio_config and bg_audio_config.get("source"):
            final_path = self._apply_background_audio_to_video(intermediate_path, output_path)
        else:
            # Sem áudio de fundo, apenas renomeia/move
            shutil.move(intermediate_path, output_path)
            final_path = output_path
            print("[UVE] Sem áudio de fundo configurado")

        # 11. Limpeza de arquivos temporários
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
            print("[UVE] 🧹 Arquivos temporários removidos")
        except Exception as e:
            print(f"[UVE] ⚠️ Falha na limpeza: {e}")

        # 12. Upload para YouTube (se configurado)
        if self.data_config.get("youtube") and self.data_config.get("debug") is not True:
            try:
                print("[UVE] 📤 Iniciando upload para o YouTube...")
                youtube_params = self.data_config.get("youtube", {}).copy()
                youtube_params["video_path"] = final_path
                youtube_uploader = YouTube(params=youtube_params)
                youtube_uploader.upload()
            except Exception as e:
                print(f"[UVE] ❌ Upload YouTube falhou: {e}")

        # 13. Abrir vídeo se em modo debug
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
        print(f"[UVE] ⏱️ Duração total: {self.total_duration:.2f}s")

        return final_path