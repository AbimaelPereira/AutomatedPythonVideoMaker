"""
AudioEngine - Serviço responsável por mixagem de áudio e música de fundo.

Este serviço encapsula toda a lógica relacionada a:
- Mixagem de áudio da cena (narração + efeito de transição)
- Aplicação de música de fundo ao vídeo final
- Volumes, fades e ajustes de áudio
- Integração com SceneAudioManager

Preserva o comportamento exato do UnifiedVideoEngine original em termos de:
- Volumes padrão
- Mix de narração com efeitos de transição
- Loop de música de fundo
- Codec e bitrate de áudio (AAC, 128k)
"""

import os
import random
from moviepy.editor import (
    AudioFileClip, VideoFileClip,
    CompositeAudioClip, concatenate_audioclips
)

from libs.SceneAudioManager import SceneAudioManager


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


class AudioEngine:
    """
    Motor de áudio para mixagem e processamento.
    
    Responsável por mixar áudio de cenas e aplicar música de fundo
    ao vídeo final.
    """
    
    VALID_AUDIO_EXTENSIONS = [".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"]
    
    def __init__(self, global_settings=None):
        """
        Inicializa o motor de áudio.
        
        Args:
            global_settings: Configurações globais (transition effects, etc.)
        """
        self.global_settings = global_settings or {}
    
    def get_transition_effect_config(self, scene_data):
        """
        Obtém configuração de efeito de transição com merge global/cena.
        
        Args:
            scene_data: Dados da cena
        
        Returns:
            Dicionário de configuração ou None
        """
        global_effect = self.global_settings.get("transition_effect_audio", {})
        scene_effect = scene_data.get("transition_effect_audio", {})
        
        if scene_effect:
            return deep_merge(global_effect, scene_effect)
        return dict(global_effect) if global_effect else None
    
    def mix_scene_audio(self, narration_clip, transition_effect_config, 
                       scene_duration, output_dir):
        """
        Mixa áudio da cena (narração + efeito de transição).
        
        Args:
            narration_clip: AudioFileClip da narração ou None
            transition_effect_config: Configuração do efeito de transição
            scene_duration: Duração da cena em segundos
            output_dir: Diretório de saída para arquivos temporários
        
        Returns:
            AudioClip mixado ou None
        """
        audio_manager = SceneAudioManager({
            "scene_duration": scene_duration,
            "output_dir": output_dir,
        })
        
        scene_audio = audio_manager.create_scene_audio(
            narration_clip=narration_clip,
            transition_effect_config=transition_effect_config,
            scene_duration=scene_duration
        )
        
        return scene_audio
    
    def apply_background_music(self, video_path, output_path, bg_audio_config):
        """
        Aplica música de fundo ao vídeo final.
        
        Args:
            video_path: Caminho do vídeo sem música de fundo
            output_path: Caminho de saída do vídeo com música
            bg_audio_config: Configuração de áudio de fundo
        
        Returns:
            Caminho do vídeo final ou video_path original se falhar
        """
        if not bg_audio_config:
            print("[AudioEngine] Sem configuração de áudio de fundo")
            return video_path
        
        audio_type = bg_audio_config.get("type", "file")
        source = bg_audio_config.get("source")
        volume = bg_audio_config.get("volume", 0.3)
        
        if not source:
            print("[AudioEngine] Áudio de fundo sem source configurado")
            return video_path
        
        try:
            # Seleciona arquivo de áudio
            if audio_type == "directory":
                audio_path = self._select_random_audio_from_dir(source)
            else:  # file
                audio_path = source
            
            if not audio_path or not os.path.exists(audio_path):
                print(f"[AudioEngine] ⚠️ Áudio de fundo não encontrado: {audio_path}")
                return video_path
            
            print(f"[AudioEngine] 🎵 Aplicando áudio de fundo: {os.path.basename(audio_path)}")
            
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
            print(f"[AudioEngine] 🎬 Renderizando vídeo com áudio de fundo...")
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
            
            print(f"[AudioEngine] ✅ Áudio de fundo aplicado: {os.path.basename(output_path)}")
            return output_path
        
        except Exception as e:
            print(f"[AudioEngine] ❌ Erro ao aplicar áudio de fundo: {e}")
            import traceback
            traceback.print_exc()
            return video_path
    
    def _select_random_audio_from_dir(self, directory):
        """
        Seleciona áudio aleatório de um diretório.
        
        Args:
            directory: Caminho do diretório
        
        Returns:
            Caminho do arquivo selecionado ou None
        """
        if not os.path.isdir(directory):
            return None
        
        files = [
            os.path.join(directory, f) for f in os.listdir(directory)
            if os.path.splitext(f.lower())[1] in self.VALID_AUDIO_EXTENSIONS
        ]
        
        return random.choice(files) if files else None
