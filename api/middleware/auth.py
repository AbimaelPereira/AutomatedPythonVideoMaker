from typing import Optional

from fastapi import Header, HTTPException, status

from config import settings


def require_service_token(x_service_token: Optional[str] = Header(default=None)) -> None:
    """Autentica chamadas via header X-Service-Token."""
    if not x_service_token or x_service_token != settings.SERVICE_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Service token inválido")
