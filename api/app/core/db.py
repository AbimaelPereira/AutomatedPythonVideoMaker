from collections.abc import Iterator
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.dialects.mysql import DATETIME

from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, pool_recycle=3600)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

# datetime(3) do MySQL
DateTime3 = DATETIME(fsp=3)


class Base(DeclarativeBase):
    """Base dos models. Só mapeia tabelas: a estrutura é do Flyway (database/)."""

    type_annotation_map = {datetime: DateTime3}


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
