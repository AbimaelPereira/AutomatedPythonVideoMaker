from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from pydantic import BaseModel
from typing import Optional

from database import get_session
from middleware.auth import get_current_user, require_service_token
from auth.models import User
from assets.models import RemoteAssetMidia
from assets import service

router = APIRouter()


# ---------------------------------------------------------------------------
# API interna por slug/url — consumida pelo videomaker (HTTPAssetStorage).
# Autenticada por X-Service-Token, não por JWT de usuário.
# Declarada antes das rotas /{asset_id} para não colidir no path matching.
# ---------------------------------------------------------------------------

class InternalMidiaCreate(BaseModel):
    url: str
    type: str = "unknown"
    extension: Optional[str] = None
    description: Optional[str] = None

class UrlBody(BaseModel):
    url: str


@router.get("/internal/slugs", dependencies=[Depends(require_service_token)])
def internal_list_slugs(session: Session = Depends(get_session)):
    return service.list_all_slugs(session)

@router.get("/internal/stats", dependencies=[Depends(require_service_token)])
def internal_stats(session: Session = Depends(get_session)):
    return service.get_stats(session)

@router.get("/internal/by-slug/{slug}", dependencies=[Depends(require_service_token)])
def internal_get_by_slug(slug: str, session: Session = Depends(get_session)):
    asset = service.get_asset_by_slug(slug, session)
    if not asset:
        raise HTTPException(status_code=404, detail="Slug não encontrado")
    return asset

@router.post("/internal/by-slug/{slug}/midia", dependencies=[Depends(require_service_token)])
def internal_add_midia(slug: str, body: InternalMidiaCreate, session: Session = Depends(get_session)):
    data = body.model_dump()
    description = data.pop("description") or ""
    return service.add_media_by_slug(slug, data, session, description=description)

@router.patch("/internal/midia/mark-invalid", dependencies=[Depends(require_service_token)])
def internal_mark_invalid(body: UrlBody, session: Session = Depends(get_session)):
    return {"affected": service.mark_invalid_by_url(body.url, session)}

@router.patch("/internal/midia/touch", dependencies=[Depends(require_service_token)])
def internal_touch(body: UrlBody, session: Session = Depends(get_session)):
    return {"affected": service.touch_last_used_by_url(body.url, session)}


class AssetCreate(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None

class AssetUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None

class MidiaCreate(BaseModel):
    url: str
    type: str = "unknown"
    extension: Optional[str] = None

class MidiaUpdate(BaseModel):
    url: Optional[str] = None
    type: Optional[str] = None
    extension: Optional[str] = None

class BulkMidiaCreate(BaseModel):
    urls: list[str]


@router.get("")
def list_assets(session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    return service.list_assets(session)

@router.get("/{asset_id}")
def get_asset(asset_id: int, session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    asset = service.get_asset(asset_id, session)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset não encontrado")
    return asset

@router.post("", status_code=201)
def create_asset(body: AssetCreate, session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    return service.create_asset(body.model_dump(), session)

@router.put("/{asset_id}")
def update_asset(asset_id: int, body: AssetUpdate, session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    from assets.models import RemoteAsset
    asset = session.get(RemoteAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset não encontrado")
    return service.update_asset(asset, body.model_dump(exclude_none=True), session)

@router.delete("/{asset_id}", status_code=204)
def delete_asset(asset_id: int, session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    from assets.models import RemoteAsset
    asset = session.get(RemoteAsset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset não encontrado")
    service.delete_asset(asset, session)

@router.get("/{asset_id}/midia")
def list_midias(asset_id: int, session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    return service.list_midias(asset_id, session)

@router.post("/{asset_id}/midia", status_code=201)
def create_midia(asset_id: int, body: MidiaCreate, session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    return service.create_midia(asset_id, body.model_dump(), session)

@router.post("/{asset_id}/midia/bulk", status_code=201)
def bulk_create_midias(asset_id: int, body: BulkMidiaCreate, session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    return service.bulk_create_midias(asset_id, body.urls, session)

@router.put("/midia/{midia_id}")
def update_midia(midia_id: int, body: MidiaUpdate, session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    midia = session.get(RemoteAssetMidia, midia_id)
    if not midia:
        raise HTTPException(status_code=404, detail="Mídia não encontrada")
    return service.update_midia(midia, body.model_dump(exclude_none=True), session)

@router.delete("/midia/{midia_id}", status_code=204)
def delete_midia(midia_id: int, session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    midia = session.get(RemoteAssetMidia, midia_id)
    if not midia:
        raise HTTPException(status_code=404, detail="Mídia não encontrada")
    service.delete_midia(midia, session)

@router.patch("/midia/{midia_id}/toggle-invalid")
def toggle_invalid(midia_id: int, session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    midia = session.get(RemoteAssetMidia, midia_id)
    if not midia:
        raise HTTPException(status_code=404, detail="Mídia não encontrada")
    return service.toggle_invalid(midia, session)
