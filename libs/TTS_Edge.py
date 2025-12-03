import os
import io
import asyncio
from pathlib import Path
from mutagen.mp3 import MP3
from pydub import AudioSegment, silence
import edge_tts
import tempfile


def ms_to_srt_time(ms: float) -> str:
    total_seconds = int(ms // 1000)
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    ms_remainder = int(ms % 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms_remainder:03d}"


class EdgeTTS:
    def __init__(self, params=None):
        defaults = {
            "text_narration_filename": os.getenv("TEXT_NARRATION_FILE", "texto.txt"),
            "voice_id": os.getenv("EDGE_TTS_VOICE", "pt-BR-AntonioNeural"),
            "audio_format": "mp3",
            "output_basename": "narration",
            "text": None,
            "silence_thresh": -40,
            "min_silence_len": 400,
            "keep_silence": 275,
        }
        if params:
            defaults.update(params)
        for k, v in defaults.items():
            setattr(self, k, v)

        self.text_file_path = Path(self.text_narration_filename)
        if self.text is None and self.text_file_path.exists():
            self.text = self.text_file_path.read_text(encoding="utf-8").strip()

    async def _synthesize_audio_async(self):
        if not self.text:
            raise ValueError("Nenhum texto disponível para síntese.")

        communicate = edge_tts.Communicate(
            self.text,
            self.voice_id,
            rate="+15%",
            boundary="WordBoundary"
        )

        word_boundaries = []
        audio_data = b""

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
            elif chunk["type"] == "WordBoundary":
                D = 10000
                start_ms = chunk["offset"] / D
                end_ms = start_ms + (chunk["duration"] / D)
                word_boundaries.append({
                    "word": chunk["text"],
                    "start": start_ms,
                    "end": end_ms
                })

        # print(word_boundaries) # Debug opcional

        return audio_data, word_boundaries

    def _remove_silences(self, audio_data, word_boundaries):
        # GARANTIA: Usa o mesmo diretório do arquivo final para o temporário
        target_dir = os.path.dirname(self.output_basename)
        if not target_dir: target_dir = "."
        
        os.makedirs(target_dir, exist_ok=True)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False, dir=target_dir) as tmp:
            tmp.write(audio_data)
            tmp.flush()
            tmp_path = tmp.name

        audio = AudioSegment.from_file(tmp_path)
        os.remove(tmp_path)

        non_silence_ranges = silence.detect_nonsilent(
            audio,
            min_silence_len=self.min_silence_len,
            silence_thresh=self.silence_thresh
        )

        new_audio = AudioSegment.empty()
        adjusted_boundaries = []
        current_time = 0
        
        # Conjunto para evitar duplicar palavras se houver sobreposição estranha
        processed_words_indices = set()

        # Tolerância em ms para "salvar" palavras que começam um pouco antes ou terminam um pouco depois
        # do corte seco do silêncio.
        TOLERANCE = 150 

        for start, end in non_silence_ranges:
            # O segmento de áudio inclui o keep_silence no final
            segment_end_extended = end + self.keep_silence
            segment = audio[start:segment_end_extended]
            new_audio += segment

            for i, w in enumerate(word_boundaries):
                if i in processed_words_indices:
                    continue

                # CORREÇÃO PRINCIPAL:
                # 1. Usa segment_end_extended (pois o áudio existe até lá)
                # 2. Adiciona TOLERANCE para pegar palavras que o pydub cortou o "rabinho" (fade out)
                # 3. Adiciona TOLERANCE no início para pegar ataques suaves
                
                word_starts_in_segment = w["start"] >= (start - TOLERANCE)
                word_ends_in_segment = w["end"] <= (segment_end_extended + TOLERANCE)

                if word_starts_in_segment and word_ends_in_segment:
                    # Calcula o novo tempo relativo
                    # max(0, ...) evita tempo negativo se a tolerância pegou algo antes
                    offset_start = max(0, w["start"] - start)
                    duration = w["end"] - w["start"]
                    
                    new_start = current_time + offset_start
                    new_end = new_start + duration

                    adjusted_boundaries.append({
                        "word": w["word"],
                        "start": new_start,
                        "end": new_end
                    })
                    processed_words_indices.add(i)

            current_time += len(segment)

        adjusted_boundaries.sort(key=lambda x: x["start"])

        final_path = f"{self.output_basename}.{self.audio_format}"
        new_audio.export(final_path, format=self.audio_format, bitrate="192k")
        return final_path, adjusted_boundaries

    def _generate_srt_word_by_word(self, word_boundaries):
        srt_path = f"{self.output_basename}.srt"
        with open(srt_path, "w", encoding="utf-8") as f:
            for i, w in enumerate(word_boundaries, 1):
                start = max(0, w['start'])
                # Garante duração mínima para não piscar na tela
                end = max(start + 100, w['end']) 
                
                f.write(f"{i}\n")
                f.write(f"{ms_to_srt_time(start)} --> {ms_to_srt_time(end)}\n")
                f.write(f"{w['word']}\n\n")
        return srt_path

    def generate_audio_and_subtitles(self):
        audio_data, word_boundaries = asyncio.get_event_loop().run_until_complete(
            self._synthesize_audio_async()
        )
        
        # Remove silêncios e ajusta legendas
        final_audio, new_boundaries = self._remove_silences(audio_data, word_boundaries)
        
        # [REMOVIDO] O exit() e prints de debug que paravam a execução
        # print(new_boundaries) 
        
        srt_file = self._generate_srt_word_by_word(new_boundaries)
        duration = MP3(str(final_audio)).info.length
        
        return {
            "audio_file": str(final_audio),
            "subtitle_file": str(srt_file),
            "audio_total_duration": duration,
            "word_boundaries": new_boundaries
        }