#!/usr/bin/env python3
"""
Runner do Kokoro TTS — executado DENTRO do venv-whisper.

Motivo: o Kokoro exige numpy>=2, incompatível com o numpy 1.22 do pipeline
principal (travado por moviepy 1.0.3). O venv-whisper já roda numpy 2.x +
torch + whisper, então síntese (Kokoro) E alinhamento de legendas (Whisper)
acontecem aqui, isolados. O pipeline principal invoca este script por
subprocesso e lê o JSON do stdout.

Uso:
    python kokoro_runner.py '<json_params>'

Params (JSON):
    {
        "text": "...",                  # obrigatório
        "output_basename": "/path/cena_01",   # gera .wav (e .mp3 se pydub)
        "voice": "pf_dora",
        "lang_code": "p",               # p = portugues BR
        "speed": 1.0,
        "whisper_enabled": true,
        "whisper_model": "base",
        "whisper_language": "pt",
        "min_word_duration": 100        # ms
    }

Saída (JSON no stdout, prefixada por "__KOKORO_RESULT__"):
    {
        "audio_file": "/path/cena_01.wav",
        "audio_total_duration": 4.17,
        "word_boundaries": [{"word": "Olá", "start": 0, "end": 320}, ...]
    }
"""
import sys
import os
import json
import warnings

warnings.filterwarnings("ignore")

RESULT_PREFIX = "__KOKORO_RESULT__"
SAMPLE_RATE = 24000

# Cache de pipeline por lang_code (carregar o modelo é caro)
_PIPELINES = {}


def _get_pipeline(lang_code: str):
    if lang_code not in _PIPELINES:
        from kokoro import KPipeline
        _PIPELINES[lang_code] = KPipeline(lang_code=lang_code)
    return _PIPELINES[lang_code]


def synthesize(params: dict) -> str:
    """Sintetiza o áudio com Kokoro e salva em .wav. Retorna o caminho."""
    import numpy as np
    import soundfile as sf

    text = params["text"]
    voice = params.get("voice", "pf_dora")
    lang_code = params.get("lang_code", "p")
    speed = float(params.get("speed", 1.0))
    output_basename = params["output_basename"]

    pipeline = _get_pipeline(lang_code)

    chunks = []
    for _gs, _ps, audio in pipeline(text, voice=voice, speed=speed):
        if audio is not None and len(audio):
            chunks.append(np.asarray(audio, dtype=np.float32))

    if not chunks:
        raise RuntimeError("Kokoro não retornou áudio para o texto fornecido.")

    full = np.concatenate(chunks)

    target_dir = os.path.dirname(output_basename) or "."
    os.makedirs(target_dir, exist_ok=True)

    wav_path = f"{output_basename}.wav"
    sf.write(wav_path, full, SAMPLE_RATE)

    duration = len(full) / SAMPLE_RATE
    return wav_path, duration


def _sanitize_word_boundaries(word_boundaries: list, expected_word_count: int,
                              audio_duration_ms: int) -> list:
    """
    Remove artefatos de alucinação do Whisper (timestamps inválidos,
    sobrepostos, além do fim do áudio, ou em excesso ao texto esperado).
    Portado de TTS_GoogleCloud._sanitize_word_boundaries.
    """
    if not word_boundaries:
        return []

    sorted_wb = sorted(word_boundaries, key=lambda w: w["start"])
    audio_limit = audio_duration_ms + 100  # 100ms de tolerância no fim

    filtered = []
    prev_end = -1
    for w in sorted_wb:
        if w["start"] < 0 or w["end"] <= w["start"]:
            continue
        if w["start"] < prev_end:
            continue
        if w["start"] >= audio_limit:
            break
        filtered.append(w)
        prev_end = w["end"]

    if expected_word_count > 0 and len(filtered) > expected_word_count + 2:
        filtered = filtered[:expected_word_count + 2]

    # Remove tokens com caracteres fora do alfabeto latino (CJK etc.) —
    # alucinação típica do Whisper em áudio TTS curto.
    def _is_latin(word: str) -> bool:
        return all(ord(c) < 0x300 or c.isspace() or not c.isalpha() for c in word)

    filtered = [w for w in filtered if _is_latin(w["word"])]

    return filtered


def align_with_whisper(audio_path: str, params: dict, audio_duration_ms: int) -> list:
    """
    Extrai word boundaries reais transcrevendo o áudio gerado com Whisper.
    Espelha TTS_GoogleCloud._generate_word_boundaries_whisper.
    """
    if not params.get("whisper_enabled", True):
        return []

    try:
        import whisper

        model_size = params.get("whisper_model", "base")
        language = params.get("whisper_language", "pt")
        text = params.get("text") or None

        model = whisper.load_model(model_size)
        result = model.transcribe(
            audio_path,
            word_timestamps=True,
            language=language,
            initial_prompt=text,
        )

        word_boundaries = []
        for segment in result.get("segments", []):
            for w in segment.get("words", []):
                word = (w.get("word") or "").strip()
                if not word:
                    continue
                word_boundaries.append({
                    "word":  word,
                    "start": int(w["start"] * 1000),
                    "end":   int(w["end"] * 1000),
                })

        expected = len((text or "").split())
        return _sanitize_word_boundaries(word_boundaries, expected, audio_duration_ms)

    except Exception as e:
        print(f"[kokoro_runner] Whisper falhou: {e}", file=sys.stderr)
        return []


def main():
    if len(sys.argv) < 2:
        print("Uso: kokoro_runner.py '<json_params>'", file=sys.stderr)
        sys.exit(2)

    params = json.loads(sys.argv[1])

    if not params.get("text"):
        print("[kokoro_runner] 'text' é obrigatório.", file=sys.stderr)
        sys.exit(2)

    audio_path, duration = synthesize(params)
    word_boundaries = align_with_whisper(audio_path, params, int(duration * 1000))

    result = {
        "audio_file": audio_path,
        "audio_total_duration": duration,
        "word_boundaries": word_boundaries,
    }
    print(RESULT_PREFIX + json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
