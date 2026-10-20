import json
import multiprocessing
import os
import shutil
from concurrent.futures import ThreadPoolExecutor

from libs.Prepare.AssetStore import AssetStore


def _put_worker(args):
    assets_dir, i = args
    AssetStore(assets_dir).put(f"k{i}", b"x" * (i + 1), kind="ai", ext="png")


def test_roundtrip_e_caminho_relativo(tmp_path):
    store = AssetStore(str(tmp_path / "assets"))
    path = store.put("ai_a", b"abc", kind="ai", ext="png", meta={"p": 1})
    assert store.get("ai_a") == path
    manifest = json.loads((tmp_path / "assets" / "manifest.json").read_text())
    assert manifest["ai_a"]["file"] == os.path.join("ai", "ai_a.png")
    assert manifest["ai_a"]["meta"] == {"p": 1}


def test_mover_pasta_mantem_get(tmp_path):
    AssetStore(str(tmp_path / "a" / "assets")).put("ai_a", b"abc", kind="ai", ext="png")
    shutil.move(str(tmp_path / "a"), str(tmp_path / "b"))
    got = AssetStore(str(tmp_path / "b" / "assets")).get("ai_a")
    assert got and got.startswith(str(tmp_path / "b"))


def test_arquivo_apagado_remove_entrada(tmp_path):
    store = AssetStore(str(tmp_path / "assets"))
    path = store.put("ai_a", b"abc", kind="ai", ext="png")
    os.remove(path)
    assert store.get("ai_a") is None
    assert "ai_a" not in store.entries()


def test_enabled_false_ignora_get_e_put_sobrescreve(tmp_path):
    AssetStore(str(tmp_path / "assets")).put("ai_a", b"old", kind="ai", ext="png")
    store = AssetStore(str(tmp_path / "assets"), enabled=False)
    assert store.get("ai_a") is None
    path = store.put("ai_a", b"new", kind="ai", ext="png")
    assert open(path, "rb").read() == b"new"


def test_directory_kind_usa_meta_file(tmp_path):
    media = tmp_path / "m.mp4"
    media.write_bytes(b"v")
    store = AssetStore(str(tmp_path / "assets"))
    store.put("dir_x", None, kind="directory", meta={"file": str(media)})
    assert store.get("dir_x") == str(media)


def test_threads_concorrentes(tmp_path):
    store = AssetStore(str(tmp_path / "assets"))
    with ThreadPoolExecutor(20) as ex:
        list(ex.map(lambda i: store.put(f"k{i}", b"x", kind="ai", ext="png"), range(20)))
    assert len(store.entries()) == 20
    assert all(store.get(f"k{i}") for i in range(20))


def test_processos_concorrentes(tmp_path):
    assets = str(tmp_path / "assets")
    with multiprocessing.get_context("spawn").Pool(4) as pool:
        pool.map(_put_worker, [(assets, i) for i in range(12)])
    assert len(AssetStore(assets).entries()) == 12
