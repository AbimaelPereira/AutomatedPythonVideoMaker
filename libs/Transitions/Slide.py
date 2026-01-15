import math
from moviepy.editor import *
from TransitionUtils import TransitionUtils


class Slide:
    def __init__(self, params=None):
        defaults = {
            "resolution_output": (720, 1280),
            "clip_1": None,
            "clip_2": None,
            "audio_file_clip": None,

            "direction": "left",  # left | right | bottom | top
            "blur_radius": 30,

            "duration": {
                "impulse": 0.3,
                "slide": 0.5,
                "shake": 0.4
            },

            "physics": {
                "impulse_distance": 50,      # Distância do recuo inicial em pixels
                "shake_amplitude": 30,       # Amplitude do balanço final em pixels
                "shake_frequency": 8,        # Frequência do balanço
                "shake_decay": 8             # Decaimento do balanço
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

    def _get_direction_vectors(self):
        """Retorna os vetores de direção baseados na configuração."""
        if self.direction == "left":
            return (1, 0)  # Move no eixo X
        elif self.direction == "right":
            return (-1, 0)
        elif self.direction == "bottom":
            return (0, -1)
        elif self.direction == "top":
            return (0, 1)
        return (1, 0)

    # --------------------------------
    # POSIÇÃO CLIP 1 (IMPULSO + SLIDE)
    # --------------------------------
    def _pos_clip1(self, t):
        d = self.duration
        p = self.physics
        vx, vy = self._get_direction_vectors()

        # O Clip 1 começa a sair no final de sua própria duração
        start_transition = self.clip_1.duration - (d["impulse"] + d["slide"])

        if t < start_transition:
            return ("center", "center")

        local = t - start_transition

        # Estágio 1: Impulso (Recuo suave)
        if local < d["impulse"]:
            progress = local / d["impulse"]
            offset = p["impulse_distance"] * math.sin(progress * math.pi)
            return (
                self.width // 2 - (self.width // 2) + (offset * -vx),
                self.height // 2 - (self.height // 2) + (offset * -vy)
            )

        # Estágio 2: Slide (Saída do Clip 1)
        progress = (local - d["impulse"]) / d["slide"]
        progress = TransitionUtils.ease_in_cubic(progress)
        
        return (
            -progress * self.width * vx,
            -progress * self.height * vy
        )

    # --------------------------------
    # POSIÇÃO CLIP 2 (SLIDE + SHAKE)
    # --------------------------------
    def _pos_clip2(self, t):
        d = self.duration
        p = self.physics
        vx, vy = self._get_direction_vectors()

        # Estágio 2: Slide (Entrada do Clip 2)
        if t < d["slide"]:
            progress = TransitionUtils.ease_out_cubic(t / d["slide"])
            return (
                (1.0 - progress) * self.width * vx,
                (1.0 - progress) * self.height * vy
            )

        # Estágio 3: Balançar até estabilizar
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

    # --------------------------------
    # PROCESS
    # --------------------------------
    def process(self):
        d = self.duration
        # O Clip 2 começa a entrar exatamente quando o Clip 1 começa o estágio de 'slide'
        # Isso cria o efeito 'grudado' (um empurrando o outro)
        overlap_duration = d["slide"]
        start_c2 = self.clip_1.duration - overlap_duration
        
        # A duração total é reduzida pela sobreposição para não haver 'buracos' ou tempo extra
        total_duration = self.clip_1.duration + self.clip_2.duration - overlap_duration

        frame = self.clip_1.get_frame(self.clip_1.duration - 0.1)
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
            # O áudio do clip 2 também deve respeitar o novo ponto de início
            audio_layers.append(c2.audio.set_start(start_c2))
        if self.audio_file_clip:
            # O efeito sonoro geralmente toca no início da transição física (slide)
            audio_layers.append(self.audio_file_clip.set_start(start_c2))

        final = CompositeVideoClip(
            [backdrop, c1, c2],
            size=(self.width, self.height)
        ).set_duration(total_duration)

        if audio_layers:
            final.audio = CompositeAudioClip(audio_layers)

        return final