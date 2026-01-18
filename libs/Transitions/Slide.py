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
                "shake": 0.9
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
        self.direction = self._get_direction()

    def _get_direction(self):
        if self.direction == "random":
            directions = ["left", "right", "bottom", "top"]
            return random.choice(directions)
        return self.direction

    def _get_direction_vectors(self):
        directions = {"left": (1, 0), "right": (-1, 0), "bottom": (0, -1), "top": (0, 1)}
        return directions.get(self.direction, (1, 0))

    def _pos_clip1(self, t):
        """Movimento do Clip 1: Impulso + Saída."""
        d, p = self.duration, self.physics
        vx, vy = self._get_direction_vectors()
        start_transition = self.clip_1.duration - (d["impulse"] + d["slide"])

        if t < start_transition:
            return (0, 0)

        local = t - start_transition
        if local < d["impulse"]:
            # Fase 1: Wiggle (Impulso)
            progress = local / d["impulse"]
            offset = p["impulse_distance"] * math.sin(progress * math.pi)
            return (offset * -vx, offset * -vy)

        # Fase 2: Saída (Slide Out)
        progress = TransitionUtils.ease_in_cubic((local - d["impulse"]) / d["slide"])
        return (-progress * self.width * vx, -progress * self.height * vy)

    def _pos_clip2_entrance(self, t):
        """Movimento do Clip 2 (Parte 1): Entrando junto com o Clip 1."""
        d = self.duration
        vx, vy = self._get_direction_vectors()
        # Sincronia perfeita: usa a mesma curva ease_in_cubic
        progress = TransitionUtils.ease_in_cubic(t / d["slide"])
        return ((1.0 - progress) * self.width * vx, (1.0 - progress) * self.height * vy)

    def _pos_clip2_shake(self, t):
        """Movimento do Clip 2 (Parte 2): Balanço (Shake) ao chegar."""
        d, p = self.duration, self.physics
        vx, vy = self._get_direction_vectors()

        # Como reiniciamos o clip, 't' começa em 0.0 aqui
        if t < d["shake"]:
            shake = TransitionUtils.damped_shake(
                t, 
                p["shake_amplitude"], 
                p["shake_frequency"], 
                p["shake_decay"], 
                d["shake"]
            )
            return (shake * vx, shake * vy)
        return (0, 0)

    def process(self):
        d = self.duration
        c1_dur = self.clip_1.duration
        c2_dur = self.clip_2.duration
        
        # Tempos chave da animação visual
        t_trans_start = c1_dur - (d["impulse"] + d["slide"]) # Começo do Impulso (visual)
        t_slide_start = c1_dur - d["slide"]                 # Começo do Slide (visual)
        
        # Frame de referência para o backdrop
        frame_ref = self.clip_1.get_frame(max(0, c1_dur - 0.1))

        # ==============================================================================
        # VIDEO (Visual permanece igual)
        # ==============================================================================
        c1_anim = self.clip_1.resize((self.width, self.height)).set_position(self._pos_clip1)
        
        c2_part1 = (self.clip_2.subclip(0, d["slide"])
                    .resize((self.width, self.height))
                    .set_position(self._pos_clip2_entrance)
                    .set_start(t_slide_start))
        
        bg1_dur = d["impulse"] + d["slide"]
        bg1 = TransitionUtils.create_blurred_backdrop(frame_ref, self.width, self.height, self.blur_radius, bg1_dur).set_start(t_trans_start)

        clip_1_ready = CompositeVideoClip([bg1, c1_anim, c2_part1], size=(self.width, self.height)).set_duration(c1_dur)

        # Parte 2 (Clip 2)
        duration_remaining = c2_dur - d["slide"]
        c2_part2 = (self.clip_2.resize((self.width, self.height))
                    .set_duration(duration_remaining)
                    .set_position(self._pos_clip2_shake))
        
        if self.clip_2.audio:
             c2_part2.audio = self.clip_2.audio.subclip(d["slide"])

        bg2 = TransitionUtils.create_blurred_backdrop(frame_ref, self.width, self.height, self.blur_radius, d["shake"]).set_start(0)
        clip_2_ready = CompositeVideoClip([bg2, c2_part2], size=(self.width, self.height)).set_duration(duration_remaining)

        # ==============================================================================
        # CORREÇÃO DE TEMPO DO ÁUDIO
        # ==============================================================================
        audio_c1_list = [clip_1_ready.audio] if clip_1_ready.audio else []
        audio_c2_list = [clip_2_ready.audio] if clip_2_ready.audio else []

        if self.audio_file_clip:
            # NOVO TEMPO DE INICIO: Ignora o 'impulse', começa no 'slide'
            # Isso é exatamente t_slide_start calculado acima
            t_audio_start = t_slide_start
            
            # 1. Adiciona o SFX ao Clip 1 no momento exato do Slide
            sfx_part1 = self.audio_file_clip.set_start(t_audio_start)
            audio_c1_list.append(sfx_part1)
            
            # 2. Cálculo de sobra (Bridging)
            # O tempo disponível agora é APENAS o tempo do slide (d["slide"])
            # Pois o áudio começou mais tarde, mais perto do fim do clip 1
            time_in_c1 = d["slide"]
            
            if self.audio_file_clip.duration > time_in_c1:
                # O que sobrar vai para o clip 2
                sfx_part2 = self.audio_file_clip.subclip(time_in_c1).set_start(0)
                audio_c2_list.append(sfx_part2)

        if audio_c1_list:
            clip_1_ready.audio = CompositeAudioClip(audio_c1_list)
        if audio_c2_list:
            clip_2_ready.audio = CompositeAudioClip(audio_c2_list)

        return clip_1_ready, clip_2_ready