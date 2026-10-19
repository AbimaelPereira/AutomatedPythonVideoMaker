"""
Saneamento de word boundaries do Whisper contra o texto que foi sintetizado.

Por que existe: o Whisper alucina no fim de áudios TTS curtos, repetindo as
primeiras palavras do texto como se o narrador as tivesse dito ("...corrigir a
rota." → legenda extra "A"). O filtro antigo era puramente temporal/quantitativo
(corte pela duração do áudio + tolerância de 2 palavras) e não pegava isso,
porque a alucinação cai DENTRO da duração do áudio e cabe na tolerância.

A correção é ancorar no texto: o TTS fala exatamente o `text` que recebeu, então
a transcrição é alinhada a esse texto e tudo que não casa com ele é descartado.

Este módulo é importado tanto pelo pipeline principal (numpy 1.x) quanto pelo
`kokoro_runner` dentro do venv-whisper (numpy 2.x), por isso usa só a stdlib.
"""

import re
import unicodedata
from difflib import SequenceMatcher


_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def normalize_token(token: str) -> str:
    """Minúsculas, sem acento e sem pontuação — base da comparação."""
    token = unicodedata.normalize("NFD", token or "")
    token = "".join(c for c in token if unicodedata.category(c) != "Mn")
    token = _PUNCT_RE.sub("", token)
    return token.lower().strip()


def _is_latin(word: str) -> bool:
    """Descarta tokens CJK/cirílico — alucinação típica em áudio TTS curto."""
    return all(ord(c) < 0x300 or c.isspace() or not c.isalpha() for c in word)


def _filter_timestamps(word_boundaries: list, audio_duration_ms: int) -> list:
    """
    Remove timestamps impossíveis e normaliza sobreposições.

    Sobreposição pequena (o Whisper costuma emitir pares como
    `6,380→6,480` seguido de `6,440→6,700`) NÃO é alucinação: é ruído de
    alinhamento. Descartar a palavra nesses casos apagava texto legítimo da
    legenda, então aqui o start é apenas empurrado para o fim do anterior.
    Só é descartada a palavra que, depois desse ajuste, não sobra duração —
    ou seja, que está inteiramente contida na anterior.
    """
    audio_limit = audio_duration_ms + 100  # tolerância p/ não cortar a última palavra real

    filtered = []
    prev_end = -1
    for w in sorted(word_boundaries, key=lambda x: x["start"]):
        if w["start"] < 0 or w["end"] <= w["start"]:
            continue
        if w["start"] >= audio_limit:
            break
        if not _is_latin(w["word"]):
            continue

        w = dict(w)
        if w["start"] < prev_end:
            w["start"] = prev_end
        if w["end"] <= w["start"]:
            continue

        filtered.append(w)
        prev_end = w["end"]
    return filtered


def align_to_text(word_boundaries: list, text: str) -> list:
    """
    Mantém apenas os boundaries que correspondem, em ordem, às palavras de
    `text`, e devolve cada um com a grafia do texto original (preservando
    acentuação e pontuação que o Whisper pode ter perdido).

    Usa `SequenceMatcher` sobre as sequências normalizadas: os blocos iguais
    dão o alinhamento; o que o Whisper inventou cai nas lacunas e é removido.
    Uma palavra do texto que o Whisper não transcreveu simplesmente não recebe
    timestamp — não inventamos tempo para ela.
    """
    expected = (text or "").split()
    if not expected or not word_boundaries:
        return word_boundaries

    exp_norm = [normalize_token(w) for w in expected]
    got_norm = [normalize_token(w["word"]) for w in word_boundaries]

    matcher = SequenceMatcher(None, exp_norm, got_norm, autojunk=False)

    aligned = []
    for exp_i, got_j, size in matcher.get_matching_blocks():
        for k in range(size):
            wb = dict(word_boundaries[got_j + k])
            wb["word"] = expected[exp_i + k]  # grafia canônica do texto
            aligned.append(wb)

    # Rede de segurança: só abandona o alinhamento quando o texto claramente
    # não descreve o áudio (cena com `text` trocado, Whisper em outro idioma,
    # transcrição vazia) — aí a transcrição crua ainda é melhor que nada.
    #
    # O critério é a cobertura do TEXTO ESPERADO, não da transcrição. Medir
    # contra a transcrição seria contraproducente: quanto mais o Whisper
    # alucina, maior o denominador, e justamente nos piores casos o filtro se
    # desligaria e devolveria a legenda suja.
    # A cobertura é medida contra o menor dos dois tamanhos: uma transcrição
    # curta (áudio cortado, Whisper que desistiu no meio) é legítima e não
    # deve reabilitar a legenda suja só por cobrir pouco do texto.
    reference = min(len(expected), len(word_boundaries))
    if reference and len(aligned) < reference * 0.5:
        return word_boundaries

    return aligned


def sanitize(word_boundaries: list, text: str, audio_duration_ms: int) -> list:
    """
    Pipeline completo: filtra timestamps impossíveis e então alinha ao texto
    falado, eliminando as repetições alucinadas no fim da cena.
    """
    if not word_boundaries:
        return []

    filtered = _filter_timestamps(word_boundaries, audio_duration_ms)
    return align_to_text(filtered, text)
