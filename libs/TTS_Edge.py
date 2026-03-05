import os
import asyncio
import time
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
    GENDER_MAP = {"Male": "masculino", "Female": "feminino"}

    def __init__(self, params=None):
        defaults = {
            "text_narration_filename": os.getenv("TEXT_NARRATION_FILE", "texto.txt"),
            "voice_id":    os.getenv("EDGE_TTS_VOICE", "pt-BR-AntonioNeural"),
            "audio_format": "mp3",
            "output_basename": "narration",
            "text": None,
            "silence_thresh": -50,
            "min_silence_len": 1200,
            "keep_silence": 100,
            "rate":  "+15%",
            "pitch": "+0Hz",
        }
        if params:
            defaults.update(params)
        for k, v in defaults.items():
            setattr(self, k, v)

        self.text_file_path = Path(self.text_narration_filename)
        if self.text is None and self.text_file_path.exists():
            self.text = self.text_file_path.read_text(encoding="utf-8").strip()

    # ------------------------------------------------------------------
    # LISTAR / AUDITAR VOZES
    # ------------------------------------------------------------------

    @staticmethod
    async def _fetch_voices_async() -> list:
        return await edge_tts.list_voices()

    @staticmethod
    def _get_all_voices() -> list:
        try:
            loop = asyncio.get_running_loop()
            try:
                import nest_asyncio
                nest_asyncio.apply()
            except ImportError:
                pass
            return loop.run_until_complete(EdgeTTS._fetch_voices_async())
        except RuntimeError:
            return asyncio.run(EdgeTTS._fetch_voices_async())

    @staticmethod
    def list_voices(
        language: str = "pt-BR",
        gender: str = None,
        generate_audio: bool = False,
        text: str = "Olá! Esta é uma demonstração de voz.",
        output_dir: str = "test_voices/edge",
        rate: str = "+15%",
        pitch: str = "+0Hz",
    ) -> list:
        """
        Lista vozes disponíveis no Edge TTS.

        Args:
            language:       Filtro de idioma (default "pt-BR"). Use "" para todas.
            gender:         "masculino", "feminino" ou None para ambos.
            generate_audio: Se True, gera um MP3 de demonstração para cada voz.
            text:           Texto narrado quando generate_audio=True.
            output_dir:     Diretório de saída dos áudios gerados.
            rate:           Velocidade para os demos (ex: "+15%").
            pitch:          Tom para os demos (ex: "+0Hz").

        Returns:
            Lista de dicts com informações das vozes filtradas.
        """
        all_voices = EdgeTTS._get_all_voices()

        if language:
            all_voices = [v for v in all_voices if language.lower() in v["Locale"].lower()]

        if gender:
            gender_en = "Male" if gender.lower() in ("masculino", "male", "m") else "Female"
            all_voices = [v for v in all_voices if v.get("Gender") == gender_en]

        if not all_voices:
            print("[EdgeTTS] Nenhuma voz encontrada com os filtros aplicados.")
            return []

        print(f"\n[EdgeTTS] 🎙️  Vozes disponíveis "
              f"({language or 'todas'}"
              f"{', ' + gender if gender else ''}):\n")

        for v in sorted(all_voices, key=lambda x: x["ShortName"]):
            g = EdgeTTS.GENDER_MAP.get(v.get("Gender", ""), "?")
            print(f"  {v['ShortName']:<42} {g}")

        print(f"\n  Total: {len(all_voices)} voz(es)\n")

        if not generate_audio:
            return all_voices

        os.makedirs(output_dir, exist_ok=True)
        print(f"[EdgeTTS] 🔊 Gerando demos em: {output_dir}\n")

        results = []
        for v in sorted(all_voices, key=lambda x: x["ShortName"]):
            voice_name = v["ShortName"]
            safe_name  = voice_name.replace("-", "_")
            out_base   = os.path.join(output_dir, safe_name)
            g = EdgeTTS.GENDER_MAP.get(v.get("Gender", ""), "?")

            try:
                tts = EdgeTTS(params={
                    "voice_id": voice_name,
                    "text": text,
                    "output_basename": out_base,
                    "rate": rate,
                    "pitch": pitch,
                })
                result = tts.generate_audio_and_subtitles()
                print(f"  ✅ {voice_name:<42} {g:<12} → {os.path.basename(result['audio_file'])}")
                results.append({"voice": voice_name, "gender": g, **result})
            except Exception as e:
                print(f"  ❌ {voice_name:<42} Erro: {e}")

        print(f"\n[EdgeTTS] Concluído. {len(results)}/{len(all_voices)} áudios gerados.\n")
        return results

    # ------------------------------------------------------------------
    # SÍNTESE
    # ------------------------------------------------------------------

    async def _synthesize_audio_async(self):
        if not self.text:
            raise ValueError("Nenhum texto disponível para síntese.")

        communicate = edge_tts.Communicate(
            self.text,
            self.voice_id,
            rate=self.rate,
            pitch=self.pitch,
            boundary="WordBoundary"
        )

        word_boundaries = []
        audio_data = b""

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
            elif chunk["type"] == "WordBoundary":
                if "offset" not in chunk or "duration" not in chunk or "text" not in chunk:
                    continue
                D = 10000
                start_ms = chunk["offset"] / D
                end_ms = start_ms + (chunk["duration"] / D)
                word_boundaries.append({"word": chunk["text"], "start": start_ms, "end": end_ms})

        word_boundaries.sort(key=lambda x: x["start"])
        return audio_data, word_boundaries

    def _remove_silences(self, audio_data, word_boundaries):
        target_dir = os.path.dirname(self.output_basename) or "."
        os.makedirs(target_dir, exist_ok=True)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False, dir=target_dir) as tmp:
            tmp.write(audio_data)
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
        processed = set()
        TOLERANCE = 150

        for start, end in non_silence_ranges:
            seg_end = end + self.keep_silence
            segment = audio[start:seg_end]
            new_audio += segment

            for i, w in enumerate(word_boundaries):
                if i in processed:
                    continue
                if w["start"] >= (start - TOLERANCE) and w["end"] <= (seg_end + TOLERANCE):
                    offset = max(0, w["start"] - start)
                    dur = w["end"] - w["start"]
                    adjusted_boundaries.append({
                        "word": w["word"],
                        "start": current_time + offset,
                        "end": current_time + offset + dur
                    })
                    processed.add(i)

            current_time += len(segment)

        adjusted_boundaries.sort(key=lambda x: x["start"])
        final_path = f"{self.output_basename}.{self.audio_format}"
        new_audio.export(final_path, format=self.audio_format, bitrate="192k")
        return final_path, adjusted_boundaries

    def _generate_srt_word_by_word(self, word_boundaries):
        srt_path = f"{self.output_basename}.srt"
        with open(srt_path, "w", encoding="utf-8") as f:
            for i, w in enumerate(word_boundaries, 1):
                start = max(0, w["start"])
                end   = max(start + 100, w["end"])
                f.write(f"{i}\n")
                f.write(f"{ms_to_srt_time(start)} --> {ms_to_srt_time(end)}\n")
                f.write(f"{w['word']}\n\n")
        return srt_path

    def generate_audio_and_subtitles(self):
        try:
            loop = asyncio.get_running_loop()
            try:
                import nest_asyncio
                nest_asyncio.apply()
            except ImportError:
                pass
            audio_data, word_boundaries = loop.run_until_complete(self._synthesize_audio_async())
        except RuntimeError:
            audio_data, word_boundaries = asyncio.run(self._synthesize_audio_async())

        if not word_boundaries:
            raise ValueError("Nenhum word boundary retornado pelo Edge TTS")

        final_audio, new_boundaries = self._remove_silences(audio_data, word_boundaries)
        srt_file = self._generate_srt_word_by_word(new_boundaries)
        duration = MP3(str(final_audio)).info.length

        return {
            "audio_file": str(final_audio),
            "subtitle_file": str(srt_file),
            "audio_total_duration": duration,
            "word_boundaries": new_boundaries
        }
