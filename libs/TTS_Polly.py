import os
import json
from pathlib import Path
from datetime import timedelta
import boto3
from dotenv import load_dotenv
from mutagen.mp3 import MP3
import wave, contextlib

load_dotenv()


def ms_to_srt_time(ms: int) -> str:
    td = timedelta(milliseconds=int(ms))
    total_seconds = int(td.total_seconds())
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    ms = int(td.microseconds / 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


class PollyTTS:
    def __init__(self, params=None):
        defaults = {
            "temp_dir": os.getenv("TEMP_DIR", "./temp_files"),
            "text_narration_filename": os.getenv("TEXT_NARRATION_FILE", "texto.txt"),
            "region": os.getenv("AWS_REGION", "us-east-1"),
            "voice_id": os.getenv("POLLY_VOICE_ID", "Camila"),
            "engine": os.getenv("POLLY_ENGINE", "neural"),
            "audio_format": os.getenv("POLLY_OUTPUT_FORMAT", "mp3"),
            "language_code": os.getenv("POLLY_LANGUAGE_CODE", "pt-BR"),
            "output_basename": os.getenv("POLLY_OUTPUT_BASENAME", "narration"),
            "text": None,
            "min_word_duration": 160,
            "last_word_duration": 400,
        }
        if params:
            defaults.update(params)
        for k, v in defaults.items():
            setattr(self, k, v)

        self.temp_dir = Path(str(self.temp_dir))
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.text_file_path = self.temp_dir / self.text_narration_filename

        if self.text is None and self.text_file_path.exists():
            self.text = self.text_file_path.read_text(encoding="utf-8").strip()

        self.polly = boto3.client("polly", region_name=self.region)

    def _synthesize_with_engine(self, **params):
        if self.engine:
            return self.polly.synthesize_speech(Engine=self.engine, **params)
        return self.polly.synthesize_speech(**params)

    def _generate_srt(self, words):
        srt_path = self.temp_dir / f"{self.output_basename}.srt"
        with open(srt_path, "w", encoding="utf-8") as srtf:
            for i, w in enumerate(words, start=1):
                start = int(w.get("time", 0))
                if i < len(words):
                    nxt = words[i]
                    end = max(int(nxt.get("time", start)) - 1, start + self.min_word_duration)
                else:
                    end = start + self.last_word_duration
                text_word = w.get("value", "").strip()
                if text_word:
                    srtf.write(f"{i}\n{ms_to_srt_time(start)} --> {ms_to_srt_time(end)}\n{text_word}\n\n")
        return srt_path

    def generate_audio_and_subtitles(self):
        if not self.text:
            raise ValueError("Nenhum texto disponível para síntese.")

        audio_params = dict(
            Text=self.text,
            TextType="text",
            OutputFormat=self.audio_format,
            VoiceId=self.voice_id,
            LanguageCode=self.language_code,
        )
        audio_resp = self._synthesize_with_engine(**audio_params)

        ext = self.audio_format if self.audio_format != "pcm" else "raw"
        audio_path = self.temp_dir / f"{self.output_basename}.{ext}"
        with open(audio_path, "wb") as f:
            f.write(audio_resp["AudioStream"].read())

        wav_path = None
        if self.audio_format == "pcm":
            wav_path = self.temp_dir / f"{self.output_basename}.wav"
            with open(audio_path, "rb") as pcmf, contextlib.closing(wave.open(str(wav_path), "wb")) as wavf:
                wavf.setnchannels(1)
                wavf.setsampwidth(2)
                wavf.setframerate(22050)
                wavf.writeframes(pcmf.read())

        sm_params = dict(
            Text=self.text,
            TextType="text",
            OutputFormat="json",
            VoiceId=self.voice_id,
            LanguageCode=self.language_code,
            SpeechMarkTypes=["word"],
        )
        sm_resp = self._synthesize_with_engine(**sm_params)
        sm_data = sm_resp["AudioStream"].read().decode("utf-8")

        words = []
        for ln in sm_data.splitlines():
            try:
                obj = json.loads(ln)
                if obj.get("type") == "word":
                    words.append(obj)
            except json.JSONDecodeError:
                continue

        srt_file = self._generate_srt(words)

        duration = 0
        if self.audio_format == "mp3":
            duration = MP3(str(audio_path)).info.length
        elif self.audio_format == "pcm":
            with wave.open(str(wav_path), "rb") as wf:
                duration = wf.getnframes() / float(wf.getframerate())

        return {"audio_file": str(wav_path or audio_path), "subtitle_file": str(srt_file), "audio_total_duration": duration}
