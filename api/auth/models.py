from sqlmodel import SQLModel, Field, Relationship
from typing import Optional
from datetime import datetime


class Group(SQLModel, table=True):
    __tablename__ = "si_groups"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    permissions: str = "{}"  # JSON string
    status: int = 1
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    users: list["User"] = Relationship(back_populates="group")


class User(SQLModel, table=True):
    __tablename__ = "si_users"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    email: str = Field(unique=True)
    password: str
    status: int = 1
    id_group: int = Field(foreign_key="si_groups.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    group: Optional[Group] = Relationship(back_populates="users")


class RefreshToken(SQLModel, table=True):
    __tablename__ = "si_refresh_tokens"

    id: Optional[int] = Field(default=None, primary_key=True)
    token: str = Field(unique=True, index=True)
    id_user: int = Field(foreign_key="si_users.id")
    expires_at: datetime
    created_at: datetime = Field(default_factory=datetime.utcnow)
