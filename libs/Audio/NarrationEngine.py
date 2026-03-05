import os
from pathlib import Path
from moviepy.editor import AudioFileClip

from libs.Whisper.WhisperWorker import WhisperWorker
from libs.Audio.tts.TTS_Edge import EdgeTTS
from libs.Audio.tts.TTS_Polly import PollyTTS
from libs.Audio.tts.TTS_GoogleCloud import GoogleCloudTTS
from libs.Audio.SilenceRemover import SilenceRemover
from libs.Audio.AudioSegmenter import AudioSegmenter


def _ms_to_srt_time(ms: float) -> str:
    total_seconds = int(ms // 1000)
    h  = total_seconds // 3600
    m  = (total_seconds % 3600) // 60
    s  = total_seconds % 60
    ms_remainder = int(ms % 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms_remainder:03d}"


class NarrationEngine:
    """
    Gerenciador centralizado de narração.

    Fluxo por cena:
      1. Provider TTS gera áudio bruto + word_boundaries
      2. NarrationEngine aplica SilenceRemover no áudio (detecta silêncios no waveform)
      3. word_boundaries são remapeados para o novo timeline
      4. SRT é regravado com os timestamps ajustados
      5. Retorna AudioFileClip, duração e caminho do SRT final

    Providers: "edge" | "polly" | "google" | "local_file"

    Configuração de silêncio no JSON (dentro de "tts"):

        # Preset
        "silence_removal": { "enabled": true, "preset": "normal" }
        # Presets: "tight" | "normal" | "relaxed"

        # Parâmetros manuais
        "silence_removal": {
            "enabled": true,
            "silence_thresh": -50,
            "min_silence_len": 1000,
            "keep_silence": 100
        }

        # Desabilitado (ou chave ausente = mesmo efeito)
        "silence_removal": { "enabled": false }
    """

    def __init__(self, tts_config: dict, output_base_dir: str):
        self.tts_config      = tts_config
        self.output_base_dir = output_base_dir
        self.provider        = tts_config.get("provider", "edge")
        self.silence_removal = tts_config.get("silence_removal")  # None se ausente

    # ------------------------------------------------------------------
    # PRÉ-PROCESSAMENTO (narração local via Whisper)
    # ------------------------------------------------------------------

    @staticmethod
    def preprocess_scenes(params: dict = {}) -> list:
        """Pré-processa cenas com áudio local via Whisper + AudioSegmenter."""
        defaults = {
            "provider":        "local_file",
            "tts_config":      {},
            "scenes_data":     [],
            "output_base_dir": ""
        }
        for key, value in defaults.items():
            if key not in params:
                params[key] = value

        provider        = params["provider"]
        tts_config      = params["tts_config"]
        scenes_data     = params["scenes_data"]
        output_base_dir = params["output_base_dir"]

        if provider != "local_file":
            return scenes_data

        audio_file = tts_config.get("audio_file")
        if not audio_file or not os.path.exists(audio_file):
            raise FileNotFoundError(f"Arquivo de áudio não encontrado: {audio_file}")

        print(f"[NarrationEngine] Processando narração local: {audio_file}")

        whisper_model  = tts_config.get("whisper_model", "base")
        whisper_worker = WhisperWorker(model_size=whisper_model)
        srt_path       = audio_file.replace(".mp3", ".srt").replace(".wav", ".srt")
        whisper_worker.generate_srt(audio_file, srt_path)

        segmenter     = AudioSegmenter(audio_file, srt_path)
        segments_info = segmenter.segment_all_scenes(scenes_data, output_base_dir)

        for scene in scenes_data:
            scene_id = scene.get("id", "")
            if scene_id in segments_info:
                scene["narration"]["audio_file"]    = segments_info[scene_id]["audio_path"]
                scene["narration"]["subtitle_file"] = segments_info[scene_id]["srt_path"]

        return scenes_data

    # ------------------------------------------------------------------
    # PROCESSAMENTO POR CENA
    # ------------------------------------------------------------------

    def process_scene_narration(self, scene_data: dict, scene_dir: str):
        """
        Processa narração de uma cena.

        Returns:
            (AudioFileClip | None, duration: float, subtitle_path: str | None)
        """
        if self.provider == "local_file":
            return self._process_local_file(scene_data)

        narration_config = scene_data.get("narration", {})
        text = narration_config.get("text", "")

        if not text:
            print("[NarrationEngine] Cena sem narração. Duração será fixa.")
            return None, narration_config.get("duration", 4.0), None

        scene_id       = scene_data.get("id", "unknown")
        audio_basename = os.path.join(scene_dir, scene_id)

        # Provider: cena > global
        provider = scene_data.get("tts", {}).get("provider") or self.provider

        # silence_removal: cena > global (None = desabilitado)
        silence_removal = scene_data.get("tts", {}).get("silence_removal") or self.silence_removal

        print(f"[NarrationEngine] Gerando narração para cena '{scene_id}' [{provider}]...")

        try:
            # 1. Síntese (só gera áudio + word_boundaries)
            if provider == "edge":
                tts_result = self._synthesize_edge(text, scene_data, audio_basename)
            elif provider == "polly":
                tts_result = self._synthesize_polly(text, scene_data, audio_basename)
            elif provider == "google":
                tts_result = self._synthesize_google(text, scene_data, audio_basename)
            else:
                raise ValueError(f"Provider TTS não suportado: {provider}")

            # 2. Remoção de silêncios no waveform (opcional)
            #    Detecta silêncios diretamente no áudio — não usa o SRT como guia.
            #    Após o corte, remapeia os word_boundaries para o novo timeline.
            tts_result = self._apply_silence_removal(tts_result, audio_basename, silence_removal)

            # 3. Regrava SRT com timestamps finais
            if tts_result.get("word_boundaries"):
                subtitle_path = self._write_srt(
                    tts_result["word_boundaries"],
                    audio_basename
                )
                tts_result["subtitle_file"] = subtitle_path

            audio_clip = AudioFileClip(tts_result["audio_file"])
            duration   = float(audio_clip.duration or 4.0)

            return audio_clip, duration, tts_result.get("subtitle_file")

        except Exception as e:
            print(f"[NarrationEngine] ❌ Erro ao processar narração: {e}")
            import traceback
            traceback.print_exc()
            return None, 4.0, None

    # ------------------------------------------------------------------
    # PROVIDERS TTS (responsabilidade: só sintetizar)
    # ------------------------------------------------------------------

    def _synthesize_edge(self, text: str, scene_data: dict, audio_basename: str) -> dict:
        voice = (scene_data.get("tts", {}).get("voice") or
                 self.tts_config.get("voice") or
                 "pt-BR-AntonioNeural")
        rate  = (scene_data.get("tts", {}).get("rate") or
                 self.tts_config.get("rate") or "+15%")
        pitch = (scene_data.get("tts", {}).get("pitch") or
                 self.tts_config.get("pitch") or "+0Hz")

        tts = EdgeTTS(params={
            "text":            text,
            "voice_id":        voice,
            "output_basename": audio_basename,
            "rate":            rate,
            "pitch":           pitch,
        })
        return tts.generate_audio_and_subtitles()

    def _synthesize_polly(self, text: str, scene_data: dict, audio_basename: str) -> dict:
        voice = (scene_data.get("tts", {}).get("voice") or
                 self.tts_config.get("voice") or
                 "Camila")

        params = {
            "text":            text,
            "voice_id":        voice,
            "output_basename": audio_basename,
        }
        if "region" in self.tts_config:
            params["region"] = self.tts_config["region"]
        if "engine" in self.tts_config:
            params["engine"] = self.tts_config["engine"]

        tts = PollyTTS(params=params)
        return tts.generate_audio_and_subtitles()

    def _synthesize_google(self, text: str, scene_data: dict, audio_basename: str) -> dict:
        """
        Google Cloud TTS (Chirp3-HD, Neural2, WaveNet, Standard).

        Configuração no JSON:
        "tts": {
            "provider": "google",
            "credentials_file": "./tokens/credentials.json",
            "voice": "pt-BR-Chirp3-HD-Charon",
            "model": "Chirp3-HD",          // opcional — inferido da voz
            "speaking_rate": 1.15,         // ignorado pelo Chirp3-HD
            "pitch": 0.0,                  // ignorado pelo Chirp3-HD
            "volume_gain_db": 0.0,
            "silence_removal": { "enabled": true, "preset": "normal" }
        }
        Override por cena:
        "tts": { "voice": "pt-BR-Chirp3-HD-Aoede" }
        """
        scene_tts = scene_data.get("tts", {})

        voice = (scene_tts.get("voice") or
                 self.tts_config.get("voice") or
                 "pt-BR-Chirp3-HD-Charon")

        model = (scene_tts.get("model") or
                 self.tts_config.get("model") or
                 "Chirp3-HD")

        # Detecção automática do modelo pela voz
        if "Neural2"  in voice: model = "Neural2"
        elif "Wavenet" in voice: model = "WaveNet"
        elif "Standard" in voice: model = "Standard"

        params = {
            "text":              text,
            "voice_id":          voice,
            "model":             model,
            "output_basename":   audio_basename,
            "show_usage_report": False,
        }

        if "credentials_file" in self.tts_config:
            params["credentials_file"] = self.tts_config["credentials_file"]

        # Parâmetros numéricos do Google TTS.
        # Ignora valores em formato Edge (ex: "+0Hz", "+15%") que podem vir
        # do tts_config global quando o provider padrão é edge.
        def _safe_float(value):
            try:
                v = str(value)
                if "Hz" in v or "%" in v:
                    return None
                return float(v)
            except (ValueError, TypeError):
                return None

        for key in ("speaking_rate", "pitch", "volume_gain_db"):
            if key in self.tts_config:
                parsed = _safe_float(self.tts_config[key])
                if parsed is not None:
                    params[key] = parsed

        # Override por cena
        for key in ("speaking_rate", "pitch"):
            if key in scene_tts:
                parsed = _safe_float(scene_tts[key])
                if parsed is not None:
                    params[key] = parsed

        tts = GoogleCloudTTS(params=params)
        return tts.generate_audio_and_subtitles()

    # ------------------------------------------------------------------
    # REMOÇÃO DE SILÊNCIOS
    # ------------------------------------------------------------------

    def _apply_silence_removal(self, tts_result: dict, audio_basename: str, silence_removal: dict = None) -> dict:
        """
        Detecta silêncios diretamente no waveform do áudio gerado e os remove.
        Não usa o SRT como guia — o SRT é consequência, não entrada.

        silence_removal vem já resolvido (cena > global) pelo process_scene_narration.
        """
        if not silence_removal:
            return tts_result

        audio_path      = tts_result["audio_file"]
        word_boundaries = tts_result.get("word_boundaries")  # None para Google TTS

        sr_result = SilenceRemover.process(
            audio_path=audio_path,
            output_path=audio_path,
            word_boundaries=word_boundaries,
            silence_removal_config=silence_removal,
        )

        tts_result["audio_file"]      = sr_result["audio_path"]
        tts_result["word_boundaries"] = sr_result["word_boundaries"]
        return tts_result

    # ------------------------------------------------------------------
    # SRT FINAL
    # ------------------------------------------------------------------

    def _write_srt(self, word_boundaries: list, audio_basename: str) -> str:
        """Grava o SRT final com os timestamps ajustados pós remoção de silêncios."""
        srt_path = f"{audio_basename}.srt"
        with open(srt_path, "w", encoding="utf-8") as f:
            for i, w in enumerate(word_boundaries, 1):
                start = max(0, w["start"])
                end   = max(start + 100, w["end"])
                f.write(f"{i}\n")
                f.write(f"{_ms_to_srt_time(start)} --> {_ms_to_srt_time(end)}\n")
                f.write(f"{w['word']}\n\n")
        return srt_path

    # ------------------------------------------------------------------
    # LOCAL FILE
    # ------------------------------------------------------------------

    def _process_local_file(self, scene_data: dict):
        audio_file    = scene_data.get("narration", {}).get("audio_file")
        subtitle_file = scene_data.get("narration", {}).get("subtitle_file")

        if not audio_file or not os.path.exists(audio_file):
            print(f"[NarrationEngine] ⚠️ Áudio local não encontrado: {audio_file}")
            return None, 4.0, None

        audio_clip = AudioFileClip(audio_file)
        return audio_clip, float(audio_clip.duration or 4.0), subtitle_file

    # ------------------------------------------------------------------
    # VALIDAÇÃO
    # ------------------------------------------------------------------

    def validate_config(self) -> bool:
        providers = ["edge", "polly", "google", "local_file"]
        if self.provider not in providers:
            raise ValueError(f"Provider '{self.provider}' não suportado. Use: {providers}")

        if self.provider == "local_file":
            audio_file = self.tts_config.get("audio_file")
            if not audio_file:
                raise ValueError("audio_file é obrigatório para provider 'local_file'")
            if not os.path.exists(audio_file):
                raise FileNotFoundError(f"Arquivo de áudio não encontrado: {audio_file}")

        if self.provider == "google":
            creds = self.tts_config.get(
                "credentials_file",
                os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
            )
            if not creds or not os.path.exists(creds):
                raise FileNotFoundError(
                    f"credentials_file não encontrado: '{creds}'. "
                    "Defina em tts_config ou via GOOGLE_APPLICATION_CREDENTIALS."
                )

        if self.silence_removal:
            preset = self.silence_removal.get("preset")
            if preset and preset not in ("tight", "normal", "relaxed"):
                raise ValueError(
                    f"silence_removal.preset '{preset}' inválido. "
                    "Use: 'tight', 'normal' ou 'relaxed'."
                )

        return True
