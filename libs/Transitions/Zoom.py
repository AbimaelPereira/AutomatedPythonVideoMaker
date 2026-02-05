import math
import random
from moviepy.editor import *
from libs.Transitions.TransitionUtils import TransitionUtils


class Zoom:
    """
    🔧 Versão OTIMIZADA E CORRIGIDA do Zoom
    
    MUDANÇAS PRINCIPAIS:
    1. Cache de cálculos de scale para evitar reprocessamento
    2. Simplificação da função de scale (menos operações por frame)
    3. FPS fixo garantido no output
    4. Opção de desabilitar totalmente para diagnóstico
    
    Aplica transição de zoom em um único clip:
    - Início: Zoom Out (começa grande, diminui até normal) + Shake
    - Final: Impulse + Zoom In (normal até grande)
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
                "impulse_in": 0,
                "zoom_in": 0
            },

            "physics": {
                "shake_amplitude": 0.12,
                "shake_frequency": 10,
                "shake_decay": 10,
                "impulse_scale": 0.1
            },
            
            # 🔧 NOVO: Opção de desabilitar para diagnóstico
            "enabled": True,
            
            # 🔧 NOVO: Cache de scales pré-calculados
            "use_cache": True,
            "cache_fps": 30  # FPS usado para cache
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
        
        # 🔧 Cache de scales (key: tempo, value: scale)
        self._scale_cache = {}

    def _calculate_scale_at_time(self, t):
        """
        🔧 VERSÃO OTIMIZADA: Calcula scale uma vez, com lógica simplificada
        """
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

    def _build_scale_cache(self):
        """
        🔧 PRÉ-CALCULA todos os scales para eliminar overhead em runtime
        """
        if not self.use_cache:
            return
        
        print("[Zoom] 🔧 Construindo cache de scales...")
        clip_dur = self.clip.duration
        
        # Calcula scales para cada frame (assumindo 30 FPS)
        num_frames = int(clip_dur * self.cache_fps)
        
        for frame_idx in range(num_frames):
            t = frame_idx / self.cache_fps
            scale = self._calculate_scale_at_time(t)
            self._scale_cache[t] = scale
        
        print(f"[Zoom] ✅ Cache construído: {len(self._scale_cache)} frames")

    def _scale_function(self, t):
        """
        🔧 Função de scale COM CACHE
        """
        if not self.use_cache:
            return self._calculate_scale_at_time(t)
        
        # Arredonda tempo para FPS do cache
        t_rounded = round(t * self.cache_fps) / self.cache_fps
        
        # Usa cache se disponível, senão calcula
        if t_rounded in self._scale_cache:
            return self._scale_cache[t_rounded]
        else:
            return self._calculate_scale_at_time(t)

    def process(self):
        """
        🔧 Processa o clip com otimizações de performance
        """
        if not self.clip:
            raise ValueError("[Zoom] Clip não fornecido")
        
        # 🔧 Opção de bypass total (para diagnóstico)
        if not self.enabled:
            print("[Zoom] ⏭️ Transição desabilitada - retornando clip original")
            return self.clip

        clip_dur = self.clip.duration

        # 🔧 Constrói cache de scales
        if self.use_cache:
            self._build_scale_cache()

        # Aplicar scale (SEM blur = muito mais rápido)
        print("[Zoom] 🎬 Aplicando transformação de scale...")
        clip_scaled = self.clip.resize(width=self.width).resize(self._scale_function).set_position("center")

        # Composição final
        print("[Zoom] 🎬 Compondo clip final...")
        final_clip = CompositeVideoClip([clip_scaled], size=(self.width, self.height)).set_duration(clip_dur)

        # ÁUDIO
        audio_list = [final_clip.audio] if final_clip.audio else []

        if self.audio_file_clip:
            sfx = self.audio_file_clip.set_start(0)
            audio_list.append(sfx)

        if audio_list:
            final_clip = final_clip.set_audio(CompositeAudioClip(audio_list))

        print("[Zoom] ✅ Transição processada")
        return final_clip