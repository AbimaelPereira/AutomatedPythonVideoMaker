import math
import random
from moviepy.editor import *
from libs.Transitions.TransitionUtils import TransitionUtils


class Zoom:
    def __init__(self, params=None):
        defaults = {
            "resolution_output": (720, 1280),
            "clip_1": None,
            "clip_2": None,
            "audio_file_clip": None,

            "zoom_type": "in",  # in | out | random
            "zoom_max_scale": 8.0,
            "blur_radius": 30,

            "duration": {
                "impulse": 0.4,
                "zoom": 0.5,
                "return": 0.4,
                "shake": 0.4
            },

            "physics": {
                "impulse_scale": 0.1,
                "shake_amplitude": 0.12,
                "shake_frequency": 10,
                "shake_decay": 10
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
        
        # Aplicar random no zoom_type se necessário
        self.zoom_type = self._get_zoom_type()

    def _get_zoom_type(self):
        """Retorna zoom_type, ou aleatório se 'random'."""
        if self.zoom_type.lower() == "random":
            return random.choice(["in", "out"])
        return self.zoom_type.lower()

    def _scale_clip1(self, t):
        d = self.duration
        p = self.physics

        start = self.clip_1.duration - (d["impulse"] + d["zoom"])

        if t < start:
            return 1.0

        local = t - start

        if local < d["impulse"]:
            progress = local / d["impulse"]
            factor = 1.0 - p["impulse_scale"]
            return 1.0 + (factor - 1.0) * math.sin(progress * math.pi / 2)

        progress = (local - d["impulse"]) / d["zoom"]
        progress = TransitionUtils.ease_in_cubic(progress)

        return (
            1.0 + (self.zoom_max_scale - 1.0) * progress
            if self.zoom_type == "in"
            else 1.0 - (1.0 - 1 / self.zoom_max_scale) * progress
        )

    def _scale_clip2(self, t):
        d = self.duration
        p = self.physics

        start_scale = self.zoom_max_scale if self.zoom_type == "in" else 1 / self.zoom_max_scale

        if t < d["return"]:
            progress = TransitionUtils.ease_out_cubic(t / d["return"])
            return start_scale + (1.0 - start_scale) * progress

        elif t < d["return"] + d["shake"]:
            dt = t - d["return"]
            shake = TransitionUtils.damped_shake(
                dt,
                p["shake_amplitude"],
                p["shake_frequency"],
                p["shake_decay"],
                d["shake"]
            )
            return 1.0 + (-shake if self.zoom_type == "in" else shake)

        return 1.0

    def process(self):
        d = self.duration
        c1_dur, c2_dur = self.clip_1.duration, self.clip_2.duration
        
        # Tempos visuais
        t_trans1_start = c1_dur - d["impulse"] - d["zoom"]
        t_trans1_dur = d["impulse"] + d["zoom"]
        t_trans2_dur = d["return"] + d["shake"]
        
        # TEMPO PARA O AUDIO (Começa apenas no ZOOM, ignorando o IMPULSE)
        t_audio_start = c1_dur - d["zoom"]

        frame = self.clip_1.get_frame(c1_dur - 0.1)

        # ==============================================================================
        # VIDEO (Visual permanece igual)
        # ==============================================================================
        c1_z = self.clip_1.resize(width=self.width).resize(self._scale_clip1).set_position("center")
        bg1 = TransitionUtils.create_blurred_backdrop(frame, self.width, self.height, self.blur_radius, t_trans1_dur).set_start(t_trans1_start)
        clip_1_ready = CompositeVideoClip([bg1, c1_z], size=(self.width, self.height)).set_duration(c1_dur)

        c2_z = self.clip_2.resize(width=self.width).resize(self._scale_clip2).set_position("center")
        bg2 = TransitionUtils.create_blurred_backdrop(frame, self.width, self.height, self.blur_radius, t_trans2_dur).set_start(0)
        clip_2_ready = CompositeVideoClip([bg2, c2_z], size=(self.width, self.height)).set_duration(c2_dur)

        # ==============================================================================
        # CORREÇÃO DE TEMPO DO ÁUDIO
        # ==============================================================================
        audio_c1_list = [clip_1_ready.audio] if clip_1_ready.audio else []
        audio_c2_list = [clip_2_ready.audio] if clip_2_ready.audio else []

        if self.audio_file_clip:
            # 1. Adiciona SFX ao Clip 1 no momento do Zoom rápido
            sfx_part1 = self.audio_file_clip.set_start(t_audio_start)
            audio_c1_list.append(sfx_part1)
            
            # 2. Cálculo de sobra
            # O tempo disponível no clip 1 agora é apenas a duração do zoom
            time_in_c1 = d["zoom"]
            
            if self.audio_file_clip.duration > time_in_c1:
                # Adiciona o restante ao Clip 2
                sfx_part2 = self.audio_file_clip.subclip(time_in_c1).set_start(0)
                audio_c2_list.append(sfx_part2)

        if audio_c1_list:
            clip_1_ready.audio = CompositeAudioClip(audio_c1_list)
        if audio_c2_list:
            clip_2_ready.audio = CompositeAudioClip(audio_c2_list)

        return clip_1_ready, clip_2_ready