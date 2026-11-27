from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import CurrentPrincipal
from app.core.db import get_session

app = FastAPI(title="AutomatedPythonVideoMaker API")


@app.get("/health")
def health(session: Session = Depends(get_session)) -> dict:
    session.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/me")
def me(principal: CurrentPrincipal) -> dict:
    return {
        "user": {"id": principal.user.id, "email": principal.user.email, "name": principal.user.name},
        "brand": {"id": principal.brand.id, "slug": principal.brand.slug, "name": principal.brand.name},
    }
