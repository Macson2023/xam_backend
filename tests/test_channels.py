from fastapi.testclient import TestClient

from tests.conftest import auth_headers, register


def create_channel(
    client: TestClient,
    owner: dict,
    *,
    title: str = "News",
    member_ids: list[str] | None = None,
    is_public: bool = True,
) -> dict:
    response = client.post(
        "/api/v1/channels",
        json={
            "title": title,
            "description": "Channel description",
            "member_ids": member_ids or [],
            "is_public": is_public,
        },
        headers=auth_headers(owner),
    )
    assert response.status_code == 201, response.text
    return response.json()


def send_channel_message(client: TestClient, user: dict, channel_id: str, content: str):
    return client.post(
        f"/api/v1/channels/{channel_id}/messages",
        json={"content": content},
        headers=auth_headers(user),
    )


def test_create_channel_with_subscribers(client: TestClient) -> None:
    owner = register(client, username="owner")
    subscriber = register(client, username="subscriber")

    channel = create_channel(client, owner, member_ids=[subscriber["user"]["id"]])

    assert channel["type"] == "channel"
    assert channel["title"] == "News"
    assert channel["owner_id"] == owner["user"]["id"]
    assert channel["my_role"] == "owner"
    assert channel["member_count"] == 2
    assert channel["is_public"] is True

    channels = client.get("/api/v1/channels", headers=auth_headers(subscriber)).json()
    assert channels[0]["id"] == channel["id"]
    assert channels[0]["my_role"] == "member"


def test_only_channel_admins_can_post(client: TestClient) -> None:
    owner = register(client, username="owner")
    subscriber = register(client, username="subscriber")
    channel = create_channel(client, owner, member_ids=[subscriber["user"]["id"]])

    assert send_channel_message(client, subscriber, channel["id"], "spam").status_code == 403
    assert send_channel_message(client, owner, channel["id"], "official").status_code == 201

    response = client.patch(
        f"/api/v1/channels/{channel['id']}/members/{subscriber['user']['id']}",
        json={"role": "admin"},
        headers=auth_headers(owner),
    )
    assert response.status_code == 200

    assert (
        send_channel_message(client, subscriber, channel["id"], "post from admin").status_code
        == 201
    )


def test_public_and_private_channel_subscriptions(client: TestClient) -> None:
    owner = register(client, username="owner")
    user = register(client, username="user")

    public_channel = create_channel(client, owner, is_public=True)
    response = client.get(f"/api/v1/channels/{public_channel['id']}", headers=auth_headers(user))
    assert response.status_code == 200
    assert response.json()["my_role"] is None

    response = client.post(
        f"/api/v1/channels/{public_channel['id']}/subscribe",
        headers=auth_headers(user),
    )
    assert response.status_code == 200
    assert response.json()["my_role"] == "member"
    assert response.json()["member_count"] == 2

    response = client.post(
        f"/api/v1/channels/{public_channel['id']}/unsubscribe",
        headers=auth_headers(user),
    )
    assert response.status_code == 204
    assert client.get("/api/v1/channels", headers=auth_headers(user)).json() == []

    private_channel = create_channel(client, owner, is_public=False)
    assert (
        client.post(
            f"/api/v1/channels/{private_channel['id']}/subscribe",
            headers=auth_headers(user),
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"/api/v1/channels/{private_channel['id']}", headers=auth_headers(user)
        ).status_code
        == 404
    )


def test_channel_unread_count_and_read(client: TestClient) -> None:
    owner = register(client, username="owner")
    subscriber = register(client, username="subscriber")
    channel = create_channel(client, owner, member_ids=[subscriber["user"]["id"]])

    assert send_channel_message(client, owner, channel["id"], "first").status_code == 201
    assert send_channel_message(client, owner, channel["id"], "second").status_code == 201

    channels = client.get("/api/v1/channels", headers=auth_headers(subscriber)).json()
    assert channels[0]["unread_count"] == 2

    response = client.post(
        f"/api/v1/channels/{channel['id']}/read", headers=auth_headers(subscriber)
    )
    assert response.json() == {"updated": 2}

    channels = client.get("/api/v1/channels", headers=auth_headers(subscriber)).json()
    assert channels[0]["unread_count"] == 0


def test_channel_update_delete_and_permissions(client: TestClient) -> None:
    owner = register(client, username="owner")
    admin = register(client, username="admin")
    outsider = register(client, username="outsider")
    channel = create_channel(client, owner, member_ids=[admin["user"]["id"]])

    client.patch(
        f"/api/v1/channels/{channel['id']}/members/{admin['user']['id']}",
        json={"role": "admin"},
        headers=auth_headers(owner),
    )

    response = client.patch(
        f"/api/v1/channels/{channel['id']}",
        json={"title": "Updated", "is_public": False},
        headers=auth_headers(admin),
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Updated"
    assert response.json()["is_public"] is False

    response = client.patch(
        f"/api/v1/channels/{channel['id']}",
        json={"title": "Hacked"},
        headers=auth_headers(outsider),
    )
    assert response.status_code == 404

    response = client.delete(f"/api/v1/channels/{channel['id']}", headers=auth_headers(admin))
    assert response.status_code == 403

    response = client.delete(f"/api/v1/channels/{channel['id']}", headers=auth_headers(owner))
    assert response.status_code == 204
    assert client.get("/api/v1/channels", headers=auth_headers(owner)).json() == []


def test_add_channel_members_and_member_removal(client: TestClient) -> None:
    owner = register(client, username="owner")
    admin = register(client, username="admin")
    newcomer = register(client, username="newcomer")
    channel = create_channel(client, owner, member_ids=[admin["user"]["id"]])

    client.patch(
        f"/api/v1/channels/{channel['id']}/members/{admin['user']['id']}",
        json={"role": "admin"},
        headers=auth_headers(owner),
    )

    response = client.post(
        f"/api/v1/channels/{channel['id']}/members",
        json={"user_ids": [newcomer["user"]["id"]]},
        headers=auth_headers(admin),
    )
    assert response.status_code == 201
    assert response.json()["member_count"] == 3

    response = client.delete(
        f"/api/v1/channels/{channel['id']}/members/{newcomer['user']['id']}",
        headers=auth_headers(admin),
    )
    assert response.status_code == 204

    response = client.delete(
        f"/api/v1/channels/{channel['id']}/members/{owner['user']['id']}",
        headers=auth_headers(owner),
    )
    assert response.status_code == 400
