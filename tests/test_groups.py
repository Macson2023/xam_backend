from fastapi.testclient import TestClient

from tests.conftest import auth_headers, register


def create_group(
    client: TestClient,
    owner: dict,
    *,
    title: str = "Team",
    member_ids: list[str] | None = None,
) -> dict:
    response = client.post(
        "/api/v1/groups",
        json={
            "title": title,
            "description": "Group description",
            "member_ids": member_ids or [],
        },
        headers=auth_headers(owner),
    )
    assert response.status_code == 201, response.text
    return response.json()


def send_group_message(client: TestClient, user: dict, group_id: str, content: str):
    return client.post(
        f"/api/v1/groups/{group_id}/messages",
        json={"content": content},
        headers=auth_headers(user),
    )


def test_create_group_with_members(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    carol = register(client, username="carol")

    group = create_group(client, alice, member_ids=[bob["user"]["id"], carol["user"]["id"]])

    assert group["type"] == "group"
    assert group["title"] == "Team"
    assert group["description"] == "Group description"
    assert group["owner_id"] == alice["user"]["id"]
    assert group["my_role"] == "owner"
    assert group["member_count"] == 3
    assert group["partner"] is None

    alice_groups = client.get("/api/v1/groups", headers=auth_headers(alice)).json()
    bob_groups = client.get("/api/v1/groups", headers=auth_headers(bob)).json()
    assert [item["id"] for item in alice_groups] == [group["id"]]
    assert bob_groups[0]["my_role"] == "member"

    detail = client.get(f"/api/v1/groups/{group['id']}", headers=auth_headers(bob)).json()
    roles = {member["user"]["username"]: member["role"] for member in detail["members"]}
    assert roles == {"alice": "owner", "bob": "member", "carol": "member"}


def test_group_members_management_and_permissions(client: TestClient) -> None:
    owner = register(client, username="owner")
    admin = register(client, username="admin")
    member = register(client, username="member")
    outsider = register(client, username="outsider")
    group = create_group(client, owner, member_ids=[admin["user"]["id"]])

    response = client.patch(
        f"/api/v1/groups/{group['id']}/members/{admin['user']['id']}",
        json={"role": "admin"},
        headers=auth_headers(owner),
    )
    assert response.status_code == 200
    assert any(
        item["user"]["id"] == admin["user"]["id"] and item["role"] == "admin"
        for item in response.json()["members"]
    )

    response = client.post(
        f"/api/v1/groups/{group['id']}/members",
        json={"user_ids": [member["user"]["id"]]},
        headers=auth_headers(admin),
    )
    assert response.status_code == 201
    assert response.json()["member_count"] == 3

    response = client.post(
        f"/api/v1/groups/{group['id']}/members",
        json={"user_ids": [outsider["user"]["id"]]},
        headers=auth_headers(member),
    )
    assert response.status_code == 403

    response = client.delete(
        f"/api/v1/groups/{group['id']}/members/{member['user']['id']}",
        headers=auth_headers(admin),
    )
    assert response.status_code == 204

    response = client.post(
        f"/api/v1/groups/{group['id']}/members",
        json={"user_ids": [member["user"]["id"]], "role": "admin"},
        headers=auth_headers(admin),
    )
    assert response.status_code == 403

    response = client.delete(
        f"/api/v1/groups/{group['id']}/members/{owner['user']['id']}",
        headers=auth_headers(owner),
    )
    assert response.status_code == 400


def test_group_messages_and_unread_count(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    outsider = register(client, username="outsider")
    group = create_group(client, alice, member_ids=[bob["user"]["id"]])

    assert send_group_message(client, alice, group["id"], "hello team").status_code == 201
    assert send_group_message(client, bob, group["id"], "hi alice").status_code == 201
    assert send_group_message(client, outsider, group["id"], "intrusion").status_code == 404

    messages = client.get(
        f"/api/v1/groups/{group['id']}/messages", headers=auth_headers(alice)
    ).json()["items"]
    assert [message["content"] for message in messages] == ["hi alice", "hello team"]

    groups = client.get("/api/v1/groups", headers=auth_headers(alice)).json()
    assert groups[0]["unread_count"] == 1

    response = client.post(f"/api/v1/groups/{group['id']}/read", headers=auth_headers(alice))
    assert response.json() == {"updated": 1}

    groups = client.get("/api/v1/groups", headers=auth_headers(alice)).json()
    assert groups[0]["unread_count"] == 0


def test_group_update_delete_and_leave(client: TestClient) -> None:
    owner = register(client, username="owner")
    member = register(client, username="member")
    outsider = register(client, username="outsider")
    group = create_group(client, owner, member_ids=[member["user"]["id"]])

    response = client.patch(
        f"/api/v1/groups/{group['id']}",
        json={"title": "Renamed", "description": None},
        headers=auth_headers(owner),
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Renamed"
    assert response.json()["description"] is None

    response = client.patch(
        f"/api/v1/groups/{group['id']}",
        json={"title": "Hacked"},
        headers=auth_headers(outsider),
    )
    assert response.status_code == 404

    assert (
        client.post(f"/api/v1/groups/{group['id']}/leave", headers=auth_headers(member)).status_code
        == 204
    )
    assert (
        client.get(f"/api/v1/groups/{group['id']}", headers=auth_headers(member)).status_code == 404
    )

    assert (
        client.post(f"/api/v1/groups/{group['id']}/leave", headers=auth_headers(owner)).status_code
        == 400
    )

    assert (
        client.delete(f"/api/v1/groups/{group['id']}", headers=auth_headers(owner)).status_code
        == 204
    )
    assert client.get("/api/v1/groups", headers=auth_headers(owner)).json() == []


def test_group_validation_and_chat_listing(client: TestClient) -> None:
    owner = register(client, username="owner")
    bob = register(client, username="bob")

    response = client.post(
        "/api/v1/groups",
        json={"title": "   "},
        headers=auth_headers(owner),
    )
    assert response.status_code == 422

    response = client.post(
        "/api/v1/groups",
        json={"title": "Missing member", "member_ids": ["00000000-0000-0000-0000-000000000000"]},
        headers=auth_headers(owner),
    )
    assert response.status_code == 404

    group = create_group(client, owner, member_ids=[bob["user"]["id"]])
    chats = client.get("/api/v1/chats", headers=auth_headers(owner)).json()
    assert [chat["type"] for chat in chats] == ["group"]
    assert chats[0]["id"] == group["id"]
