from datetime import datetime
from sqlmodel import Session, select, func
from assets.models import RemoteAsset, RemoteAssetMidia

IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "avif"}
VIDEO_EXTENSIONS = {"mp4", "webm", "mov", "avi"}

# extension é varchar(20) no banco; URLs com query string geram "extensões" enormes.
MAX_EXTENSION_LEN = 20


def _infer_type(url: str) -> tuple[str, str]:
    ext = url.rsplit(".", 1)[-1].lower() if "." in url else ""
    if ext in IMAGE_EXTENSIONS:
        return "image", ext
    if ext in VIDEO_EXTENSIONS:
        return "video", ext
    return "unknown", ext


def list_assets(session: Session):
    """Lista assets com contadores agregados (total, válidas, inválidas) e última data de uso."""
    rows = session.exec(
        select(
            RemoteAssetMidia.id_asset,
            func.count(RemoteAssetMidia.id),
            func.sum(RemoteAssetMidia.is_invalid),
            func.max(RemoteAssetMidia.last_used),
        ).group_by(RemoteAssetMidia.id_asset)
    ).all()
    agg = {
        r[0]: {
            "midia_count": int(r[1] or 0),
            "invalid_count": int(r[2] or 0),
            "last_used": r[3],
        }
        for r in rows
    }

    result = []
    for asset in session.exec(select(RemoteAsset)).all():
        a = agg.get(asset.id, {"midia_count": 0, "invalid_count": 0, "last_used": None})
        valid_count = a["midia_count"] - a["invalid_count"]
        result.append({
            **asset.model_dump(),
            "midia_count": a["midia_count"],
            "invalid_count": a["invalid_count"],
            "valid_count": valid_count,
            "last_used": a["last_used"],
        })
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
        midia = RemoteAssetMidia(
            id_asset=asset_id, url=url, type=type_,
            extension=_sanitize_extension(ext),
        )
        session.add(midia)
        created.append(midia)
    session.commit()
    for m in created:
        session.refresh(m)
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


# --- API interna por slug/url (consumida pelo videomaker via HTTPAssetStorage) ---

def _slug_to_name(slug: str) -> str:
    return slug.replace("_", " ").replace("-", " ").strip().title() or slug


def _sanitize_extension(ext: str | None) -> str | None:
    if not ext:
        return None
    return ext if len(ext) <= MAX_EXTENSION_LEN else None


def get_asset_by_slug(slug: str, session: Session):
    """Retorna {slug, description, midias:[...]} ou None — formato compatível com RemoteAssetStorage."""
    asset = session.exec(select(RemoteAsset).where(RemoteAsset.slug == slug)).first()
    if not asset:
        return None
    midias = session.exec(select(RemoteAssetMidia).where(RemoteAssetMidia.id_asset == asset.id)).all()
    return {**asset.model_dump(), "midias": [m.model_dump() for m in midias]}


def add_media_by_slug(slug: str, data: dict, session: Session, description: str = "") -> RemoteAssetMidia:
    """Cria o asset se não existir e faz upsert da mídia por URL (merge: reseta is_invalid e toca last_used)."""
    asset = session.exec(select(RemoteAsset).where(RemoteAsset.slug == slug)).first()
    if not asset:
        asset = RemoteAsset(name=_slug_to_name(slug), slug=slug, description=description or None)
        session.add(asset)
        session.commit()
        session.refresh(asset)

    url = data["url"]
    midia = session.exec(
        select(RemoteAssetMidia).where(
            RemoteAssetMidia.id_asset == asset.id, RemoteAssetMidia.url == url
        )
    ).first()

    if midia:
        midia.is_invalid = 0
        midia.last_used = datetime.utcnow()
    else:
        type_ = data.get("type") or "unknown"
        ext = _sanitize_extension(data.get("extension"))
        if type_ == "unknown" and not data.get("extension"):
            type_, ext = _infer_type(url)
            ext = _sanitize_extension(ext)
        midia = RemoteAssetMidia(
            id_asset=asset.id, url=url, type=type_, extension=ext,
            last_used=datetime.utcnow(),
        )
        session.add(midia)

    session.commit()
    session.refresh(midia)
    return midia


def mark_invalid_by_url(url: str, session: Session) -> int:
    """Marca como inválida toda mídia com essa URL. Retorna quantas foram afetadas."""
    midias = session.exec(select(RemoteAssetMidia).where(RemoteAssetMidia.url == url)).all()
    for m in midias:
        m.is_invalid = 1
    if midias:
        session.commit()
    return len(midias)


def touch_last_used_by_url(url: str, session: Session) -> int:
    """Atualiza last_used de toda mídia com essa URL. Retorna quantas foram afetadas."""
    now = datetime.utcnow()
    midias = session.exec(select(RemoteAssetMidia).where(RemoteAssetMidia.url == url)).all()
    for m in midias:
        m.last_used = now
    if midias:
        session.commit()
    return len(midias)


def list_all_slugs(session: Session) -> list[str]:
    return list(session.exec(select(RemoteAsset.slug)).all())


def get_stats(session: Session) -> dict:
    total_slugs = session.exec(select(func.count(RemoteAsset.id))).one()
    total_media = session.exec(select(func.count(RemoteAssetMidia.id))).one()
    invalid = session.exec(
        select(func.count(RemoteAssetMidia.id)).where(RemoteAssetMidia.is_invalid == 1)
    ).one()
    return {
        "total_slugs": total_slugs,
        "total_media": total_media,
        "invalid_media": invalid,
        "valid_media": total_media - invalid,
    }
