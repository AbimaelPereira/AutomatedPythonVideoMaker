"""Presets de movimento: tabela literal, sem código.

Preset = `tracks` + `ease` + `duration` default. O que a ação declarar vence,
PROPRIEDADE A PROPRIEDADE (declarar `scale` num `pop_in` troca só o scale; o
`opacity` do preset continua valendo).

Convenção de unidades: deslocamentos em `"%"` são fração da caixa do elemento,
então um `slide_in_right` funciona igual num card de 300 px e num de 900 px.
"""

PRESETS: dict = {
    # --- opacidade ---
    "fade_in":  {"duration": 0.5, "ease": "out_quad", "tracks": {"opacity": [0.0, 1.0]}},
    "fade_out": {"duration": 0.5, "ease": "in_quad",  "tracks": {"opacity": [1.0, 0.0]}},

    # --- entradas deslizando ---
    "slide_in_left":  {"duration": 0.55, "ease": "out_cubic",
                       "tracks": {"x": ["-60%", 0], "opacity": [0.0, 1.0]}},
    "slide_in_right": {"duration": 0.55, "ease": "out_cubic",
                       "tracks": {"x": ["60%", 0], "opacity": [0.0, 1.0]}},
    "slide_in_up":    {"duration": 0.55, "ease": "out_cubic",
                       "tracks": {"y": ["60%", 0], "opacity": [0.0, 1.0]}},
    "slide_in_down":  {"duration": 0.55, "ease": "out_cubic",
                       "tracks": {"y": ["-60%", 0], "opacity": [0.0, 1.0]}},

    # --- saídas deslizando (inverso) ---
    "slide_out_left":  {"duration": 0.45, "ease": "in_cubic",
                        "tracks": {"x": [0, "-60%"], "opacity": [1.0, 0.0]}},
    "slide_out_right": {"duration": 0.45, "ease": "in_cubic",
                        "tracks": {"x": [0, "60%"], "opacity": [1.0, 0.0]}},
    "slide_out_up":    {"duration": 0.45, "ease": "in_cubic",
                        "tracks": {"y": [0, "-60%"], "opacity": [1.0, 0.0]}},
    "slide_out_down":  {"duration": 0.45, "ease": "in_cubic",
                        "tracks": {"y": [0, "60%"], "opacity": [1.0, 0.0]}},

    # --- escala (transborda a caixa: motion de UI) ---
    "pop_in":  {"duration": 0.45, "ease": "out_back",
                "tracks": {"scale": [0.82, 1.0], "opacity": [0.0, 1.0]}},
    "pop_out": {"duration": 0.35, "ease": "in_quad",
                "tracks": {"scale": [1.0, 0.86], "opacity": [1.0, 0.0]}},
    "punch":   {"duration": 0.3, "ease": "out_quad",
                "tracks": {"scale": [1.0, 1.08, 1.0]}},

    # --- deslocamento curto ---
    "rise": {"duration": 0.5, "ease": "out_cubic",
             "tracks": {"y": [40, 0], "opacity": [0.0, 1.0]}},

    # Senoide amortecida em 6 keyframes (amplitude caindo), não um `random`:
    # o princípio P6 exige que o mesmo JSON gere os mesmos frames.
    "shake": {"duration": 0.5, "ease": "linear",
              "tracks": {"x": [[0.0, 0], [0.2, "4%"], [0.4, "-3%"],
                               [0.6, "2%"], [0.8, "-1%"], [1.0, 0]]}},

    # --- zoom (fica DENTRO da caixa, recortando: ken burns) ---
    "ken_burns_in":  {"duration": None, "ease": "linear",
                      "tracks": {"zoom": [1.0, 1.15]}},
    "ken_burns_out": {"duration": None, "ease": "linear",
                      "tracks": {"zoom": [1.15, 1.0]}},

    # Flutuação lenta; `loop` repete o bloco até o fim da cena/`visible`.
    "float": {"duration": 2.0, "ease": "in_out_sine", "loop": True,
              "tracks": {"y": [[0.0, 0], [0.5, "-3%"], [1.0, 0]]}},
}

NAMES = tuple(PRESETS.keys())


def expand(name: str) -> dict:
    """Cópia rasa-segura do preset (o chamador mescla por cima sem mutar a tabela)."""
    preset = PRESETS[name]
    return {
        "duration": preset.get("duration"),
        "ease": preset.get("ease"),
        "loop": preset.get("loop", False),
        "tracks": {prop: value for prop, value in preset["tracks"].items()},
    }
