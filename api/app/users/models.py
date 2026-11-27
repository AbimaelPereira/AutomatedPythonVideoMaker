from datetime import datetime

from sqlalchemy import ForeignKey, ForeignKeyConstraint, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class User(Base):
    __tablename__ = "app_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255))
    name: Mapped[str | None] = mapped_column(String(255))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(server_default=text("1"))
    last_login_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("CURRENT_TIMESTAMP(3)"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("CURRENT_TIMESTAMP(3)"))


class BrandUser(Base):
    __tablename__ = "app_brand_users"

    brand_id: Mapped[int] = mapped_column(ForeignKey("app_brands.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(server_default=text("CURRENT_TIMESTAMP(3)"))


class ApiToken(Base):
    __tablename__ = "app_api_tokens"
    __table_args__ = (
        ForeignKeyConstraint(
            ["brand_id", "user_id"], ["app_brand_users.brand_id", "app_brand_users.user_id"]
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int]
    brand_id: Mapped[int]
    name: Mapped[str | None] = mapped_column(String(100))
    prefix: Mapped[str] = mapped_column(String(16))
    token_hash: Mapped[str] = mapped_column(String(64))
    last_used_at: Mapped[datetime | None]
    expires_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=text("CURRENT_TIMESTAMP(3)"))
