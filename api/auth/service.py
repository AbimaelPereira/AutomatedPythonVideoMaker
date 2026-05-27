from datetime import datetime, timedelta
from jose import jwt, JWTError
import bcrypt
from sqlmodel import Session, select
import secrets

from config import settings
from auth.models import User, RefreshToken


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "name": user.name,
        "email": user.email,
        "id_group": user.id_group,
        "exp": datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def create_refresh_token(user: User, session: Session) -> str:
    token = secrets.token_urlsafe(64)
    expires_at = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    session.add(RefreshToken(token=token, id_user=user.id, expires_at=expires_at))
    session.commit()
    return token


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])


def authenticate_user(email: str, password: str, session: Session) -> User | None:
    user = session.exec(select(User).where(User.email == email)).first()
    if not user or not verify_password(password, user.password):
        return None
    return user


def rotate_refresh_token(old_token: str, session: Session) -> tuple[User, str] | None:
    record = session.exec(
        select(RefreshToken).where(RefreshToken.token == old_token)
    ).first()

    if not record or record.expires_at < datetime.utcnow():
        return None

    user = session.get(User, record.id_user)
    session.delete(record)

    new_token = create_refresh_token(user, session)
    return user, new_token
