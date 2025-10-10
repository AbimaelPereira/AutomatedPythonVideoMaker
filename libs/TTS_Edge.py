# libs/EdgeTTS.py
import os
import asyncio
from pathlib import Path
from mutagen.mp3 import MP3
import edge_tts


def ms_to_srt_time(ms: float) -> str:
    """Converte milissegundos para o formato SRT hh:mm:ss,ms"""
    total_seconds = int(ms // 1000)
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    ms_remainder = int(ms % 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms_remainder:03d}"


class EdgeTTS:
    def __init__(self, params=None):
        defaults = {
            "temp_dir": os.getenv("TEMP_DIR", "./temp_files"),
            "text_narration_filename": os.getenv("TEXT_NARRATION_FILE", "texto.txt"),
            "voice_id": os.getenv("EDGE_TTS_VOICE", "pt-BR-ThalitaNeural"),
            "audio_format": "mp3",
            "output_basename": "narration",
            "text": None,
            # "ssml": False,
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

    async def _synthesize_audio_async(self):
        if not self.text:
            raise ValueError("Nenhum texto disponível para síntese.")

        output_path = self.temp_dir / f"{self.output_basename}.{self.audio_format}"

        communicate = edge_tts.Communicate(
            self.text,
            self.voice_id,
            rate="+15%",
            # ssml=self.ssml,
            boundary="WordBoundary"
        )

        word_boundaries = []

        # Abre o arquivo de áudio para escrita
        with open(output_path, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":

                    D = 10000
                    start_ms = chunk["offset"] / D
                    end_ms = start_ms + (chunk["duration"] / D)
                    word_boundaries.append({
                        "word": chunk["text"],
                        "start": start_ms,
                        "end": end_ms
                    })
        return output_path, word_boundaries

    def _generate_srt_word_by_word(self, word_boundaries):
        if not word_boundaries:
            raise ValueError("Nenhum boundary de palavra disponível para gerar SRT.")

        srt_path = self.temp_dir / f"{self.output_basename}.srt"
        index = 1

        with open(srt_path, "w", encoding="utf-8") as f:
            for w in word_boundaries:
                f.write(f"{index}\n")
                f.write(f"{ms_to_srt_time(w['start'])} --> {ms_to_srt_time(w['end'])}\n")
                f.write(f"{w['word']}\n\n")
                index += 1

        return srt_path

    def generate_audio_and_subtitles(self):
        # Gera áudio e captura os word boundaries
        output_path, word_boundaries = asyncio.get_event_loop().run_until_complete(
            self._synthesize_audio_async()
        )

        # Gera SRT palavra por palavra
        srt_file = self._generate_srt_word_by_word(word_boundaries)

        # Obtém duração total do áudio
        duration = MP3(str(output_path)).info.length

        return {
            "audio_file": str(output_path),
            "subtitle_file": str(srt_file),
            "audio_total_duration": duration
        }
    

if __name__ == "__main__":
    text = """<speak version="1.0" xml:lang="pt-BR">
  <voice name="pt-BR-AntonioNeural">
    <prosody rate="+20%" pitch="+5%" volume="+3dB">
      Olá! Eu sou o Antônio. Agora falando mais rápido, com tom agudo e volume mais alto.
    </prosody>
    <prosody rate="-20%" pitch="-5%" volume="-6dB">
      Agora mais lento, mais grave e com volume mais baixo.
    </prosody>
  </voice>
</speak>"""

    tts = EdgeTTS({
        "text": text,
        "voice_id": "pt-BR-AntonioNeural",
        "output_basename": "demo_ssml"
    })
    result = tts.generate_audio_and_subtitles()
    print(result)