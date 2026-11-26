from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, Relationship, SQLModel


class Brand(SQLModel, table=True):
    __tablename__ = "app_brands"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(unique=True)
    name: str
    description: Optional[str] = None
    defaults: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    youtube_accounts: list["BrandAccountYoutube"] = Relationship(back_populates="brand")
    instagram_accounts: list["BrandAccountInstagram"] = Relationship(back_populates="brand")


class BrandAccountYoutube(SQLModel, table=True):
    __tablename__ = "app_brand_account_youtube"

    id: Optional[int] = Field(default=None, primary_key=True)
    brand_id: int = Field(foreign_key="app_brands.id")
    channel_id: str = Field(unique=True)
    channel_title: Optional[str] = None
    access_token: Optional[str] = None  # criptografado
    refresh_token: Optional[str] = None  # criptografado
    token_expires_at: Optional[datetime] = None
    default_privacy: str = "private"
    default_category_id: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    brand: Optional[Brand] = Relationship(back_populates="youtube_accounts")


class BrandAccountInstagram(SQLModel, table=True):
    __tablename__ = "app_brand_account_instagram"

    id: Optional[int] = Field(default=None, primary_key=True)
    brand_id: int = Field(foreign_key="app_brands.id")
    ig_user_id: str = Field(unique=True)
    username: Optional[str] = None
    access_token: Optional[str] = None  # criptografado
    token_expires_at: Optional[datetime] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    brand: Optional[Brand] = Relationship(back_populates="instagram_accounts")
