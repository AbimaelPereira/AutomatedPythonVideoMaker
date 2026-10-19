"""Âncoras de narração: casamento de palavra/frase/sentence e `on_missing`.

Usa o SRT sintético de `tests/fixtures` (palavras de 0,4 s a partir de 0,2 s),
então os tempos esperados são valores exatos, não aproximações.

    pytest tests/test_anchors.py -q
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from libs.Motion import resolve_motion                        # noqa: E402
from libs.Motion.anchors import AnchorResolver, normalize      # noqa: E402
from libs.Motion.errors import AnchorNotFound, MotionError     # noqa: E402
from libs.Motion.timeline import build_timeline                # noqa: E402
from tests.fixtures.make_fixtures import SRT_TEXT, build, srt_entries  # noqa: E402

BOX = (0, 0, 400, 300)
RES = (1920, 1080)
DURATION = 8.0


@pytest.fixture(scope="module")
def words():
    """O SRT sintético lido pelo MESMO parser do render (`parse_srt_words`)."""
    from libs.Subtitle.SubtitleUtils import parse_srt_words

    build()
    return parse_srt_words(os.path.join(HERE, "fixtures", "assets", "words.srt"),
                           uppercase=False)


def _resolver(words, on_missing="proportional"):
    return AnchorResolver(words=words, narration_text=SRT_TEXT,
                          scene_duration=DURATION, on_missing=on_missing)


def _start_of(word: str, nth: int = 1) -> float:
    """Tempo esperado de uma palavra, direto da tabela do gerador."""
    hits = [entry for entry in srt_entries()
            if normalize(entry[1]) == normalize(word)]
    return hits[nth - 1][2]


# ---------------------------------------------------------------------------
# NORMALIZAÇÃO
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Mão.", "mao"), ("BILHÃO", "bilhao"), ("sozinho;", "sozinho"),
    ("  dois   espaços ", "dois espacos"), ("Porém", "porem"),
])
def test_normalize(raw, expected):
    assert normalize(raw) == expected


# ---------------------------------------------------------------------------
# PALAVRA
# ---------------------------------------------------------------------------

def test_word_first_occurrence(words):
    assert _resolver(words).resolve({"word": "dinheiro"}) == pytest.approx(1.0)
    assert _start_of("dinheiro") == pytest.approx(1.0)


def test_word_nth_occurrence(words):
    assert _resolver(words).resolve({"word": "dinheiro", "nth": 2}) \
        == pytest.approx(_start_of("dinheiro", 2))


def test_word_ignores_accent_and_punctuation(words):
    resolver = _resolver(words)
    assert resolver.resolve({"word": "mao"}) == pytest.approx(_start_of("mão"))
    assert resolver.resolve({"word": "BILHÃO!"}) == pytest.approx(_start_of("bilhão"))


def test_word_fuzzy_tolerates_small_divergence(words):
    """Divergência pequena ainda casa (ratio ≥ 88); grande vira miss.

    `bilhoes` × `bilhao` dá 77 — abaixo do limiar de propósito: aceitar isso
    animaria na palavra errada, que é pior que cair no `on_missing`.
    """
    resolver = _resolver(words)
    assert resolver.resolve({"word": "dinheir"}) == pytest.approx(_start_of("dinheiro"))
    assert resolver.resolve({"word": "bilhoes"}) is None


def test_word_align_variants(words):
    resolver = _resolver(words)
    start = _start_of("lucro")
    assert resolver.resolve({"word": "lucro", "align": "start"}) == pytest.approx(start)
    assert resolver.resolve({"word": "lucro", "align": "end"}) == pytest.approx(start + 0.4)
    assert resolver.resolve({"word": "lucro", "align": "center"}) == pytest.approx(start + 0.2)


def test_word_offset_is_applied_last(words):
    assert _resolver(words).resolve({"word": "lucro", "offset": -0.12}) \
        == pytest.approx(_start_of("lucro") - 0.12)


def test_offset_is_clamped_to_the_scene(words):
    resolver = _resolver(words)
    assert resolver.resolve({"word": "Hoje", "offset": -5.0}) == 0.0
    assert resolver.resolve({"word": "juros", "offset": 99.0}) == DURATION


def test_word_index_is_one_based(words):
    assert _resolver(words).resolve({"word_index": 9}) \
        == pytest.approx(srt_entries()[8][2])


def test_word_index_out_of_range_is_a_miss(words):
    resolver = _resolver(words)
    assert resolver.resolve({"word_index": 999}) is None
    assert resolver.misses


# ---------------------------------------------------------------------------
# FRASE E SENTENCE
# ---------------------------------------------------------------------------

def test_phrase_matches_word_window(words):
    assert _resolver(words).resolve({"phrase": "um bilhão não"}) \
        == pytest.approx(_start_of("um"))


def test_phrase_align_end_uses_last_word(words):
    assert _resolver(words).resolve({"phrase": "um bilhão não", "align": "end"}) \
        == pytest.approx(_start_of("não") + 0.4)


def test_phrase_not_found_is_a_miss(words):
    assert _resolver(words).resolve({"phrase": "taxa selic acumulada"}) is None


def test_sentence_maps_to_srt_words(words):
    # 2ª frase: "Porém o lucro de um bilhão não aparece sozinho"
    assert _resolver(words).resolve({"sentence": 2}) == pytest.approx(_start_of("Porém"))


def test_sentence_survives_divergence_between_text_and_srt(words):
    """O texto escrito diverge do falado (número escrito como dígito).

    O alinhamento é por `SequenceMatcher` sobre as palavras, não por contagem,
    então uma troca pontual não deve desalinhar a frase inteira.
    """
    text = SRT_TEXT.replace("um bilhão", "1 bilhão")
    resolver = AnchorResolver(words=words, narration_text=text,
                              scene_duration=DURATION)
    assert resolver.resolve({"sentence": 2}) == pytest.approx(_start_of("Porém"))


def test_sentence_out_of_range_is_a_miss(words):
    assert _resolver(words).resolve({"sentence": 9}) is None


# ---------------------------------------------------------------------------
# LITERAIS
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("spec,expected", [
    (0.8, 0.8), ("0.8", 0.8), ("0.8s", 0.8),
    ("50%", 4.0), ("start", 0.0), ("end", DURATION),
])
def test_literal_anchors(words, spec, expected):
    assert _resolver(words).resolve(spec) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# on_missing
# ---------------------------------------------------------------------------

_MISSING = [{"at": {"word": "criptomoeda"}, "preset": "fade_in"},
            {"at": {"word": "dividendos"}, "preset": "fade_out"}]


def test_on_missing_proportional_distributes_in_order(words):
    timeline = build_timeline(
        _MISSING, box=BOX, resolution=RES, scene_duration=DURATION,
        anchor_resolver=_resolver(words, "proportional"),
        defaults={"on_missing": "proportional"},
    )
    starts = [a["start"] for a in timeline.actions]
    assert starts == pytest.approx([DURATION / 3, 2 * DURATION / 3])


def test_on_missing_start_anchors_at_zero(words):
    timeline = build_timeline(
        _MISSING, box=BOX, resolution=RES, scene_duration=DURATION,
        anchor_resolver=_resolver(words, "start"),
        defaults={"on_missing": "start"},
    )
    assert [a["start"] for a in timeline.actions] == [0.0, 0.0]


def test_on_missing_skip_drops_the_action(words):
    timeline = build_timeline(
        _MISSING, box=BOX, resolution=RES, scene_duration=DURATION,
        anchor_resolver=_resolver(words, "skip"),
        defaults={"on_missing": "skip"},
    )
    assert timeline.actions == []
    assert timeline.warnings


def test_on_missing_strict_raises(words):
    with pytest.raises((AnchorNotFound, MotionError)):
        build_timeline(
            _MISSING, box=BOX, resolution=RES, scene_duration=DURATION,
            anchor_resolver=_resolver(words, "strict"),
            defaults={"on_missing": "strict"},
        )


def test_miss_log_suggests_nearby_words(words):
    resolver = _resolver(words)
    resolver.resolve({"word": "dinheiroo zzz"})
    assert resolver.misses and "próximas" in resolver.misses[0]


# ---------------------------------------------------------------------------
# CENA SEM NARRAÇÃO
# ---------------------------------------------------------------------------

def test_scene_without_srt_falls_back_without_raising():
    """`words=None` (cena sem narração) não pode derrubar o render — princípio P4."""
    element = {"motion": [{"at": {"word": "qualquer"}, "preset": "fade_in"}]}
    timeline = resolve_motion(element=element, box=BOX, resolution=RES,
                              scene_duration=DURATION, words=None)
    assert timeline is not None
    assert timeline.actions[0]["start"] == pytest.approx(DURATION / 2)
