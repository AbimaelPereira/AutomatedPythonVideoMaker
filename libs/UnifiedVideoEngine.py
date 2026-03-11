import os
import json
import numpy as np
import random
from moviepy.editor import *
import subprocess
import shutil
import gc
import hashlib
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed

from libs.Config import Config
from libs.VisualClip import VisualClip, force_rgb
from libs.Subtitle import Subtitle
from libs.MediaDownloader import MediaDownloader
from libs.LayoutEngine import LayoutEngine
from libs.YouTube import YouTube
from libs.Background.BackgroundEngine import BackgroundEngine
from libs.Audio.NarrationEngine import NarrationEngine
from libs.Transitions.TransitionEngine import TransitionEngine
from libs.RemoteAssetManager import RemoteAssetManager

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


# 🔧 NOVA FUNÇÃO GLOBAL: Worker isolado para processar uma cena
def _process_scene_worker(scene_data_bundle):
    """
    Worker isolado para processar uma cena em paralelo.
    
    Args:
        scene_data_bundle: Dict com todos os dados necessários para processar a cena
    
    Returns:
        Tuple (scene_index, scene_clip_path) ou (scene_index, None) em caso de erro
    """
    scene_index = scene_data_bundle["scene_index"]
    scene = scene_data_bundle["scene"]
    total_scenes = scene_data_bundle["total_scenes"]
    output_dir = scene_data_bundle["output_dir"]
    resolution_output = scene_data_bundle["resolution_output"]
    tts_config = scene_data_bundle["tts_config"]
    global_settings = scene_data_bundle["global_settings"]
    config_instance_data = scene_data_bundle["config_instance_data"]
    remote_assets_config = scene_data_bundle["remote_assets_config"]
    ai_cache_dir = scene_data_bundle["ai_cache_dir"]
    
    try:
        scene_id = scene.get("id", f"cena_{scene_index}")
        print(f"\n[Worker-{scene_index}] 📝 Processando cena {scene_index + 1}/{total_scenes}: {scene_id}")
        
        scene_dir = os.path.join(output_dir, scene_id)
        os.makedirs(scene_dir, exist_ok=True)
        
        # Reconstruir objetos necessários neste processo
        remote_asset_manager = RemoteAssetManager(config=remote_assets_config)
        
        if AI_AVAILABLE and ai_cache_dir:
            ai_cache = AICache(ai_cache_dir)
        else:
            ai_cache = None
        
        # 1. Narração
        narration_engine = NarrationEngine(tts_config, output_dir)
        narration_clip, duration_from_tts, subtitle_file = narration_engine.process_scene_narration(scene, scene_dir)
        
        # 2. Duração
        scene_duration = scene.get("duration", duration_from_tts)
        if not scene_duration or scene_duration < 0.1:
            scene_duration = 4.0
            print(f"[Worker-{scene_index}] Usando duração padrão: {scene_duration}s")
        else:
            print(f"[Worker-{scene_index}] Duração da cena: {scene_duration}s")
        
        # 3. Componentes
        bg_engine = BackgroundEngine(
            resolution_output=resolution_output,
            dir_clips_cache={},
            ai_cache=ai_cache,
            remote_asset_manager=remote_asset_manager,
        )
        background_clip = bg_engine.build_scene_background(
            global_settings,
            scene,
            float(scene_duration),
            scene_dir,
            output_dir
        )
        
        # Visual elements
        visual_clip = _create_visual_elements_clip_worker(
            scene, scene_duration, scene_dir, resolution_output,
            remote_asset_manager, config_instance_data
        )
        
        # Subtitles
        subtitle_clip = None
        if scene.get("narration", {}).get("subtitles", False):
            subtitle_clip = _create_subtitle_clip_worker(
                scene_duration, subtitle_file, config_instance_data,
                resolution_output, global_settings, scene_data=scene  # ✅ CORRIGIDO
            )
        
        # 4. Composição
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
                print(f"[Worker-{scene_index}] ⚠️ Falha ao aplicar force_rgb: {e}")
                safe_clips.append(c)
        
        # 6. Compor cena final
        composed_clip = CompositeVideoClip(safe_clips, size=resolution_output).set_duration(scene_duration)
        composed_clip = composed_clip.fl_image(force_rgb)
        
        # 7. Narração
        if narration_clip:
            composed_clip = composed_clip.set_audio(narration_clip)
        
        # 8. Transições
        transitions_config = global_settings.get("transitions")
        if transitions_config and transitions_config.get("enabled", False):
            print(f"[Worker-{scene_index}] 🎬 Aplicando transição...")
            try:
                transition_engine = TransitionEngine({
                    "clip": composed_clip,
                    "transitions_settings": transitions_config,
                    "resolution": resolution_output
                })
                composed_clip = transition_engine.apply_transition()
                print(f"[Worker-{scene_index}] ✅ Transição aplicada")
            except Exception as e:
                print(f"[Worker-{scene_index}] ⚠️ Falha ao aplicar transição: {e}")
        
        # 9. Renderizar cena
        scene_clip_path = os.path.join(scene_dir, f"{scene_id}.mp4")
        temp_audiofile = os.path.join(scene_dir, f"{scene_id}.m4a")
        
        print(f"[Worker-{scene_index}] 🎬 Renderizando cena {scene_index + 1}/{total_scenes}...")
        
        composed_clip.write_videofile(
            scene_clip_path,
            codec='libx264',
            audio_codec='aac',
            temp_audiofile=temp_audiofile,
            remove_temp=True,
            fps=30,
            preset='medium',
            threads=4,
            verbose=False,
            logger=None,
            ffmpeg_params=[
                '-vsync', 'cfr',
                '-g', '60',
                '-bf', '2'
            ]
        )
        
        print(f"[Worker-{scene_index}] ✅ Cena renderizada: {os.path.basename(scene_clip_path)}")
        
        # Cleanup
        try:
            composed_clip.close()
            if narration_clip:
                narration_clip.close()
        except:
            pass
        
        del composed_clip
        gc.collect()
        
        return (scene_index, scene_clip_path)
        
    except Exception as e:
        print(f"[Worker-{scene_index}] ❌ Erro ao processar cena: {e}")
        import traceback
        traceback.print_exc()
        return (scene_index, None)


def _create_visual_elements_clip_worker(scene_data, scene_duration, scene_dir, 
                                       resolution_output, remote_asset_manager, config_instance_data):
    """Versão worker de _create_visual_elements_clip"""
    elements = scene_data.get("visual_elements", [])
    if not elements:
        return None
    
    print(f"[Worker] Processando {len(elements)} elementos visuais...")
    
    valid_clips_info = []
    valid_element_data_for_layout = []
    
    for i, element_data in enumerate(elements):
        try:
            config = {
                "element_data": element_data,
                "resolution_output": resolution_output,
                "temp_dir": scene_dir,
                "duration": scene_duration,
                "remote_asset_manager": remote_asset_manager,
            }
            
            processor = VisualClip(config)
            raw_clip = processor.generate()
            
            if raw_clip:
                w, h = raw_clip.size
                element_data_copy = element_data.copy()
                element_data_copy['original_size'] = (w, h)
                
                valid_clips_info.append(raw_clip)
                valid_element_data_for_layout.append(element_data_copy)
            
        except Exception as e:
            print(f"[Worker] ❌ Erro no elemento {i + 1}: {e}")
    
    if not valid_clips_info:
        return None
    
    # Reconstruir config_instance mínimo
    config_instance = type('Config', (), config_instance_data)()
    
    try:
        layout_results = LayoutEngine.process_stack_layout(
            valid_element_data_for_layout,
            config_instance
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
            except Exception as e:
                print(f"[Worker] ❌ Falha ao posicionar elemento {i + 1}: {e}")
        
        if not final_clips:
            return None
        
        return CompositeVideoClip(final_clips, size=resolution_output).set_duration(
            scene_duration).fl_image(force_rgb)
    
    except Exception as e:
        print(f"[Worker] ❌ Falha no LayoutEngine: {e}")
        centered_clips = []
        for i, clip in enumerate(valid_clips_info):
            try:
                clip_centered = clip.set_position('center')
                centered_clips.append(clip_centered)
            except:
                pass
        
        if centered_clips:
            return CompositeVideoClip(centered_clips, size=resolution_output).set_duration(
                scene_duration).fl_image(force_rgb)
        
        return None


# ✅ CORRIGIDO: adicionado parâmetro scene_data=None
def _create_subtitle_clip_worker(scene_duration, subtitle_file, config_instance_data,
                                 resolution_output, global_settings, scene_data=None):
    """Versão worker de _create_subtitle_clip"""
    try:
        if not subtitle_file or not os.path.exists(subtitle_file):
            return None
        
        subtitle_config = {
            "subtitle_narration_file": subtitle_file,
            "resolution_output": resolution_output,
            "padding_bottom": config_instance_data.get('padding_bottom', 200),
            "padding_side": config_instance_data.get('padding_side', 50),
            "padding_top": config_instance_data.get('padding_top', 200),
            "has_visual_elements": True,
        }
        
        # global_settings.subtitle sobrescreve defaults
        global_subtitle_config = global_settings.get("subtitle", {})
        subtitle_config.update(global_subtitle_config)

        # ✅ CORRIGIDO: scene.subtitle sobrescreve global
        scene_subtitle_config = (scene_data or {}).get("subtitle", {})
        subtitle_config.update(scene_subtitle_config)
        
        subtitle_generator = Subtitle(params=subtitle_config)
        subtitle_clip = subtitle_generator.generate()
        
        if subtitle_clip:
            subtitle_clip = subtitle_clip.set_duration(scene_duration)
            return subtitle_clip
        
        return None
    
    except Exception as e:
        print(f"[Worker] ❌ Falha ao criar legendas: {e}")
        return None


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

        # AI Cache
        if AI_AVAILABLE:
            cache_dir = os.path.join(os.getcwd(), "cache", "ai_generated")
            self.ai_cache = AICache(cache_dir)
            self.ai_cache_dir = cache_dir
        else:
            self.ai_cache = None
            self.ai_cache_dir = None

        # Remote Asset Manager
        print("[UVE] 🔧 Inicializando Remote Asset Manager...")
        remote_assets_config = self.global_settings.get("remote_assets", {})
        self.remote_asset_manager = RemoteAssetManager(config=remote_assets_config)
        self.remote_assets_config = remote_assets_config
        print("[UVE] ✅ Remote Asset Manager inicializado")
        
        stats = self.remote_asset_manager.get_stats()
        if stats["total_slugs"] > 0:
            print(f"[UVE] 📊 Remote Assets: {stats['total_slugs']} slugs, {stats['valid_media']} URLs válidas")

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
                    "remote_asset_manager": self.remote_asset_manager,
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

    # ✅ CORRIGIDO: adicionado parâmetro scene_data=None
    def _create_subtitle_clip(self, scene_duration, subtitle_file, has_visual_elements=False, scene_data=None):
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

            # global_settings.subtitle sobrescreve defaults
            global_subtitle_config = self.global_settings.get("subtitle", {})
            subtitle_config.update(global_subtitle_config)

            # ✅ CORRIGIDO: scene.subtitle sobrescreve global
            scene_subtitle_config = (scene_data or {}).get("subtitle", {})
            subtitle_config.update(scene_subtitle_config)

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
        Se ducking estiver habilitado no JSON, usa AudioEffects.apply_ducking.

        JSON:
        {
            "background": {
                "audio": {
                    "source": "./assets/audio/background/musica.mp3",
                    "volume": 0.8,
                    "ducking": {
                        "enabled": true,
                        "ducking_db": -18.0,
                        "threshold_db": -40.0,
                        "attack_ms": 50,
                        "release_ms": 300
                    }
                }
            }
        }
        """
        bg_audio_config = self.global_settings.get("background", {}).get("audio", {})

        if not bg_audio_config:
            print("[UVE] Sem configuração de áudio de fundo")
            return video_path

        audio_type = bg_audio_config.get("type", "file")
        source     = bg_audio_config.get("source")
        volume     = bg_audio_config.get("volume", 0.2)

        if not source:
            print("[UVE] Áudio de fundo sem source configurado")
            return video_path

        try:
            # Resolve o arquivo de áudio de fundo
            if audio_type == "directory":
                if not os.path.isdir(source):
                    print(f"[UVE] ⚠️ Diretório de áudio não encontrado: {source}")
                    return video_path

                valid_extensions = ('.mp3', '.wav', '.ogg', '.m4a')
                audio_files = [
                    f for f in os.listdir(source)
                    if f.lower().endswith(valid_extensions)
                ]
                if not audio_files:
                    print(f"[UVE] ⚠️ Nenhum arquivo de áudio válido em: {source}")
                    return video_path

                audio_path = os.path.join(source, random.choice(audio_files))
            else:
                audio_path = source

            if not audio_path or not os.path.exists(audio_path):
                print(f"[UVE] ⚠️ Áudio de fundo não encontrado: {audio_path}")
                return video_path

            ducking_config  = bg_audio_config.get("ducking", {})
            ducking_enabled = ducking_config.get("enabled", False)

            if ducking_enabled:
                print("[UVE] 🎚️ Ducking habilitado — processando via AudioEffects...")
                return self._apply_background_audio_with_ducking(
                    video_path=video_path,
                    output_path=output_path,
                    audio_path=audio_path,
                    volume=volume,
                    ducking_config=ducking_config,
                )
            else:
                print(f"[UVE] 🎵 Aplicando áudio de fundo sem ducking: {os.path.basename(audio_path)}")
                return self._apply_background_audio_simple(
                    video_path=video_path,
                    output_path=output_path,
                    audio_path=audio_path,
                    volume=volume,
                )

        except Exception as e:
            print(f"[UVE] ❌ Erro ao aplicar áudio de fundo: {e}")
            import traceback
            traceback.print_exc()
            return video_path


    def _apply_background_audio_with_ducking(
        self,
        video_path: str,
        output_path: str,
        audio_path: str,
        volume: float,
        ducking_config: dict,
    ) -> str:
        """
        Aplica áudio de fundo com ducking automático baseado na narração do vídeo.
        """
        from pydub import AudioSegment
        from libs.Audio.AudioEffects import AudioEffects

        temp_narration = os.path.join(self.output_dir, "_temp_narration_for_ducking.mp3")
        temp_mixed     = os.path.join(self.output_dir, "_temp_ducked_mix.mp3")

        try:
            # 1. Duração exata do vídeo (via ffprobe)
            probe_cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path
            ]
            probe_result = subprocess.run(
                probe_cmd, check=True, capture_output=True, text=True
            )
            video_duration_s = float(probe_result.stdout.strip())
            video_duration_ms = int(video_duration_s * 1000)
            print(f"[UVE] ⏱️ Duração do vídeo: {video_duration_s:.2f}s")

            # 2. Extrai narração do vídeo
            print("[UVE] 🎤 Extraindo narração do vídeo para ducking...")
            cmd_extract = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-vn",
                "-acodec", "libmp3lame",
                "-b:a", "192k",
                "-ar", "44100",
                "-ac", "2",
                temp_narration
            ]
            subprocess.run(cmd_extract, check=True, capture_output=True)
            print("[UVE] ✅ Narração extraída")

            # 3. Carrega áudios
            print("[UVE] 📂 Carregando áudios para ducking...")
            narration_seg  = AudioSegment.from_file(temp_narration)
            background_seg = AudioSegment.from_file(audio_path)

            if len(background_seg) < video_duration_ms:
                loops_needed   = (video_duration_ms // len(background_seg)) + 1
                background_seg = background_seg * loops_needed

            background_seg = background_seg[:video_duration_ms]
            print(f"[UVE] ✂️ Background cortado para {video_duration_s:.2f}s")

            # 4. Aplica volume no background (dB)
            if volume != 1.0:
                import math
                volume_db      = 20 * math.log10(max(volume, 1e-6))
                background_seg = background_seg.apply_gain(volume_db)
                print(f"[UVE] 🔊 Volume do background: {volume} ({volume_db:.1f} dB)")

            # 5. Ducking
            duck_params = {
                "ducking_db":   ducking_config.get("ducking_db",   -18.0),
                "threshold_db": ducking_config.get("threshold_db", -40.0),
                "attack_ms":    ducking_config.get("attack_ms",      50),
                "release_ms":   ducking_config.get("release_ms",    300),
                "chunk_ms":     ducking_config.get("chunk_ms",       10),
            }
            print(f"[UVE] 🎚️ Parâmetros de ducking: {duck_params}")

            mixed_seg = AudioEffects.apply_ducking(
                narration=narration_seg,
                background=background_seg,
                **duck_params
            )

            mixed_seg = mixed_seg[:video_duration_ms]
            mixed_seg.export(temp_mixed, format="mp3", bitrate="192k")
            print(f"[UVE] ✅ Mix com ducking gerado ({len(mixed_seg)/1000:.2f}s)")

            # 6. Re-encoda vídeo + áudio juntos
            print("[UVE] 🎬 Combinando vídeo + áudio mixado (re-encode completo)...")
            cmd_merge = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", temp_mixed,
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "20",
                "-r", "30",
                "-vsync", "cfr",
                "-g", "60",
                "-bf", "2",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "44100",
                "-ac", "2",
                "-shortest",
                "-movflags", "+faststart",
                output_path
            ]
            subprocess.run(cmd_merge, check=True, capture_output=True)
            print(f"[UVE] ✅ Vídeo final com ducking: {os.path.basename(output_path)}")

            return output_path

        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode(errors="replace") if e.stderr else "N/A"
            print(f"[UVE] ❌ Erro FFmpeg no ducking:\n{stderr}")
            return video_path
        except Exception as e:
            print(f"[UVE] ❌ Erro inesperado no ducking: {e}")
            import traceback
            traceback.print_exc()
            return video_path
        finally:
            for tmp in [temp_narration, temp_mixed]:
                if os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except Exception:
                        pass

    def _apply_background_audio_simple(
        self,
        video_path: str,
        output_path: str,
        audio_path: str,
        volume: float,
    ) -> str:
        """
        Aplica áudio de fundo simples (sem ducking) — comportamento original.
        """
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
            fps=30,
            preset='medium',
            threads=4,
            verbose=False,
            logger=None,
            ffmpeg_params=['-vsync', 'cfr']
        )
        
        video_clip.close()
        bg_audio.close()
        final_video.close()
        
        print(f"[UVE] ✅ Áudio de fundo aplicado: {os.path.basename(output_path)}")
        return output_path

    def _render_scene(self, scene_index, scene_id, total_scenes, composed_clip, narration_clip, scene_dir):
        """
        Renderiza cena com FPS fixo e CFR garantido.
        """
        scene_clip_path = os.path.join(scene_dir, f"{scene_id}.mp4")
        temp_audiofile = os.path.join(scene_dir, f"{scene_id}.m4a")

        print(f"[UVE] 🎬 Renderizando cena {scene_index + 1}/{total_scenes}...")

        composed_clip.write_videofile(
            scene_clip_path,
            codec='libx264',
            audio_codec='aac',
            temp_audiofile=temp_audiofile,
            remove_temp=True,
            fps=30,
            bitrate="2000k",
            preset='faster',
            threads=4,
            verbose=False,
            logger=None,
            ffmpeg_params=[
                '-vsync', 'cfr',
                '-g', '60',
                '-bf', '2'
            ]
        )

        print(f"[UVE] ✅ Cena {scene_index + 1} renderizada: {os.path.basename(scene_clip_path)}")

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
        """Método principal de renderização com suporte a paralelização."""
        print("[UVE] 🚀 Iniciando processamento do vídeo...")

        scenes = self.data_config.get("scenes", [])
        total_scenes = len(scenes)

        if not scenes:
            print("[UVE] ❌ Nenhuma cena encontrada na configuração")
            return None

        # PRÉ-PROCESSAMENTO
        try:
            scenes = NarrationEngine.preprocess_scenes({
                "provider": self.tts_config.get("provider", "edge"),
                "tts_config": self.tts_config,
                "scenes_data": scenes,
                "output_base_dir": self.output_dir
            })
        except Exception as e:
            print(f"[UVE] ⚠️ Pré-processamento de narração falhou: {e}")

        # Determinar número de workers
        max_parallel = self.config_instance.max_parallel_scenes
        max_workers = min(max_parallel, multiprocessing.cpu_count(), len(scenes))
        
        try:
            import psutil
            available_ram_gb = psutil.virtual_memory().available / (1024**3)
            if available_ram_gb < 4 and max_workers > 1:
                print(f"[UVE] ⚠️ RAM disponível baixa ({available_ram_gb:.1f}GB). Forçando modo sequencial.")
                max_workers = 1
        except ImportError:
            pass
        
        scene_files = []
        
        if max_workers == 1:
            print("[UVE] 🔄 Modo sequencial ativado (MAX_PARALLEL_SCENES=1)")
            
            for scene_index, scene in enumerate(scenes):
                scene_id = scene.get("id", f"cena_{scene_index}")
                print(f"\n[UVE] 📝 Processando cena {scene_index + 1}/{total_scenes}: {scene_id}")

                scene_dir = os.path.join(self.output_dir, scene_id)
                os.makedirs(scene_dir, exist_ok=True)

                # 1. Narração
                narration_engine = NarrationEngine(self.tts_config, self.output_dir)
                narration_clip, duration_from_tts, subtitle_file = narration_engine.process_scene_narration(scene, scene_dir)

                # 2. Duração
                scene_duration = scene.get("duration", duration_from_tts)
                if not scene_duration or scene_duration < 0.1:
                    scene_duration = 4.0
                    print(f"[UVE] Usando duração padrão: {scene_duration}s")
                else:
                    print(f"[UVE] Duração da cena: {scene_duration}s")

                # 3. Componentes
                try:
                    bg_engine = BackgroundEngine(
                        resolution_output=self.resolution_output,
                        dir_clips_cache=self.dir_media_index,
                        ai_cache=self.ai_cache,
                        remote_asset_manager=self.remote_asset_manager,
                    )
                    background_clip = bg_engine.build_scene_background(
                        self.global_settings, 
                        scene, 
                        float(scene_duration), 
                        scene_dir, 
                        self.output_dir
                    )

                    visual_clip = self._create_visual_elements_clip(scene, scene_duration, scene_dir)

                    subtitle_clip = None
                    if scene.get("narration", {}).get("subtitles", False):
                        has_visuals = bool(scene.get("visual_elements"))
                        # ✅ CORRIGIDO: passa scene=scene para aplicar override por cena
                        subtitle_clip = self._create_subtitle_clip(
                            scene_duration, subtitle_file, has_visuals, scene_data=scene
                        )

                    # 4. Composição
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
                            print(f"[UVE] ⚠️ Falha ao aplicar force_rgb: {e}")
                            safe_clips.append(c)

                    # 6. Compor cena final
                    composed_clip = CompositeVideoClip(safe_clips, size=self.resolution_output).set_duration(scene_duration)
                    composed_clip = composed_clip.fl_image(force_rgb)

                    # 7. Narração
                    if narration_clip:
                        composed_clip = composed_clip.set_audio(narration_clip)

                    # 8. Transições
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
                    else:
                        print(f"[UVE] ⏭️ Transições desabilitadas")

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
                    print(f"[UVE] ❌ Erro ao processar cena {scene_index + 1} (ID: {scene_id}): {e}")
                    import traceback
                    traceback.print_exc()
                    continue
        
        else:
            print(f"[UVE] ⚡ Modo paralelo ativado: {max_workers} workers")
            
            config_instance_data = {
                'padding_bottom': getattr(self.config_instance, 'padding_bottom', 200),
                'padding_top': getattr(self.config_instance, 'padding_top', 100),
                'padding_side': getattr(self.config_instance, 'padding_side', 50),
                'width': self.config_instance.width,
                'height': self.config_instance.height,
            }
            
            scene_bundles = []
            for scene_index, scene in enumerate(scenes):
                bundle = {
                    "scene_index": scene_index,
                    "scene": scene,
                    "total_scenes": total_scenes,
                    "output_dir": self.output_dir,
                    "resolution_output": self.resolution_output,
                    "tts_config": self.tts_config,
                    "global_settings": self.global_settings,
                    "config_instance_data": config_instance_data,
                    "remote_assets_config": self.remote_assets_config,
                    "ai_cache_dir": self.ai_cache_dir,
                }
                scene_bundles.append(bundle)
            
            results = []
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(_process_scene_worker, bundle): bundle["scene_index"]
                    for bundle in scene_bundles
                }
                
                for future in as_completed(futures):
                    try:
                        scene_index, scene_path = future.result(timeout=600)
                        if scene_path:
                            results.append((scene_index, scene_path))
                            print(f"[UVE] ✅ Cena {scene_index + 1} concluída com sucesso")
                        else:
                            print(f"[UVE] ❌ Cena {scene_index + 1} falhou")
                    except Exception as e:
                        print(f"[UVE] ❌ Exceção no worker: {e}")
                        import traceback
                        traceback.print_exc()
            
            results.sort(key=lambda x: x[0])
            scene_files = [path for _, path in results]

        # 9. Concatenar cenas
        slug = self.data_config.get("slug", "video_final")
        output_filename = f"{slug}.mp4"

        intermediate_path = os.path.join(self.output_dir, f"{slug}_no_bg_audio.mp4")
        output_path       = os.path.join(self.output_dir, output_filename)

        if not scene_files:
            print("[UVE] ❌ Nenhuma cena foi renderizada com sucesso")
            return None

        try:
            print(f"[UVE] 🔗 Concatenando {len(scene_files)} cenas...")

            concat_list_path = os.path.join(self.output_dir, "concat_list.txt")
            with open(concat_list_path, "w", encoding="utf-8") as f:
                for p in scene_files:
                    f.write(f"file '{os.path.abspath(p)}'\n")

            print("[UVE] 🎬 Concatenando com re-encoding e FPS constante...")
            ffmpeg_cmd = [
                "ffmpeg", "-y", 
                "-f", "concat", 
                "-safe", "0",
                "-i", concat_list_path,
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "20",
                "-r", "30",
                "-vsync", "cfr",
                "-g", "60",
                "-bf", "2",
                "-pix_fmt", "yuv420p",
                "-keyint_min", "60",
                "-sc_threshold", "0",
                "-force_key_frames", "expr:gte(t,n_forced*2)",
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "44100",
                "-ac", "2",
                "-movflags", "+faststart",
                intermediate_path
            ]

            result = subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True)
            print(f"[UVE] ✅ Vídeo concatenado: {intermediate_path}")

        except subprocess.CalledProcessError as e:
            print(f"[UVE] ❌ Falha na concatenação FFmpeg")
            print(f"[UVE] stderr: {e.stderr if e.stderr else 'N/A'}")
            return None
        except Exception as e:
            print(f"[UVE] ❌ Erro inesperado na concatenação: {e}")
            import traceback
            traceback.print_exc()
            return None

        # 10. Áudio de fundo (com ou sem ducking)
        bg_audio_config = self.global_settings.get("background", {}).get("audio", {})
        if bg_audio_config and bg_audio_config.get("source"):
            final_path = self._apply_background_audio_to_video(intermediate_path, output_path)
        else:
            shutil.move(intermediate_path, output_path)
            final_path = output_path
            print("[UVE] Sem áudio de fundo configurado")

        # Estatísticas Remote Assets
        print("\n[UVE] 📊 Estatísticas de Remote Assets:")
        final_stats = self.remote_asset_manager.get_stats()
        print(f"[UVE]    Total de slugs: {final_stats['total_slugs']}")
        print(f"[UVE]    URLs válidas: {final_stats['valid_media']}")
        print(f"[UVE]    URLs inválidas: {final_stats['invalid_media']}")

        # 11. Upload YouTube
        if self.data_config.get("youtube") and self.data_config.get("debug") is not True:
            try:
                print("[UVE] 📤 Iniciando upload para o YouTube...")
                youtube_params = self.data_config.get("youtube", {}).copy()
                youtube_params["video_path"] = final_path
                youtube_uploader = YouTube(params=youtube_params)
                youtube_uploader.upload()
            except Exception as e:
                print(f"[UVE] ❌ Upload YouTube falhou: {e}")

        # 12. Abrir vídeo
        if self.data_config.get("debug") is True:
            try:
                print("[UVE] 🎥 Abrindo vídeo final...")
                if os.name == 'nt': 
                    os.startfile(final_path)
                elif os.name == 'posix':
                    subprocess.run(
                        ["open" if "darwin" in os.uname().sysname.lower() else "xdg-open", final_path])
            except Exception as e:
                print(f"[UVE] ⚠️ Falha ao abrir vídeo: {e}")

        print(f"\n[UVE] 🎉 Processamento concluído com sucesso!")
        print(f"[UVE] 📁 Arquivo final: {final_path}")

        return final_path
