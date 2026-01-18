import os
import random
from moviepy.editor import AudioFileClip
from libs.Transitions.Slide import Slide
from libs.Transitions.Zoom import Zoom

class TransitionEngine:
    def __init__(self, config: dict):

        defaults = {
            "clips": None,
            "transitions_settings": None,
            "resolution": (1920, 1080),

            "audio_settings": None,
            "visual_settings": None,
            "transition_type": None,
        }

        # adicionar todos os atributos no self
        self.config = {**defaults, **config}
        for key, value in self.config.items():
            setattr(self, key, value)

        # clips, transitions_settings, resolution são obrigatórios
        list_required = ["clips", "transitions_settings", "resolution"]
        for item in list_required:
            if getattr(self, item) is None:
                raise ValueError(f"[TransitionEngine] Parâmetro obrigatório ausente: {item}")

        # se tiver self.transitions_settings.audio setar audio_settings
        if self.transitions_settings.get("audio"):
            self.audio_settings = self.transitions_settings["audio"]

        if self.transitions_settings.get("visual"):
            self.visual_settings = self.transitions_settings["visual"]

        if self.transitions_settings.get("type"):
            self.transition_type = self.transitions_settings["type"]        

    def _get_clip_audio(self):
        """
        Retorna o áudio do clipe, se disponível.
        """
        if not self.audio_settings:
            return None

        type = self.audio_settings.get("type") # 'directory' ou 'file'
        source = self.audio_settings.get("source") # diretório ou arquivo
        volume = self.audio_settings.get("volume", 1.0)

        if type == "directory":
            # validar source
            if not source or not os.path.exists(source):
                return None
            
            files = [f for f in os.listdir(source) if f.endswith(('.mp3', '.wav'))]
            if not files:
                return None
            
            audio_path = os.path.join(source, random.choice(files))
        elif type == "file":
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


    def apply_transitions(self):
        if not self.clips:
            return None
        if len(self.clips) == 1:
            return self.clips[0]

        # Define os parâmetros base para a transição
        params = {
            "resolution_output": self.resolution,
            **self.visual_settings,
        }

        clip_1 = self.clips[0]
        clip_2 = self. clips[1]
        
        params["clip_1"] = clip_1
        params["clip_2"] = clip_2

        # audio
        audio_clip = self._get_clip_audio()
        if audio_clip: 
            params["audio_file_clip"] = audio_clip
        # print debug params
        print(f"[TransitionEngine] Params: {params}")

        # Seleciona a classe de transição
        transition_map = {
            "slide": Slide,
            "zoom":  Zoom,
            "random":  random.choice([Slide, Zoom])
        }

        TransitionClass = transition_map.get(self.transition_type)
        if not TransitionClass: 
            raise ValueError(f"[TransitionEngine] Tipo de transição desconhecido: {self.transition_type}")

        transition_instance = TransitionClass(params)
        return transition_instance.process()
