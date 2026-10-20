"""Execução de preview/prepare em subprocesso e persistência do resultado."""

import json
import os
import subprocess
import tempfile
import uuid
from typing import Optional

from videomaker_runtime import VIDEOMAKER_DIR, videomaker_python

_WORKER = os.path.join(os.path.dirname(__file__), "render_worker.py")
_SPOOL_DIR = os.path.join(tempfile.gettempdir(), "canaisdark_preview_jobs")


def timeout_s() -> int:
    return int(os.getenv("PREVIEW_TIMEOUT_S", 3600))


def sync_max_scenes() -> int:
    return int(os.getenv("PREVIEW_SYNC_MAX_SCENES", 3))


class RenderError(RuntimeError):
    """Falha do subprocesso. `invalid=True` = requisição inválida (422)."""

    def __init__(self, message: str, invalid: bool = False):
        super().__init__(message)
        self.invalid = invalid


def validate_video(video: dict) -> None:
    """Checagens baratas antes de enfileirar. Levanta ValueError."""
    if not isinstance(video, dict):
        raise ValueError("`video` deve ser um objeto JSON")
    slug = video.get("slug")
    if not slug or not isinstance(slug, str):
        raise ValueError("`video.slug` é obrigatório")
    if "/" in slug or "\\" in slug or ".." in slug or "\0" in slug:
        raise ValueError(f"`video.slug` inválido: {slug!r}")
    if not scene_count(video):
        raise ValueError("`video` precisa de `scenes` ou `chapters` com cenas")


def scene_count(video: dict) -> int:
    if isinstance(video.get("chapters"), list):
        return sum(len(c.get("scenes") or []) for c in video["chapters"] if isinstance(c, dict))
    scenes = video.get("scenes")
    return len(scenes) if isinstance(scenes, list) else 0


def requested_scene_count(video: dict, scenes: Optional[list]) -> int:
    return scene_count(video) if scenes is None else len(scenes)


def run_subprocess(mode: str, video: dict, scenes: Optional[list], force: bool) -> dict:
    """Devolve `{"mode", "output_dir", "result"}` do worker."""
    payload = {"videomaker_dir": VIDEOMAKER_DIR, "video": video,
               "scenes": scenes, "force": force, "mode": mode}
    try:
        proc = subprocess.run(
            [videomaker_python(), _WORKER], input=json.dumps(payload),
            capture_output=True, text=True, timeout=timeout_s(), cwd=VIDEOMAKER_DIR,
        )
    except subprocess.TimeoutExpired:
        raise RenderError(f"{mode} excedeu {timeout_s()}s")

    if proc.returncode != 0:
        lines = (proc.stderr or "").strip().splitlines()
        message = lines[-1] if lines else f"worker saiu com código {proc.returncode}"
        raise RenderError(message, invalid=proc.returncode == 2)

    for line in reversed((proc.stdout or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    raise RenderError("worker terminou sem devolver resultado")


def spool_request(payload: dict) -> str:
    """Grava a requisição em disco: `app_jobs.config` é VARCHAR(255)."""
    os.makedirs(_SPOOL_DIR, exist_ok=True)
    path = os.path.join(_SPOOL_DIR, f"{uuid.uuid4().hex}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    return path


def _load_request(config: dict) -> dict:
    path = config.get("request_file")
    if not path:
        return config
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _save_result(job_id: Optional[int], output: dict) -> dict:
    """Grava o resultado completo em disco; `Job.output` guarda só o caminho."""
    previews_dir = os.path.join(output["output_dir"], "previews")
    os.makedirs(previews_dir, exist_ok=True)
    name = f"result-{job_id if job_id is not None else uuid.uuid4().hex}.json"
    path = os.path.join(previews_dir, name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(output["result"], f, ensure_ascii=False)
    os.replace(tmp, path)
    return {"result_file": path}


def _run(mode: str, config: dict, job_id: Optional[int]) -> dict:
    req = _load_request(config)
    output = run_subprocess(mode, req["video"], req.get("scenes"), bool(req.get("force")))
    return _save_result(job_id, output)


def run_preview(config: dict, job_id: Optional[int] = None) -> dict:
    return _run("preview", config, job_id)


def run_prepare(config: dict, job_id: Optional[int] = None) -> dict:
    return _run("prepare", config, job_id)


def read_result(result_file: str) -> Optional[dict]:
    try:
        with open(result_file, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None
