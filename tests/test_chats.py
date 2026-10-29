from fastapi.testclient import TestClient

from tests.conftest import auth_headers, create_chat, register


def send_message(client: TestClient, user: dict, chat_id: str, content: str):
    return client.post(
        f"/api/v1/chats/{chat_id}/messages",
        json={"content": content},
        headers=auth_headers(user),
    )


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


def test_empty_chat_list(client: TestClient) -> None:
    alice = register(client, username="alice")

    response = client.get("/api/v1/chats", headers=auth_headers(alice))

    assert response.status_code == 200
    assert response.json() == []


def test_chat_creation_returns_empty_overview(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")

    chat = create_chat(client, alice, bob["user"]["id"])

    assert chat["partner"]["id"] == bob["user"]["id"]
    assert chat["unread_count"] == 0
    assert chat["last_message"] is None
    assert chat["created_at"] == chat["last_activity"]


def test_chat_with_invalid_participant_id_is_rejected(client: TestClient) -> None:
    alice = register(client, username="alice")

    response = client.post(
        "/api/v1/chats",
        json={"participant_id": "not-a-uuid"},
        headers=auth_headers(alice),
    )

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_chat_list_is_sorted_by_last_activity(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    carol = register(client, username="carol")
    chat_with_bob = create_chat(client, alice, bob["user"]["id"])
    chat_with_carol = create_chat(client, alice, carol["user"]["id"])

    assert send_message(client, carol, chat_with_carol["id"], "from carol").status_code == 201

    chats = client.get("/api/v1/chats", headers=auth_headers(alice)).json()
    assert [item["id"] for item in chats] == [chat_with_carol["id"], chat_with_bob["id"]]

    assert send_message(client, bob, chat_with_bob["id"], "from bob").status_code == 201

    chats = client.get("/api/v1/chats", headers=auth_headers(alice)).json()
    assert [item["id"] for item in chats] == [chat_with_bob["id"], chat_with_carol["id"]]


def test_unread_counts_are_tracked_per_user(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    assert send_message(client, alice, chat["id"], "first").status_code == 201
    assert send_message(client, alice, chat["id"], "second").status_code == 201
    assert send_message(client, bob, chat["id"], "reply").status_code == 201

    alice_chats = client.get("/api/v1/chats", headers=auth_headers(alice)).json()
    bob_chats = client.get("/api/v1/chats", headers=auth_headers(bob)).json()
    assert alice_chats[0]["unread_count"] == 1
    assert alice_chats[0]["last_message"]["content"] == "reply"
    assert bob_chats[0]["unread_count"] == 2
    assert bob_chats[0]["last_message"]["content"] == "reply"

    response = client.post(f"/api/v1/chats/{chat['id']}/read", headers=auth_headers(bob))
    assert response.json() == {"updated": 2}

    bob_chats = client.get("/api/v1/chats", headers=auth_headers(bob)).json()
    alice_chats = client.get("/api/v1/chats", headers=auth_headers(alice)).json()
    assert bob_chats[0]["unread_count"] == 0
    assert alice_chats[0]["unread_count"] == 1


def test_unknown_chat_returns_404(client: TestClient) -> None:
    alice = register(client, username="alice")
    unknown_chat_id = "00000000-0000-0000-0000-000000000000"

    assert (
        client.get(
            f"/api/v1/chats/{unknown_chat_id}/messages", headers=auth_headers(alice)
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/chats/{unknown_chat_id}/messages",
            json={"content": "hello"},
            headers=auth_headers(alice),
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/chats/{unknown_chat_id}/read", headers=auth_headers(alice)
        ).status_code
        == 404
    )
