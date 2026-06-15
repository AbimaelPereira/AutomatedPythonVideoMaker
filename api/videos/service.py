import json
from datetime import datetime
from sqlmodel import Session, select
from videos.models import Video


def create_video_after_upload(
    session: Session,
    *,
    youtube_id: str,
    title: str,
    description: str | None = None,
    tags: list[str] | None = None,
    category_id: str | None = None,
    slug: str | None = None,
    channel_id: int | None = None,
    privacy_status: str | None = None,
    published_at: datetime | None = None,
    thumbnail_path: str | None = None,
    duration_seconds: float | None = None,
    transcript: str | None = None,
) -> Video:
    video = Video(
        youtube_id=youtube_id,
        title=title,
        description=description,
        tags=json.dumps(tags, ensure_ascii=False) if tags else None,
        category_id=category_id,
        slug=slug,
        channel_id=channel_id,
        privacy_status=privacy_status,
        published_at=published_at,
        thumbnail_path=thumbnail_path,
        duration_seconds=duration_seconds,
        transcript=transcript,
    )
    session.add(video)
    session.commit()
    session.refresh(video)
    return video


def get_video_by_youtube_id(session: Session, youtube_id: str) -> Video | None:
    return session.exec(select(Video).where(Video.youtube_id == youtube_id)).first()
