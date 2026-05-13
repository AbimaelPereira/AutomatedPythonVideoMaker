import numpy as np
from moviepy.editor import (
    ImageSequenceClip,
    CompositeAudioClip,
)


class Fade:
    """
    Transição de Fade — aplica fade in no início e fade out no final do clip.

    Estratégia de pré-renderização (mesma arquitetura do Zoom v3):
      - Calcula o alpha de cada frame via NumPy (sem loop Python puro)
      - Pré-renderiza todos os frames e entrega ao FFmpeg via ImageSequenceClip
      - FFmpeg apenas empacota → render rápido

    Parâmetros configuráveis via JSON:
      "transitions": {
        "enabled": true,
        "type": "fade",
        "visual": {
          "fade_in_duration":  0.5,   // segundos de fade in  (default 0.5)
          "fade_out_duration": 0.5,   // segundos de fade out (default 0.5)
          "color": [0, 0, 0]          // cor do fade (default preto)
        }
      }
    """

    def __init__(self, params=None):
        defaults = {
            "resolution_output": (1080, 1920),
            "clip": None,
            "audio_file_clip": None,

            # Duração dos fades em segundos
            "fade_in_duration":  0.5,
            "fade_out_duration": 0.5,

            # Cor do fade (RGB 0-255)
            "color": [0, 0, 0],

            "enabled": True,
            "fps": 30,
        }

        if params:
            for k, v in params.items():
                defaults[k] = v

        for k, v in defaults.items():
            setattr(self, k, v)

        self.width, self.height = self.resolution_output

        # Garante que color é uma lista/tupla de 3 ints
        if isinstance(self.color, str):
            # Aceita hex "#000000"
            hex_val = self.color.lstrip('#')
            if len(hex_val) == 6:
                self.color = [int(hex_val[i:i+2], 16) for i in (0, 2, 4)]
            else:
                self.color = [0, 0, 0]

    # ------------------------------------------------------------------
    # CÁLCULO DE ALPHA POR FRAME — vetorizado
    # ------------------------------------------------------------------

    def _compute_alphas(self, total_frames: int, clip_dur: float) -> np.ndarray:
        """
        Retorna array de shape (total_frames,) com o alpha do conteúdo em cada frame.
        alpha=1.0 → frame original visível
        alpha=0.0 → cor sólida (fade completo)
        """
        times = np.linspace(0, clip_dur - 1 / self.fps, total_frames)
        alphas = np.ones(total_frames, dtype=np.float32)

        fade_in_frames  = int(self.fade_in_duration  * self.fps)
        fade_out_frames = int(self.fade_out_duration * self.fps)

        # Fade in: alpha vai de 0 → 1 nos primeiros fade_in_frames
        if fade_in_frames > 0:
            fi_end = min(fade_in_frames, total_frames)
            alphas[:fi_end] = np.linspace(0.0, 1.0, fi_end)

        # Fade out: alpha vai de 1 → 0 nos últimos fade_out_frames
        if fade_out_frames > 0:
            fo_start = max(total_frames - fade_out_frames, 0)
            fo_len   = total_frames - fo_start
            # Se fade in e fade out se sobrepõem, o mínimo vence
            fo_values = np.linspace(1.0, 0.0, fo_len)
            alphas[fo_start:] = np.minimum(alphas[fo_start:], fo_values)

        return alphas

    # ------------------------------------------------------------------
    # PRÉ-RENDERIZAÇÃO
    # ------------------------------------------------------------------

    def _prerender_frames(self) -> list:
        clip      = self.clip
        clip_dur  = clip.duration
        fps       = self.fps
        total_frames = int(clip_dur * fps)

        color_arr = np.array(self.color, dtype=np.float32)   # shape (3,)
        alphas    = self._compute_alphas(total_frames, clip_dur)

        times = np.linspace(0, clip_dur - 1 / fps, total_frames)

        print(f"[Fade] 🔧 Pré-renderizando {total_frames} frames "
              f"(fade_in={self.fade_in_duration}s, fade_out={self.fade_out_duration}s)...")

        frames = []
        for i, (t, alpha) in enumerate(zip(times, alphas)):
            raw = clip.get_frame(float(t))

            # Garante 3 canais (H, W, 3)
            if raw.ndim == 2:
                raw = np.dstack((raw, raw, raw))

            if abs(alpha - 1.0) < 1e-4:
                # Frame totalmente visível — sem mistura
                frames.append(raw.astype(np.uint8))
            elif abs(alpha) < 1e-4:
                # Frame totalmente escuro
                frame = np.full_like(raw, color_arr.astype(np.uint8))
                frames.append(frame)
            else:
                # Mistura linear: alpha * original + (1 - alpha) * color
                frame_f = raw.astype(np.float32)
                mixed   = alpha * frame_f + (1.0 - alpha) * color_arr
                frames.append(np.clip(mixed, 0, 255).astype(np.uint8))

            if (i + 1) % 30 == 0 or i == total_frames - 1:
                pct = int((i + 1) / total_frames * 100)
                print(f"[Fade]   {pct}% ({i + 1}/{total_frames})")

        print(f"[Fade] ✅ {len(frames)} frames prontos")
        return frames

    # ------------------------------------------------------------------
    # PROCESSO PRINCIPAL
    # ------------------------------------------------------------------

    def process(self):
        if not self.clip:
            raise ValueError("[Fade] Clip não fornecido")

        if not self.enabled:
            print("[Fade] ⏭️ Transição desabilitada — retornando clip original")
            return self.clip

        clip_dur = self.clip.duration

        # 1. Pré-renderiza todos os frames
        frames = self._prerender_frames()

        # 2. ImageSequenceClip — FFmpeg apenas empacota
        print("[Fade] 🎬 Montando ImageSequenceClip...")
        final_clip = ImageSequenceClip(frames, fps=self.fps).set_duration(clip_dur)

        # 3. Áudio (preserva narração + efeito sonoro opcional)
        audio_list = []
        if self.clip.audio is not None:
            audio_list.append(self.clip.audio)
        if self.audio_file_clip is not None:
            audio_list.append(self.audio_file_clip.set_start(0))
        if audio_list:
            final_clip = final_clip.set_audio(CompositeAudioClip(audio_list))

        print("[Fade] ✅ Transição processada")
        return final_clip
