import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.conftest import UPLOAD_DIR, auth_headers, create_chat, register

OGG_AUDIO = b"OggS" + b"\x00" * 64
MP3_AUDIO = b"ID3" + b"\x00" * 64
MP4_VIDEO_NOTE = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64
WEBM_VIDEO_NOTE = b"\x1aE\xdf\xa3" + b"\x00" * 64

AUDIO_URL_PATTERN = re.compile(r"^/media/audio/[0-9a-f]{32}\.(ogg|mp3)$")
VIDEO_NOTE_URL_PATTERN = re.compile(r"^/media/video_notes/[0-9a-f]{32}\.(mp4|webm)$")


def _post_media(
    client: TestClient,
    user: dict,
    url: str,
    data: bytes,
    *,
    filename: str,
    content_type: str,
    duration_seconds: float | None = None,
    client_message_id: str | None = None,
):
    form = {}
    if duration_seconds is not None:
        form["duration_seconds"] = str(duration_seconds)
    if client_message_id is not None:
        form["client_message_id"] = client_message_id
    return client.post(
        url,
        files={"file": (filename, data, content_type)},
        data=form,
        headers=auth_headers(user),
    )


def _send_audio(
    client: TestClient,
    user: dict,
    chat_id: str,
    data: bytes = OGG_AUDIO,
    filename: str = "voice.ogg",
    content_type: str = "audio/ogg",
    duration_seconds: float | None = 12,
    client_message_id: str | None = None,
):
    return _post_media(
        client,
        user,
        f"/api/v1/chats/{chat_id}/audio",
        data,
        filename=filename,
        content_type=content_type,
        duration_seconds=duration_seconds,
        client_message_id=client_message_id,
    )


def _send_video_note(
    client: TestClient,
    user: dict,
    chat_id: str,
    data: bytes = MP4_VIDEO_NOTE,
    filename: str = "circle.mp4",
    content_type: str = "video/mp4",
    duration_seconds: float | None = 8,
    client_message_id: str | None = None,
):
    return _post_media(
        client,
        user,
        f"/api/v1/chats/{chat_id}/video-notes",
        data,
        filename=filename,
        content_type=content_type,
        duration_seconds=duration_seconds,
        client_message_id=client_message_id,
    )


def test_send_audio_message(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    response = _send_audio(client, alice, chat["id"])

    assert response.status_code == 201, response.text
    message = response.json()
    assert message["message_type"] == "audio"
    assert message["content"] == ""
    assert message["media_mime_type"] == "audio/ogg"
    assert message["media_size_bytes"] == len(OGG_AUDIO)
    assert message["media_duration_seconds"] == 12
    assert message["image_url"] is None
    assert AUDIO_URL_PATTERN.match(message["media_url"])

    audio_path = Path(UPLOAD_DIR) / message["media_url"].removeprefix("/media/")
    assert audio_path.read_bytes() == OGG_AUDIO

    media = client.get(message["media_url"])
    assert media.status_code == 200
    assert media.content == OGG_AUDIO

    history = client.get(
        f"/api/v1/chats/{chat['id']}/messages", headers=auth_headers(bob)
    ).json()["items"]
    assert len(history) == 1
    assert history[0]["message_type"] == "audio"
    assert history[0]["media_url"] == message["media_url"]


def test_send_audio_detects_mp3(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    response = _send_audio(
        client, alice, chat["id"], data=MP3_AUDIO, filename="voice.mp3", content_type="audio/mpeg"
    )

    assert response.status_code == 201
    message = response.json()
    assert message["media_mime_type"] == "audio/mpeg"
    assert message["media_url"].endswith(".mp3")


def test_send_video_note(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    response = _send_video_note(client, alice, chat["id"])

    assert response.status_code == 201, response.text
    message = response.json()
    assert message["message_type"] == "video_note"
    assert message["content"] == ""
    assert message["media_mime_type"] == "video/mp4"
    assert message["media_size_bytes"] == len(MP4_VIDEO_NOTE)
    assert message["media_duration_seconds"] == 8
    assert VIDEO_NOTE_URL_PATTERN.match(message["media_url"])

    file_path = Path(UPLOAD_DIR) / message["media_url"].removeprefix("/media/")
    assert file_path.read_bytes() == MP4_VIDEO_NOTE


def test_send_webm_video_note(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    response = _send_video_note(
        client,
        alice,
        chat["id"],
        data=WEBM_VIDEO_NOTE,
        filename="circle.webm",
        content_type="video/webm",
    )

    assert response.status_code == 201
    assert response.json()["media_mime_type"] == "video/webm"


def test_audio_duration_is_optional(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    response = _send_audio(client, alice, chat["id"], duration_seconds=None)

    assert response.status_code == 201
    assert response.json()["media_duration_seconds"] is None


def test_audio_rejects_invalid_duration(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    assert _send_audio(client, alice, chat["id"], duration_seconds=0).status_code == 422
    assert _send_audio(client, alice, chat["id"], duration_seconds=4000).status_code == 422


def test_audio_rejects_non_audio_file(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    response = _send_audio(
        client,
        alice,
        chat["id"],
        data=b"<html>not audio</html>",
        filename="voice.ogg",
        content_type="audio/ogg",
    )

    assert response.status_code == 415
    assert isinstance(response.json()["detail"], str)


def test_video_note_rejects_non_video_file(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    response = _send_video_note(
        client,
        alice,
        chat["id"],
        data=b"\x89PNG\r\n\x1a\n" + b"\x00" * 16,
        filename="circle.mp4",
        content_type="video/mp4",
    )

    assert response.status_code == 415


def test_audio_rejects_empty_and_oversized_files(client: TestClient, monkeypatch) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    assert _send_audio(client, alice, chat["id"], data=b"").status_code == 400

    monkeypatch.setattr(settings, "max_audio_size_bytes", 8)
    assert _send_audio(client, alice, chat["id"]).status_code == 413


def test_outsider_cannot_send_audio(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    outsider = register(client, username="outsider")
    chat = create_chat(client, alice, bob["user"]["id"])

    response = _send_audio(client, outsider, chat["id"])

    assert response.status_code == 404


def test_audio_upload_is_idempotent_by_client_message_id(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])
    client_message_id = "2b7a8d2f-1a6c-4d1e-8b4f-7c2d3e4f5a6b"

    first = _send_audio(client, alice, chat["id"], client_message_id=client_message_id)
    second = _send_audio(client, alice, chat["id"], client_message_id=client_message_id)

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    history = client.get(
        f"/api/v1/chats/{chat['id']}/messages", headers=auth_headers(alice)
    ).json()["items"]
    assert len(history) == 1

    audio_files = list((Path(UPLOAD_DIR) / "audio").glob("*.ogg"))
    assert len(audio_files) == 1


def test_audio_message_is_broadcast_over_websocket(client: TestClient) -> None:
    alice = register(client, username="alice")
    bob = register(client, username="bob")
    chat = create_chat(client, alice, bob["user"]["id"])

    with client.websocket_connect(f"/ws?token={alice['access_token']}") as websocket:
        response = _send_audio(client, bob, chat["id"])
        assert response.status_code == 201

        event = websocket.receive_json()

    assert event["type"] == "new_message"
    assert event["data"]["id"] == response.json()["id"]
    assert event["data"]["message_type"] == "audio"
    assert event["data"]["media_url"] == response.json()["media_url"]


def test_group_and_channel_media_endpoints(client: TestClient) -> None:
    owner = register(client, username="owner")
    member = register(client, username="member")

    group_response = client.post(
        "/api/v1/groups",
        json={"title": "Team", "member_ids": [member["user"]["id"]]},
        headers=auth_headers(owner),
    )
    assert group_response.status_code == 201
    group_id = group_response.json()["id"]

    audio_response = _post_media(
        client,
        member,
        f"/api/v1/groups/{group_id}/audio",
        OGG_AUDIO,
        filename="voice.ogg",
        content_type="audio/ogg",
        duration_seconds=5,
    )
    assert audio_response.status_code == 201, audio_response.text
    assert audio_response.json()["message_type"] == "audio"

    channel_response = client.post(
        "/api/v1/channels",
        json={"title": "News", "member_ids": [member["user"]["id"]]},
        headers=auth_headers(owner),
    )
    assert channel_response.status_code == 201
    channel_id = channel_response.json()["id"]

    video_response = _post_media(
        client,
        owner,
        f"/api/v1/channels/{channel_id}/video-notes",
        MP4_VIDEO_NOTE,
        filename="circle.mp4",
        content_type="video/mp4",
        duration_seconds=9,
    )
    assert video_response.status_code == 201, video_response.text
    assert video_response.json()["message_type"] == "video_note"

    forbidden = _post_media(
        client,
        member,
        f"/api/v1/channels/{channel_id}/audio",
        OGG_AUDIO,
        filename="voice.ogg",
        content_type="audio/ogg",
    )
    assert forbidden.status_code == 403
