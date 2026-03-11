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
    RESOLUTIONS = {"9:16": (1080, 1920), "16:9": (1920, 1080)}
    return RESOLUTIONS.get(output_ratio, (1080, 1920))