from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.brands.models import Brand
from app.core.db import get_session
from app.core.security import hash_token
from app.users.models import ApiToken, User

_bearer = HTTPBearer(auto_error=False)


@dataclass
class Principal:
    """Quem está chamando: o usuário e a única marca que o token pode acessar."""

    user: User
    brand: Brand
    token_id: int


def get_principal(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[Session, Depends(get_session)],
) -> Principal:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token ausente")

    now = datetime.now()
    row = session.execute(
        select(ApiToken, User, Brand)
        .join(User, User.id == ApiToken.user_id)
        .join(Brand, Brand.id == ApiToken.brand_id)
        .where(ApiToken.token_hash == hash_token(creds.credentials))
    ).first()

    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido")
    token, user, brand = row
    if token.revoked_at is not None or (token.expires_at and token.expires_at <= now):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token revogado ou expirado")
    if not user.is_active or not brand.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Usuário ou marca inativa")

    token.last_used_at = now
    session.commit()
    return Principal(user=user, brand=brand, token_id=token.id)


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]
