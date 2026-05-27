from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel

from database import get_session
from middleware.auth import get_current_user
from auth.models import User
from jobs.models import Job
from jobs import worker

router = APIRouter()


class CreateJobRequest(BaseModel):
    type: str
    config: dict


@router.post("")
def create_job(
    body: CreateJobRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    import json
    job = Job(id_user=current_user.id, type=body.type, config=json.dumps(body.config))
    session.add(job)
    session.commit()
    session.refresh(job)

    background_tasks.add_task(worker.run_job, job.id)

    return {"id": job.id, "status": job.status}


@router.get("")
def list_jobs(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    jobs = session.exec(select(Job).where(Job.id_user == current_user.id)).all()
    return jobs


@router.get("/{job_id}")
def get_job(
    job_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    job = session.get(Job, job_id)
    if not job or job.id_user != current_user.id:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    return job
