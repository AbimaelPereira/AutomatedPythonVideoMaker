"""
SpeechService - Serviço responsável por TTS (Text-to-Speech) e geração de legendas.

Este serviço encapsula toda a lógica relacionada a:
- Geração de áudio de narração usando TTS (Edge TTS)
- Criação de arquivos de legenda (SRT) com word boundaries
- Geração de clips de legenda sincronizados

Preserva o comportamento exato do UnifiedVideoEngine original em termos de:
- Voz utilizada
- Duração do áudio
- Posicionamento das legendas (centro sem elementos visuais, inferior com elementos)
- Formatação e estilo das legendas
"""

import os
from moviepy.editor import AudioFileClip
from libs.TTS_Edge import EdgeTTS
from libs.Subtitle import Subtitle


class SpeechService:
    """
    Serviço de TTS e legendas.
    
    Responsável por gerar áudio de narração e legendas sincronizadas,
    mantendo compatibilidade total com o fluxo original do UnifiedVideoEngine.
    """
    
    def __init__(self, tts_config=None, resolution_output=(1080, 1920), config_instance=None):
        """
        Inicializa o serviço de fala.
        
        Args:
            tts_config: Configuração de TTS (voz, etc.)
            resolution_output: Tupla (width, height) para resolução do vídeo
            config_instance: Instância de Config para paddings e outras configurações
        """
        self.tts_config = tts_config or {}
        self.resolution_output = resolution_output
        self.config_instance = config_instance
    
    def generate_narration(self, text, voice=None, output_basename=None, scene_id="unknown"):
        """
        Gera áudio de narração usando TTS.
        
        Args:
            text: Texto para narração
            voice: Voz a ser usada (ex: "pt-BR-AntonioNeural")
            output_basename: Caminho base para salvar o áudio (sem extensão)
            scene_id: ID da cena para logging
        
        Returns:
            Tupla (audio_clip, duration, word_boundaries, subtitle_file)
            - audio_clip: AudioFileClip ou None
            - duration: Duração em segundos ou duração padrão
            - word_boundaries: Lista de word timings ou None
            - subtitle_file: Caminho para arquivo SRT ou None
        """
        if not text:
            print(f"[SpeechService] Cena {scene_id} sem narração. Duração será fixa.")
            return None, 4.0, None, None
        
        if not voice:
            voice = self.tts_config.get("voice", "pt-BR-AntonioNeural")
        
        print(f"[SpeechService] Gerando áudio para cena {scene_id}...")
        
        try:
            tts_params = {
                "text": text,
                "voice_id": voice,
                "output_basename": output_basename,
            }
            
            tts_engine = EdgeTTS(params=tts_params)
            tts_result = tts_engine.generate_audio_and_subtitles()
            
            final_audio_path = tts_result.get("audio_file")
            word_boundaries = tts_result.get("word_boundaries")
            subtitle_file = tts_result.get("subtitle_file")
            
            if not final_audio_path or not os.path.exists(final_audio_path):
                print(f"[SpeechService] ERRO: Arquivo de áudio não foi criado: {final_audio_path}")
                return None, 4.0, None, None
            
            audio_clip = AudioFileClip(final_audio_path)
            duration = audio_clip.duration
            
            print(f"[SpeechService] ✅ Áudio gerado com sucesso - Duração: {duration:.2f}s")
            return audio_clip, duration, word_boundaries, subtitle_file
        
        except Exception as e:
            print(f"[SpeechService] ERRO ao gerar TTS: {e}")
            import traceback
            traceback.print_exc()
            return None, 4.0, None, None
    
    def create_subtitles(self, subtitle_file, scene_duration, has_visual_elements=False, 
                        global_subtitle_config=None):
        """
        Cria clip de legendas a partir de arquivo SRT.
        
        Args:
            subtitle_file: Caminho para arquivo SRT
            scene_duration: Duração da cena em segundos
            has_visual_elements: Se há elementos visuais (afeta posicionamento)
            global_subtitle_config: Configuração global de legendas
        
        Returns:
            Clip de legenda ou None em caso de erro
        """
        try:
            if not subtitle_file or not os.path.exists(subtitle_file):
                print("[SpeechService] ⚠️ Arquivo de legenda não encontrado")
                return None
            
            print(f"[SpeechService] Gerando legendas do arquivo: {subtitle_file}")
            
            subtitle_config = {
                "subtitle_narration_file": subtitle_file,
                "resolution_output": self.resolution_output,
                "padding_bottom": getattr(self.config_instance, 'padding_bottom', 200) if self.config_instance else 200,
                "padding_side": getattr(self.config_instance, 'padding_side', 50) if self.config_instance else 50,
                "padding_top": getattr(self.config_instance, 'padding_top', 200) if self.config_instance else 200,
                "has_visual_elements": has_visual_elements,
            }
            
            if global_subtitle_config:
                subtitle_config.update(global_subtitle_config)
            
            position = 'inferior' if has_visual_elements else 'centro'
            print(f"[SpeechService] Configurações de legenda: posição={position}")
            
            subtitle_generator = Subtitle(params=subtitle_config)
            subtitle_clip = subtitle_generator.generate()
            
            if subtitle_clip:
                subtitle_clip = subtitle_clip.set_duration(scene_duration)
                print("[SpeechService] ✅ Legendas geradas com sucesso")
                return subtitle_clip
            else:
                print("[SpeechService] ❌ Falha na geração das legendas")
                return None
        
        except Exception as e:
            print(f"[SpeechService] ❌ Falha ao criar legendas: {e}")
            import traceback
            traceback.print_exc()
            return None
