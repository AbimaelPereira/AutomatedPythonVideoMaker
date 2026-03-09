import math
import numpy as np
from moviepy.editor import (
    ImageSequenceClip,
    CompositeVideoClip,
    CompositeAudioClip,
)
from libs.Transitions.TransitionUtils import TransitionUtils


class Zoom:
    """
    Transição de Zoom — versão híbrida (melhor das duas abordagens).

    v1 (pré-renderização + PIL LANCZOS):
      ✅ Render FFmpeg rápido (frames já prontos)
      ❌ Preparação lenta (PIL LANCZOS por frame)

    v2 (fl() + bilinear NumPy):
      ✅ Preparação instantânea
      ❌ Render FFmpeg lento (NumPy bloqueando o pipe frame a frame)

    v3 (esta) — híbrida:
      ✅ Preparação rápida  → bilinear NumPy (sem PIL)
      ✅ Render FFmpeg rápido → ImageSequenceClip (frames prontos)
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
                "zoom_in": 0,
            },

            "physics": {
                "shake_amplitude": 0.12,
                "shake_frequency": 10,
                "shake_decay": 10,
                "impulse_scale": 0.1,
            },

            "enabled": True,
            "fps": 30,
        }

        if params:
            for k, v in params.items():
                if k in defaults and isinstance(defaults[k], dict) and isinstance(v, dict):
                    defaults[k].update(v)
                else:
                    defaults[k] = v

        for k, v in defaults.items():
            setattr(self, k, v)

        self.width, self.height = self.resolution_output

    # ------------------------------------------------------------------
    # CÁLCULO DE SCALE (idêntico ao original)
    # ------------------------------------------------------------------

    def _scale_at(self, t: float, clip_dur: float) -> float:
        d = self.duration
        p = self.physics

        if t < d["zoom_out"]:
            progress = TransitionUtils.ease_out_cubic(t / d["zoom_out"])
            return self.zoom_max_scale - (self.zoom_max_scale - 1.0) * progress

        if t < d["zoom_out"] + d["shake_out"]:
            local_t = t - d["zoom_out"]
            shake = TransitionUtils.damped_shake(
                local_t,
                p["shake_amplitude"],
                p["shake_frequency"],
                p["shake_decay"],
                d["shake_out"],
            )
            return 1.0 - shake

        end_transition_start = clip_dur - (d["impulse_in"] + d["zoom_in"])
        if t < end_transition_start:
            return 1.0

        local_t = t - end_transition_start

        if d["impulse_in"] > 0 and local_t < d["impulse_in"]:
            progress = local_t / d["impulse_in"]
            factor = 1.0 - p["impulse_scale"]
            return 1.0 + (factor - 1.0) * math.sin(progress * math.pi / 2)

        if d["zoom_in"] > 0:
            zoom_in_local = local_t - d["impulse_in"]
            progress = TransitionUtils.ease_in_cubic(zoom_in_local / d["zoom_in"])
            return 1.0 + (self.zoom_max_scale - 1.0) * progress

        return 1.0

    # ------------------------------------------------------------------
    # ZOOM BILINEAR NUMPY — sem PIL, sem subprocess
    # ------------------------------------------------------------------

    def _zoom_frame(self, frame: np.ndarray, scale: float,
                    grid_y: np.ndarray, grid_x: np.ndarray) -> np.ndarray:
        """
        Aplica zoom num frame via interpolação bilinear NumPy puro.
        Recebe grids pré-calculados para não recriar meshgrid por frame.
        """
        if abs(scale - 1.0) < 0.001:
            return frame

        h, w = frame.shape[:2]
        half_h = (h - 1) / 2.0
        half_w = (w - 1) / 2.0

        src_y = (grid_y - 0.5) / scale * (h - 1) + half_h
        src_x = (grid_x - 0.5) / scale * (w - 1) + half_w

        valid = (src_y >= 0) & (src_y <= h - 1) & (src_x >= 0) & (src_x <= w - 1)

        src_y_c = np.clip(src_y, 0, h - 1)
        src_x_c = np.clip(src_x, 0, w - 1)

        y0 = src_y_c.astype(np.int32)
        x0 = src_x_c.astype(np.int32)
        y1 = np.minimum(y0 + 1, h - 1)
        x1 = np.minimum(x0 + 1, w - 1)

        fy = (src_y_c - y0).astype(np.float32)[:, :, np.newaxis]
        fx = (src_x_c - x0).astype(np.float32)[:, :, np.newaxis]

        f00 = frame[y0, x0].astype(np.float32)
        f01 = frame[y0, x1].astype(np.float32)
        f10 = frame[y1, x0].astype(np.float32)
        f11 = frame[y1, x1].astype(np.float32)

        result = (
            f00 * (1 - fy) * (1 - fx) +
            f01 * (1 - fy) * fx +
            f10 * fy * (1 - fx) +
            f11 * fy * fx
        )

        result = np.clip(result, 0, 255).astype(np.uint8)
        result[~valid] = 0

        return result

    # ------------------------------------------------------------------
    # PRÉ-RENDERIZAÇÃO — todos os frames antes do FFmpeg
    # ------------------------------------------------------------------

    def _prerender_frames(self) -> list:
        """
        Extrai e processa todos os frames ANTES de passar pro FFmpeg.

        - Pré-calcula grids de coordenadas uma única vez (não por frame)
        - Usa bilinear NumPy (sem PIL) para o zoom
        - Retorna lista de arrays prontos para ImageSequenceClip

        O FFmpeg recebe frames já processados → não faz nenhum cálculo
        em runtime → render rápido.
        """
        clip = self.clip
        clip_dur = clip.duration
        fps = self.fps
        total_frames = int(clip_dur * fps)

        h, w = self.height, self.width

        # Grids pré-calculados uma única vez para todos os frames
        grid_y, grid_x = np.mgrid[0:h, 0:w].astype(np.float32)
        grid_y /= (h - 1)
        grid_x /= (w - 1)

        # Pré-calcula todos os scales de uma vez (sem loop pesado)
        times = np.linspace(0, clip_dur - 1 / fps, total_frames)
        scales = [self._scale_at(float(t), clip_dur) for t in times]

        print(f"[Zoom] 🔧 Pré-renderizando {total_frames} frames (bilinear NumPy)...")

        frames = []
        for i, (t, scale) in enumerate(zip(times, scales)):
            raw = clip.get_frame(float(t))

            # force_rgb: garante 3 canais
            if raw.ndim == 2:
                raw = np.dstack((raw, raw, raw))

            frames.append(self._zoom_frame(raw, scale, grid_y, grid_x))

            if (i + 1) % 30 == 0 or i == total_frames - 1:
                pct = int((i + 1) / total_frames * 100)
                print(f"[Zoom]   {pct}% ({i + 1}/{total_frames})")

        print(f"[Zoom] ✅ {len(frames)} frames prontos")
        return frames

    # ------------------------------------------------------------------
    # PROCESSO PRINCIPAL
    # ------------------------------------------------------------------

    def process(self):
        if not self.clip:
            raise ValueError("[Zoom] Clip não fornecido")

        if not self.enabled:
            print("[Zoom] ⏭️ Transição desabilitada — retornando clip original")
            return self.clip

        clip_dur = self.clip.duration

        # 1. Pré-renderiza todos os frames (bilinear NumPy — rápido)
        frames = self._prerender_frames()

        # 2. ImageSequenceClip — FFmpeg só empacota, não calcula nada
        print("[Zoom] 🎬 Montando ImageSequenceClip...")
        final_clip = ImageSequenceClip(frames, fps=self.fps).set_duration(clip_dur)

        # 3. Áudio
        audio_list = []
        if self.clip.audio is not None:
            audio_list.append(self.clip.audio)
        if self.audio_file_clip is not None:
            audio_list.append(self.audio_file_clip.set_start(0))
        if audio_list:
            final_clip = final_clip.set_audio(CompositeAudioClip(audio_list))

        print("[Zoom] ✅ Transição processada")
        return final_clip
