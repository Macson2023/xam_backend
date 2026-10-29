from uuid import uuid4

from fastapi.testclient import TestClient

from tests.conftest import auth_headers, create_chat, register


def _send(client: TestClient, user: dict, chat_id: str, content: str, client_message_id=None):
    body = {"content": content}
    if client_message_id is not None:
        body["client_message_id"] = client_message_id
    return client.post(f"/api/v1/chats/{chat_id}/messages", json=body, headers=auth_headers(user))


def test_send_and_fetch_messages(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    response = _send(client, alice, chat["id"], "  hello bob  ")
    assert response.status_code == 201
    message = response.json()
    assert message["content"] == "hello bob"
    assert message["sender_id"] == alice["user"]["id"]
    assert message["is_read"] is False

    response = client.get(f"/api/v1/chats/{chat['id']}/messages", headers=auth_headers(bob))
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [message["id"]]


def test_message_idempotency_by_client_message_id(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])
    client_message_id = "1a6f7c1e-0f5b-4f0e-9a3e-6a1c2b3d4e5f"

    first = _send(client, alice, chat["id"], "once", client_message_id)
    second = _send(client, alice, chat["id"], "twice", client_message_id)

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["content"] == "once"

    items = client.get(f"/api/v1/chats/{chat['id']}/messages", headers=auth_headers(alice)).json()[
        "items"
    ]
    assert len(items) == 1


def test_history_cursor_pagination(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    sent_ids = []
    for index in range(5):
        response = _send(client, alice, chat["id"], f"message {index}")
        assert response.status_code == 201
        sent_ids.append(response.json()["id"])

    first_page = client.get(
        f"/api/v1/chats/{chat['id']}/messages",
        params={"limit": 2},
        headers=auth_headers(alice),
    ).json()
    assert [item["id"] for item in first_page["items"]] == [sent_ids[4], sent_ids[3]]
    assert first_page["next_cursor"]

    second_page = client.get(
        f"/api/v1/chats/{chat['id']}/messages",
        params={"limit": 2, "before": first_page["next_cursor"]},
        headers=auth_headers(alice),
    ).json()
    assert [item["id"] for item in second_page["items"]] == [sent_ids[2], sent_ids[1]]


def test_mark_chat_read(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])
    _send(client, alice, chat["id"], "hi bob")

    response = client.post(f"/api/v1/chats/{chat['id']}/read", headers=auth_headers(bob))
    assert response.status_code == 200
    assert response.json() == {"updated": 1}

    items = client.get(f"/api/v1/chats/{chat['id']}/messages", headers=auth_headers(bob)).json()[
        "items"
    ]
    assert items[0]["is_read"] is True


def test_empty_content_is_rejected(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    response = _send(client, alice, chat["id"], "   ")
    assert response.status_code == 422


def test_outsider_cannot_read_or_write_chat(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    outsider = register(client, username="outsider")
    chat = create_chat(client, alice, bob["user"]["id"])

    assert (
        client.get(
            f"/api/v1/chats/{chat['id']}/messages", headers=auth_headers(outsider)
        ).status_code
        == 404
    )
    assert _send(client, outsider, chat["id"], "intrusion").status_code == 404
    assert (
        client.post(f"/api/v1/chats/{chat['id']}/read", headers=auth_headers(outsider)).status_code
        == 404
    )


def test_message_content_length_boundaries(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    assert _send(client, alice, chat["id"], "x" * 4000).status_code == 201
    assert _send(client, alice, chat["id"], "x" * 4001).status_code == 422


def test_invalid_client_message_id_is_rejected(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    response = _send(client, alice, chat["id"], "hello", "not-a-uuid")

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_client_message_id_is_scoped_per_sender(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])
    client_message_id = str(uuid4())

    from_alice = _send(client, alice, chat["id"], "from alice", client_message_id)
    from_bob = _send(client, bob, chat["id"], "from bob", client_message_id)

    assert from_alice.status_code == from_bob.status_code == 201
    assert from_alice.json()["id"] != from_bob.json()["id"]

    items = client.get(f"/api/v1/chats/{chat['id']}/messages", headers=auth_headers(alice)).json()[
        "items"
    ]
    assert len(items) == 2


def test_client_message_id_is_scoped_per_chat(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    carol = register(client, username="carol")
    chat_with_bob = create_chat(client, alice, bob["user"]["id"])
    chat_with_carol = create_chat(client, alice, carol["user"]["id"])
    client_message_id = str(uuid4())

    first = _send(client, alice, chat_with_bob["id"], "first chat", client_message_id)
    second = _send(client, alice, chat_with_carol["id"], "second chat", client_message_id)

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


def test_mark_read_does_not_touch_own_messages(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])
    assert _send(client, alice, chat["id"], "hello bob").status_code == 201

    response = client.post(f"/api/v1/chats/{chat['id']}/read", headers=auth_headers(alice))
    assert response.json() == {"updated": 0}

    response = client.post(f"/api/v1/chats/{chat['id']}/read", headers=auth_headers(bob))
    assert response.json() == {"updated": 1}

    response = client.post(f"/api/v1/chats/{chat['id']}/read", headers=auth_headers(bob))
    assert response.json() == {"updated": 0}


def test_pagination_returns_no_cursor_for_last_page(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])
    for index in range(3):
        assert _send(client, alice, chat["id"], f"message {index}").status_code == 201

    page = client.get(
        f"/api/v1/chats/{chat['id']}/messages",
        params={"limit": 10},
        headers=auth_headers(alice),
    ).json()

    assert len(page["items"]) == 3
    assert page["next_cursor"] is None


def test_pagination_validates_limit_and_before(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    for limit in (0, 101):
        response = client.get(
            f"/api/v1/chats/{chat['id']}/messages",
            params={"limit": limit},
            headers=auth_headers(alice),
        )
        assert response.status_code == 422

    response = client.get(
        f"/api/v1/chats/{chat['id']}/messages",
        params={"before": "not-a-date"},
        headers=auth_headers(alice),
    )
    assert response.status_code == 422
