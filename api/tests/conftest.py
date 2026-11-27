"""Testes rodam no banco da branch (schemas do database/flyway.toml), dentro de uma
transação que é desfeita no fim de cada teste: nada fica gravado."""

import os
import re
from pathlib import Path

_toml = (Path(__file__).resolve().parents[2] / "database" / "flyway.toml").read_text()
os.environ["MYSQL_DBNAME"] = re.search(r'schemas\s*=\s*\[\s*"([^"]+)"', _toml).group(1)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.db import engine, get_session  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def session():
    conn = engine.connect()
    trans = conn.begin()
    s = Session(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        yield s
    finally:
        s.close()
        trans.rollback()
        conn.close()


@pytest.fixture
def client(session):
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()
