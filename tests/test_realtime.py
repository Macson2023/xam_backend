import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.conftest import auth_headers, create_chat, register


def ws_url(user: dict) -> str:
    return f"/ws?token={user['access_token']}"


def test_websocket_requires_valid_token(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws?token=bad-token"):
            pass

    assert exc_info.value.code == 1008


def test_websocket_requires_token(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws"):
            pass

    assert exc_info.value.code == 1008


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


def test_non_object_ws_event_returns_error(client: TestClient) -> None:
    alice = register(client, username="alice")

    with client.websocket_connect(ws_url(alice)) as websocket:
        websocket.send_text("[1, 2, 3]")
        event = websocket.receive_json()

    assert event == {"type": "error", "data": {"detail": "Event must be a JSON object"}}


def test_unknown_ws_event_returns_error(client: TestClient) -> None:
    alice = register(client, username="alice")

    with client.websocket_connect(ws_url(alice)) as websocket:
        websocket.send_json({"type": "unknown"})
        event = websocket.receive_json()

    assert event == {"type": "error", "data": {"detail": "Unknown event type"}}


def test_typing_without_valid_chat_id_returns_error(client: TestClient) -> None:
    alice = register(client, username="alice")

    with client.websocket_connect(ws_url(alice)) as websocket:
        websocket.send_json({"type": "typing", "data": {}})
        assert websocket.receive_json() == {
            "type": "error",
            "data": {"detail": "Invalid chat_id"},
        }

        websocket.send_json({"type": "typing", "data": {"chat_id": "not-a-uuid"}})
        assert websocket.receive_json() == {
            "type": "error",
            "data": {"detail": "Invalid chat_id"},
        }


def test_typing_for_unknown_chat_returns_error(client: TestClient) -> None:
    alice = register(client, username="alice")

    with client.websocket_connect(ws_url(alice)) as websocket:
        websocket.send_json(
            {"type": "typing", "data": {"chat_id": "00000000-0000-0000-0000-000000000000"}}
        )
        event = websocket.receive_json()

    assert event == {"type": "error", "data": {"detail": "Chat not found"}}


def test_typing_event_is_forwarded_to_partner(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    with client.websocket_connect(ws_url(alice)) as alice_ws:
        with client.websocket_connect(ws_url(bob)) as bob_ws:
            online = alice_ws.receive_json()
            assert online == {
                "type": "user_status",
                "data": {"user_id": bob["user"]["id"], "status": "online"},
            }

            alice_ws.send_json(
                {"type": "typing", "data": {"chat_id": chat["id"], "is_typing": False}}
            )
            event = bob_ws.receive_json()

    assert event == {
        "type": "typing",
        "data": {"chat_id": chat["id"], "user_id": alice["user"]["id"], "is_typing": False},
    }


def test_sender_receives_own_new_message(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    with client.websocket_connect(ws_url(alice)) as websocket:
        response = client.post(
            f"/api/v1/chats/{chat['id']}/messages",
            json={"content": "to myself"},
            headers=auth_headers(alice),
        )
        assert response.status_code == 201

        event = websocket.receive_json()

    assert event["type"] == "new_message"
    assert event["data"]["id"] == response.json()["id"]
    assert event["data"]["sender_id"] == alice["user"]["id"]
