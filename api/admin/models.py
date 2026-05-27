from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class Module(SQLModel, table=True):
    __tablename__ = "si_modules"

    id: Optional[int] = Field(default=None, primary_key=True)
    id_parent: Optional[int] = Field(default=None, foreign_key="si_modules.id")
    name: str
    slug: str = Field(unique=True)
    icon: Optional[str] = None
    status: int = 1
    order_by: int = 0
    show_in_menu: int = 1
    actions: str = "view"  # CSV: "view,create,edit,delete"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
