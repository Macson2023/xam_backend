import asyncio
import json
import socket
import threading
import time

import httpx
import pytest
import uvicorn
import websockets

from app.main import app
from app.realtime import manager
from tests.conftest import _reset_database, auth_headers

TIMEOUT = 10


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def base_url():
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=lambda: asyncio.run(server.serve()), daemon=True)
    thread.start()

    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("Test server did not start")

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture()
def clean_state():
    asyncio.run(_reset_database())
    manager._connections.clear()
    yield


async def _wait_for_message(websocket) -> dict:
    raw = await asyncio.wait_for(websocket.recv(), timeout=TIMEOUT)
    return json.loads(raw)


def _register(http: httpx.Client, username: str) -> dict:
    response = http.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "password": "password123",
            "display_name": username.title(),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_presence_online_offline_and_typing(base_url, clean_state) -> None:
    ws_base = base_url.replace("http://", "ws://")

    with httpx.Client(base_url=base_url) as http:
        alice = _register(http, "alice")
        bob = _register(http, "bob")
        chat = http.post(
            "/api/v1/chats",
            json={"participant_id": bob["user"]["id"]},
            headers=auth_headers(alice),
        ).json()

        async with websockets.connect(f"{ws_base}/ws?token={alice['access_token']}") as alice_ws:
            async with websockets.connect(f"{ws_base}/ws?token={bob['access_token']}") as bob_ws:
                online = await _wait_for_message(alice_ws)
                assert online["type"] == "user_status"
                assert online["data"] == {"user_id": bob["user"]["id"], "status": "online"}

                await bob_ws.send(json.dumps({"type": "typing", "data": {"chat_id": chat["id"]}}))
                typing = await _wait_for_message(alice_ws)
                assert typing["type"] == "typing"
                assert typing["data"] == {
                    "chat_id": chat["id"],
                    "user_id": bob["user"]["id"],
                    "is_typing": True,
                }

                await bob_ws.close()

            offline = await _wait_for_message(alice_ws)
            assert offline["type"] == "user_status"
            assert offline["data"] == {"user_id": bob["user"]["id"], "status": "offline"}


@pytest.mark.asyncio
async def test_new_message_delivered_to_other_user(base_url, clean_state) -> None:
    ws_base = base_url.replace("http://", "ws://")

    with httpx.Client(base_url=base_url) as http:
        alice = _register(http, "alice")
        bob = _register(http, "bob")
        chat = http.post(
            "/api/v1/chats",
            json={"participant_id": bob["user"]["id"]},
            headers=auth_headers(alice),
        ).json()

        async with websockets.connect(f"{ws_base}/ws?token={alice['access_token']}") as alice_ws:
            response = http.post(
                f"/api/v1/chats/{chat['id']}/messages",
                json={"content": "real server message"},
                headers=auth_headers(bob),
            )
            assert response.status_code == 201

            event = await _wait_for_message(alice_ws)
            assert event["type"] == "new_message"
            assert event["data"]["id"] == response.json()["id"]
            assert event["data"]["content"] == "real server message"


@pytest.mark.asyncio
async def test_typing_for_foreign_chat_returns_error(base_url, clean_state) -> None:
    ws_base = base_url.replace("http://", "ws://")

    with httpx.Client(base_url=base_url) as http:
        alice = _register(http, "alice")
        bob = _register(http, "bob")
        outsider = _register(http, "outsider")
        chat = http.post(
            "/api/v1/chats",
            json={"participant_id": bob["user"]["id"]},
            headers=auth_headers(alice),
        ).json()

        async with websockets.connect(
            f"{ws_base}/ws?token={outsider['access_token']}"
        ) as outsider_ws:
            await outsider_ws.send(json.dumps({"type": "typing", "data": {"chat_id": chat["id"]}}))
            event = await _wait_for_message(outsider_ws)

    assert event == {"type": "error", "data": {"detail": "Chat not found"}}
