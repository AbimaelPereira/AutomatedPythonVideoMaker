import os
import random
from moviepy.editor import AudioFileClip
from libs.Transitions.Zoom import Zoom


class TransitionEngine:
    """
    Engine de transição simplificado que aplica zoom out + zoom in em clips individuais.
    """
    def __init__(self, config: dict):
        defaults = {
            "clip": None,  # Clip único a ser processado
            "transitions_settings": None,
            "resolution": (1920, 1080),
            "audio_settings": None,
            "visual_settings": None,
        }

        self.config = {**defaults, **config}
        for key, value in self.config.items():
            setattr(self, key, value)

        # Validar parâmetros obrigatórios
        if self.clip is None:
            raise ValueError("[TransitionEngine] Parâmetro obrigatório ausente: clip")
        
        if self.transitions_settings is None:
            raise ValueError("[TransitionEngine] Parâmetro obrigatório ausente: transitions_settings")

        # Extrair configurações
        if self.transitions_settings.get("audio"):
            self.audio_settings = self.transitions_settings["audio"]

        if self.transitions_settings.get("visual"):
            self.visual_settings = self.transitions_settings["visual"]

    def _get_clip_audio(self):
        """
        Retorna o áudio do efeito de transição, se disponível.
        """
        if not self.audio_settings:
            return None

        audio_type = self.audio_settings.get("type")  # 'directory' ou 'file'
        source = self.audio_settings.get("source")  # diretório ou arquivo
        volume = self.audio_settings.get("volume", 1.0)

        if audio_type == "directory":
            if not source or not os.path.exists(source):
                return None
            
            files = [f for f in os.listdir(source) if f.endswith(('.mp3', '.wav'))]
            if not files:
                return None
            
            audio_path = os.path.join(source, random.choice(files))
        
        elif audio_type == "file":
            audio_path = source
            if not audio_path or not os.path.exists(audio_path):
                return None
        else:
            return None

        try:
            audio_clip = AudioFileClip(audio_path)
            return audio_clip.volumex(volume)
        except Exception as e:
            print(f"[TransitionEngine] ⚠️ Erro ao carregar áudio: {e}")
            return None

    def apply_transition(self):
        """
        Aplica a transição de zoom no clip fornecido.
        """
        if not self.clip:
            return None

        # Configurar parâmetros da transição
        params = {
            "resolution_output": self.resolution,
            "clip": self.clip,
        }

        # Adicionar configurações visuais se fornecidas
        if self.visual_settings:
            params.update(self.visual_settings)

        # Adicionar áudio se configurado
        audio_clip = self._get_clip_audio()
        if audio_clip:
            params["audio_file_clip"] = audio_clip

        print(f"[TransitionEngine] Aplicando transição Zoom com params: {params.keys()}")

        # Criar e processar transição
        try:
            transition_instance = Zoom(params)
            return transition_instance.process()
        except Exception as e:
            print(f"[TransitionEngine] ❌ Erro ao aplicar transição: {e}")
            import traceback
            traceback.print_exc()
            return self.clip  # Retorna clip original em caso de erro
