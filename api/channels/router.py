import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session
from typing import Optional

from database import get_session
from middleware.auth import get_current_user
from auth.models import User
from channels import service

router = APIRouter()


class ChannelResponse(BaseModel):
    id: int
    slug: str
    name: str
    config: dict
    status: int

    @classmethod
    def from_orm(cls, channel):
        return cls(
            id=channel.id,
            slug=channel.slug,
            name=channel.name,
            config=json.loads(channel.config),
            status=channel.status,
        )


class CreateChannelRequest(BaseModel):
    slug: str
    name: str
    config: dict = {}


class UpdateChannelRequest(BaseModel):
    name: Optional[str] = None
    config: Optional[dict] = None


@router.get("")
def list_channels(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    channels = service.get_all(session)
    return [ChannelResponse.from_orm(c) for c in channels]


@router.get("/{slug}")
def get_channel(
    slug: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    channel = service.get_by_slug(session, slug)
    if not channel:
        raise HTTPException(status_code=404, detail="Canal não encontrado")
    return ChannelResponse.from_orm(channel)


@router.post("")
def create_channel(
    body: CreateChannelRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if service.get_by_slug(session, body.slug):
        raise HTTPException(status_code=409, detail="Slug já existe")
    channel = service.create(session, body.slug, body.name, body.config)
    return ChannelResponse.from_orm(channel)


@router.put("/{slug}")
def update_channel(
    slug: str,
    body: UpdateChannelRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    channel = service.get_by_slug(session, slug)
    if not channel:
        raise HTTPException(status_code=404, detail="Canal não encontrado")
    channel = service.update(session, channel, body.name, body.config)
    return ChannelResponse.from_orm(channel)


@router.delete("/{slug}")
def delete_channel(
    slug: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    channel = service.get_by_slug(session, slug)
    if not channel:
        raise HTTPException(status_code=404, detail="Canal não encontrado")
    service.delete(session, channel)
    return {"ok": True}
