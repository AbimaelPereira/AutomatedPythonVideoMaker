import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

sys_path_libs = str(Path(__file__).parent.parent / "libs")
import sys
if sys_path_libs not in sys.path:
    sys.path.insert(0, sys_path_libs)

from AIProviders.GeminiProvider import GeminiProvider
from reelscutter.db import get_pipeline, upsert_pipeline

YTDLP_BROWSER = "brave:~/snap/brave/current/.config/BraveSoftware/Brave-Browser"

PROMPTS_DIR = Path(__file__).parent / "prompts"


class ReelsCutter:
    def __init__(
        self,
        channel_name: str,
        temp_dir: str = None,
        jsons_dir: str = None,
        min_words: int = 12,
        max_words: int = 18,
        min_duration: int = 55,
        max_duration: int = 85,
        prompt_file: str = "evangelico_br.md",
    ):
        self.channel_name = channel_name
        self.min_words = min_words
        self.max_words = max_words
        self.min_duration = min_duration
        self.max_duration = max_duration

        base = Path(__file__).parent.parent
        self.temp_dir = Path(temp_dir) if temp_dir else base / "temp"
        self.jsons_dir = Path(jsons_dir) if jsons_dir else base / "jsons"
        self.temp_dir.mkdir(exist_ok=True)
        self.jsons_dir.mkdir(exist_ok=True)

        prompt_path = PROMPTS_DIR / prompt_file
        self.prompt_template = prompt_path.read_text(encoding="utf-8")

        self.gemini = GeminiProvider()

    # ── Utilitários ────────────────────────────────────────────────────────────

    def extract_video_id(self, url: str) -> str:
        patterns = [
            r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})",
            r"shorts/([A-Za-z0-9_-]{11})",
        ]
        for pat in patterns:
            m = re.search(pat, url)
            if m:
                return m.group(1)
        raise ValueError(f"Não foi possível extrair o video_id de: {url}")

    def slugify(self, text: str) -> str:
        text = text.upper()
        text = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE)
        return re.sub(r"\s+", "_", text.strip())

    def today_publish_at(self) -> str:
        return datetime.now().strftime("%Y-%m-%d 17:00:00")

    # ── Step 1: transcrição ────────────────────────────────────────────────────

    def get_transcript(self, url: str) -> dict:
        video_id = self.extract_video_id(url)
        transcript = self._fetch_transcript(video_id)
        text = self._transcript_with_timestamps(transcript)
        return {"video_id": video_id, "transcript": transcript, "text": text}

    def _fetch_transcript(self, video_id: str) -> list[dict]:
        from youtube_transcript_api import YouTubeTranscriptApi
        try:
            ytt = YouTubeTranscriptApi()
            fetched = ytt.fetch(video_id, languages=["pt", "pt-BR", "en"])
            return [{"text": s.text, "start": s.start, "duration": s.duration} for s in fetched]
        except Exception:
            fetched = YouTubeTranscriptApi.list_transcripts(video_id) \
                .find_transcript(["pt", "pt-BR", "en"]).fetch()
            return [{"text": s["text"], "start": s["start"], "duration": s["duration"]} for s in fetched]

    def _transcript_with_timestamps(self, transcript: list[dict]) -> str:
        return "\n".join(f"[{s['start']:.1f}s] {s['text'].strip()}" for s in transcript)

    # ── Step 2: download de áudio ──────────────────────────────────────────────

    def download_audio(self, url: str, video_id: str) -> str:
        out_path = str(self.temp_dir / f"{video_id}.mp3")
        import os
        if os.path.exists(out_path):
            return out_path

        strategies = [
            ["yt-dlp", "--cookies-from-browser", YTDLP_BROWSER,
             "--extractor-args", "youtube:player_client=default,android_vr",
             "-x", "--audio-format", "mp3", "--audio-quality", "0", "-o", out_path, url],
            ["yt-dlp", "--extractor-args", "youtube:player_client=android_vr",
             "-x", "--audio-format", "mp3", "--audio-quality", "0", "-o", out_path, url],
        ]

        last_error = None
        for cmd in strategies:
            try:
                subprocess.run(cmd, check=True, capture_output=True)
                return out_path
            except subprocess.CalledProcessError as e:
                last_error = e

        raise RuntimeError(f"Não foi possível baixar o áudio. Último erro: {last_error}")

    # ── Step 3: Gemini ─────────────────────────────────────────────────────────

    def call_gemini(self, transcription_text: str) -> list[dict]:
        prompt = self.prompt_template.format(
            transcription=transcription_text,
            min_words=self.min_words,
            max_words=self.max_words,
            min_duration=self.min_duration,
            max_duration=self.max_duration,
        )
        return self.gemini.generate_json(prompt)

    # ── Step 4: corte de áudio ─────────────────────────────────────────────────

    def cut_audio(self, source_mp3: str, start: float, end: float, out_path: str):
        from pydub import AudioSegment
        audio = AudioSegment.from_mp3(source_mp3)
        audio[int(start * 1000):int(end * 1000)].export(out_path, format="mp3")

    # ── Step 5: build JSON ─────────────────────────────────────────────────────

    def build_scenes(self, scenes_text: list[str]) -> list[dict]:
        merged, buffer = [], ""
        for block in scenes_text:
            block = block.strip()
            if not block:
                continue
            combined = (buffer + " " + block).strip() if buffer else block
            if len(combined.split()) < self.min_words:
                buffer = combined
            else:
                merged.append(combined)
                buffer = ""
        if buffer:
            if merged:
                merged[-1] = (merged[-1] + " " + buffer).strip()
            else:
                merged.append(buffer)

        return [
            {"id": str(i).zfill(4), "narration": {"text": text, "subtitles": True}}
            for i, text in enumerate(merged, 1)
        ]

    def build_json(self, clip: dict, audio_filename: str) -> dict:
        title = clip["title"]
        scenes = self.build_scenes(clip.get("scenes_text", []))

        return {
            "slug": self.slugify(title),
            "channel_name": self.channel_name,
            "output_ratio": "9:16",
            "global_settings": {
                "tts": {"provider": "local_file", "audio_file": f"./temp/{audio_filename}"}
            },
            "scenes": scenes,
            "youtube": {
                "title": f"🙏 {title.upper()} 🙏",
                "tags": ["devocional com jesus", "palavra de deus", "fe", "biblia", "versiculo biblico"],
                "description": (
                    '📖 Leia a Biblia diariamente.\n'
                    '🙏 Inscreva-se para receber a Palavra de Deus todo dia.'
                ),
                "publish_at": self.today_publish_at(),
            },
        }

    # ── Pipeline com banco ─────────────────────────────────────────────────────

    def load_existing(self, video_id: str) -> dict | None:
        """Retorna os dados do banco se o video_id já foi processado, None caso contrário."""
        record = get_pipeline(video_id)
        if record is None:
            return None
        return record.to_dict()

    def process(self, url: str, video_id: str, transcription_text: str) -> dict:
        audio_path = self.download_audio(url, video_id)
        clips = self.call_gemini(transcription_text)

        upsert_pipeline(
            video_id=video_id,
            gemini_json=clips,
        )

        return {"audio_path": audio_path, "clips": clips}

    def save_transcript(self, video_id: str, transcript: list[dict]):
        upsert_pipeline(video_id=video_id, transcript_json=transcript)

    def save_curation(self, video_id: str, curated_clips: list[dict]):
        upsert_pipeline(video_id=video_id, curation_json=curated_clips)

    def generate(self, audio_path: str, clips: list[dict], video_id: str = None) -> list[dict]:
        results = []
        for n, clip in enumerate(clips, 1):
            slug = self.slugify(clip["title"])
            filename = f"clip_{n:02d}_{slug[:40]}.mp3"
            clip_path = str(self.temp_dir / filename)

            try:
                self.cut_audio(audio_path, clip["start_time"], clip["end_time"], clip_path)
            except Exception as e:
                results.append({"clip_number": n, "error": str(e)})
                continue

            doc = self.build_json(clip, filename)
            results.append({"clip_number": n, "json_path": self._save_clip_json(doc, n), "data": doc})

        if video_id:
            exported = [r["data"] for r in results if "data" in r]
            upsert_pipeline(video_id=video_id, exported_jsons=exported)

        return results

    def save_consolidated(self, video_id: str, clips_data: list[dict]) -> str:
        path = str(self.jsons_dir / f"{video_id}.json")
        docs = [c["data"] for c in clips_data if "data" in c]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(docs, f, ensure_ascii=False, indent=2)
        return path

    def _save_clip_json(self, doc: dict, clip_number: int) -> str:
        path = str(self.temp_dir / f"clip_{clip_number:02d}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        return path
