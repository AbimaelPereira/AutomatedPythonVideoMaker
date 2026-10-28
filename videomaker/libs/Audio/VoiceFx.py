"""
VoiceFx — Efeitos de timbre na narração (pitch shift + compressor) via ffmpeg.

Uso standalone:
    from libs.Audio.VoiceFx import VoiceFx

    result = VoiceFx.process(
        audio_path="narration.mp3",
        output_path="narration.mp3",    # pode ser o mesmo arquivo
        voice_fx_config={               # vem direto do JSON tts.voice_fx
            "enabled": True,
            "pitch_shift": 0.90,        # < 1 = mais grave, > 1 = mais agudo
            "compressor": {"ratio": 4}
        }
    )
    # result = {"audio_path": str, "applied": bool}

Os efeitos preservam a duração: o pitch shift troca a taxa de amostragem
(asetrate) e compensa o tempo com atempo. Por isso word_boundaries e SRT
continuam válidos e NÃO são remapeados.
"""

import os
import shutil
import subprocess
import tempfile


# Taxa de trabalho. O Edge gera 24 kHz — sem reamostrar antes, o asetrate
# assumiria a taxa errada e aceleraria o áudio.
WORK_RATE = 44100

COMPRESSOR_DEFAULTS = {
    "ratio":        4,
    "threshold_db": -18,   # dBFS a partir do qual comprime
    "attack":       20,    # ms
    "release":      250,   # ms
    "makeup":       1,     # ganho linear pós-compressão (1–64)
}


class VoiceFx:
    """Aplica pitch shift e compressor num arquivo de áudio."""

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    @staticmethod
    def process(audio_path: str, output_path: str, voice_fx_config: dict = None) -> dict:
        """
        Args:
            audio_path:      Caminho do MP3/WAV de entrada.
            output_path:     Caminho de saída (MP3). Pode ser igual a audio_path.
            voice_fx_config: Dict vindo de tts.voice_fx no JSON.
                             Se None ou {"enabled": false}, retorna sem processar.

        Returns:
            {"audio_path": str, "applied": bool}
        """
        cfg = voice_fx_config or {}
        if not cfg.get("enabled", False):
            return {"audio_path": audio_path, "applied": False}

        af = VoiceFx.build_filter(cfg)
        if not af:
            return {"audio_path": audio_path, "applied": False}

        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        # ffmpeg não lê e grava o mesmo arquivo — passa por um temporário
        fd, tmp_path = tempfile.mkstemp(suffix=".mp3", dir=out_dir or None)
        os.close(fd)
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", audio_path,
                 "-af", af, "-ar", str(WORK_RATE), "-b:a", "192k", tmp_path],
                check=True,
            )
            shutil.move(tmp_path, output_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        print(f"[VoiceFx] 🎛️  {af}")
        return {"audio_path": output_path, "applied": True}

    # ------------------------------------------------------------------
    # Montagem do filtro
    # ------------------------------------------------------------------

    @staticmethod
    def build_filter(cfg: dict) -> str:
        """Monta a cadeia -af do ffmpeg. String vazia = nada a aplicar."""
        filters = []

        shift = float(cfg.get("pitch_shift", 1.0))
        if shift <= 0:
            raise ValueError(f"voice_fx.pitch_shift precisa ser > 0 (recebido {shift})")
        if abs(shift - 1.0) > 1e-6:
            filters += [
                f"aresample={WORK_RATE}",
                f"asetrate={WORK_RATE}*{shift}",
                f"aresample={WORK_RATE}",
                VoiceFx._atempo_chain(1 / shift),
            ]

        comp = cfg.get("compressor")
        if comp:
            c = dict(COMPRESSOR_DEFAULTS)
            if isinstance(comp, dict):
                c.update(comp)
            else:
                c["ratio"] = comp   # atalho: "compressor": 4
            threshold = 10 ** (float(c["threshold_db"]) / 20)
            filters.append(
                f"acompressor=threshold={threshold:.6f}:ratio={c['ratio']}"
                f":attack={c['attack']}:release={c['release']}:makeup={c['makeup']}"
            )

        return ",".join(filters)

    @staticmethod
    def _atempo_chain(factor: float) -> str:
        """atempo aceita 0.5–2.0 por instância; encadeia para fatores maiores."""
        parts = []
        while factor > 2.0:
            parts.append("atempo=2.0")
            factor /= 2.0
        while factor < 0.5:
            parts.append("atempo=0.5")
            factor /= 0.5
        parts.append(f"atempo={factor:.6f}")
        return ",".join(parts)
