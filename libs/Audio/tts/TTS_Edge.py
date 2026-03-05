import os
import asyncio
from pathlib import Path
from mutagen.mp3 import MP3
import edge_tts


def ms_to_srt_time(ms: float) -> str:
    total_seconds = int(ms // 1000)
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    ms_remainder = int(ms % 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms_remainder:03d}"


class EdgeTTS:
    """
    Gera áudio e SRT usando Microsoft Edge TTS.
    Responsabilidade: síntese apenas.
    Remoção de silêncios é responsabilidade do NarrationEngine.
    """

    GENDER_MAP = {"Male": "masculino", "Female": "feminino"}

    def __init__(self, params=None):
        defaults = {
            "text_narration_filename": os.getenv("TEXT_NARRATION_FILE", "texto.txt"),
            "voice_id":        os.getenv("EDGE_TTS_VOICE", "pt-BR-AntonioNeural"),
            "audio_format":    "mp3",
            "output_basename": "narration",
            "text":            None,
            "rate":            "+15%",
            "pitch":           "+0Hz",
        }
        if params:
            defaults.update(params)
        for k, v in defaults.items():
            setattr(self, k, v)

        self.text_file_path = Path(self.text_narration_filename)
        if self.text is None and self.text_file_path.exists():
            self.text = self.text_file_path.read_text(encoding="utf-8").strip()

    # ------------------------------------------------------------------
    # LISTAR VOZES
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
                end_ms   = start_ms + (chunk["duration"] / D)
                word_boundaries.append({"word": chunk["text"], "start": start_ms, "end": end_ms})

        word_boundaries.sort(key=lambda x: x["start"])
        return audio_data, word_boundaries

    def _generate_srt_word_by_word(self, word_boundaries: list) -> str:
        srt_path = f"{self.output_basename}.srt"
        with open(srt_path, "w", encoding="utf-8") as f:
            for i, w in enumerate(word_boundaries, 1):
                start = max(0, w["start"])
                end   = max(start + 100, w["end"])
                f.write(f"{i}\n")
                f.write(f"{ms_to_srt_time(start)} --> {ms_to_srt_time(end)}\n")
                f.write(f"{w['word']}\n\n")
        return srt_path

    def generate_audio_and_subtitles(self) -> dict:
        """
        Sintetiza texto e gera SRT com word boundaries reais do Edge TTS.
        NÃO remove silêncios — responsabilidade do NarrationEngine.

        Returns:
            {
                "audio_file":           str,
                "subtitle_file":        str,
                "audio_total_duration": float,
                "word_boundaries":      list,  # [{"word", "start", "end"}] em ms
            }
        """
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

        # Salva áudio bruto
        target_dir = os.path.dirname(self.output_basename) or "."
        os.makedirs(target_dir, exist_ok=True)
        audio_path = f"{self.output_basename}.{self.audio_format}"
        with open(audio_path, "wb") as f:
            f.write(audio_data)

        # SRT com boundaries originais (sem ajuste de silêncio)
        srt_file = self._generate_srt_word_by_word(word_boundaries)
        duration = MP3(str(audio_path)).info.length

        return {
            "audio_file":           audio_path,
            "subtitle_file":        srt_file,
            "audio_total_duration": duration,
            "word_boundaries":      word_boundaries,
        }
