from sqlmodel import SQLModel, Field
from sqlalchemy import Column, Text
from typing import Optional
from datetime import datetime


class Video(SQLModel, table=True):
    __tablename__ = "app_videos"

    id: Optional[int] = Field(default=None, primary_key=True)

    # Identificação
    youtube_id: Optional[str] = Field(default=None, unique=True, index=True)
    channel_id: Optional[int] = Field(default=None, foreign_key="app_channels.id")
    slug: Optional[str] = Field(default=None)  # slug do JSON de geração

    # Metadados do vídeo
    title: str
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    tags: Optional[str] = Field(default=None, sa_column=Column(Text))        # JSON array serializado
    category_id: Optional[str] = Field(default=None)
    duration_seconds: Optional[float] = Field(default=None)
    thumbnail_path: Optional[str] = Field(default=None)

    # Transcrição completa extraída das cenas
    transcript: Optional[str] = Field(default=None, sa_column=Column(Text))

    # Status de publicação
    privacy_status: Optional[str] = Field(default=None)  # public, private, unlisted
    published_at: Optional[datetime] = Field(default=None)

    # Métricas (preenchidas depois via sync com YouTube Analytics)
    views: Optional[int] = Field(default=None)
    likes: Optional[int] = Field(default=None)
    comments: Optional[int] = Field(default=None)
    shares: Optional[int] = Field(default=None)
    subscribers_gained: Optional[int] = Field(default=None)
    subscribers_lost: Optional[int] = Field(default=None)
    impressions: Optional[int] = Field(default=None)
    impressions_ctr_rate: Optional[float] = Field(default=None)
    average_view_duration: Optional[float] = Field(default=None)
    average_view_percentage: Optional[float] = Field(default=None)
    estimated_minutes_watched: Optional[float] = Field(default=None)

    # Métricas detalhadas em JSON (audience retention, top countries, faixas etárias, etc.)
    audience_retention_data: Optional[str] = Field(default=None, sa_column=Column(Text))
    top_countries: Optional[str] = Field(default=None, sa_column=Column(Text))
    age_group_data: Optional[str] = Field(default=None, sa_column=Column(Text))
    traffic_source_types: Optional[str] = Field(default=None, sa_column=Column(Text))

    # Controle
    metrics_updated_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
