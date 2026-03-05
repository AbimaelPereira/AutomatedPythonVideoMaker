"""
SilenceRemover — Remove silêncios de áudio com re-alinhamento de word boundaries.

Uso standalone:
    from libs.SilenceRemover import SilenceRemover

    result = SilenceRemover.process(
        audio_path="narration.mp3",
        output_path="narration_clean.mp3",
        word_boundaries=[...],          # opcional — lista de {"word", "start", "end"} em ms
        silence_removal_config={        # vem direto do JSON tts.silence_removal
            "enabled": True,
            "preset": "normal"
            # ou: "silence_thresh": -50, "min_silence_len": 800, "keep_silence": 80
        }
    )
    # result = {"audio_path": str, "word_boundaries": list, "removed": bool}

Integração nos engines TTS:
    - TTS_Edge.py      → passa word_boundaries reais (word-boundary events)
    - TTS_GoogleCloud  → passa word_boundaries estimados (ou None)
"""

import os
import tempfile
from pydub import AudioSegment, silence as pydub_silence
from mutagen.mp3 import MP3


# ==============================================================================
# Presets
# ==============================================================================
PRESETS = {
    # Corte agressivo — ideal para Shorts onde cada ms conta
    "tight": {
        "silence_thresh":  -45,   # dBFS — detecta silêncios menos profundos
        "min_silence_len":  600,  # ms  — corta pausas curtas também
        "keep_silence":      50,  # ms  — deixa só uma borda mínima
    },
    # Balanceado — uso geral, narração normal
    "normal": {
        "silence_thresh":  -50,
        "min_silence_len":  900,
        "keep_silence":     80,
    },
    # Preserva pausas — entrevistas, narração dramática, respirações intencionais
    "relaxed": {
        "silence_thresh":  -55,   # só silêncios muito profundos
        "min_silence_len": 1500,  # ignora pausas curtas
        "keep_silence":    150,   # mantém bordas maiores
    },
}


class SilenceRemover:
    """Remove silêncios de um arquivo de áudio e re-alinha word boundaries."""

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    @staticmethod
    def process(
        audio_path: str,
        output_path: str,
        word_boundaries: list = None,
        silence_removal_config: dict = None,
    ) -> dict:
        """
        Remove silêncios do áudio e re-alinha os word boundaries.

        Args:
            audio_path:             Caminho do MP3/WAV de entrada.
            output_path:            Caminho de saída (MP3).
            word_boundaries:        Lista de {"word", "start"(ms), "end"(ms)}.
                                    Pode ser None — neste caso só o áudio é processado.
            silence_removal_config: Dict vindo de tts.silence_removal no JSON.
                                    Se None ou {"enabled": false}, retorna sem processar.

        Returns:
            {
                "audio_path":       str,   # caminho do arquivo final
                "word_boundaries":  list,  # boundaries re-alinhados (ou originais)
                "removed":          bool,  # True se processamento foi aplicado
            }
        """
        cfg = silence_removal_config or {}

        # Se não habilitado ou config ausente → devolve sem tocar
        if not cfg.get("enabled", False):
            return {
                "audio_path":      audio_path,
                "word_boundaries": word_boundaries or [],
                "removed":         False,
            }

        params = SilenceRemover._resolve_params(cfg)
        audio  = AudioSegment.from_file(audio_path)

        ranges = SilenceRemover._detect_nonsilent(audio, params)

        # Nada a cortar
        if not ranges:
            return {
                "audio_path":      audio_path,
                "word_boundaries": word_boundaries or [],
                "removed":         False,
            }

        new_audio, adjusted_wb = SilenceRemover._rebuild(
            audio, ranges, word_boundaries or [], params["keep_silence"]
        )

        # Só salva se realmente cortou algo
        original_len = len(audio)
        new_len      = len(new_audio)
        if new_len >= original_len:
            return {
                "audio_path":      audio_path,
                "word_boundaries": word_boundaries or [],
                "removed":         False,
            }

        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        new_audio.export(output_path, format="mp3", bitrate="192k")

        removed_ms = original_len - new_len
        print(
            f"[SilenceRemover] ✂️  {removed_ms}ms removidos  "
            f"({original_len}ms → {new_len}ms)"
        )

        return {
            "audio_path":      output_path,
            "word_boundaries": adjusted_wb,
            "removed":         True,
        }

    # ------------------------------------------------------------------
    # Resolução de parâmetros
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_params(cfg: dict) -> dict:
        """
        Resolve parâmetros finais, dando prioridade a:
          1. valores explícitos no cfg
          2. preset nomeado
          3. preset "normal" como fallback
        """
        preset_name = cfg.get("preset", "normal")
        base        = dict(PRESETS.get(preset_name, PRESETS["normal"]))

        # Valores explícitos sobrescrevem o preset
        for key in ("silence_thresh", "min_silence_len", "keep_silence"):
            if key in cfg:
                base[key] = cfg[key]

        return base

    # ------------------------------------------------------------------
    # Detecção de regiões não-silenciosas
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_nonsilent(audio: AudioSegment, params: dict) -> list:
        """
        Detecta regiões não-silenciosas com margem de segurança.

        Retorna lista de (start_ms, end_ms) já com keep_silence aplicado
        e bordas unificadas quando estão muito próximas (evita cortes errados).
        """
        keep = params["keep_silence"]

        raw_ranges = pydub_silence.detect_nonsilent(
            audio,
            min_silence_len=params["min_silence_len"],
            silence_thresh=params["silence_thresh"],
        )

        if not raw_ranges:
            return []

        # Expande cada segmento com keep_silence nas duas bordas
        expanded = []
        audio_len = len(audio)
        for start, end in raw_ranges:
            s = max(0,         start - keep)
            e = min(audio_len, end   + keep)
            expanded.append((s, e))

        # Mescla segmentos sobrepostos ou muito próximos (gap < keep*2)
        # Evita criar buracos artificiais no meio de falas
        merged = [expanded[0]]
        for s, e in expanded[1:]:
            prev_s, prev_e = merged[-1]
            gap = s - prev_e
            if gap <= keep * 2:
                merged[-1] = (prev_s, max(prev_e, e))
            else:
                merged.append((s, e))

        return merged

    # ------------------------------------------------------------------
    # Reconstrução do áudio e re-alinhamento de word boundaries
    # ------------------------------------------------------------------

    @staticmethod
    def _rebuild(
        audio: AudioSegment,
        ranges: list,
        word_boundaries: list,
        keep_silence: int,
    ):
        """
        Concatena apenas os segmentos não-silenciosos e re-mapeia
        cada word boundary para o novo timeline.

        Estratégia de mapeamento:
        - Cada palavra pertence ao segmento que contém seu ponto médio.
        - Palavras que caíam em silêncio removido são descartadas
          (situação rara com presets bem calibrados).
        - Tolerance generosa para não perder palavras nas bordas.
        """
        new_audio     = AudioSegment.empty()
        current_ms    = 0          # cursor no novo timeline
        segment_map   = []         # [(orig_start, orig_end, new_start)]

        for orig_start, orig_end in ranges:
            segment_map.append((orig_start, orig_end, current_ms))
            new_audio  += audio[orig_start:orig_end]
            current_ms += (orig_end - orig_start)

        if not word_boundaries:
            return new_audio, []

        # Re-alinha cada word boundary
        adjusted = []
        TOLERANCE = keep_silence + 30   # margem extra nas bordas de segmento

        for w in word_boundaries:
            w_mid = (w["start"] + w["end"]) / 2

            best_seg   = None
            best_dist  = float("inf")

            for orig_start, orig_end, new_start in segment_map:
                lo = orig_start - TOLERANCE
                hi = orig_end   + TOLERANCE

                if lo <= w_mid <= hi:
                    # Ponto médio está dentro (ou na borda) do segmento
                    dist = 0
                else:
                    dist = min(abs(w_mid - orig_start), abs(w_mid - orig_end))

                if dist < best_dist:
                    best_dist = dist
                    best_seg  = (orig_start, orig_end, new_start)

            # Descarta se estava claramente no silêncio (> 2× tolerance)
            if best_dist > TOLERANCE * 2:
                continue

            orig_start, orig_end, new_start = best_seg

            # Calcula offset dentro do segmento (clampado nas bordas)
            offset_start = max(0, min(w["start"] - orig_start, orig_end - orig_start))
            offset_end   = max(0, min(w["end"]   - orig_start, orig_end - orig_start))

            # Garante duração mínima de 80ms para não criar legendas invisíveis
            new_w_start = new_start + offset_start
            new_w_end   = new_start + offset_end
            if new_w_end - new_w_start < 80:
                new_w_end = new_w_start + 80

            adjusted.append({
                "word":  w["word"],
                "start": new_w_start,
                "end":   new_w_end,
            })

        adjusted.sort(key=lambda x: x["start"])
        return new_audio, adjusted
