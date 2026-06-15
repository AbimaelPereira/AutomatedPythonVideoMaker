import os
import json


def deep_merge(base: dict, override: dict) -> dict:
    """Merge recursivo. override vence em conflitos de valores primitivos."""
    if not isinstance(base, dict):
        return override
    result = base.copy()
    for key, value in (override or {}).items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _filter_comment_keys(d: dict) -> dict:
    """Remove chaves que terminam com / (convenção de comentário JSON)."""
    return {
        k: (_filter_comment_keys(v) if isinstance(v, dict) else v)
        for k, v in d.items()
        if not k.endswith("/")
    }


def load_channel_config(channel_name: str) -> dict:
    """Carrega JSON do canal de channels_config/{channel_name}.json.
    Retorna {} se não encontrar. Filtra chaves que terminam com /."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    channel_file = os.path.join(base_dir, "channels_config", f"{channel_name}.json")
    if not os.path.exists(channel_file):
        print(f"[utils] Canal '{channel_name}': arquivo não encontrado em {channel_file}")
        return {}
    try:
        with open(channel_file, "r", encoding="utf-8") as f:
            raw = json.load(f)
        filtered = _filter_comment_keys(raw)
        print(f"[utils] Configuração do canal '{channel_name}' carregada.")
        return filtered
    except Exception as e:
        print(f"[utils] Erro ao carregar canal '{channel_name}': {e}")
        return {}


def resolve_output_resolution(output_ratio: str) -> tuple:
    RESOLUTIONS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "16:9-2k": (2560, 1440), "9:16-2k": (1440, 2560)}
    return RESOLUTIONS.get(output_ratio, (1080, 1920))


# Presets de qualidade de encoding (x264). crf menor = mais qualidade/arquivo maior.
QUALITY_PRESETS = {
    "draft":    {"crf": 26, "preset": "veryfast", "fps": 30, "pix_fmt": "yuv420p"},
    "balanced": {"crf": 20, "preset": "medium",   "fps": 30, "pix_fmt": "yuv420p"},
    "high":     {"crf": 18, "preset": "slow",     "fps": 30, "pix_fmt": "yuv420p"},
    "max":      {"crf": 16, "preset": "slower",   "fps": 30, "pix_fmt": "yuv420p"},
}

# Valores aceitos para validação (evita passar lixo pro ffmpeg).
_X264_PRESETS = {
    "ultrafast", "superfast", "veryfast", "faster", "fast",
    "medium", "slow", "slower", "veryslow", "placebo",
}


def resolve_output_quality(quality) -> dict:
    """Resolve a config de qualidade de encoding a partir do JSON.

    Aceita:
      - None / ausente            → preset "high"
      - str (ex.: "balanced")     → preset nomeado
      - dict {crf, preset, fps...}→ parte de um preset (campo "preset" nomeado, se houver)
                                     e sobrescreve os campos informados.
    """
    if quality is None:
        return dict(QUALITY_PRESETS["high"])

    if isinstance(quality, str):
        if quality not in QUALITY_PRESETS:
            raise ValueError(
                f"output.quality '{quality}' inválido. Use um de {list(QUALITY_PRESETS)} ou um objeto."
            )
        return dict(QUALITY_PRESETS[quality])

    if isinstance(quality, dict):
        # "preset" pode ser um nome de preset (base) OU um preset x264 cru.
        base_name = quality.get("preset")
        if isinstance(base_name, str) and base_name in QUALITY_PRESETS:
            resolved = dict(QUALITY_PRESETS[base_name])
        else:
            resolved = dict(QUALITY_PRESETS["high"])
        # Override fino: qualquer chave do dict vence a base.
        for k, v in quality.items():
            resolved[k] = v

        # Validações.
        x264_preset = resolved.get("preset")
        if isinstance(x264_preset, str) and x264_preset in QUALITY_PRESETS:
            # "preset" ficou como nome de preset → herda o preset x264 real da base.
            x264_preset = QUALITY_PRESETS[x264_preset]["preset"]
        if x264_preset not in _X264_PRESETS:
            raise ValueError(f"preset x264 '{x264_preset}' inválido. Use um de {sorted(_X264_PRESETS)}.")
        resolved["preset"] = x264_preset

        crf = int(resolved.get("crf", 18))
        if not 0 <= crf <= 51:
            raise ValueError(f"crf {crf} fora do intervalo válido (0-51).")
        resolved["crf"] = crf
        resolved["fps"] = int(resolved.get("fps", 30))
        resolved.setdefault("pix_fmt", "yuv420p")
        return resolved

    raise ValueError(f"output.quality deve ser str ou dict, recebido {type(quality).__name__}.")