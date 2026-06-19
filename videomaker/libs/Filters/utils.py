"""Helpers compartilhados pelos filtros."""

# Fator de downscale para processamento interno dos filtros de overlay.
# O blur é aplicado em resolução reduzida e depois o frame é upscalado,
# reduzindo o custo do GaussianBlur em ~16x sem perda visual perceptível.
FILTER_SCALE = 0.25


def hex_to_rgb(hex_value):
    if not isinstance(hex_value, str):
        return tuple(hex_value)
    hex_value = hex_value.lstrip('#')
    try:
        if len(hex_value) == 6:
            return tuple(int(hex_value[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        pass
    return (255, 255, 255)
