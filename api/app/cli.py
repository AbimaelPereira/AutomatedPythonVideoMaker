"""Utilitários de linha de comando.

    uv run python -m app.cli create-token --email x@y.com --brand slug [--name worker]

Cria usuário e vínculo com a marca se não existirem e imprime o token (uma única vez).
"""

import argparse

from sqlalchemy import select

from app.brands.models import Brand
from app.core.db import SessionLocal
from app.core.security import generate_token
from app.users.models import ApiToken, BrandUser, User


def create_token(email: str, brand_slug: str, name: str | None) -> str:
    with SessionLocal() as s:
        brand = s.scalar(select(Brand).where(Brand.slug == brand_slug))
        if brand is None:
            raise SystemExit(f"Marca '{brand_slug}' não existe")
        user = s.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email)
            s.add(user)
            s.flush()
        if s.get(BrandUser, (brand.id, user.id)) is None:
            s.add(BrandUser(brand_id=brand.id, user_id=user.id))
            s.flush()
        token, prefix, digest = generate_token()
        s.add(ApiToken(user_id=user.id, brand_id=brand.id, name=name, prefix=prefix, token_hash=digest))
        s.commit()
        return token


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("create-token")
    t.add_argument("--email", required=True)
    t.add_argument("--brand", required=True)
    t.add_argument("--name")
    a = p.parse_args()
    if a.cmd == "create-token":
        print(create_token(a.email, a.brand, a.name))


if __name__ == "__main__":
    main()
