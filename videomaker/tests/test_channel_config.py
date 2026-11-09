import json

import pytest

from libs import utils


@pytest.fixture
def canais(tmp_path, monkeypatch):
    config = tmp_path / "Meu Canal" / "credentials" / "channel_config.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"youtube": {"a": 1}, "doc/": "x"}))
    monkeypatch.setenv("CHANNELS_DIR", str(tmp_path))
    return config


def test_slug_vem_da_pasta_do_canal(canais):
    assert utils.channel_slug(str(canais)) == "meu_canal"


def test_slug_de_outros_caminhos_e_nomes():
    assert utils.channel_slug("/abs/outro.json") == "outro"
    assert utils.channel_slug("hacker") == "hacker"


def test_slug_encontra_config_na_pasta_do_canal(canais):
    assert utils.load_channel_config("meu_canal") == {"youtube": {"a": 1}}


@pytest.mark.parametrize("nome", ["nao_existe", "/nao/existe.json"])
def test_canal_inexistente_levanta_erro(canais, nome):
    with pytest.raises(FileNotFoundError):
        utils.load_channel_config(nome)
