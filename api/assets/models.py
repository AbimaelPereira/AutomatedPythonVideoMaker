from sqlmodel import SQLModel, Field, Relationship
from typing import Optional
from datetime import datetime


class RemoteAsset(SQLModel, table=True):
    __tablename__ = "app_remote_assets"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    slug: str = Field(unique=True)
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    midias: list["RemoteAssetMidia"] = Relationship(back_populates="asset")


class RemoteAssetMidia(SQLModel, table=True):
    __tablename__ = "app_remote_assets_midia"

    id: Optional[int] = Field(default=None, primary_key=True)
    id_asset: int = Field(foreign_key="app_remote_assets.id")
    url: str
    type: str = "unknown"  # "image" | "video" | "unknown"
    extension: Optional[str] = None
    is_invalid: int = 0
    last_used: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    asset: Optional[RemoteAsset] = Relationship(back_populates="midias")
