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
from libs.OverlayEngine import OverlayEngine

AVAILABLE_RESOLUTIONS = {"9: 16": (1080, 1920), "16:9":  (1920, 1080)}

def hex_to_rgb(hex_value):
    """Converte cor hexadecimal para tupla RGB"""
    if not isinstance(hex_value, str):
        return hex_value 
    hex_value = hex_value.lstrip('#')
    try:
        if len(hex_value) == 6:
            return tuple(int(hex_value[i: i+2], 16) for i in (0, 2, 4))
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

        self.bg_cache = {}  # Cache para clipes de fundo
        self.last_used_videos = []  # Histórico dos últimos vídeos usados para evitar repetições
        self.max_history = 3  # Quantos vídeos manter no histórico

        # Configuração da instância
        self.config_instance = Config()
        
        # Aplicar configurações de padding se especificadas
        if "padding_bottom" in self.global_settings:
            self.config_instance.padding_bottom = self.global_settings["padding_bottom"]
        if "padding_top" in self.global_settings:
            self.config_instance.padding_top = self.global_settings["padding_top"]
        if "padding_side" in self.global_settings:
            self.config_instance.padding_side = self.global_settings["padding_side"]
        
        self.config_instance.width = self.resolution_output[0]
        self.config_instance.height = self.resolution_output[1]


        # Configuração de diretórios
        slug = data_config.get("slug", "video_sem_slug")
        base_output_dir = getattr(self.config_instance, 'output_dir', os.path.join(os.getcwd(), "output"))
        self.output_dir = os.path.join(base_output_dir, slug)
        os.makedirs(self.output_dir, exist_ok=True)
        
        self.final_clips = []
        self.total_duration = 0.0

    def _get_tts_engine(self):
        """Retorna instância do motor TTS"""
        return EdgeTTS()

    def _process_narration(self, scene_data, target_dir):
        """
        Processa narração da cena gerando áudio e legendas.
        CORREÇÃO: Implementação completa do TTS que estava quebrada.
        """
        narration_config = scene_data.get("narration", {})
        text = narration_config.get("text", "")
        
        if not text:
            print("[UVE] Cena sem narração.Duração será fixa.")
            return None, narration_config.get("duration", 4.0), None, None

        # Definir voz (prioridade:  cena > global > padrão)
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
        """
        Seleciona vídeos aleatórios para cobrir a duração necessária,
        evitando repetições consecutivas e entre cenas.
        """
        if not available_clips: 
            return []
            
        selected_clips = []
        current_duration = 0.0
        attempts = 0
        max_attempts = len(available_clips) * 3
        
        # Filtrar vídeos que não estão no histórico recente
        available_for_selection = []
        for clip in available_clips:
            clip_path = getattr(clip, 'filename', str(hash(str(clip))))
            if clip_path not in self.last_used_videos: 
                available_for_selection.append(clip)
        
        # Se todos os vídeos estão no histórico, usar todos (resetar histórico)
        if not available_for_selection:
            print(f"[UVE] Resetando histórico de vídeos para evitar deadlock")
            available_for_selection = available_clips.copy()
            self.last_used_videos = []
        
        print(f"[UVE] Selecionando vídeos para duração: {target_duration:.2f}s")
        print(f"[UVE] Vídeos disponíveis:  {len(available_for_selection)} (histórico: {len(self.last_used_videos)})")
        
        while current_duration < target_duration and attempts < max_attempts:
            attempts += 1
            
            if not available_for_selection:
                break
                
            # Selecionar vídeo aleatório
            selected_clip = random.choice(available_for_selection)
            clip_duration = getattr(selected_clip, 'duration', 4.0)
            
            # Calcular quanto deste vídeo precisamos
            remaining_duration = target_duration - current_duration
            actual_duration = min(clip_duration, remaining_duration)
            
            # Criar subclip se necessário
            if actual_duration < clip_duration: 
                # Usar uma parte aleatória do vídeo se for mais longo que o necessário
                start_time = random.uniform(0, max(0, clip_duration - actual_duration))
                clip_segment = selected_clip.subclip(start_time, start_time + actual_duration)
            else:
                clip_segment = selected_clip.copy()
            
            selected_clips.append(clip_segment)
            current_duration += actual_duration
            
            # Adicionar ao histórico
            clip_path = getattr(selected_clip, 'filename', str(hash(str(selected_clip))))
            if clip_path not in self.last_used_videos:
                self.last_used_videos.append(clip_path)
            
            # Remover da seleção atual para evitar repetição imediata
            available_for_selection.remove(selected_clip)
            
            print(f"[UVE] Vídeo selecionado: duração {actual_duration:.2f}s (total: {current_duration:.2f}s)")
            
            # Se não há mais vídeos disponíveis, parar
            if not available_for_selection and current_duration < target_duration: 
                print(f"[UVE] ⚠️ Acabaram os vídeos únicos.Duração atual: {current_duration:.2f}s")
                break
        
        # Manter histórico limitado
        if len(self.last_used_videos) > self.max_history:
            self.last_used_videos = self.last_used_videos[-self.max_history:]
        
        print(f"[UVE] ✅ {len(selected_clips)} vídeos selecionados para duração total: {current_duration:.2f}s")
        return selected_clips

    def _create_background_clip(self, scene_data, scene_duration, scene_dir, video_dir):
        """
        Cria clip de fundo com merge de configurações global/cena.
        CORREÇÃO: Múltiplos vídeos aleatórios para cobrir duração da cena.
        """
        print(f"[UVE] Criando fundo para duração: {scene_duration:.2f}s")
        
        # Merge de background (cena sobrescreve global)
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
                print(f"[UVE] Carregando vídeo de fundo:  {path}")
                
                bg_clip = VideoFileClip(path, audio=False)
                bg_clip = bg_clip.resize(newsize=self.resolution_output)
                
                # Ajustar duração (loop se necessário)
                if bg_clip.duration < scene_duration:  
                    bg_clip = bg_clip.loop(duration=scene_duration)
                else:
                    bg_clip = bg_clip.subclip(0, scene_duration)
                    
                bg_clip = bg_clip.without_audio()

            elif bg_type == "directory":
                source_dir = visual_config.get("source")
                if not source_dir:
                    raise ValueError("Diretório source não especificado")
                
                print(f"[UVE] Processando vídeos do diretório: {source_dir}")
                
                # Sistema de cache melhorado
                if source_dir not in self.bg_cache:
                    print(f"[UVE] Carregando vídeos do diretório para cache...")
                    loader = BackgroundVideo({
                        "background_videos_dir": source_dir,
                        "resolution_output": self.resolution_output,
                        "output_ratio": self.output_ratio,
                        "crossfade_duration":  self.global_settings.get("crossfade_duration", 0.8),
                        "enable_crossfade":  self.global_settings.get("enable_crossfade", True),
                        "shuffle_clips": self.global_settings.get("shuffle_clips", True),
                        "loop_background":  self.global_settings.get("loop_background", True),
                        "max_clips": self.global_settings.get("max_clips")
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
                    
                    # NOVO: Selecionar múltiplos vídeos para cobrir a duração
                    scene_id = scene_data.get('id', 'unknown')
                    selected_clips = self._select_random_videos_for_duration(
                        cached_clips, scene_duration, scene_id
                    )
                    
                    if selected_clips: 
                        if len(selected_clips) == 1:
                            # Um vídeo apenas
                            bg_clip = selected_clips[0]
                            # Ajustar duração se necessário
                            if bg_clip.duration < scene_duration:
                                bg_clip = bg_clip.loop(duration=scene_duration)
                            elif bg_clip.duration > scene_duration: 
                                bg_clip = bg_clip.subclip(0, scene_duration)
                        else:
                            # Múltiplos vídeos - concatenar
                            print(f"[UVE] Concatenando {len(selected_clips)} vídeos para o fundo")
                            
                            # Verificar se há crossfade habilitado
                            enable_crossfade = self.global_settings.get("enable_crossfade", False)
                            crossfade_duration = self.global_settings.get("crossfade_duration", 0.5)
                            
                            if enable_crossfade and len(selected_clips) > 1:
                                # Concatenar com crossfade
                                bg_clip = selected_clips[0]
                                for next_clip in selected_clips[1:]: 
                                    bg_clip = concatenate_videoclips(
                                        [bg_clip, next_clip], 
                                        method="compose"
                                    )
                                    # Aplicar crossfade entre os clipes
                                    if bg_clip.duration > crossfade_duration:
                                        fade_start = bg_clip.duration - len(selected_clips) * crossfade_duration
                                        bg_clip = bg_clip.crossfadein(crossfade_duration)
                            else:
                                # Concatenar simples
                                bg_clip = concatenate_videoclips(selected_clips, method="compose")
                            
                            # Ajustar duração final se necessário
                            if bg_clip.duration > scene_duration: 
                                bg_clip = bg_clip.subclip(0, scene_duration)
                            elif bg_clip.duration < scene_duration: 
                                # Se ainda for menor, fazer loop do último segmento
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
                        bg_clip = ColorClip(size=self.resolution_output, color=(0,0,0)).set_duration(scene_duration)
                else:
                    print("[UVE] ⚠️ Cache vazio, usando fundo preto")
                    bg_clip = ColorClip(size=self.resolution_output, color=(0,0,0)).set_duration(scene_duration)

            else:
                print(f"[UVE] ⚠️ Tipo de fundo desconhecido: {bg_type}, usando preto")
                bg_clip = ColorClip(size=self.resolution_output, color=(0,0,0)).set_duration(scene_duration)
                
        except Exception as e:  
            print(f"[UVE] ❌ Falha ao criar fundo: {e}")
            import traceback
            traceback.print_exc()
            print(f"[UVE] Usando fundo preto como fallback")
            bg_clip = ColorClip(size=self.resolution_output, color=(0,0,0)).set_duration(scene_duration)

        # Processar overlays (seu sistema atual)
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

        # Composição final
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
        """
        Cria elementos visuais da cena.
        CORREÇÃO: Melhorado tratamento de erros e posicionamento.
        """
        elements = scene_data.get("visual_elements", [])
        if not elements:
            return None
            
        print(f"[UVE] Processando {len(elements)} elementos visuais...")
        
        # PASSO 1: Gerar clips "crus" para descobrir tamanhos reais
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
                    print(f"[UVE] ✅ Elemento {i+1} gerado:  {w}x{h}")
                else: 
                    print(f"[UVE] ⚠️ Falha ao gerar elemento {i+1}")
                    
            except Exception as e: 
                print(f"[UVE] ❌ Erro no elemento {i+1}: {e}")

        if not valid_clips_info:
            print("[UVE] ❌ Nenhum elemento visual foi gerado com sucesso")
            return None

        # PASSO 2: Aplicar LayoutEngine para posicionamento
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
                    print(f"[UVE] ✅ Elemento {i+1} posicionado: {final_size} @ {final_pos}")
                except Exception as e:
                    print(f"[UVE] ❌ Falha ao posicionar elemento {i+1}: {e}")
            
            if not final_clips:
                print("[UVE] ❌ Nenhum elemento foi posicionado corretamente")
                return None
                
            return CompositeVideoClip(final_clips, size=self.resolution_output).set_duration(scene_duration).fl_image(force_rgb)
            
        except Exception as e:
            print(f"[UVE] ❌ Falha no LayoutEngine: {e}")
            # Fallback:  posicionar elementos centralizados
            print("[UVE] Usando posicionamento centralizado como fallback")
            
            centered_clips = []
            for i, clip in enumerate(valid_clips_info):
                try:
                    clip_centered = clip.set_position('center')
                    centered_clips.append(clip_centered)
                except Exception as e: 
                    print(f"[UVE] ❌ Falha no fallback do elemento {i+1}:  {e}")
            
            if centered_clips:
                return CompositeVideoClip(centered_clips, size=self.resolution_output).set_duration(scene_duration).fl_image(force_rgb)
            
            return None

    def _create_subtitle_clip(self, scene_duration, subtitle_file, has_visual_elements=False):
        """
        Cria clip de legendas.
        CORREÇÃO: Integração adequada com configurações globais e posicionamento.
        """
        try:
            if not subtitle_file or not os.path.exists(subtitle_file):
                print("[UVE] ⚠️ Arquivo de legenda não encontrado")
                return None
                
            print(f"[UVE] Gerando legendas do arquivo: {subtitle_file}")
            
            # Configurações base das legendas
            subtitle_config = {
                "subtitle_narration_file": subtitle_file,  # Nome correto do parâmetro
                "resolution_output": self.resolution_output,
                "padding_bottom": getattr(self.config_instance, 'padding_bottom', 200),
                "padding_side": getattr(self.config_instance, 'padding_side', 50),
                "padding_top": getattr(self.config_instance, 'padding_top', 200),
                "has_visual_elements":  has_visual_elements,
            }
            
            # Mesclar com configurações globais de subtitle
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

    def run(self, output_filename="final_video.mp4"):
        """
        Método principal de renderização.
        CORREÇÃO: Melhor tratamento de erros e limpeza de memória.
        """
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
            print(f"\n[UVE] 📝 Processando cena {scene_index+1}/{total_scenes}: {scene_id}")

            scene_dir = os.path.join(self.output_dir, scene_id)
            os.makedirs(scene_dir, exist_ok=True)

            # 1.Processar narração
            audio_clip, duration_from_tts, word_timing, subtitle_file = self._process_narration(scene, scene_dir)
            
            # 2.Definir duração da cena
            scene_duration = scene.get("duration", duration_from_tts)
            if not scene_duration or scene_duration < 0.1:
                scene_duration = 4.0
                print(f"[UVE] Usando duração padrão: {scene_duration}s")
            else:
                print(f"[UVE] Duração da cena:  {scene_duration}s")

            # 3.Criar componentes da cena
            try:
                background_clip = self._create_background_clip(scene, scene_duration, scene_dir, self.output_dir)
                visual_clip = self._create_visual_elements_clip(scene, scene_duration, scene_dir)

                subtitle_clip = None
                if scene.get("narration", {}).get("subtitles", False):
                    has_visuals = bool(scene.get("visual_elements"))
                    subtitle_clip = self._create_subtitle_clip(scene_duration, subtitle_file, has_visuals)

                # 4.Composição da cena
                final_scene_clip = [background_clip]
                if visual_clip:  
                    final_scene_clip.append(visual_clip)
                    print("[UVE] ✅ Elementos visuais adicionados")
                if subtitle_clip: 
                    final_scene_clip.append(subtitle_clip)
                    print("[UVE] ✅ Legendas adicionadas")

                # 5.Aplicar force_rgb em todos os clips
                safe_clips = []
                for c in final_scene_clip:
                    try:
                        c = c.fl_image(force_rgb) 
                        safe_clips.append(c)
                    except Exception as e: 
                        print(f"[UVE] ⚠️ Falha ao aplicar force_rgb: {e}")
                        safe_clips.append(c)

                # 6.Compor cena final
                composed_clip = CompositeVideoClip(safe_clips, size=self.resolution_output).set_duration(scene_duration)
                composed_clip = composed_clip.fl_image(force_rgb)

                # 7.Adicionar áudio se existir
                if audio_clip: 
                    if composed_clip.audio:
                        composed_clip.audio = CompositeAudioClip([composed_clip.audio, audio_clip])
                    else: 
                        composed_clip = composed_clip.set_audio(audio_clip)
                    print("[UVE] ✅ Áudio da narração adicionado")

                # 8.Renderizar cena para arquivo temporário
                temp_scene_path = os.path.join(temp_dir, f"scene_{scene_index:04d}.mp4")
                temp_audiofile = os.path.join(temp_dir, f"temp-audio-{scene_index}.m4a")
                
                print(f"[UVE] 🎬 Renderizando cena {scene_index+1}/{total_scenes}...")
                
                composed_clip.write_videofile(
                    temp_scene_path,
                    codec='libx264',
                    audio_codec='aac',
                    temp_audiofile=temp_audiofile,
                    remove_temp=True,
                    fps=24,
                    preset='medium',
                    threads=4,  # Melhor performance
                    verbose=False,
                    logger=None
                )
                
                scene_files.append(temp_scene_path)
                print(f"[UVE] ✅ Cena {scene_index+1} renderizada:  {os.path.basename(temp_scene_path)}")
                
                # Limpeza de memória
                try:
                    composed_clip.close()
                    if audio_clip:
                        audio_clip.close()
                except:
                    pass
                
                del composed_clip
                if 'audio_clip' in locals():
                    del audio_clip
                gc.collect()
                
            except Exception as e: 
                print(f"[UVE] ❌ Erro ao processar cena {scene_index+1}:  {e}")
                import traceback
                traceback.print_exc()
                continue

        # 9.Concatenar cenas em vídeo final
        slug = self.data_config.get("slug", "video_final")
        if not output_filename.endswith('.mp4'):
            output_filename = f"{slug}.mp4"
            
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

            # Tentar concatenação rápida primeiro
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_list_path, "-c", "copy", output_path
            ]
            
            subprocess.run(ffmpeg_cmd, check=True, capture_output=True)
            print(f"[UVE] ✅ Vídeo final concatenado:  {output_path}")
            
        except subprocess.CalledProcessError as e:
            print("[UVE] ⚠️ Concatenação rápida falhou, tentando re-encoding...")
            try:
                # Fallback com re-encoding
                ffmpeg_cmd_reencode = [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", concat_list_path,
                    "-c: v", "libx264", "-preset", "medium", "-crf", "20",
                    "-c:a", "aac", "-b: a", "128k",
                    output_path
                ]
                subprocess.run(ffmpeg_cmd_reencode, check=True, capture_output=True)
                print(f"[UVE] ✅ Vídeo final concatenado (re-encoded): {output_path}")
            except Exception as e: 
                print(f"[UVE] ❌ Falha na concatenação: {e}")
                return None
        except Exception as e: 
            print(f"[UVE] ❌ Falha na concatenação:  {e}")
            return None

        # 10.Limpeza de arquivos temporários
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
            print("[UVE] 🧹 Arquivos temporários removidos")
        except Exception as e:
            print(f"[UVE] ⚠️ Falha na limpeza:  {e}")

        # 11.Upload para YouTube (se configurado)
        if self.data_config.get("youtube") and self.data_config.get("debug") is not True:
            try:
                print("[UVE] 📤 Iniciando upload para o YouTube...")
                youtube_params = self.data_config.get("youtube", {}).copy()
                youtube_params["video_path"] = output_path
                youtube_uploader = YouTube(params=youtube_params)
                youtube_uploader.upload()
            except Exception as e: 
                print(f"[UVE] ❌ Upload YouTube falhou: {e}")

        # 12.Abrir vídeo se em modo debug
        if self.data_config.get("debug") is True:
            try:
                print("[UVE] 🎥 Abrindo vídeo final...")
                if os.name == 'nt':  # Windows
                    os.startfile(output_path)
                elif os.name == 'posix':  # macOS/Linux
                    subprocess.run(["open" if "darwin" in os.uname().sysname.lower() else "xdg-open", output_path])
            except Exception as e: 
                print(f"[UVE] ⚠️ Falha ao abrir vídeo: {e}")

        print(f"\n[UVE] 🎉 Processamento concluído com sucesso!")
        print(f"[UVE] 📁 Arquivo final: {output_path}")
        print(f"[UVE] ⏱️ Duração total: {self.total_duration:.2f}s")
        
        return output_path