import os
import json
import subprocess
from pathlib import Path

from mutagen.mp3 import MP3
from pydub import AudioSegment


def ms_to_srt_time(ms: float) -> str:
    total_seconds = int(ms // 1000)
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    ms_remainder = int(ms % 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms_remainder:03d}"


# Caminhos do runner isolado (venv-whisper) — relativos a videomaker/
_THIS_DIR     = Path(__file__).resolve()
_VIDEOMAKER   = _THIS_DIR.parents[3]                       # .../videomaker
_RUNNER_PY    = _VIDEOMAKER / "libs" / "Whisper" / "kokoro_runner.py"
_VENV_PYTHON  = _VIDEOMAKER / "libs" / "Whisper" / "venv-whisper" / "bin" / "python"

RESULT_PREFIX = "__KOKORO_RESULT__"


class KokoroTTS:
    """
    Kokoro TTS — modelo local de 82M (open-weight, gratuito).

    A síntese roda num subprocesso isolado (venv-whisper) porque o Kokoro
    exige numpy>=2, incompatível com o numpy 1.22 do pipeline principal
    (travado por moviepy 1.0.3). O runner faz síntese + alinhamento de
    legendas via Whisper e devolve os word_boundaries por JSON.

    Português Brasileiro: lang_code="p", vozes pf_dora (F), pm_alex/pm_santa (M).

    Saída de generate_audio_and_subtitles():
        {
            "audio_file":           str (.mp3),
            "subtitle_file":        str (.srt),
            "audio_total_duration": float (s),
            "word_boundaries":      list[{"word", "start", "end"}] em ms,
        }
    """

    def __init__(self, params=None):
        defaults = {
            "text_narration_filename": os.getenv("TEXT_NARRATION_FILE", "texto.txt"),
            "voice_id":          os.getenv("KOKORO_VOICE", "pf_dora"),
            "lang_code":         "p",          # p = português brasileiro
            "speed":             1.0,
            "audio_format":      "mp3",
            "output_basename":   "narration",
            "text":              None,
            "min_word_duration": 100,          # ms
            # Whisper — timestamps reais pós-síntese (igual ao Google TTS)
            "whisper_enabled":   True,
            "whisper_model":     "base",
            "whisper_language":  "pt",
        }
        if params:
            defaults.update(params)
        for k, v in defaults.items():
            setattr(self, k, v)

        self.text_file_path = Path(self.text_narration_filename)
        if self.text is None and self.text_file_path.exists():
            self.text = self.text_file_path.read_text(encoding="utf-8").strip()

    # ------------------------------------------------------------------
    # SUBPROCESSO (síntese + alinhamento no venv-whisper)
    # ------------------------------------------------------------------

    def _run_kokoro_subprocess(self) -> dict:
        if not _VENV_PYTHON.exists():
            raise RuntimeError(
                f"Python do venv-whisper não encontrado em {_VENV_PYTHON}. "
                f"Instale o Kokoro nesse venv: "
                f"libs/Whisper/venv-whisper/bin/python -m pip install 'kokoro>=0.9.4' soundfile"
            )

        runner_params = {
            "text":             self.text,
            "output_basename":  self.output_basename,
            "voice":            self.voice_id,
            "lang_code":        self.lang_code,
            "speed":            float(self.speed),
            "whisper_enabled":  self.whisper_enabled,
            "whisper_model":    self.whisper_model,
            "whisper_language": self.whisper_language,
            "min_word_duration": self.min_word_duration,
        }

        proc = subprocess.run(
            [str(_VENV_PYTHON), str(_RUNNER_PY), json.dumps(runner_params, ensure_ascii=False)],
            capture_output=True,
            text=True,
        )

        if proc.returncode != 0:
            raise RuntimeError(
                f"kokoro_runner falhou (rc={proc.returncode}):\n{proc.stderr.strip()}"
            )

        # O JSON de resultado vem prefixado; ignora ruído (warnings do HF/torch)
        result_line = None
        for line in proc.stdout.splitlines():
            if line.startswith(RESULT_PREFIX):
                result_line = line[len(RESULT_PREFIX):]
                break

        if result_line is None:
            raise RuntimeError(
                f"kokoro_runner não retornou resultado.\nstdout:\n{proc.stdout}\n"
                f"stderr:\n{proc.stderr}"
            )

        return json.loads(result_line)

    # ------------------------------------------------------------------
    # SRT
    # ------------------------------------------------------------------

    def _generate_srt(self, word_boundaries: list) -> str:
        srt_path = f"{self.output_basename}.srt"
        with open(srt_path, "w", encoding="utf-8") as f:
            for i, w in enumerate(word_boundaries, 1):
                start = max(0, w["start"])
                end   = max(start + self.min_word_duration, w["end"])
                f.write(f"{i}\n{ms_to_srt_time(start)} --> {ms_to_srt_time(end)}\n{w['word']}\n\n")
        return srt_path

    def _generate_srt_from_duration(self, duration_ms: int) -> tuple:
        """Fallback quando o Whisper não retorna timestamps: divide a duração."""
        words = (self.text or "").split()
        if not words:
            return f"{self.output_basename}.srt", []

        ms_per_word = duration_ms / len(words)
        boundaries = []
        for i, word in enumerate(words):
            start = int(i * ms_per_word)
            end   = int((i + 1) * ms_per_word)
            boundaries.append({"word": word, "start": start, "end": end})
        return self._generate_srt(boundaries), boundaries

    # ------------------------------------------------------------------
    # API PÚBLICA
    # ------------------------------------------------------------------

    def generate_audio_and_subtitles(self) -> dict:
        if not self.text:
            raise ValueError("Nenhum texto disponível para síntese (Kokoro).")

        result = self._run_kokoro_subprocess()

        wav_path        = result["audio_file"]
        duration        = float(result.get("audio_total_duration", 0.0))
        word_boundaries = result.get("word_boundaries") or []

        # Converte WAV (24kHz) → MP3 para uniformizar com os demais providers
        mp3_path = f"{self.output_basename}.{self.audio_format}"
        if self.audio_format == "mp3":
            AudioSegment.from_wav(wav_path).export(mp3_path, format="mp3")
            try:
                os.remove(wav_path)
            except OSError:
                pass
            audio_path = mp3_path
            duration = MP3(audio_path).info.length
        else:
            audio_path = wav_path

        # SRT: usa boundaries reais do Whisper; senão, estima pela duração
        if word_boundaries:
            srt_file = self._generate_srt(word_boundaries)
        else:
            print("[KokoroTTS] ⚠️ Sem timestamps do Whisper — estimando pela duração.")
            srt_file, word_boundaries = self._generate_srt_from_duration(int(duration * 1000))

        return {
            "audio_file":           audio_path,
            "subtitle_file":        srt_file,
            "audio_total_duration": duration,
            "word_boundaries":      word_boundaries,
        }


if __name__ == "__main__":
    tts = KokoroTTS(params={
        "text": "Olá! Esta é uma demonstração da voz do Kokoro em português brasileiro.",
        "voice_id": "pf_dora",
        "output_basename": "/tmp/kokoro_tts_demo",
    })
    out = tts.generate_audio_and_subtitles()
    print(json.dumps(out, ensure_ascii=False, indent=2))
