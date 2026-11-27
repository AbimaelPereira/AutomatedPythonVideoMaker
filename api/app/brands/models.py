from datetime import datetime
from typing import Any

from sqlalchemy import JSON, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Brand(Base):
    __tablename__ = "app_brands"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    defaults: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("CURRENT_TIMESTAMP(3)"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("CURRENT_TIMESTAMP(3)"))
