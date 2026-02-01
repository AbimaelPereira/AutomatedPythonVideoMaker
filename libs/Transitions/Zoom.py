import math
import random
from moviepy.editor import *
from libs.Transitions.TransitionUtils import TransitionUtils


class Zoom:
    """
    Versão OTIMIZADA do Zoom - SEM BLUR para máxima performance.
    
    Aplica transição de zoom em um único clip:
    - Início: Zoom Out (começa grande, diminui até normal) + Shake
    - Final: Impulse + Zoom In (normal até grande)
    
    Esta versão é MUITO mais rápida pois não aplica blur.
    """
    def __init__(self, params=None):
        defaults = {
            "resolution_output": (720, 1280),
            "clip": None,
            "audio_file_clip": None,

            "zoom_max_scale": 15.0,

            "duration": {
                "zoom_out": 0.2,
                "shake_out": 0.4,
                "impulse_in": 0.4,
                "zoom_in": 0.2
            },

            "physics": {
                "shake_amplitude": 0.12,
                "shake_frequency": 10,
                "shake_decay": 10,
                "impulse_scale": 0.1
            }
        }

        if params:
            for k, v in params.items():
                if k in defaults and isinstance(defaults[k], dict):
                    defaults[k].update(v)
                else:
                    defaults[k] = v

        for k, v in defaults.items():
            setattr(self, k, v)

        self.width, self.height = self.resolution_output

    def _scale_function(self, t):
        """Calcula o scale para cada momento do clip."""
        d = self.duration
        p = self.physics
        clip_dur = self.clip.duration

        # INÍCIO: Zoom Out
        if t < d["zoom_out"]:
            progress = TransitionUtils.ease_out_cubic(t / d["zoom_out"])
            return self.zoom_max_scale - (self.zoom_max_scale - 1.0) * progress

        # Shake Out
        elif t < d["zoom_out"] + d["shake_out"]:
            local_t = t - d["zoom_out"]
            shake = TransitionUtils.damped_shake(
                local_t,
                p["shake_amplitude"],
                p["shake_frequency"],
                p["shake_decay"],
                d["shake_out"]
            )
            return 1.0 - shake

        # MEIO: Normal
        end_transition_start = clip_dur - (d["impulse_in"] + d["zoom_in"])
        if t < end_transition_start:
            return 1.0

        local_t = t - end_transition_start

        # Impulse In
        if local_t < d["impulse_in"]:
            progress = local_t / d["impulse_in"]
            factor = 1.0 - p["impulse_scale"]
            return 1.0 + (factor - 1.0) * math.sin(progress * math.pi / 2)

        # FINAL: Zoom In
        zoom_in_local = local_t - d["impulse_in"]
        progress = TransitionUtils.ease_in_cubic(zoom_in_local / d["zoom_in"])
        return 1.0 + (self.zoom_max_scale - 1.0) * progress

    def process(self):
        """Processa o clip - VERSÃO RÁPIDA sem blur."""
        if not self.clip:
            raise ValueError("[ZoomFast] Clip não fornecido")

        clip_dur = self.clip.duration

        # Aplicar apenas scale (SEM blur = muito mais rápido)
        clip_scaled = self.clip.resize(width=self.width).resize(self._scale_function).set_position("center")

        # Composição final
        final_clip = CompositeVideoClip([clip_scaled], size=(self.width, self.height)).set_duration(clip_dur)

        # ÁUDIO
        audio_list = [final_clip.audio] if final_clip.audio else []

        if self.audio_file_clip:
            sfx = self.audio_file_clip.set_start(0)
            audio_list.append(sfx)

        if audio_list:
            final_clip = final_clip.set_audio(CompositeAudioClip(audio_list))

        return final_clip
