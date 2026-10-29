import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.conftest import auth_headers, create_chat, register


def ws_url(user: dict) -> str:
    return f"/ws?token={user['access_token']}"


def test_websocket_requires_valid_token(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws?token=bad-token"):
            pass


def test_websocket_ping_pong(client: TestClient) -> None:
    alice = register(client, username="alice")

    with client.websocket_connect(ws_url(alice)) as websocket:
        websocket.send_text("ping")
        assert websocket.receive_json() == {"type": "pong"}

        websocket.send_json({"type": "ping"})
        assert websocket.receive_json() == {"type": "pong"}


def test_new_message_is_broadcast_over_websocket(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    with client.websocket_connect(ws_url(alice)) as websocket:
        response = client.post(
            f"/api/v1/chats/{chat['id']}/messages",
            json={"content": "live message"},
            headers=auth_headers(bob),
        )
        assert response.status_code == 201

        event = websocket.receive_json()

    assert event["type"] == "new_message"
    assert event["data"]["id"] == response.json()["id"]
    assert event["data"]["content"] == "live message"


def test_invalid_ws_event_returns_error(client: TestClient) -> None:
    alice = register(client, username="alice")

    with client.websocket_connect(ws_url(alice)) as websocket:
        websocket.send_text("not-json")
        event = websocket.receive_json()

    assert event == {"type": "error", "data": {"detail": "Invalid JSON"}}
