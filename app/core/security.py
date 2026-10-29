from datetime import UTC, datetime, timedelta
from uuid import UUID

import bcrypt
import jwt

from app.core.config import settings

BCRYPT_MAX_PASSWORD_BYTES = 72


class InvalidTokenError(Exception):
    pass


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > BCRYPT_MAX_PASSWORD_BYTES:
        raise ValueError("Password is too long")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(subject: UUID | str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(subject),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> UUID:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError("Invalid or expired token") from exc

    if payload.get("type") != "access":
        raise InvalidTokenError("Invalid token type")

    subject = payload.get("sub")
    if not subject:
        raise InvalidTokenError("Token has no subject")

    try:
        return UUID(subject)
    except ValueError as exc:
        raise InvalidTokenError("Invalid token subject") from exc
