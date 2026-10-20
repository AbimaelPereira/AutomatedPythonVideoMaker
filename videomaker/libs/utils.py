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

# Qualidade de encoding das CENAS INTERMEDIÁRIAS.
#
# Cenas individuais são artefato descartável: são concatenadas e re-encodadas (ou
# copiadas) no passe final. Gastar preset "slow"/crf18 nelas é desperdício — a
# qualidade é jogada fora depois. Medido em 1440p (15s de fonte real):
#   slow=60.3s  medium=23.8s  veryfast=11.9s  ultrafast=4.5s
#
# ultrafast + crf12 é visualmente ~lossless (a perda real acontece no encode final,
# que é o único que usa output.quality) e ~13x mais rápido que slow.
#
# Custo: arquivos ~8-10x maiores em disco. `estimate_intermediate_size_gb` estima
# a necessidade e `check_free_space` falha cedo se não couber.
INTERMEDIATE_QUALITY = {"crf": 12, "preset": "ultrafast", "pix_fmt": "yuv420p"}

# Permite forçar o comportamento antigo (encodar cenas na qualidade final) para
# comparação A/B: INTERMEDIATE_ENCODE=0 python main.py ...
USE_INTERMEDIATE_ENCODE = os.getenv("INTERMEDIATE_ENCODE", "1") not in ("0", "false", "False")


def resolve_intermediate_quality(final_quality: dict) -> dict:
    """Qualidade para render de cena intermediária.

    Herda `fps` da qualidade final (mudar fps entre cena e saída causaria
    resampling temporal) e substitui crf/preset pelo perfil rápido.
    Com INTERMEDIATE_ENCODE=0, devolve a qualidade final inalterada.
    """
    if not USE_INTERMEDIATE_ENCODE:
        return dict(final_quality)
    q = dict(INTERMEDIATE_QUALITY)
    q["fps"] = final_quality.get("fps", 30)
    return q


def estimate_intermediate_size_gb(total_duration_s: float, resolution: tuple) -> float:
    """Estima o espaço em disco das cenas intermediárias (crf 12, ultrafast).

    Baseado em bits-por-pixel MEDIDO nesse perfil: 1440p30 com movimento rendeu
    ~0.39 bpp (~43 Mbps, ~13 GB para 45 min). Conteúdo mais estático (imagem +
    zoom lento, o caso comum aqui) fica bem abaixo disso, então a estimativa é
    conservadora de propósito — o objetivo é falhar cedo, não prever com precisão.
    """
    if not total_duration_s or total_duration_s <= 0:
        return 0.0
    w, h = resolution
    bits_per_frame = w * h * 0.39
    bytes_total = (bits_per_frame / 8) * 30 * total_duration_s
    return bytes_total / (1024 ** 3)


def check_free_space(path: str, needed_gb: float, label: str = "render") -> tuple:
    """Verifica espaço livre em disco. Retorna (ok, free_gb, needed_gb).

    Não levanta exceção — quem chama decide se aborta. Um render de 45 min que
    morre no meio por falta de disco desperdiça horas; melhor avisar antes.
    """
    try:
        import shutil as _shutil
        free_gb = _shutil.disk_usage(path).free / (1024 ** 3)
    except Exception:
        return (True, 0.0, needed_gb)   # não conseguiu medir: não bloqueia
    return (free_gb >= needed_gb, free_gb, needed_gb)


def _default_safe_paddings(resolution: tuple) -> dict:
    """Paddings padrão de "área segura" conforme a orientação da tela.

    Paddings significam apenas margem segura (a faixa onde visuais e legendas
    podem ser ancorados via `placement`). Verticais: 9:16 mantém os históricos
    (top 100 / bottom 850, calibrados para a legenda legada); 16:9 usa margens
    simétricas de ~5% por não ter zona de legenda dedicada.
    """
    w, h = resolution
    if w >= h:  # paisagem (16:9 etc.) — margens simétricas de ~5%
        return {
            "padding_side":   int(w * 0.05),   # 1920 → 96
            "padding_top":    int(h * 0.05),   # 1080 → 54
            "padding_bottom": int(h * 0.05),   # 1080 → 54
        }
    # retrato (9:16) — preserva os defaults históricos
    return {
        "padding_side":   50,
        "padding_top":    100,
        "padding_bottom": 850,
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