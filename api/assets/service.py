from sqlmodel import Session, select, func
from assets.models import RemoteAsset, RemoteAssetMidia

IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "avif"}
VIDEO_EXTENSIONS = {"mp4", "webm", "mov", "avi"}


def _infer_type(url: str) -> tuple[str, str]:
    ext = url.rsplit(".", 1)[-1].lower() if "." in url else ""
    if ext in IMAGE_EXTENSIONS:
        return "image", ext
    if ext in VIDEO_EXTENSIONS:
        return "video", ext
    return "unknown", ext


def list_assets(session: Session):
    assets = session.exec(select(RemoteAsset)).all()
    result = []
    for asset in assets:
        count = session.exec(select(func.count(RemoteAssetMidia.id)).where(RemoteAssetMidia.id_asset == asset.id)).one()
        result.append({**asset.model_dump(), "midia_count": count})
    return result

def get_asset(asset_id: int, session: Session):
    asset = session.get(RemoteAsset, asset_id)
    if not asset:
        return None
    midias = session.exec(select(RemoteAssetMidia).where(RemoteAssetMidia.id_asset == asset_id)).all()
    return {**asset.model_dump(), "midias": [m.model_dump() for m in midias]}

def create_asset(data: dict, session: Session) -> RemoteAsset:
    asset = RemoteAsset(**data)
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset

def update_asset(asset: RemoteAsset, data: dict, session: Session) -> RemoteAsset:
    for k, v in data.items():
        setattr(asset, k, v)
    session.commit()
    session.refresh(asset)
    return asset

def delete_asset(asset: RemoteAsset, session: Session):
    session.exec(select(RemoteAssetMidia).where(RemoteAssetMidia.id_asset == asset.id))
    midias = session.exec(select(RemoteAssetMidia).where(RemoteAssetMidia.id_asset == asset.id)).all()
    for m in midias:
        session.delete(m)
    session.delete(asset)
    session.commit()


def list_midias(asset_id: int, session: Session):
    return session.exec(select(RemoteAssetMidia).where(RemoteAssetMidia.id_asset == asset_id)).all()

def create_midia(asset_id: int, data: dict, session: Session) -> RemoteAssetMidia:
    midia = RemoteAssetMidia(id_asset=asset_id, **data)
    session.add(midia)
    session.commit()
    session.refresh(midia)
    return midia

def bulk_create_midias(asset_id: int, urls: list[str], session: Session):
    created = []
    for url in urls:
        type_, ext = _infer_type(url)
        midia = RemoteAssetMidia(id_asset=asset_id, url=url, type=type_, extension=ext)
        session.add(midia)
        created.append(midia)
    session.commit()
    return created

def update_midia(midia: RemoteAssetMidia, data: dict, session: Session) -> RemoteAssetMidia:
    for k, v in data.items():
        setattr(midia, k, v)
    session.commit()
    session.refresh(midia)
    return midia

def delete_midia(midia: RemoteAssetMidia, session: Session):
    session.delete(midia)
    session.commit()

def toggle_invalid(midia: RemoteAssetMidia, session: Session) -> RemoteAssetMidia:
    midia.is_invalid = 0 if midia.is_invalid else 1
    session.commit()
    session.refresh(midia)
    return midia
