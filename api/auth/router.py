from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session
from pydantic import BaseModel

from database import get_session
from middleware.auth import get_current_user
from auth.models import User
from auth import service

router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/login")
def login(body: LoginRequest, session: Session = Depends(get_session)):
    user = service.authenticate_user(body.email, body.password, session)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")

    return {
        "access_token": service.create_access_token(user),
        "refresh_token": service.create_refresh_token(user, session),
        "user": {"id": user.id, "name": user.name, "email": user.email, "id_group": user.id_group},
    }


@router.post("/refresh")
def refresh(body: RefreshRequest, session: Session = Depends(get_session)):
    result = service.rotate_refresh_token(body.refresh_token, session)
    if not result:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token inválido ou expirado")

    user, new_refresh = result
    return {
        "access_token": service.create_access_token(user),
        "refresh_token": new_refresh,
    }


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "name": current_user.name, "email": current_user.email, "id_group": current_user.id_group}
