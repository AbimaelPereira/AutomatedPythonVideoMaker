import math
import random
from moviepy.editor import *
from libs.Transitions.TransitionUtils import TransitionUtils


class Slide:
    def __init__(self, params=None):
        defaults = {
            "resolution_output": (720, 1280),
            "clip_1": None,
            "clip_2": None,
            "audio_file_clip": None,

            "direction": "left",  # left | right | bottom | top | random
            "blur_radius": 30,

            "duration": {
                "impulse": 0.3,
                "slide": 0.5,
                "shake": 0.4
            },

            "physics": {
                "impulse_distance": 50,
                "shake_amplitude": 30,
                "shake_frequency": 8,
                "shake_decay": 8
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
        
        # Aplicar random na direção se necessário
        self.direction = self._get_direction()

    def _get_direction(self):
        """Retorna direção, ou aleatória se 'random'."""
        if self.direction == "random":
            directions = ["left", "right", "bottom", "top"]
            return random.choice(directions)
        return self.direction

    def _get_direction_vectors(self):
        """Retorna os vetores de direção baseados na configuração."""
        if self.direction == "left":
            return (1, 0)
        elif self.direction == "right":
            return (-1, 0)
        elif self.direction == "bottom":
            return (0, -1)
        elif self.direction == "top":
            return (0, 1)
        return (1, 0)

    def _pos_clip1(self, t):
        d = self.duration
        p = self.physics
        vx, vy = self._get_direction_vectors()

        start_transition = self.clip_1.duration - (d["impulse"] + d["slide"])

        if t < start_transition:
            return ("center", "center")

        local = t - start_transition

        if local < d["impulse"]:
            progress = local / d["impulse"]
            offset = p["impulse_distance"] * math.sin(progress * math.pi)
            return (
                self.width // 2 - (self.width // 2) + (offset * -vx),
                self.height // 2 - (self.height // 2) + (offset * -vy)
            )

        progress = (local - d["impulse"]) / d["slide"]
        progress = TransitionUtils.ease_in_cubic(progress)
        
        return (
            -progress * self.width * vx,
            -progress * self.height * vy
        )

    def _pos_clip2(self, t):
        d = self.duration
        p = self.physics
        vx, vy = self._get_direction_vectors()

        if t < d["slide"]:
            progress = TransitionUtils.ease_out_cubic(t / d["slide"])
            return (
                (1.0 - progress) * self.width * vx,
                (1.0 - progress) * self.height * vy
            )

        elif t < d["slide"] + d["shake"]:
            dt = t - d["slide"]
            shake = TransitionUtils.damped_shake(
                dt,
                p["shake_amplitude"],
                p["shake_frequency"],
                p["shake_decay"],
                d["shake"]
            )
            return (
                shake * vx,
                shake * vy
            )

        return (0, 0)

    def process(self):
        d = self.duration
        overlap_duration = d["slide"]
        start_c2 = self.clip_1.duration - overlap_duration
        
        total_duration = self.clip_1.duration + self.clip_2.duration - overlap_duration

        # Captura o frame de forma segura
        t_frame = max(0, self.clip_1.duration - 0.1)
        frame = self.clip_1.get_frame(t_frame)

        backdrop = TransitionUtils.create_blurred_backdrop(
            frame, self.width, self.height,
            self.blur_radius, total_duration
        )

        c1 = (
            self.clip_1.resize((self.width, self.height))
            .set_position(self._pos_clip1)
        )

        c2 = (
            self.clip_2.resize((self.width, self.height))
            .set_position(self._pos_clip2)
            .set_start(start_c2)
        )

        audio_layers = []
        if c1.audio:
            audio_layers.append(c1.audio)
        if c2.audio:
            audio_layers.append(c2.audio.set_start(start_c2))
        if self.audio_file_clip:
            audio_layers.append(self.audio_file_clip.set_start(start_c2))

        final = CompositeVideoClip(
            [backdrop, c1, c2],
            size=(self.width, self.height)
        ).set_duration(total_duration)

        if audio_layers:
            final.audio = CompositeAudioClip(audio_layers)

        return final