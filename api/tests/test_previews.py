import json
import os
import subprocess
import sys

import pytest
from sqlmodel import Session

from jobs.models import Job
from previews import service
from tests.conftest import make_video


class FakeRun:
    """Substitui subprocess.run: captura o payload e devolve o JSON do worker."""

    def __init__(self, tmp_path, returncode=0, stderr=""):
        self.calls, self.tmp_path = [], tmp_path
        self.returncode, self.stderr = returncode, stderr

    def __call__(self, cmd, input=None, **kw):
        payload = json.loads(input)
        self.calls.append(payload)
        out_dir = str(self.tmp_path / payload["video"]["slug"])
        scenes = [{"index": i + 1, "scene_id": s.get("id"),
                   "path": f"{out_dir}/previews/{i + 1:02d}-{s.get('id')}.png",
                   "status": "rendered", "error": None, "warnings": []}
                  for i, s in enumerate(payload["video"]["scenes"])]
        body = {"mode": payload["mode"], "output_dir": out_dir,
                "result": {"slug": payload["video"]["slug"], "scenes": scenes}}
        return subprocess.CompletedProcess(cmd, self.returncode,
                                           "log\n" + json.dumps(body), self.stderr)


@pytest.fixture
def fake_run(tmp_path, monkeypatch):
    fake = FakeRun(tmp_path)
    monkeypatch.setattr(service.subprocess, "run", fake)
    monkeypatch.setattr(service, "videomaker_python", lambda: sys.executable)
    return fake


def _jobs(db_engine):
    with Session(db_engine) as s:
        return s.query(Job).all()


def test_sem_slug_422(client):
    r = client.post("/previews", json={"video": {"scenes": [{"id": "a"}]}})
    assert r.status_code == 422


def test_slug_traversal_422(client):
    r = client.post("/previews", json={"video": make_video(slug="../x")})
    assert r.status_code == 422


def test_sem_cenas_422(client):
    r = client.post("/previews", json={"video": {"slug": "x"}})
    assert r.status_code == 422


def test_wait_true_uma_cena(client, fake_run):
    r = client.post("/previews", json={"video": make_video(2), "scenes": ["s1"], "wait": True})
    assert r.status_code == 200
    assert r.json()["scenes"][0]["path"].endswith(".png")
    assert fake_run.calls[0]["scenes"] == ["s1"] and fake_run.calls[0]["mode"] == "preview"


def test_wait_true_muitas_cenas_422(client, fake_run):
    r = client.post("/previews", json={"video": make_video(10), "wait": True})
    assert r.status_code == 422 and "fila" in r.json()["detail"]
    assert fake_run.calls == []


def test_wait_false_cria_job_e_resultado(client, fake_run, db_engine):
    r = client.post("/previews", json={"video": make_video(2), "force": True})
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    (job,) = _jobs(db_engine)
    assert job.type == "preview" and job.status == "done"
    assert len(job.config) <= 255 and len(job.output) <= 255
    assert fake_run.calls[0]["force"] is True

    got = client.get(f"/previews/{job_id}").json()
    assert got["status"] == "done" and got["error"] is None
    assert len(got["result"]["scenes"]) == 2


def test_prepare_enfileira(client, fake_run, db_engine):
    r = client.post("/previews/prepare", json={"video": make_video(1)})
    assert r.status_code == 202
    assert _jobs(db_engine)[0].type == "prepare" and fake_run.calls[0]["mode"] == "prepare"


def test_get_de_outro_usuario_404(client, fake_run, current_user):
    job_id = client.post("/previews", json={"video": make_video(1)}).json()["job_id"]
    current_user["id"] = 2
    assert client.get(f"/previews/{job_id}").status_code == 404
    assert client.get("/previews/9999").status_code == 404


def test_run_job_grava_result_file(client, fake_run, db_engine):
    client.post("/previews", json={"video": make_video(1)})
    (job,) = _jobs(db_engine)
    path = json.loads(job.output)["result_file"]
    assert os.path.isfile(path) and path.endswith(f"result-{job.id}.json")


def test_subprocesso_com_erro_vira_job_error(client, tmp_path, monkeypatch, db_engine):
    fake = FakeRun(tmp_path, returncode=1, stderr="traceback\nRuntimeError: boom")
    monkeypatch.setattr(service.subprocess, "run", fake)
    monkeypatch.setattr(service, "videomaker_python", lambda: sys.executable)
    job_id = client.post("/previews", json={"video": make_video(1)}).json()["job_id"]
    got = client.get(f"/previews/{job_id}").json()
    assert got["status"] == "error" and "boom" in got["error"]
    assert len(_jobs(db_engine)[0].output) <= 255


def test_wait_true_erro_do_worker_500_e_invalido_422(client, tmp_path, monkeypatch):
    monkeypatch.setattr(service, "videomaker_python", lambda: sys.executable)
    monkeypatch.setattr(service.subprocess, "run",
                        FakeRun(tmp_path, returncode=1, stderr="RuntimeError: x"))
    assert client.post("/previews", json={"video": make_video(1), "wait": True}).status_code == 500
    monkeypatch.setattr(service.subprocess, "run",
                        FakeRun(tmp_path, returncode=2, stderr="ValueError: cena 'z' não existe"))
    r = client.post("/previews", json={"video": make_video(1), "scenes": ["z"], "wait": True})
    assert r.status_code == 422


@pytest.mark.slow
def test_integracao_real(client, tmp_path):
    from PIL import Image
    red = tmp_path / "red.png"
    Image.new("RGB", (100, 100), (255, 0, 0)).save(red)
    video = {"slug": "integ", "output": {"dir": str(tmp_path / "out"), "ratio": "16:9"},
             "scenes": [{"id": "a", "background": {"visual": {"type": "color", "color": "#000000"}},
                         "visual_elements": [{"type": "image", "source": str(red)}]}]}
    r = client.post("/previews", json={"video": video, "wait": True})
    assert r.status_code == 200, r.text
    path = r.json()["scenes"][0]["path"]
    assert os.path.isfile(path) and path.startswith(str(tmp_path / "out" / "integ" / "previews"))
