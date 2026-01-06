import os
import json
import numpy as np
import random
from moviepy.editor import *

from libs.Config import Config
from libs.BackgroundVideo import BackgroundVideo
from libs.VisualClip import VisualClip, force_rgb 
from libs.Subtitle import Subtitle
from libs.MediaDownloader import MediaDownloader 
from libs.TTS_Edge import EdgeTTS
from libs.LayoutEngine import LayoutEngine 
from libs.YouTube import YouTube

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

    # =========================================================================
    # GERADOR DE OVERLAY BOKEH/LIGHT LEAK (ESTILO DAS IMAGENS)
    # =========================================================================

    # =========================================================================
    # CORREÇÃO: GERADOR DE OVERLAY BOKEH (SEM BORDA QUADRADA)
    # =========================================================================

    def _create_radial_light_blob(self, size_px, color_rgb):
        """
        Cria uma bola de luz que desaparece TOTALMENTE nas bordas (sem quadrado visível).
        """
        import numpy as np # Garante que numpy está disponível
        
        # 1. Tamanho do grid (resolução da bola)
        res = int(size_px)
        # Garante tamanho ímpar para ter um centro perfeito (opcional, mas bom)
        if res % 2 == 0: res += 1
        
        # 2. Cria coordenadas de -1 a 1
        x = np.linspace(-1, 1, res)
        y = np.linspace(-1, 1, res)
        X, Y = np.meshgrid(x, y)
        
        # 3. Calcula distância do centro (Raio)
        radius = np.sqrt(X**2 + Y**2)
        
        # 4. Máscara Suave (Correção do "Quadrado")
        # - Usamos 'clip' para garantir que nada além do raio 1.0 seja desenhado
        # - A função (1 - radius) cria um decaimento linear
        # - Elevamos ao cubo (**3) para suavizar e parecer luz (decaimento exponencial visual)
        alpha_mask = np.clip(1.0 - radius, 0, 1) # Corta tudo fora do círculo
        alpha_mask = alpha_mask ** 3 # Suaviza a queda (quanto maior a potência, mais "focado" no centro)

        # 5. Criar a Imagem RGBA diretamente (Melhor performance e mistura)
        # Cria um array vazio com 4 canais (R, G, B, A)
        img_array = np.zeros((res, res, 4), dtype=np.uint8)
        
        # Preenche as cores RGB
        img_array[:, :, 0] = color_rgb[0]
        img_array[:, :, 1] = color_rgb[1]
        img_array[:, :, 2] = color_rgb[2]
        
        # Preenche o Alpha (escala 0-255)
        img_array[:, :, 3] = (alpha_mask * 255).astype(np.uint8)
        
        # Cria o ImageClip a partir do array
        blob_clip = ImageClip(img_array, transparent=True)
        
        return blob_clip

    def _create_bokeh_overlay(self, duration, base_color=(255, 120, 50), overall_opacity=0.6, speed_factor=1.0, size_factor=1.5):
        """
        Gera bolas de luz que ORBITAM a tela passando pelas 4 bordas.
        
        Args:
            speed_factor: Multiplicador de velocidade (1.0 = normal, 2.0 = dobro).
            size_factor: Multiplicador de tamanho das bolas.
        """
        W, H = self.resolution_output
        
        # Definição das 4 bolas de luz (uma para cada "canto" inicial aproximado)
        # Phase: define onde no círculo ela começa (0 a 2pi)
        # Direction: 1 (horário) ou -1 (anti-horário)
        blobs_config = [
            {"phase": np.pi / 2,     "color_offset": (-10, -10, 0), "size": 1.2 * size_factor}, # Começa Em Baixo
            {"phase": 3 * np.pi / 2, "color_offset": (10, 10, 10),  "size": 0.9 * size_factor}, # Começa Em Cima
        ]

        bokeh_clips = []

        for config in blobs_config:
            # 1. Tamanho
            blob_size = int(W * config["size"])
            
            # 2. Cor
            r = min(max(base_color[0] + config["color_offset"][0], 0), 255)
            g = min(max(base_color[1] + config["color_offset"][1], 0), 255)
            b = min(max(base_color[2] + config["color_offset"][2], 0), 255)
            
            # Gera a bola
            blob = self._create_radial_light_blob(blob_size, (r, g, b))
            blob = blob.set_duration(duration).set_opacity(overall_opacity)

            # 3. MATEMÁTICA ORBITAL (ELIPSE)
            orbit_radius_x = W * 0.6
            orbit_radius_y = H * 0.6
            
            center_x = W / 2
            center_y = H / 2
            
            angular_speed = 0.8 * speed_factor

            blob = blob.set_position(
                lambda t, 
                       cx=center_x, cy=center_y, 
                       rx=orbit_radius_x, ry=orbit_radius_y, 
                       bs=blob_size, 
                       ph=config["phase"], 
                       sp=angular_speed: 
                (
                    (cx + rx * np.cos(sp * t + ph)) - bs / 2,
                    (cy + ry * np.sin(sp * t + ph)) - bs / 2
                )
            )
            
            bokeh_clips.append(blob)

        if not bokeh_clips:
            return None
            
        return CompositeVideoClip(bokeh_clips, size=self.resolution_output).set_duration(duration)

    def _create_background_clip(self, scene_data, scene_duration, scene_dir, video_dir):
        # Faz merge entre global background e scene background (scene sobrescreve global),
        # mas REGISTER se a cena explicitamente definiu `audio` para que não apliquemos
        # o áudio global por cena (isso causaria restart da música).
        global_background = self.global_settings.get("background", {}) or {}
        scene_background = scene_data.get("background", None)

        if scene_background is not None:
            # merge: global <- scene (scene overrides)
            background_config = deep_merge(global_background, scene_background)
            storage_dir = scene_dir
            per_scene_audio_defined = "audio" in scene_background
        else:
            background_config = dict(global_background)  # usar global como está
            storage_dir = video_dir
            per_scene_audio_defined = False

        visual_config = background_config.get("visual", {})
        bg_clip = None
        bg_type = visual_config.get("type", "color")
        bg_source = visual_config.get("source")

        if bg_type == "color":
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
                    bg_clip = ColorClip(self.resolution_output, color=(0,0,0), duration=scene_duration)
            else:
                 bg_clip = ColorClip(self.resolution_output, color=(0,0,0), duration=scene_duration)

        elif bg_type == "directory" and bg_source:           
            if bg_source not in self.bg_cache:
                print(f"[UVE] Alimentando cache para o diretório: {bg_source}")
                loader = BackgroundVideo(params={
                    "background_videos_dir": bg_source,
                    "resolution_output": self.resolution_output,
                    "max_clip_duration": 4,
                })
                self.bg_cache[bg_source] = loader.get_processed_clips()

            bg_video_processor = BackgroundVideo(params={
                "background_videos_dir": bg_source,
                "max_total_video_duration": scene_duration,
                "resolution_output": self.resolution_output,
                "loop_background": True,
                "shuffle_clips": background_config.get("shuffle", True)
            })

            bg_clip = bg_video_processor.generate_background_video(
                preloaded_clips=self.bg_cache[bg_source]
            )
        elif bg_type == "video" and bg_source:
            video_path = bg_source
            if video_path.lower().startswith(("http:", "https:")):
                video_path = MediaDownloader.resolve_source_path(video_path, storage_dir)
            if video_path and os.path.exists(video_path):
                try:
                    bg_clip = VideoFileClip(video_path, audio=False)
                    width, height = bg_clip.size
                    target_w, target_h = self.resolution_output
                    
                    if (width / height) < (target_w / target_h):
                        bg_clip = bg_clip.resize(width=target_w)
                        bg_clip = vfx.crop(bg_clip, x_center=target_w/2, y_center=target_h/2, width=target_w, height=target_h)
                    else:
                        bg_clip = bg_clip.resize(height=target_h)
                        bg_clip = vfx.crop(bg_clip, x_center=target_w/2, y_center=target_h/2, width=target_w, height=target_h)
                    
                    if bg_clip.duration < scene_duration:
                        bg_clip = vfx.loop(bg_clip, duration=scene_duration)
                    else:
                        bg_clip = bg_clip.subclip(0, scene_duration)
                except Exception as e:
                    bg_clip = ColorClip(self.resolution_output, color=(0,0,0), duration=scene_duration)
            else:
                bg_clip = ColorClip(self.resolution_output, color=(0,0,0), duration=scene_duration)

        if bg_clip is None:
            bg_clip = ColorClip(self.resolution_output, color=(0,0,0), duration=scene_duration)

        # Aplicar áudio por cena somente se a cena explicitamente definiu audio.
        audio_config = background_config.get("audio", {}) if per_scene_audio_defined else {}

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
        
        elif audio_config.get("type") == "file" and audio_config.get("source"):
            audio_source = MediaDownloader.resolve_source_path(audio_config["source"], storage_dir)
            if audio_source and os.path.exists(audio_source):
                bg_audio_clip = AudioFileClip(audio_source)
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
        if not visual_elements:
            return None

        # PASSO 1: Gerar os clipes "crus" para descobrir seus tamanhos REAIS
        valid_clips_info = []
        valid_element_data_for_layout = []

        print(f"[UVE] Gerando {len(visual_elements)} elementos visuais para cálculo de layout...")

        for element_data in visual_elements:
            config = {
                "element_data": element_data,
                "resolution_output": self.resolution_output,
                "temp_dir": scene_dir, 
                "duration": scene_duration
            }
            processor = VisualClip(config)
            raw_clip = processor.generate()
            
            if raw_clip:
                w, h = raw_clip.size
                element_data_copy = element_data.copy()
                element_data_copy['original_size'] = (w, h)
                
                valid_clips_info.append(raw_clip)
                valid_element_data_for_layout.append(element_data_copy)
            else:
                print(f"[UVE] Aviso: Falha ao gerar elemento visual (ignorando no layout).")

        if not valid_clips_info:
            return None

        layout_results = LayoutEngine.process_stack_layout(valid_element_data_for_layout, self.config_instance)
        
        final_clips = []
        
        for i, clip in enumerate(valid_clips_info):
            if i >= len(layout_results): break
            
            layout = layout_results[i]
            final_size = layout['final_size']
            final_pos = layout['final_position']
            
            try:
                clip_resized = clip.resize(newsize=final_size)
                clip_positioned = clip_resized.set_position(final_pos)
                final_clips.append(clip_positioned)
            except Exception as e:
                print(f"[ERRO UVE] Falha ao redimensionar clip {i}: {e}")
        
        if not final_clips:
            return None
            
        return CompositeVideoClip(final_clips, size=self.resolution_output).set_duration(scene_duration)

    def _create_subtitle_clip(self, scene_duration, subtitle_file):
        if not subtitle_file or not os.path.exists(subtitle_file):
            return None
        
        padding_bottom = self.config_instance.padding_bottom
        padding_side = self.config_instance.padding_side
        
        subtitle_config = self.global_settings.get("subtitle", {}).copy()
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

        # bg_config = scene.get("background", {})
        bg_config = self.global_settings.get("background", {})
            
        if bg_config.get("visual") == "directory":
            source_dir = bg_config.get("source")
            
            # VERIFICAÇÃO DO CACHE:
            if source_dir not in self.bg_cache:
                print(f"[UVE] Cache vazio. Processando vídeos de: {source_dir}")
                loader = BackgroundVideo({
                    "background_videos_dir": source_dir,
                    "resolution_output": self.resolution_output
                })
                self.bg_cache[source_dir] = loader.get_all_processed_clips()

            # NOTE: aqui bg_video_processor/scene_duration não é crítico — this block is legacy
            bg_video_processor = BackgroundVideo({
                "background_videos_dir": source_dir,
                "max_total_video_duration": None,
                "resolution_output": self.resolution_output
            })
            
            bg_clip = bg_video_processor.generate_background_video(
                preloaded_clips=self.bg_cache[source_dir]
            )

        for scene in self.data_config.get("scenes", []):
            scene_id = scene.get("id", "cena_desconhecida")
            print(f"[UVE] Processando cena: {scene_id}")

            scene_dir = os.path.join(self.output_dir, scene_id)
            os.makedirs(scene_dir, exist_ok=True)

            # 1. Narração
            audio_clip, duration_from_tts, word_timing, subtitle_file = self._process_narration(scene, scene_dir)
            
            # 2. Duração
            scene_duration = scene.get("duration", duration_from_tts)
            if not scene_duration or scene_duration < 0.1:
                scene_duration = 4.0 

            # 3. Fundo
            background_clip = self._create_background_clip(scene, scene_duration, scene_dir, self.output_dir)
            
            # 4. Elementos Visuais
            visual_clip = self._create_visual_elements_clip(scene, scene_duration, scene_dir)
            
            # 5. Legendas
            subtitle_clip = None
            if scene.get("narration", {}).get("subtitles", False):
                subtitle_clip = self._create_subtitle_clip(scene_duration, subtitle_file)

            # 6. Composição
            final_scene_clip = [background_clip]

            if visual_clip: final_scene_clip.append(visual_clip)
            if subtitle_clip: final_scene_clip.append(subtitle_clip)

            # Debug layout area
            if os.getenv("DEBUG_LAYOUT") == "1":
                W, H = self.resolution_output
                pad_top = self.config_instance.padding_top
                pad_side = self.config_instance.padding_side
                
                debug_w = W - (2 * pad_side)
                debug_h = H - pad_top
                
                debug_area = ColorClip(
                    size=(int(debug_w), int(debug_h)), 
                    color=(255, 0, 0)
                ).set_opacity(0.3).set_position((pad_side, pad_top)).set_duration(scene_duration)
                
                final_scene_clip.append(debug_area)

            safe_clips = []
            for c in final_scene_clip:
                try:
                    c = c.fl_image(force_rgb) 
                    safe_clips.append(c)
                except Exception as e:
                    safe_clips.append(c)

            composed_clip = CompositeVideoClip(safe_clips, size=self.resolution_output).set_duration(scene_duration)
            composed_clip = composed_clip.fl_image(force_rgb)

            if audio_clip:
                composed_clip.audio = CompositeAudioClip([composed_clip.audio, audio_clip]) if composed_clip.audio else audio_clip

            all_scene_clips.append(composed_clip)
            self.total_duration += scene_duration

        if not all_scene_clips:
            return None
            
        final_video = concatenate_videoclips(all_scene_clips, method="compose")
        slug = self.data_config.get("slug", "final_video")
        output_filename = f"{slug}.mp4"
        output_path = os.path.join(self.output_dir, output_filename)
        
        # Aplicar o audio global uma única vez no final
        global_bg_audio_config = self.global_settings.get("background", {}).get("audio", {}) or {}
        try:
            total_dur = self.total_duration if self.total_duration > 0 else final_video.duration
        except Exception:
            total_dur = final_video.duration

        if global_bg_audio_config and global_bg_audio_config.get("type"):
            try:
                bg_audio_clip = None
                if global_bg_audio_config.get("type") == "directory" and global_bg_audio_config.get("source"):
                    bg_music_dir = global_bg_audio_config["source"]
                    full_bg_music_dir = os.path.join(os.getcwd(), bg_music_dir)
                    if os.path.isdir(full_bg_music_dir):
                        music_files = [os.path.join(full_bg_music_dir, f) for f in os.listdir(full_bg_music_dir) if f.endswith(".mp3")]
                        if music_files:
                            bg_audio_clip = AudioFileClip(random.choice(music_files))
                elif global_bg_audio_config.get("type") == "file" and global_bg_audio_config.get("source"):
                    audio_source = MediaDownloader.resolve_source_path(global_bg_audio_config["source"], self.output_dir)
                    if audio_source and os.path.exists(audio_source):
                        bg_audio_clip = AudioFileClip(audio_source)

                if bg_audio_clip:
                    if bg_audio_clip.duration < total_dur:
                        bg_audio_clip = afx.audio_loop(bg_audio_clip, duration=total_dur)
                    else:
                        bg_audio_clip = bg_audio_clip.subclip(0, total_dur)

                    bg_audio_clip = bg_audio_clip.volumex(global_bg_audio_config.get("volume", 0.1))

                    if final_video.audio:
                        combined_audio = CompositeAudioClip([final_video.audio, bg_audio_clip])
                    else:
                        combined_audio = bg_audio_clip

                    final_video = final_video.set_audio(combined_audio)
            except Exception as e:
                print(f"[UVE] Aviso: falha ao aplicar audio de fundo global: {e}")

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

        if self.data_config.get("youtube") and self.data_config.get("debug") is not True:
            print("[UVE] Iniciando upload para o YouTube...")
            youtube_params = self.data_config.get("youtube", {})
            youtube_params["video_path"] = output_path

            youtube_uploader = YouTube(params=youtube_params)
            youtube_uploader.upload()

        return output_path