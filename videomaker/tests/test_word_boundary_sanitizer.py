"""Saneamento dos word boundaries do Whisper.

Regressão do bug em que a legenda mostrava, no fim de cada cena, a PRIMEIRA
palavra da própria cena — como se o narrador a tivesse repetido. A causa era o
`initial_prompt=text` passado ao Whisper, que condiciona o decoder a continuar o
prompt: terminado o áudio, ele "continuava" o texto e inventava o começo dele.

Os casos marcados REAL abaixo são transcrições realmente produzidas pelo
pipeline (provider kokoro) para as cenas de `.claude/testes_motion.json`.
"""

import pytest

from libs.Whisper.WordBoundarySanitizer import (
    align_to_text,
    normalize_token,
    sanitize,
)


def wb(pairs):
    """[(word, start, end), ...] → formato de word boundary."""
    return [{"word": w, "start": s, "end": e} for w, s, e in pairs]


def words(result):
    return [w["word"] for w in result]


# ----------------------------------------------------------------------
# normalize_token
# ----------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Olá,", "ola"),
    ("RECORRÊNCIA.", "recorrencia"),
    ("não", "nao"),
    ("—", ""),
    ("", ""),
])
def test_normalize_token(raw, expected):
    assert normalize_token(raw) == expected


# ----------------------------------------------------------------------
# A alucinação do fim da cena (o bug relatado)
# ----------------------------------------------------------------------

def test_remove_primeira_palavra_alucinada_no_fim():
    """REAL — cena_02_frase_e_janela: SRT terminava com "A", a 1ª palavra."""
    text = ("A maioria das empresas descobre isso tarde demais. Quando percebem, "
            "o caixa já secou e não há tempo de corrigir a rota.")
    transcricao = wb([
        ("de", 6140, 6280), ("corrigir", 6280, 6680),
        ("a", 6680, 6780), ("rota.", 6780, 7160),
        ("A", 7160, 7380),  # alucinação: 1ª palavra do texto
    ])
    out = sanitize(transcricao, text, 7464)
    assert words(out)[-1] == "rota."
    assert len(out) == 4


def test_remove_duas_palavras_alucinadas():
    """REAL — cena_01_stagger: SRT terminava com "Três um"."""
    text = "Três passos, um de cada vez, na ordem exata em que precisam acontecer."
    transcricao = wb([
        ("em", 2840, 2940), ("que", 2940, 3040),
        ("precisam", 3040, 3540), ("acontecer.", 3540, 4040),
        ("Três", 4040, 4140), ("um", 4059, 4159),  # alucinação
    ])
    out = sanitize(transcricao, text, 4536)
    assert words(out)[-1] == "acontecer."


def test_remove_repeticao_alucinada():
    """REAL — cena_02_text_box: SRT terminava com "derruba lento"."""
    text = ("Texto animado é o caso mais comum de todos, e hoje é justamente o "
            "que derruba a cena inteira para o caminho lento.")
    transcricao = wb([
        ("para", 5600, 5700), ("o", 5700, 5800),
        ("caminho", 5800, 6020), ("lento.", 6020, 6440),
        ("derruba", 6440, 6540), ("lento.", 6460, 6560),  # alucinação
    ])
    out = sanitize(transcricao, text, 6792)
    assert words(out)[-1] == "lento."
    assert len(out) == 4


def test_cena_sem_alucinacao_fica_intacta():
    """REAL — cena_02_encadeado: transcrição correta não deve perder nada."""
    text = ("Entra, respira, pulsa e sai. Quatro momentos encadeados sem nenhum "
            "tempo escrito a mão.")
    transcricao = wb([
        ("nenhum", 3800, 4040), ("tempo", 4040, 4320),
        ("escrito", 4320, 4700), ("a", 4700, 4860), ("mão.", 4860, 5080),
    ])
    out = sanitize(transcricao, text, 5424)
    assert words(out) == ["nenhum", "tempo", "escrito", "a", "mão."]


# ----------------------------------------------------------------------
# Sobreposição leve: ruído de alinhamento, não alucinação
# ----------------------------------------------------------------------

def test_sobreposicao_leve_nao_descarta_palavra():
    """REAL — cena_03_sentence_e_nth: "a" (6380→6480) e "ordem" (6440→6700).

    O filtro antigo descartava "ordem" por começar antes do fim de "a",
    apagando texto legítimo da legenda. Agora o start é apenas empurrado.
    """
    out = sanitize(wb([("a", 6380, 6480), ("ordem", 6440, 6700)]), "a ordem", 7464)
    assert words(out) == ["a", "ordem"]
    assert out[1]["start"] == out[0]["end"]  # sem sobreposição no resultado


def test_palavra_contida_na_anterior_e_descartada():
    out = sanitize(wb([("ok", 0, 1000), ("x", 100, 400)]), "ok x", 2000)
    assert words(out) == ["ok"]


# ----------------------------------------------------------------------
# Filtros temporais
# ----------------------------------------------------------------------

def test_descarta_palavra_apos_fim_do_audio():
    out = sanitize(wb([("ok", 0, 100), ("lixo", 9000, 9100)]), "ok", 1000)
    assert words(out) == ["ok"]


def test_descarta_timestamps_invalidos():
    entrada = wb([("neg", -500, -100), ("invertido", 800, 300), ("boa", 0, 200)])
    out = sanitize(entrada, "boa", 1000)
    assert words(out) == ["boa"]


def test_ultima_palavra_dentro_da_tolerancia_e_mantida():
    """Palavra que começa até 100ms após o fim nominal do áudio é real."""
    out = sanitize(wb([("fim", 1050, 1200)]), "fim", 1000)
    assert words(out) == ["fim"]


def test_descarta_tokens_nao_latinos():
    out = sanitize(wb([("ola", 0, 200), ("世界", 200, 400)]), "ola", 1000)
    assert words(out) == ["ola"]


# ----------------------------------------------------------------------
# Grafia canônica
# ----------------------------------------------------------------------

def test_restaura_acentuacao_e_pontuacao_do_texto():
    """O Whisper pode perder acento/pontuação; o texto original é a verdade."""
    out = sanitize(wb([("recorrencia", 0, 500)]), "recorrência.", 1000)
    assert words(out) == ["recorrência."]


def test_preserva_timestamps_ao_realinhar():
    out = sanitize(wb([("nao", 100, 450)]), "não", 1000)
    assert out[0]["start"] == 100 and out[0]["end"] == 450


# ----------------------------------------------------------------------
# Palavras repetidas no texto
# ----------------------------------------------------------------------

def test_texto_com_palavra_repetida_nao_perde_ocorrencias():
    """"ordem" aparece duas vezes — ambas devem manter timestamp."""
    text = "Essa ordem não é negociável, e quem inverte a ordem quebra."
    transcricao = wb([
        ("Essa", 0, 200), ("ordem", 200, 400), ("não", 400, 500),
        ("é", 500, 600), ("negociável,", 600, 900), ("e", 900, 1000),
        ("quem", 1000, 1150), ("inverte", 1150, 1400), ("a", 1400, 1500),
        ("ordem", 1500, 1700), ("quebra.", 1700, 2000),
    ])
    out = sanitize(transcricao, text, 2200)
    assert len(out) == 11
    assert words(out).count("ordem") == 2


# ----------------------------------------------------------------------
# Rede de segurança
# ----------------------------------------------------------------------

def test_texto_totalmente_diverso_devolve_transcricao():
    """Texto que não descreve o áudio → transcrição crua é melhor que nada."""
    transcricao = wb([("gato", 0, 100), ("cão", 100, 200), ("peixe", 200, 300)])
    out = sanitize(transcricao, "oito nove dez", 1000)
    assert words(out) == ["gato", "cão", "peixe"]


def test_transcricao_curta_legitima_nao_reabilita_legenda_suja():
    """Whisper que transcreveu só o começo não deve reverter o alinhamento."""
    out = sanitize(wb([("primeiro", 0, 400)]), "primeiro você mede depois corta", 500)
    assert words(out) == ["primeiro"]


def test_entrada_vazia():
    assert sanitize([], "qualquer", 1000) == []


def test_texto_vazio_devolve_transcricao():
    out = sanitize(wb([("a", 0, 100)]), "", 1000)
    assert words(out) == ["a"]


# ----------------------------------------------------------------------
# Invariantes gerais
# ----------------------------------------------------------------------

def test_resultado_e_subsequencia_ordenada_e_monotonica():
    text = "um dois três quatro cinco seis"
    transcricao = wb([
        ("um", 0, 100), ("dois", 100, 200), ("ruido", 200, 250),
        ("três", 250, 350), ("quatro", 350, 450), ("cinco", 450, 550),
        ("seis", 550, 650), ("um", 650, 700),  # alucinação final
    ])
    out = sanitize(transcricao, text, 700)

    esperado = iter(text.split())
    assert all(any(g == e for e in esperado) for g in words(out)), "fora de ordem"
    assert all(out[i]["start"] >= out[i - 1]["start"] for i in range(1, len(out)))
    assert words(out)[-1] == "seis"


def test_align_to_text_isolado_remove_insercao():
    out = align_to_text(wb([("a", 0, 100), ("X", 100, 200), ("b", 200, 300)]), "a b")
    assert words(out) == ["a", "b"]
