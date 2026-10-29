from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from fastapi.testclient import TestClient

from app.core.config import settings
from tests.conftest import DEFAULT_PASSWORD, auth_headers, register


def signed_token(**claims: object) -> str:
    payload: dict[str, object] = {
        "sub": str(uuid4()),
        "type": "access",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    payload.update(claims)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def test_register_returns_token_and_user(client: TestClient) -> None:
    payload = register(client, username="alice", display_name="Alice")

    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["expires_in"] == 3600
    assert payload["user"]["username"] == "alice"
    assert payload["user"]["display_name"] == "Alice"
    assert "password_hash" not in payload["user"]


def test_register_rejects_duplicate_username(client: TestClient) -> None:
    register(client, username="alice")
    response = client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "password": DEFAULT_PASSWORD, "display_name": "Alice 2"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Username already taken"}


def test_register_validates_username(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"username": "a!", "password": DEFAULT_PASSWORD, "display_name": "Bad"},
    )

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_login_success_and_failure(client: TestClient) -> None:
    register(client, username="alice", password="supersecret1")

    response = client.post(
        "/api/v1/auth/login", json={"username": "alice", "password": "supersecret1"}
    )
    assert response.status_code == 200
    assert response.json()["user"]["username"] == "alice"

    response = client.post(
        "/api/v1/auth/login", json={"username": "alice", "password": "wrongpass"}
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid username or password"}


def test_me_requires_valid_token(client: TestClient) -> None:
    user = register(client, username="alice")

    response = client.get("/api/v1/users/me", headers=auth_headers(user))
    assert response.status_code == 200
    assert response.json()["id"] == user["user"]["id"]

    assert client.get("/api/v1/users/me").status_code == 401
    assert (
        client.get("/api/v1/users/me", headers={"Authorization": "Bearer nope"}).status_code == 401
    )


def test_search_users_excludes_current_user(client: TestClient) -> None:
    alice = register(client, username="alice")
    register(client, username="alicia")
    register(client, username="bob")

    response = client.get("/api/v1/users/search", params={"q": "ali"}, headers=auth_headers(alice))
    assert response.status_code == 200
    usernames = [item["username"] for item in response.json()]
    assert usernames == ["alicia"]


def test_register_rejects_blank_display_name(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "password": DEFAULT_PASSWORD, "display_name": "   "},
    )

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_register_rejects_password_longer_than_bcrypt_limit(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "password": "я" * 40, "display_name": "Alice"},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Password is too long"}


def test_register_rejects_too_long_password_at_schema_level(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "password": "a" * 73, "display_name": "Alice"},
    )

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_login_with_unknown_user_returns_401(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"username": "nobody", "password": DEFAULT_PASSWORD}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid username or password"}


def test_protected_endpoint_rejects_non_bearer_scheme(client: TestClient) -> None:
    response = client.get("/api/v1/users/me", headers={"Authorization": "Basic abc"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_protected_endpoint_rejects_token_for_unknown_user(client: TestClient) -> None:
    response = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {signed_token()}"})

    assert response.status_code == 401


def test_protected_endpoint_rejects_expired_token(client: TestClient) -> None:
    user = register(client, username="alice")
    token = signed_token(sub=user["user"]["id"], exp=datetime.now(UTC) - timedelta(seconds=1))

    response = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_protected_endpoint_rejects_non_access_token(client: TestClient) -> None:
    user = register(client, username="alice")
    token = signed_token(sub=user["user"]["id"], type="refresh")

    response = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
