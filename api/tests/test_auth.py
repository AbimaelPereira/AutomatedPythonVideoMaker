from datetime import datetime, timedelta

from app.brands.models import Brand
from app.core.security import generate_token
from app.users.models import ApiToken, BrandUser, User


def _token(session, **token_fields) -> str:
    brand = Brand(slug="test_brand", name="Test Brand")
    user = User(email="test@example.com")
    session.add_all([brand, user])
    session.flush()
    session.add(BrandUser(brand_id=brand.id, user_id=user.id))
    session.flush()
    token, prefix, digest = generate_token()
    session.add(ApiToken(user_id=user.id, brand_id=brand.id, prefix=prefix, token_hash=digest, **token_fields))
    session.flush()
    return token


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_sem_token(client):
    assert client.get("/me").status_code == 401


def test_token_invalido(client):
    assert client.get("/me", headers={"Authorization": "Bearer nada"}).status_code == 401


def test_token_valido(client, session):
    token = _token(session)
    r = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["brand"]["slug"] == "test_brand"


def test_token_revogado(client, session):
    token = _token(session, revoked_at=datetime.now())
    assert client.get("/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_token_expirado(client, session):
    token = _token(session, expires_at=datetime.now() - timedelta(minutes=1))
    assert client.get("/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
