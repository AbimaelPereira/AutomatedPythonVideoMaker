from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class Channel(SQLModel, table=True):
    __tablename__ = "app_channels"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(unique=True)
    name: str
    config: str = "{}"  # JSON — espelho do channels_config/{slug}.json
    status: int = 1
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
