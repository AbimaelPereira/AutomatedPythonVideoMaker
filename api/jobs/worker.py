from datetime import datetime
from sqlmodel import Session
import json
import sys
import os

from database import engine
from jobs.models import Job

# Garante que o videomaker é importável
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "videomaker"))


def run_job(job_id: int):
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job:
            return

        job.status = "processing"
        job.updated_at = datetime.utcnow()
        session.commit()

        try:
            config = json.loads(job.config)

            if job.type == "video":
                _run_video_job(config)
            else:
                raise ValueError(f"Tipo de job desconhecido: {job.type}")

            job.status = "done"
            job.output = json.dumps({"message": "Concluído com sucesso"})

        except Exception as e:
            job.status = "error"
            job.output = json.dumps({"error": str(e)})

        finally:
            job.updated_at = datetime.utcnow()
            session.commit()


def _run_video_job(config: dict):
    from libs.UnifiedVideoEngine import UnifiedVideoEngine
    engine = UnifiedVideoEngine(config)
    engine.run()
