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
                resultado = {"message": "Concluído com sucesso"}
            elif job.type == "youtube_upload":
                resultado = _run_youtube_upload_job(config)
            elif job.type == "youtube_sync":
                resultado = _run_youtube_sync_job(config)
            else:
                raise ValueError(f"Tipo de job desconhecido: {job.type}")

            job.status = "done"
            job.output = _output_curto(resultado)

        except Exception as e:
            job.status = "error"
            job.output = _output_curto({"error": f"{type(e).__name__}: {e}"})

        finally:
            job.updated_at = datetime.utcnow()
            session.commit()


# `Job.output` é VARCHAR(255). Um resultado maior que isso fazia o commit
# estourar com DataError — e como o erro acontecia DENTRO do `finally`, o job
# ficava preso em "processing" para sempre, sem nunca registrar o que houve.
OUTPUT_MAX_CHARS = 255


def _output_curto(resultado: dict) -> str:
    """Serializa o resultado garantindo que caiba na coluna."""
    texto = json.dumps(resultado, ensure_ascii=False)
    if len(texto) <= OUTPUT_MAX_CHARS:
        return texto

    # Não dá para truncar JSON no meio (viraria string inválida), então troca
    # por um aviso válido que ainda diz o que aconteceu.
    aviso = json.dumps({"truncado": True,
                        "resumo": texto[:OUTPUT_MAX_CHARS - 60]},
                       ensure_ascii=False)
    return aviso[:OUTPUT_MAX_CHARS]


def _run_video_job(config: dict):
    from libs.UnifiedVideoEngine import UnifiedVideoEngine
    engine = UnifiedVideoEngine(config)
    engine.run()


def _run_youtube_upload_job(config: dict) -> dict:
    """Sobe um MP4 já renderizado. Ver `youtube.service.upload`."""
    from youtube import service
    return service.upload(config["slug"], config.get("overrides"))


def _run_youtube_sync_job(config: dict) -> dict:
    """Coleta os dados do canal num JSON. Ver `youtube.service.sync`."""
    from youtube import service
    return service.sync(
        config["slug"],
        path=config.get("path"),
        inicio=config.get("inicio", "2020-01-01"),
        fim=config.get("fim"),
        com_analytics_por_video=config.get("com_analytics_por_video", True),
    )
