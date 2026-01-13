"""
VideoOrchestrator - Orquestrador principal do fluxo de geração de vídeo.

Este módulo coordena todos os serviços para gerar o vídeo final,
mantendo a mesma lógica e ordem de operações do UnifiedVideoEngine original.

Preserva:
- Ordem de processamento das cenas
- Comportamento de fallback
- Logs e mensagens
- Fluxo end-to-end idêntico
"""

import os
import gc
import shutil
from moviepy.editor import CompositeVideoClip
from libs.VisualClip import force_rgb

from libs.core.ConfigManager import ConfigManager
from libs.services.SpeechService import SpeechService
from libs.services.AssetManager import AssetManager
from libs.services.SceneRenderer import SceneRenderer
from libs.services.AudioEngine import AudioEngine
from libs.pipeline.ExportPipeline import ExportPipeline
from libs.delivery.DeliveryService import DeliveryService


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


class VideoOrchestrator:
    """
    Orquestrador de geração de vídeo.
    
    Coordena todos os serviços e gerencia o fluxo completo
    de geração do vídeo, desde as cenas até a entrega final.
    """
    
    def __init__(self, data_config):
        """
        Inicializa o orquestrador.
        
        Args:
            data_config: Dicionário de configuração do vídeo
        """
        self.data_config = data_config
        
        # Configuração
        self.config_manager = ConfigManager(data_config)
        self.config_instance = self.config_manager.get_config_instance()
        self.resolution_output = self.config_manager.get_resolution()
        self.global_settings = self.config_manager.get_global_settings()
        
        # Setup diretório de saída
        slug = data_config.get("slug", "video_sem_slug")
        base_output_dir = getattr(self.config_instance, 'output_dir', 
                                  os.path.join(os.getcwd(), "output"))
        self.output_dir = os.path.join(base_output_dir, slug)
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Inicializar serviços
        self.speech_service = SpeechService(
            tts_config=self.config_manager.get_tts_config(),
            resolution_output=self.resolution_output,
            config_instance=self.config_instance
        )
        
        self.asset_manager = AssetManager(
            resolution_output=self.resolution_output,
            global_settings=self.global_settings
        )
        
        self.scene_renderer = SceneRenderer(
            resolution_output=self.resolution_output,
            config_instance=self.config_instance,
            global_settings=self.global_settings
        )
        
        self.audio_engine = AudioEngine(
            global_settings=self.global_settings
        )
        
        self.export_pipeline = ExportPipeline()
        self.delivery_service = DeliveryService()
        
        # Estado
        self.total_duration = 0.0
    
    def run(self, output_filename="final_video.mp4"):
        """
        Executa o fluxo completo de geração de vídeo.
        
        Args:
            output_filename: Nome do arquivo de saída
        
        Returns:
            Caminho do vídeo final ou None em caso de erro
        """
        print("[VideoOrchestrator] 🚀 Iniciando processamento do vídeo...")
        
        scene_files = []
        temp_dir = os.path.join(self.output_dir, "_temp")
        os.makedirs(temp_dir, exist_ok=True)
        
        scenes = self.data_config.get("scenes", [])
        total_scenes = len(scenes)
        
        if not scenes:
            print("[VideoOrchestrator] ❌ Nenhuma cena encontrada na configuração")
            return None
        
        # Processar cada cena
        for scene_index, scene in enumerate(scenes):
            scene_id = scene.get("id", f"cena_{scene_index}")
            print(f"\n[VideoOrchestrator] 📝 Processando cena {scene_index + 1}/{total_scenes}: {scene_id}")
            
            scene_dir = os.path.join(self.output_dir, scene_id)
            os.makedirs(scene_dir, exist_ok=True)
            
            try:
                # 1. Processar narração
                narration_clip, duration_from_tts, word_timing, subtitle_file = self._process_scene_narration(
                    scene, scene_dir, scene_id
                )
                
                # 2. Definir duração da cena
                scene_duration = self._determine_scene_duration(scene, duration_from_tts)
                
                # 3. Criar background
                background_clip = self._create_scene_background(scene, scene_duration, scene_dir)
                
                # 4. Criar elementos visuais
                visual_clip = self._create_scene_visuals(scene, scene_duration, scene_dir)
                
                # 5. Criar legendas
                subtitle_clip = self._create_scene_subtitles(scene, scene_duration, subtitle_file, 
                                                             bool(scene.get("visual_elements")))
                
                # 6. Compor cena
                composed_clip = self._compose_scene(
                    background_clip, visual_clip, subtitle_clip, scene_duration
                )
                
                # 7. Adicionar áudio
                composed_clip = self._add_scene_audio(
                    composed_clip, narration_clip, scene, scene_duration, scene_dir
                )
                
                # 8. Renderizar cena
                temp_scene_path = self._render_scene(
                    composed_clip, scene_index, total_scenes, temp_dir
                )
                
                if temp_scene_path:
                    scene_files.append(temp_scene_path)
                    self.total_duration += scene_duration
                
                # 9. Limpeza de memória
                self._cleanup_scene_memory(composed_clip, narration_clip)
            
            except Exception as e:
                print(f"[VideoOrchestrator] ❌ Erro ao processar cena {scene_index + 1}: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        # 10. Concatenar cenas
        slug = self.data_config.get("slug", "video_final")
        if not output_filename.endswith('.mp4'):
            output_filename = f"{slug}.mp4"
        
        intermediate_path = self.export_pipeline.concatenate_scenes(scene_files, temp_dir, slug)
        if not intermediate_path:
            return None
        
        # 11. Aplicar áudio de fundo
        output_path = os.path.join(self.output_dir, output_filename)
        final_path = self._apply_background_music(intermediate_path, output_path)
        
        # 12. Limpeza
        self.export_pipeline.cleanup_temp_files(temp_dir)
        
        # 13. Entrega (YouTube, debug)
        self._deliver_video(final_path)
        
        print(f"\n[VideoOrchestrator] 🎉 Processamento concluído com sucesso!")
        print(f"[VideoOrchestrator] 📁 Arquivo final: {final_path}")
        print(f"[VideoOrchestrator] ⏱️ Duração total: {self.total_duration:.2f}s")
        
        return final_path
    
    def _process_scene_narration(self, scene, scene_dir, scene_id):
        """Processa narração da cena."""
        narration_config = scene.get("narration", {})
        text = narration_config.get("text", "")
        
        if not text:
            return None, narration_config.get("duration", 4.0), None, None
        
        voice = (scene.get("tts", {}).get("voice") or
                self.config_manager.get_tts_config().get("voice") or
                "pt-BR-AntonioNeural")
        
        audio_basename = os.path.join(scene_dir, f"audio_{scene_id}")
        
        return self.speech_service.generate_narration(
            text=text,
            voice=voice,
            output_basename=audio_basename,
            scene_id=scene_id
        )
    
    def _determine_scene_duration(self, scene, duration_from_tts):
        """Determina duração da cena."""
        scene_duration = scene.get("duration", duration_from_tts)
        if not scene_duration or scene_duration < 0.1:
            scene_duration = 4.0
            print(f"[VideoOrchestrator] Usando duração padrão: {scene_duration}s")
        else:
            print(f"[VideoOrchestrator] Duração da cena: {scene_duration}s")
        return scene_duration
    
    def _create_scene_background(self, scene, scene_duration, scene_dir):
        """Cria background da cena."""
        # Merge de configurações global + cena
        global_background = self.global_settings.get("background", {}) or {}
        scene_background = scene.get("background", None)
        
        if scene_background is not None:
            background_config = deep_merge(global_background, scene_background)
            storage_dir = scene_dir
            print("[VideoOrchestrator] Usando configuração de fundo mesclada (global + cena)")
        else:
            background_config = dict(global_background)
            storage_dir = self.output_dir
            print("[VideoOrchestrator] Usando configuração de fundo global")
        
        background_clip = self.asset_manager.create_background(
            background_config, scene_duration, storage_dir
        )
        
        # Aplicar overlays
        return self.scene_renderer.apply_overlays(background_clip, scene, scene_duration)
    
    def _create_scene_visuals(self, scene, scene_duration, scene_dir):
        """Cria elementos visuais da cena."""
        elements = scene.get("visual_elements", [])
        if not elements:
            return None
        
        return self.scene_renderer.create_visuals(elements, scene_duration, scene_dir)
    
    def _create_scene_subtitles(self, scene, scene_duration, subtitle_file, has_visuals):
        """Cria legendas da cena."""
        if not scene.get("narration", {}).get("subtitles", False):
            return None
        
        global_subtitle_config = self.global_settings.get("subtitle", {})
        
        return self.speech_service.create_subtitles(
            subtitle_file=subtitle_file,
            scene_duration=scene_duration,
            has_visual_elements=has_visuals,
            global_subtitle_config=global_subtitle_config
        )
    
    def _compose_scene(self, background_clip, visual_clip, subtitle_clip, scene_duration):
        """Compõe todos os elementos da cena."""
        final_scene_clip = [background_clip]
        
        if visual_clip:
            final_scene_clip.append(visual_clip)
            print("[VideoOrchestrator] ✅ Elementos visuais adicionados")
        
        if subtitle_clip:
            final_scene_clip.append(subtitle_clip)
            print("[VideoOrchestrator] ✅ Legendas adicionadas")
        
        # Aplicar force_rgb em todos os clips
        safe_clips = []
        for c in final_scene_clip:
            try:
                c = c.fl_image(force_rgb)
                safe_clips.append(c)
            except Exception as e:
                print(f"[VideoOrchestrator] ⚠️ Falha ao aplicar force_rgb: {e}")
                safe_clips.append(c)
        
        # Compor cena final
        composed_clip = CompositeVideoClip(safe_clips, size=self.resolution_output).set_duration(scene_duration)
        return composed_clip.fl_image(force_rgb)
    
    def _add_scene_audio(self, composed_clip, narration_clip, scene, scene_duration, scene_dir):
        """Adiciona áudio à cena."""
        effect_config = self.audio_engine.get_transition_effect_config(scene)
        
        scene_audio = self.audio_engine.mix_scene_audio(
            narration_clip=narration_clip,
            transition_effect_config=effect_config,
            scene_duration=scene_duration,
            output_dir=scene_dir
        )
        
        if scene_audio:
            composed_clip = composed_clip.set_audio(scene_audio)
            print("[VideoOrchestrator] ✅ Áudio da cena composto (narração + efeito)")
        elif narration_clip:
            composed_clip = composed_clip.set_audio(narration_clip)
            print("[VideoOrchestrator] ✅ Áudio da narração adicionado")
        
        return composed_clip
    
    def _render_scene(self, composed_clip, scene_index, total_scenes, temp_dir):
        """Renderiza cena para arquivo."""
        temp_scene_path = os.path.join(temp_dir, f"scene_{scene_index:04d}.mp4")
        temp_audiofile = os.path.join(temp_dir, f"temp-audio-{scene_index}.m4a")
        
        print(f"[VideoOrchestrator] 🎬 Renderizando cena {scene_index + 1}/{total_scenes}...")
        
        try:
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
            
            print(f"[VideoOrchestrator] ✅ Cena {scene_index + 1} renderizada: {os.path.basename(temp_scene_path)}")
            return temp_scene_path
        
        except Exception as e:
            print(f"[VideoOrchestrator] ❌ Erro ao renderizar cena: {e}")
            return None
    
    def _cleanup_scene_memory(self, composed_clip, narration_clip):
        """Libera memória da cena."""
        try:
            composed_clip.close()
            if narration_clip:
                narration_clip.close()
        except:
            pass
        
        del composed_clip
        gc.collect()
    
    def _apply_background_music(self, intermediate_path, output_path):
        """Aplica música de fundo ao vídeo final."""
        bg_audio_config = self.global_settings.get("background", {}).get("audio", {})
        
        if bg_audio_config and bg_audio_config.get("source"):
            return self.audio_engine.apply_background_music(
                intermediate_path, output_path, bg_audio_config
            )
        else:
            # Sem áudio de fundo, apenas move
            shutil.move(intermediate_path, output_path)
            print("[VideoOrchestrator] Sem áudio de fundo configurado")
            return output_path
    
    def _deliver_video(self, final_path):
        """Entrega o vídeo (upload, debug)."""
        # Upload para YouTube (se configurado e não em debug)
        if self.data_config.get("youtube") and self.data_config.get("debug") is not True:
            youtube_config = self.data_config.get("youtube", {})
            self.delivery_service.upload_to_youtube(final_path, youtube_config)
        
        # Abrir vídeo em modo debug
        if self.data_config.get("debug") is True:
            self.delivery_service.open_video_in_player(final_path)
