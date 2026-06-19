import json
from datetime import datetime
from sqlmodel import Session, select
from channels.service import get_by_slug
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
    channel_slug: str | None = None,
    privacy_status: str | None = None,
    published_at: datetime | None = None,
    thumbnail_path: str | None = None,
    duration_seconds: float | None = None,
    transcript: str | None = None,
) -> Video:
    if channel_id is None and channel_slug:
        channel = get_by_slug(session, channel_slug)
        channel_id = channel.id if channel else None

    video = get_video_by_youtube_id(session, youtube_id)
    if video is None:
        video = Video(youtube_id=youtube_id)
        session.add(video)

    video.title = title
    video.description = description
    video.tags = json.dumps(tags, ensure_ascii=False) if tags else None
    video.category_id = category_id
    video.slug = slug
    video.channel_id = channel_id
    video.privacy_status = privacy_status
    video.published_at = published_at
    video.thumbnail_path = thumbnail_path
    video.duration_seconds = duration_seconds
    video.transcript = transcript
    video.updated_at = datetime.utcnow()

    session.commit()
    session.refresh(video)
    return video


def get_video_by_youtube_id(session: Session, youtube_id: str) -> Video | None:
    return session.exec(select(Video).where(Video.youtube_id == youtube_id)).first()
