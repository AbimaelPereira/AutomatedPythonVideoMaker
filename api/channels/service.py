import json
from datetime import datetime
from sqlmodel import Session, select
from channels.models import Channel


def get_all(session: Session) -> list[Channel]:
    return session.exec(select(Channel)).all()


def get_by_slug(session: Session, slug: str) -> Channel | None:
    return session.exec(select(Channel).where(Channel.slug == slug)).first()


def create(session: Session, slug: str, name: str, config: dict) -> Channel:
    channel = Channel(slug=slug, name=name, config=json.dumps(config))
    session.add(channel)
    session.commit()
    session.refresh(channel)
    return channel


def update(session: Session, channel: Channel, name: str | None, config: dict | None) -> Channel:
    if name is not None:
        channel.name = name
    if config is not None:
        channel.config = json.dumps(config)
    channel.updated_at = datetime.utcnow()
    session.add(channel)
    session.commit()
    session.refresh(channel)
    return channel


def delete(session: Session, channel: Channel) -> None:
    session.delete(channel)
    session.commit()
