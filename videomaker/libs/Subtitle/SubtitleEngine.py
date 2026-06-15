"""
SubtitleEngine — despachante de tipos de legenda.

Espelha o padrão do `TransitionEngine`: lê `params["type"]` e delega para a
classe de legenda correspondente, todas expondo a mesma interface `.generate()`
(retorna um CompositeVideoClip).

Tipos disponíveis:
  - "classic" (padrão / type ausente) → ClassicSubtitle (comportamento legado)
  - "karaoke"                         → KaraokeSubtitle (word-by-word acumulativo)

Configuração no JSON (bloco "subtitle", mesclável via deep_merge):

  # Clássico (default — nada muda para quem já usa)
  "subtitle": { "font_path": "...", "font_size": 90, "color": "#FFF", ... }

  # Karaokê
  "subtitle": {
    "type": "karaoke",
    "words_per_group": 4,
    "layout": "one_per_line",
    "palette": [ { "fill": "#FFF", "stroke": "#000", "stroke_width": 3,
                   "shadow": {"color":"#000","opacity":0.85,"blur":6,"offset":[4,4]},
                   "font_path": "..." }, ... ]
  }
"""

from libs.Subtitle.types.ClassicSubtitle import ClassicSubtitle
from libs.Subtitle.types.KaraokeSubtitle import KaraokeSubtitle


_TYPES = {
    "classic": ClassicSubtitle,
    "karaoke": KaraokeSubtitle,
}


class SubtitleEngine:
    def __init__(self, params=None):
        params = dict(params or {})
        self._type = str(params.pop("type", "classic") or "classic").lower()

        cls = _TYPES.get(self._type)
        if cls is None:
            print(f"[SubtitleEngine] ⚠️ Tipo de legenda desconhecido '{self._type}'. Usando 'classic'.")
            cls = ClassicSubtitle
            self._type = "classic"

        print(f"[SubtitleEngine] Gerando legendas tipo '{self._type}'...")
        self._impl = cls(params=params)

    def generate(self):
        return self._impl.generate()
