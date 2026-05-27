import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    create_engine, Column, String, Text, DateTime, Integer
)
from sqlalchemy.orm import declarative_base, Session

DB_PATH = Path(__file__).parent.parent / "reels_pipelines.db"

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
Base = declarative_base()


class ReelsPipeline(Base):
    __tablename__ = "reels_pipelines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String(20), unique=True, nullable=False, index=True)
    transcript_json = Column(Text, nullable=True)
    gemini_json = Column(Text, nullable=True)
    curation_json = Column(Text, nullable=True)
    exported_jsons = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        def _load(val):
            try:
                return json.loads(val) if val else None
            except Exception:
                return val

        return {
            "id": self.id,
            "video_id": self.video_id,
            "transcript_json": _load(self.transcript_json),
            "gemini_json": _load(self.gemini_json),
            "curation_json": _load(self.curation_json),
            "exported_jsons": _load(self.exported_jsons),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


Base.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)


def upsert_pipeline(video_id: str, **fields) -> ReelsPipeline:
    with get_session() as session:
        record = session.query(ReelsPipeline).filter_by(video_id=video_id).first()
        if record is None:
            record = ReelsPipeline(video_id=video_id)
            session.add(record)
        for key, value in fields.items():
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            setattr(record, key, value)
        record.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(record)
        return record


def get_pipeline(video_id: str) -> ReelsPipeline | None:
    with get_session() as session:
        record = session.query(ReelsPipeline).filter_by(video_id=video_id).first()
        if record:
            session.expunge(record)
        return record


def list_pipelines(page: int = 1, per_page: int = 20) -> tuple[list[ReelsPipeline], int]:
    with get_session() as session:
        total = session.query(ReelsPipeline).count()
        records = (
            session.query(ReelsPipeline)
            .order_by(ReelsPipeline.updated_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        for r in records:
            session.expunge(r)
        return records, total
