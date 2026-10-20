from libs.Prepare.keys import ai_key, directory_key, remote_asset_key, url_key

BLOCK = {"type": "ai", "prompt": "um gato", "parameters": {"model": "flux"}}


def test_ai_mesma_chave():
    assert ai_key(BLOCK, BLOCK["parameters"]) == ai_key(dict(BLOCK), {"model": "flux"})
    assert ai_key(BLOCK, {"model": "flux"}).startswith("ai_")


def test_ai_modelo_do_canal_muda_chave():
    assert ai_key(BLOCK, {"model": "flux"}) != ai_key(BLOCK, {"model": "turbo"})


def test_ai_resolucao_entra_no_hash():
    p = {"model": "flux"}
    assert ai_key(BLOCK, p, (1080, 1920)) != ai_key(BLOCK, p, (1920, 1080))
    assert ai_key(BLOCK, p, (1080, 1920)) != ai_key(BLOCK, p)


def test_ai_cache_key_explicito_vence():
    b = dict(BLOCK, cache_key="minha")
    assert ai_key(b, {"model": "a"}, (1, 2)) == ai_key(b, {"model": "b"}) == "ai_minha"


def test_url_ignora_markdown():
    u = "https://x.com/a.jpg"
    assert url_key(f"[x]({u})") == url_key(u)


def test_remote_e_directory_estaveis():
    assert remote_asset_key("s1", "background", "slug") == remote_asset_key("s1", "background", "slug")
    assert remote_asset_key("s1", "background", "a") != remote_asset_key("s2", "background", "a")
    assert directory_key("s1", "background", "/d").startswith("dir_")
