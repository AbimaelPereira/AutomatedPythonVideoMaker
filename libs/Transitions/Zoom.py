import math
from moviepy.editor import *
from TransitionUtils import TransitionUtils


class Zoom:
    def __init__(self, params=None):
        defaults = {
            "resolution_output": (720, 1280),
            "clip_1": None,
            "clip_2": None,
            "audio_file_clip": None,

            "zoom_type": "IN",          # IN | OUT
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

    # --------------------------------
    # ESCALA CLIP 1 (ZOOM DISPARO)
    # --------------------------------
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
            if self.zoom_type == "IN"
            else 1.0 - (1.0 - 1 / self.zoom_max_scale) * progress
        )

    # --------------------------------
    # ESCALA CLIP 2 (RETORNO + SHAKE)
    # --------------------------------
    def _scale_clip2(self, t):
        d = self.duration
        p = self.physics

        start_scale = self.zoom_max_scale if self.zoom_type == "IN" else 1 / self.zoom_max_scale

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
            return 1.0 + (-shake if self.zoom_type == "IN" else shake)

        return 1.0

    # --------------------------------
    # PROCESS
    # --------------------------------
    def process(self):
        start_c2 = self.clip_1.duration
        total_duration = self.clip_1.duration + self.clip_2.duration

        frame = self.clip_1.get_frame(self.clip_1.duration - 0.1)

        backdrop = TransitionUtils.create_blurred_backdrop(
            frame, self.width, self.height,
            self.blur_radius, total_duration
        )

        c1 = (
            self.clip_1.resize((self.width, self.height))
            .resize(self._scale_clip1)
            .set_position("center")
        )

        c2 = (
            self.clip_2.resize((self.width, self.height))
            .resize(self._scale_clip2)
            .set_position("center")
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
