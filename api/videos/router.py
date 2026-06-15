from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional
from database import get_session
from videos.models import Video
from videos.service import create_video_after_upload

router = APIRouter()


class VideoCreateRequest(BaseModel):
    youtube_id: str
    title: str
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    category_id: Optional[str] = None
    slug: Optional[str] = None
    channel_id: Optional[int] = None
    privacy_status: Optional[str] = None
    thumbnail_path: Optional[str] = None
    duration_seconds: Optional[float] = None
    transcript: Optional[str] = None


@router.post("/", response_model=Video, status_code=201)
def create_video(payload: VideoCreateRequest, session: Session = Depends(get_session)):
    return create_video_after_upload(session, **payload.model_dump())


@router.get("/", response_model=list[Video])
def list_videos(session: Session = Depends(get_session)):
    return session.exec(select(Video)).all()


@router.get("/{video_id}", response_model=Video)
def get_video(video_id: int, session: Session = Depends(get_session)):
    video = session.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video
