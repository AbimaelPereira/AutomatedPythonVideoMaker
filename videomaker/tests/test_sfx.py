"""Efeitos sonoros das animações: schema, origem do som, deduplicação e mixagem.

    pytest tests/test_sfx.py -q
"""

import math
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from libs.Audio.SfxMixer import collect_events, mix   # noqa: E402
from libs.Motion.schema import validate                # noqa: E402

WORDS = [{"word": "ever", "start": 0.0, "end": 0.3},
         {"word": "had", "start": 0.3, "end": 0.5},
         {"word": "problem", "start": 0.6, "end": 1.0}]


@pytest.fixture()
def sounds(tmp_path):
    from pydub.generators import Sine
    folder = tmp_path / "pops"
    folder.mkdir()
    for n in range(2):
        Sine(880 + n * 100).to_audio_segment(duration=120).export(folder / f"p{n}.wav", format="wav")
    whoosh = tmp_path / "whoosh.wav"
    Sine(300).to_audio_segment(duration=300).export(whoosh, format="wav")
    return str(folder), str(whoosh)


def _scene(*elements, **extra):
    return {"id": "c1", "narration": {"text": "ever had problem"},
            "visual_elements": list(elements), **extra}


def test_schema_aceita_formas_validas():
    for sfx in ("assets/sfx/pop", {"source": "x.wav", "volume": 0.5, "offset": -0.1}, False):
        assert validate({"actions": [{"preset": "pop_in", "sfx": sfx}]}) == []


def test_schema_rejeita_campo_desconhecido_e_sem_source():
    errs = validate({"actions": [{"preset": "pop_in", "sfx": {"src": "x.wav"}}]})
    msgs = " ".join(str(e) for e in errs)
    assert "chave desconhecida 'src'" in msgs and "sfx sem 'source'" in msgs


def test_som_da_acao_e_default_do_preset(sounds):
    pops, whoosh = sounds
    gs = {"sfx": {"presets": {"pop_in": pops, "slide_in_*": {"source": whoosh, "volume": 0.5}}}}
    scene = _scene(
        {"type": "color", "motion": [{"at": {"word": "problem"}, "preset": "pop_in"}]},
        {"type": "color", "motion": [{"at": 0.2, "preset": "slide_in_left"}]},
        {"type": "color", "motion": [{"at": 0.4, "preset": "fade_in", "sfx": whoosh}]},
        {"type": "color", "motion": [{"at": 0.5, "preset": "pop_in", "sfx": False}]},
    )
    events = collect_events(scene=scene, effective_gs=gs, scene_duration=2.0, words=WORDS)
    assert [round(t, 2) for t, _, _ in events] == [0.2, 0.4, 0.6]
    assert events[0][1] == whoosh and math.isclose(events[0][2], 0.5 * 0.7)
    assert events[2][1].startswith(pops)


def test_mesmo_som_no_mesmo_instante_nao_dobra(sounds):
    _, whoosh = sounds
    scene = _scene(*[{"type": "color", "motion": [{"at": 0.5, "preset": "pop_in", "sfx": whoosh}]}] * 3)
    events = collect_events(scene=scene, effective_gs={}, scene_duration=2.0, words=WORDS)
    assert len(events) == 1


def test_eventos_avulsos_e_desligar(sounds):
    _, whoosh = sounds
    scene = _scene(sfx={"events": [{"at": {"word": "had"}, "source": whoosh, "offset": -0.1}]})
    events = collect_events(scene=scene, effective_gs={}, scene_duration=2.0, words=WORDS)
    assert [round(t, 2) for t, _, _ in events] == [0.2]
    off = collect_events(scene=scene, effective_gs={"sfx": {"enabled": False}},
                         scene_duration=2.0, words=WORDS)
    assert off == []


def test_mix_tem_duracao_da_cena_e_som_no_instante(sounds, tmp_path):
    from pydub import AudioSegment
    _, whoosh = sounds
    out = mix(narration_path=None, events=[(1.0, whoosh, 1.0)], scene_duration=2.0,
              out_path=str(tmp_path / "m.wav"))
    seg = AudioSegment.from_file(out)
    assert abs(len(seg) - 2000) <= 1
    assert seg[:900].rms == 0 and seg[1000:1300].rms > 0
