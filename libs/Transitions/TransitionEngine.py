import os
import random
from moviepy.editor import AudioFileClip
from libs.Transitions.Zoom import Zoom
from libs.Transitions.Fade import Fade


class TransitionEngine:
    """
    Engine de transição que suporta múltiplos tipos de transição.

    Tipos disponíveis:
      - "zoom"  (padrão) → zoom out + shake + zoom in
      - "fade"            → fade in no início + fade out no final

    Configuração no JSON:

      # Zoom (comportamento anterior, sem mudança)
      "transitions": {
        "enabled": true,
        "type": "zoom",
        "visual": {
          "zoom_max_scale": 15.0,
          "duration": { "zoom_out": 0.2, "shake_out": 0.4 },
          "physics":  { "shake_amplitude": 0.12 }
        },
        "audio": { "type": "directory", "source": "assets/sfx", "volume": 0.8 }
      }

      # Fade
      "transitions": {
        "enabled": true,
        "type": "fade",
        "visual": {
          "fade_in_duration":  0.5,
          "fade_out_duration": 0.5,
          "color": [0, 0, 0]
        }
      }

      # Desativar transição em cena específica (override do global)
      "transitions": { "enabled": false }
    """

    def __init__(self, config: dict):
        defaults = {
            "clip": None,
            "transitions_settings": None,
            "resolution": (1920, 1080),
            "audio_settings": None,
            "visual_settings": None,
        }

        self.config = {**defaults, **config}
        for key, value in self.config.items():
            setattr(self, key, value)

        if self.clip is None:
            raise ValueError("[TransitionEngine] Parâmetro obrigatório ausente: clip")

        if self.transitions_settings is None:
            raise ValueError("[TransitionEngine] Parâmetro obrigatório ausente: transitions_settings")

        # Extrai sub-configs
        if self.transitions_settings.get("audio"):
            self.audio_settings = self.transitions_settings["audio"]

        if self.transitions_settings.get("visual"):
            self.visual_settings = self.transitions_settings["visual"]

    # ------------------------------------------------------------------
    # ÁUDIO DE TRANSIÇÃO
    # ------------------------------------------------------------------

    def _get_clip_audio(self):
        """Retorna o áudio do efeito de transição, se disponível."""
        if not self.audio_settings:
            return None

        audio_type = self.audio_settings.get("type")
        source     = self.audio_settings.get("source")
        volume     = self.audio_settings.get("volume", 1.0)

        if audio_type == "directory":
            if not source or not os.path.exists(source):
                return None
            files = [f for f in os.listdir(source) if f.endswith(('.mp3', '.wav'))]
            if not files:
                return None
            audio_path = os.path.join(source, random.choice(files))

        elif audio_type == "file":
            audio_path = source
            if not audio_path or not os.path.exists(audio_path):
                return None
        else:
            return None

        try:
            return AudioFileClip(audio_path).volumex(volume)
        except Exception as e:
            print(f"[TransitionEngine] ⚠️ Erro ao carregar áudio: {e}")
            return None

    # ------------------------------------------------------------------
    # APLICAR TRANSIÇÃO
    # ------------------------------------------------------------------

    def apply_transition(self):
        """
        Detecta o tipo de transição e delega para a classe correspondente.
        Retorna o clip processado (ou o original em caso de erro).
        """
        if not self.clip:
            return None

        transition_type = self.transitions_settings.get("type", "zoom").lower()

        print(f"[TransitionEngine] Aplicando transição '{transition_type}'...")

        try:
            if transition_type == "fade":
                return self._apply_fade()
            else:
                # Padrão: zoom (comportamento anterior preservado)
                return self._apply_zoom()

        except Exception as e:
            print(f"[TransitionEngine] ❌ Erro ao aplicar transição '{transition_type}': {e}")
            import traceback
            traceback.print_exc()
            return self.clip  # fallback: clip original

    # ------------------------------------------------------------------
    # ZOOM
    # ------------------------------------------------------------------

    def _apply_zoom(self):
        params = {
            "resolution_output": self.resolution,
            "clip": self.clip,
        }

        if self.visual_settings:
            params.update(self.visual_settings)

        audio_clip = self._get_clip_audio()
        if audio_clip:
            params["audio_file_clip"] = audio_clip

        print(f"[TransitionEngine] Zoom params: {list(params.keys())}")

        transition = Zoom(params)
        return transition.process()

    # ------------------------------------------------------------------
    # FADE
    # ------------------------------------------------------------------

    def _apply_fade(self):
        params = {
            "resolution_output": self.resolution,
            "clip": self.clip,
        }

        # Aplica configurações visuais específicas do fade
        if self.visual_settings:
            # Campos reconhecidos pelo Fade
            for key in ("fade_in_duration", "fade_out_duration", "color", "fps", "enabled"):
                if key in self.visual_settings:
                    params[key] = self.visual_settings[key]

        # Áudio (opcional — fade normalmente não tem sfx, mas suporta)
        audio_clip = self._get_clip_audio()
        if audio_clip:
            params["audio_file_clip"] = audio_clip

        print(f"[TransitionEngine] Fade params: {list(params.keys())}")

        transition = Fade(params)
        return transition.process()
