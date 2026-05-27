from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class Job(SQLModel, table=True):
    __tablename__ = "app_jobs"

    id: Optional[int] = Field(default=None, primary_key=True)
    id_user: int = Field(foreign_key="si_users.id")
    type: str  # "video" | "reelscutter"
    status: str = "pending"  # "pending" | "processing" | "done" | "error"
    config: str = "{}"  # JSON — configuração enviada pelo usuário
    output: str = "{}"  # JSON — resultado (path do vídeo, erros, etc.)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
