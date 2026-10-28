"""Efeito de voz da narração: montagem do filtro e preservação da duração.

    pytest tests/test_voice_fx.py -q
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from libs.Audio.VoiceFx import VoiceFx   # noqa: E402


@pytest.fixture()
def voice_24k(tmp_path):
    # 24 kHz como o Edge — pega o bug de asetrate sem aresample antes
    from pydub.generators import Sine
    path = tmp_path / "narration.mp3"
    Sine(220).to_audio_segment(duration=2000).set_frame_rate(24000).export(path, format="mp3")
    return str(path)


def test_desabilitado_nao_toca_no_arquivo(voice_24k, tmp_path):
    out = str(tmp_path / "out.mp3")
    for cfg in (None, {}, {"enabled": False, "pitch_shift": 0.9}):
        r = VoiceFx.process(voice_24k, out, cfg)
        assert r == {"audio_path": voice_24k, "applied": False}
    assert not os.path.exists(out)


def test_filtro_pitch_e_compressor():
    af = VoiceFx.build_filter({"pitch_shift": 0.9, "compressor": {"ratio": 6, "threshold_db": -20}})
    assert af.startswith("aresample=44100,asetrate=44100*0.9,aresample=44100,atempo=1.111111")
    assert "acompressor=threshold=0.100000:ratio=6:attack=20:release=250:makeup=1" in af


def test_compressor_atalho_e_pitch_neutro():
    assert VoiceFx.build_filter({"compressor": 4}).startswith("acompressor=")
    assert VoiceFx.build_filter({"pitch_shift": 1.0}) == ""


def test_atempo_encadeia_fora_do_intervalo():
    assert VoiceFx._atempo_chain(4.0) == "atempo=2.0,atempo=2.000000"
    assert VoiceFx._atempo_chain(0.25) == "atempo=0.5,atempo=0.500000"


def test_pitch_shift_invalido():
    with pytest.raises(ValueError):
        VoiceFx.build_filter({"pitch_shift": 0})


def test_preserva_duracao(voice_24k, tmp_path):
    from pydub import AudioSegment
    out = str(tmp_path / "out_fx.mp3")
    r = VoiceFx.process(voice_24k, out, {"enabled": True, "pitch_shift": 0.85, "compressor": 4})
    assert r == {"audio_path": out, "applied": True}
    before = len(AudioSegment.from_file(voice_24k))
    after = len(AudioSegment.from_file(out))
    assert abs(after - before) < 60   # ms — só padding de frame MP3
