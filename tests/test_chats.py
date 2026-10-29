from fastapi.testclient import TestClient

from tests.conftest import auth_headers, create_chat, register


def test_chat_creation_is_idempotent_for_both_users(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")

    first = create_chat(client, alice, bob["user"]["id"])
    second = create_chat(client, alice, bob["user"]["id"])
    reversed_chat = create_chat(client, bob, alice["user"]["id"])

    assert first["id"] == second["id"] == reversed_chat["id"]
    assert first["partner"]["username"] == "bob"
    assert reversed_chat["partner"]["username"] == "alice"


def test_chat_with_self_is_rejected(client: TestClient) -> None:
    alice = register(client, username="alice")

    response = client.post(
        "/api/v1/chats",
        json={"participant_id": alice["user"]["id"]},
        headers=auth_headers(alice),
    )

    assert response.status_code == 400


def test_chat_with_unknown_participant_returns_404(client: TestClient) -> None:
    alice = register(client, username="alice")

    response = client.post(
        "/api/v1/chats",
        json={"participant_id": "00000000-0000-0000-0000-000000000000"},
        headers=auth_headers(alice),
    )

    assert response.status_code == 404


def test_chat_list_shows_last_message_and_unread_count(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    response = client.post(
        f"/api/v1/chats/{chat['id']}/messages",
        json={"content": "hello alice"},
        headers=auth_headers(bob),
    )
    assert response.status_code == 201

    response = client.get("/api/v1/chats", headers=auth_headers(alice))
    assert response.status_code == 200
    chats = response.json()
    assert len(chats) == 1
    assert chats[0]["last_message"]["content"] == "hello alice"
    assert chats[0]["unread_count"] == 1

    bob_chats = client.get("/api/v1/chats", headers=auth_headers(bob)).json()
    assert bob_chats[0]["unread_count"] == 0


def test_swagger_and_health_available(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/docs").status_code == 200
