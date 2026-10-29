from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def make_token(
    secret: str | None = None,
    algorithm: str | None = None,
    **overrides: object,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "sub": str(uuid4()),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    payload.update(overrides)
    return jwt.encode(
        payload,
        secret or settings.secret_key,
        algorithm=algorithm or settings.jwt_algorithm,
    )


def test_hash_password_is_salted_and_verifiable() -> None:
    first = hash_password("password123")
    second = hash_password("password123")

    assert first != second
    assert verify_password("password123", first) is True
    assert verify_password("password124", first) is False


def test_hash_password_accepts_exactly_72_bytes() -> None:
    assert verify_password("a" * 72, hash_password("a" * 72)) is True


def test_hash_password_rejects_password_longer_than_72_bytes() -> None:
    with pytest.raises(ValueError):
        hash_password("a" * 73)

    with pytest.raises(ValueError):
        hash_password("я" * 37)


def test_verify_password_returns_false_for_malformed_hash() -> None:
    assert verify_password("password123", "not-a-bcrypt-hash") is False


def test_access_token_roundtrip() -> None:
    user_id = uuid4()

    assert decode_access_token(create_access_token(user_id)) == user_id
    assert decode_access_token(create_access_token(str(user_id))) == user_id


def test_decode_rejects_tampered_token() -> None:
    token = make_token()

    with pytest.raises(InvalidTokenError):
        decode_access_token(token + "tampered")


def test_decode_rejects_token_signed_with_other_secret() -> None:
    token = make_token(secret="another-secret-key-with-32-bytes-min")

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_decode_rejects_expired_token() -> None:
    token = make_token(exp=datetime.now(UTC) - timedelta(seconds=1))

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_decode_rejects_non_access_token_type() -> None:
    token = make_token(type="refresh")

    with pytest.raises(InvalidTokenError, match="Invalid token type"):
        decode_access_token(token)


def test_decode_rejects_missing_subject() -> None:
    token = jwt.encode(
        {"type": "access", "exp": datetime.now(UTC) + timedelta(minutes=5)},
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(InvalidTokenError, match="no subject"):
        decode_access_token(token)


def test_decode_rejects_non_uuid_subject() -> None:
    token = make_token(sub="not-a-uuid")

    with pytest.raises(InvalidTokenError, match="Invalid token subject"):
        decode_access_token(token)
