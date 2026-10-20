import os
import sys

for key, value in (("MYSQL_USER", "t"), ("MYSQL_PASS", "t"), ("MYSQL_DBNAME", "t"),
                   ("JWT_SECRET", "t")):
    os.environ.setdefault(key, value)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import auth.models  # noqa: F401,E402 — registra as tabelas
import jobs.models  # noqa: F401,E402
from auth.models import User  # noqa: E402
from database import get_session  # noqa: E402
from middleware.auth import get_current_user  # noqa: E402


@pytest.fixture
def db_engine(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    import jobs.worker
    monkeypatch.setattr(jobs.worker, "engine", engine)
    return engine


@pytest.fixture
def current_user():
    """Troque `current_user["id"]` para simular outro usuário."""
    return {"id": 1}


@pytest.fixture
def client(db_engine, current_user):
    from previews.router import router

    app = FastAPI()
    app.include_router(router, prefix="/previews")

    def session_override():
        with Session(db_engine) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_current_user] = lambda: User(
        id=current_user["id"], name="u", email="u@x", password="x", id_group=1)
    return TestClient(app)


def make_video(n=1, slug="meu_video", **extra):
    video = {"slug": slug, "scenes": [{"id": f"s{i}"} for i in range(n)]}
    video.update(extra)
    return video
