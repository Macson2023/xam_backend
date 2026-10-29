import base64
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.conftest import UPLOAD_DIR, auth_headers, create_chat, register

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
IMAGE_URL_PATTERN = re.compile(r"^/media/images/[0-9a-f]{32}\.png$")


def _upload(
    client: TestClient,
    user: dict,
    chat_id: str,
    image: bytes = PNG_BYTES,
    filename: str = "photo.png",
    content_type: str = "image/png",
    caption: str | None = None,
    client_message_id: str | None = None,
):
    data = {}
    if caption is not None:
        data["caption"] = caption
    if client_message_id is not None:
        data["client_message_id"] = client_message_id
    return client.post(
        f"/api/v1/chats/{chat_id}/images",
        files={"file": (filename, image, content_type)},
        data=data,
        headers=auth_headers(user),
    )


def test_upload_image_message(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    response = _upload(client, alice, chat["id"], caption="  look at this  ")
    assert response.status_code == 201, response.text
    message = response.json()

    assert message["message_type"] == "image"
    assert message["content"] == "look at this"
    assert message["sender_id"] == alice["user"]["id"]
    assert message["image_mime_type"] == "image/png"
    assert message["image_size_bytes"] == len(PNG_BYTES)
    assert IMAGE_URL_PATTERN.match(message["image_url"])

    image_path = Path(UPLOAD_DIR) / message["image_url"].removeprefix("/media/")
    assert image_path.read_bytes() == PNG_BYTES

    media = client.get(message["image_url"])
    assert media.status_code == 200
    assert media.headers["content-type"] == "image/png"
    assert media.content == PNG_BYTES

    history = client.get(f"/api/v1/chats/{chat['id']}/messages", headers=auth_headers(bob)).json()[
        "items"
    ]
    assert len(history) == 1
    assert history[0]["id"] == message["id"]
    assert history[0]["message_type"] == "image"
    assert history[0]["image_url"] == message["image_url"]


def test_upload_image_without_caption(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    response = _upload(client, alice, chat["id"])

    assert response.status_code == 201
    assert response.json()["content"] == ""


def test_upload_rejects_non_image_file(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    response = _upload(
        client, alice, chat["id"], image=b"<html>not an image</html>", content_type="text/html"
    )

    assert response.status_code == 415
    assert isinstance(response.json()["detail"], str)


def test_upload_rejects_svg(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    response = _upload(
        client,
        alice,
        chat["id"],
        image=b'<svg xmlns="http://www.w3.org/2000/svg"></svg>',
        filename="image.svg",
        content_type="image/svg+xml",
    )

    assert response.status_code == 415


def test_upload_rejects_oversized_image(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "max_image_size_bytes", 8)
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    response = _upload(client, alice, chat["id"])

    assert response.status_code == 413
    assert isinstance(response.json()["detail"], str)


def test_upload_rejects_empty_image(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    response = _upload(client, alice, chat["id"], image=b"")

    assert response.status_code == 400


def test_outsider_cannot_upload_image(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    outsider = register(client, username="outsider")
    chat = create_chat(client, alice, bob["user"]["id"])

    response = _upload(client, outsider, chat["id"])

    assert response.status_code == 404


def test_image_upload_is_idempotent_by_client_message_id(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])
    client_message_id = "1a6f7c1e-0f5b-4f0e-9a3e-6a1c2b3d4e5f"

    first = _upload(client, alice, chat["id"], client_message_id=client_message_id)
    second = _upload(client, alice, chat["id"], client_message_id=client_message_id)

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    history = client.get(
        f"/api/v1/chats/{chat['id']}/messages", headers=auth_headers(alice)
    ).json()["items"]
    assert len(history) == 1

    image_files = list((Path(UPLOAD_DIR) / "images").glob("*.png"))
    assert len(image_files) == 1


def test_invalid_client_message_id_is_rejected(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    response = _upload(client, alice, chat["id"], client_message_id="not-a-uuid")

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_too_long_caption_is_rejected(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    response = _upload(client, alice, chat["id"], caption="x" * 4001)

    assert response.status_code == 422


def test_text_message_keeps_text_type(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    response = client.post(
        f"/api/v1/chats/{chat['id']}/messages",
        json={"content": "hello"},
        headers=auth_headers(alice),
    )

    assert response.status_code == 201
    message = response.json()
    assert message["message_type"] == "text"
    assert message["image_url"] is None
    assert message["image_mime_type"] is None
    assert message["image_size_bytes"] is None


def test_image_message_is_broadcast_over_websocket(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    with client.websocket_connect(f"/ws?token={alice['access_token']}") as websocket:
        response = _upload(client, bob, chat["id"])
        assert response.status_code == 201

        event = websocket.receive_json()

    assert event["type"] == "new_message"
    assert event["data"]["id"] == response.json()["id"]
    assert event["data"]["message_type"] == "image"
    assert event["data"]["image_url"] == response.json()["image_url"]
