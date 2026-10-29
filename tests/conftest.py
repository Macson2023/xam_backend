import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

DB_PATH = Path(tempfile.gettempdir()) / "xam_backend_test.db"
UPLOAD_DIR = Path(tempfile.gettempdir()) / "xam_backend_test_uploads"
if DB_PATH.exists():
    DB_PATH.unlink()
if UPLOAD_DIR.exists():
    shutil.rmtree(UPLOAD_DIR)

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"
os.environ["SECRET_KEY"] = "test-secret-key-with-at-least-32-bytes"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "60"
os.environ["AUTO_CREATE_TABLES"] = "false"
os.environ["UPLOAD_DIR"] = str(UPLOAD_DIR)

from fastapi.testclient import TestClient  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.realtime import manager  # noqa: E402

DEFAULT_PASSWORD = "password123"


async def _reset_database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)


@pytest.fixture()
def client():
    asyncio.run(_reset_database())
    shutil.rmtree(UPLOAD_DIR, ignore_errors=True)
    manager._connections.clear()
    with TestClient(app) as test_client:
        yield test_client


def register(
    client: TestClient,
    username: str | None = None,
    password: str = DEFAULT_PASSWORD,
    display_name: str | None = None,
) -> dict:
    username = username or f"user_{uuid4().hex[:10]}"
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "password": password,
            "display_name": display_name or username.upper(),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def auth_headers(user: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {user['access_token']}"}


def create_chat(client: TestClient, sender: dict, participant_id: str) -> dict:
    response = client.post(
        "/api/v1/chats",
        json={"participant_id": participant_id},
        headers=auth_headers(sender),
    )
    assert response.status_code == 200, response.text
    return response.json()
