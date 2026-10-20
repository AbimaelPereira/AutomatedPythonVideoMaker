"""Preview por cena (PNG em pose de repouso) e prepare de assets, via fila de jobs."""

import json
from typing import List, Optional, Union

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlmodel import Session

from auth.models import User
from database import get_session
from jobs import worker
from jobs.models import Job
from middleware.auth import get_current_user
from previews import service

router = APIRouter()

_TYPES = ("preview", "prepare")


class PreviewRequest(BaseModel):
    video: dict
    scenes: Optional[List[Union[str, int]]] = None   # ids ou índices 1-based; null = todas
    force: bool = False
    wait: bool = False


class PrepareRequest(BaseModel):
    video: dict
    scenes: Optional[List[Union[str, int]]] = None
    force: bool = False


def _validate(video: dict):
    try:
        service.validate_video(video)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


def _enqueue(kind: str, body, background_tasks: BackgroundTasks,
             session: Session, user: User) -> JSONResponse:
    request_file = service.spool_request(
        {"video": body.video, "scenes": body.scenes, "force": body.force})
    job = Job(id_user=user.id, type=kind, config=json.dumps({"request_file": request_file}))
    session.add(job)
    session.commit()
    session.refresh(job)
    background_tasks.add_task(worker.run_job, job.id)
    return JSONResponse(status_code=202, content={"job_id": job.id, "status": job.status})


@router.post("")
def create_preview(
    body: PreviewRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _validate(body.video)
    if not body.wait:
        return _enqueue("preview", body, background_tasks, session, current_user)

    limit = service.sync_max_scenes()
    if service.requested_scene_count(body.video, body.scenes) > limit:
        raise HTTPException(
            status_code=422,
            detail=f"`wait=true` aceita até {limit} cenas; use a fila (`wait=false`) "
                   f"e acompanhe em GET /previews/{{job_id}}",
        )
    try:
        output = service.run_subprocess("preview", body.video, body.scenes, body.force)
    except service.RenderError as e:
        raise HTTPException(status_code=422 if e.invalid else 500, detail=str(e))
    return output["result"]


@router.post("/prepare")
def create_prepare(
    body: PrepareRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _validate(body.video)
    return _enqueue("prepare", body, background_tasks, session, current_user)


@router.get("/{job_id}")
def get_preview(
    job_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    job = session.get(Job, job_id)
    if not job or job.id_user != current_user.id or job.type not in _TYPES:
        raise HTTPException(status_code=404, detail="Job não encontrado")

    try:
        output = json.loads(job.output or "{}")
    except ValueError:
        output = {}
    result = service.read_result(output["result_file"]) if output.get("result_file") else None
    return {"job_id": job.id, "status": job.status, "result": result,
            "error": output.get("error")}
