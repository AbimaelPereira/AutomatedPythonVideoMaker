from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from pydantic import BaseModel
from typing import Optional

from database import get_session
from middleware.auth import get_current_user, require_admin
from auth.models import User
from admin import service

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    id_group: int
    status: int = 1

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    id_group: Optional[int] = None
    status: Optional[int] = None

class GroupCreate(BaseModel):
    name: str
    permissions: dict = {}
    status: int = 1

class GroupUpdate(BaseModel):
    name: Optional[str] = None
    permissions: Optional[dict] = None
    status: Optional[int] = None

class ModuleCreate(BaseModel):
    name: str
    slug: str
    icon: Optional[str] = None
    id_parent: Optional[int] = None
    status: int = 1
    order_by: int = 0
    show_in_menu: int = 1
    actions: str = "view"

class ModuleUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    icon: Optional[str] = None
    id_parent: Optional[int] = None
    status: Optional[int] = None
    order_by: Optional[int] = None
    show_in_menu: Optional[int] = None
    actions: Optional[str] = None


# ── Users ──────────────────────────────────────────────────────────────────

@router.get("/users")
def list_users(session: Session = Depends(get_session), _: User = Depends(require_admin)):
    return service.list_users(session)

@router.get("/users/{user_id}")
def get_user(user_id: int, session: Session = Depends(get_session), _: User = Depends(require_admin)):
    user = service.get_user(user_id, session)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return user

@router.post("/users", status_code=201)
def create_user(body: UserCreate, session: Session = Depends(get_session), _: User = Depends(require_admin)):
    return service.create_user(body.model_dump(), session)

@router.put("/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, session: Session = Depends(get_session), _: User = Depends(require_admin)):
    user = service.get_user(user_id, session)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    return service.update_user(user, body.model_dump(exclude_none=True), session)

@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, session: Session = Depends(get_session), _: User = Depends(require_admin)):
    user = service.get_user(user_id, session)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    service.delete_user(user, session)


# ── Groups ─────────────────────────────────────────────────────────────────

@router.get("/groups")
def list_groups(session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    return service.list_groups(session)

@router.get("/groups/{group_id}")
def get_group(group_id: int, session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    group = service.get_group(group_id, session)
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    return group

@router.post("/groups", status_code=201)
def create_group(body: GroupCreate, session: Session = Depends(get_session), _: User = Depends(require_admin)):
    return service.create_group(body.model_dump(), session)

@router.put("/groups/{group_id}")
def update_group(group_id: int, body: GroupUpdate, session: Session = Depends(get_session), _: User = Depends(require_admin)):
    group = service.get_group(group_id, session)
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    return service.update_group(group, body.model_dump(exclude_none=True), session)

@router.delete("/groups/{group_id}", status_code=204)
def delete_group(group_id: int, session: Session = Depends(get_session), _: User = Depends(require_admin)):
    group = service.get_group(group_id, session)
    if not group:
        raise HTTPException(status_code=404, detail="Grupo não encontrado")
    service.delete_group(group, session)


# ── Modules ────────────────────────────────────────────────────────────────

@router.get("/modules")
def list_visible_modules(session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    group = service.get_group(current_user.id_group, session)
    return service.list_visible_modules(current_user.id_group, group.permissions if group else "{}", session)

@router.get("/si-modules")
def list_modules(session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    return service.list_modules(session)

@router.get("/si-modules/parents")
def list_parent_modules(session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    return service.list_parent_modules(session)

@router.get("/si-modules/{module_id}")
def get_module(module_id: int, session: Session = Depends(get_session), _: User = Depends(get_current_user)):
    module = service.get_module(module_id, session)
    if not module:
        raise HTTPException(status_code=404, detail="Módulo não encontrado")
    return module

@router.post("/si-modules", status_code=201)
def create_module(body: ModuleCreate, session: Session = Depends(get_session), _: User = Depends(require_admin)):
    return service.create_module(body.model_dump(), session)

@router.put("/si-modules/{module_id}")
def update_module(module_id: int, body: ModuleUpdate, session: Session = Depends(get_session), _: User = Depends(require_admin)):
    module = service.get_module(module_id, session)
    if not module:
        raise HTTPException(status_code=404, detail="Módulo não encontrado")
    return service.update_module(module, body.model_dump(exclude_none=True), session)

@router.delete("/si-modules/{module_id}", status_code=204)
def delete_module(module_id: int, session: Session = Depends(get_session), _: User = Depends(require_admin)):
    module = service.get_module(module_id, session)
    if not module:
        raise HTTPException(status_code=404, detail="Módulo não encontrado")
    service.delete_module(module, session)
