from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, ForeignKeyConstraint, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Content(Base):
    __tablename__ = "app_contents"

    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[str] = mapped_column(String(26))
    brand_id: Mapped[int] = mapped_column(ForeignKey("app_brands.id"))
    requested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("app_users.id"))
    title: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), server_default=text("'queued'"))
    request: Mapped[dict[str, Any]] = mapped_column(JSON)
    settings: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    video_key: Mapped[str | None] = mapped_column(String(512))
    audio_key: Mapped[str | None] = mapped_column(String(512))
    output_key: Mapped[str | None] = mapped_column(String(512))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=text("CURRENT_TIMESTAMP(3)"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("CURRENT_TIMESTAMP(3)"))


class Chapter(Base):
    __tablename__ = "app_content_chapters"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_id: Mapped[int] = mapped_column(ForeignKey("app_contents.id"))
    position: Mapped[int]
    title: Mapped[str | None] = mapped_column(String(255))
    settings: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(server_default=text("CURRENT_TIMESTAMP(3)"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("CURRENT_TIMESTAMP(3)"))


class Scene(Base):
    __tablename__ = "app_content_scenes"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_id: Mapped[int] = mapped_column(ForeignKey("app_contents.id"))
    chapter_id: Mapped[int | None] = mapped_column(ForeignKey("app_content_chapters.id"))
    position: Mapped[int]
    request: Mapped[dict[str, Any]] = mapped_column(JSON)
    request_hash: Mapped[str | None] = mapped_column(String(64))
    resolved: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), server_default=text("'pending'"))
    preview_key: Mapped[str | None] = mapped_column(String(512))
    output_key: Mapped[str | None] = mapped_column(String(512))
    preview_ms: Mapped[int | None]
    render_ms: Mapped[int | None]
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=text("CURRENT_TIMESTAMP(3)"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("CURRENT_TIMESTAMP(3)"))
