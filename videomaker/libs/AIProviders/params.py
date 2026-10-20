"""Parâmetros de geração de IA — um único lugar, para todos os caminhos.

Todo bloco de IA do JSON (`background.visual`, `visual_elements[].source`,
`youtube.thumbnail`) declara os argumentos do provider dentro de `parameters`:

    {"type": "ai", "prompt": "...", "parameters": {"model": "zimage"}}

Antes cada caminho lia de um lugar diferente — o fundo lia `parameters`, o
visual_element e a thumbnail liam `model`/`width`/`height` soltos. Um bloco no
formato "do outro" perdia o modelo em silêncio e caía no default `flux`. Agora
chave solta é ERRO: `reject_flat_keys` levanta antes do render começar.

Ordem de precedência (cada nível sobrescreve o anterior):
    defaults do caminho  <  global_settings.ai.parameters (canal/vídeo)  <  bloco.parameters

`global_settings.ai.parameters` é onde o canal fixa, p.ex., `model` e
`enable_fallback: false` para todos os blocos de IA de uma vez.
"""

import hashlib
import json

# Argumentos do provider que antes eram aceitos soltos no bloco. Qualquer um
# deles fora de `parameters` é rejeitado.
PROVIDER_KEYS = (
    "model", "width", "height", "seed", "enhance", "negative_prompt",
    "quality", "safe", "transparent", "timeout", "enable_fallback",
    "duration", "aspectRatio", "audio", "image",
)


def reject_flat_keys(block: dict, where: str) -> None:
    """Levanta ValueError se o bloco tem argumento do provider fora de `parameters`."""
    flat = [k for k in PROVIDER_KEYS if k in (block or {})]
    if flat:
        raise ValueError(
            f"{where}: {flat} fora de `parameters`. Blocos de IA aceitam os "
            f"argumentos do provider SÓ dentro de `parameters` — ex.: "
            f'"parameters": {{"model": "zimage"}}.'
        )


def resolve_parameters(block: dict, global_settings: dict = None,
                       where: str = "bloco de IA", defaults: dict = None) -> dict:
    """kwargs finais do provider: defaults < global_settings.ai.parameters < bloco."""
    reject_flat_keys(block, where)
    merged = dict(defaults or {})
    channel = ((global_settings or {}).get("ai") or {}).get("parameters") or {}
    merged.update(channel)
    merged.update((block or {}).get("parameters") or {})
    return merged


def cache_key(block: dict, parameters: dict) -> str:
    """Chave do asset de IA (sem o prefixo "ai_"). `cache_key` explícito vence; senão hash do pedido.

    Usa os parâmetros JÁ resolvidos (com o default do canal): trocar o modelo
    do canal precisa invalidar a imagem gerada com o modelo anterior. Precisa
    ser calculada ANTES de sobrescrever width/height pela resolução de saída,
    e igual nos caminhos MoviePy e ffmpeg — senão os dois não dividem cache.
    """
    if block.get("cache_key"):
        return block["cache_key"]
    data = {
        "provider": block.get("provider", "pollinations"),
        "type": block.get("content_type", "image"),
        "prompt": block.get("prompt", ""),
        "parameters": parameters,
    }
    return hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()[:12]


def validate_video_ai_blocks(scenes: list, thumbnail: dict = None) -> None:
    """Checa TODOS os blocos de IA do vídeo antes do render. Levanta no primeiro erro.

    O caminho de fundo engole exceções e cai em cor sólida; sem esta checagem
    prévia um bloco inválido viraria cena preta em vez de erro.
    """
    errors = []
    for scene in scenes or []:
        sid = scene.get("id", "?")
        visual = ((scene.get("background") or {}).get("visual") or {})
        if visual.get("type") == "ai":
            try:
                reject_flat_keys(visual, f"cena '{sid}' background.visual")
            except ValueError as e:
                errors.append(str(e))
        for i, el in enumerate(scene.get("visual_elements") or []):
            src = el.get("source")
            if isinstance(src, dict) and src.get("type") == "ai":
                try:
                    reject_flat_keys(src, f"cena '{sid}' visual_elements[{i}].source")
                except ValueError as e:
                    errors.append(str(e))
    if isinstance(thumbnail, dict) and thumbnail.get("type") == "ai":
        try:
            reject_flat_keys(thumbnail, "youtube.thumbnail")
        except ValueError as e:
            errors.append(str(e))
    if errors:
        raise ValueError("Blocos de IA inválidos:\n  - " + "\n  - ".join(errors))
