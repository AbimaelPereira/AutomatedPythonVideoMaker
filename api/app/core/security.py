import hashlib
import secrets

TOKEN_PREFIX = "avm_"


def generate_token() -> tuple[str, str, str]:
    """Retorna (token puro, prefix, sha256). O token puro só é mostrado uma vez."""
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    return token, token[:12], hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
