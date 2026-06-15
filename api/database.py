from sqlmodel import SQLModel, create_engine, Session
from config import settings

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.ENVIRONMENT == "development",
    pool_pre_ping=True,   # testa a conexão antes de usar; recupera de "Lost connection to MySQL"
    pool_recycle=3600,    # recicla conexões com mais de 1h (evita wait_timeout do MySQL)
)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
