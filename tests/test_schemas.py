from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.chat import ChatCreate
from app.schemas.message import MessageCreate


def test_register_request_strips_display_name() -> None:
    payload = RegisterRequest(username="alice", password="password123", display_name="  Alice  ")

    assert payload.display_name == "Alice"


def test_register_request_rejects_blank_display_name() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(username="alice", password="password123", display_name="   ")


@pytest.mark.parametrize("username", ["ab", "a" * 33, "a!", "a b", "абв"])
def test_register_request_rejects_invalid_usernames(username: str) -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(username=username, password="password123", display_name="Alice")


def test_register_request_validates_password_length() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(username="alice", password="short", display_name="Alice")

    with pytest.raises(ValidationError):
        RegisterRequest(username="alice", password="a" * 73, display_name="Alice")

    assert (
        RegisterRequest(username="alice", password="a" * 72, display_name="Alice").password
        == "a" * 72
    )


def test_login_request_length_limits() -> None:
    with pytest.raises(ValidationError):
        LoginRequest(username="", password="password123")

    with pytest.raises(ValidationError):
        LoginRequest(username="alice", password="")

    assert LoginRequest(username="alice", password="x").password == "x"


def test_message_create_strips_content_and_parses_client_message_id() -> None:
    client_message_id = uuid4()

    payload = MessageCreate(content="  hello  ", client_message_id=str(client_message_id))

    assert payload.content == "hello"
    assert payload.client_message_id == client_message_id
    assert isinstance(payload.client_message_id, UUID)


def test_message_create_rejects_blank_or_too_long_content() -> None:
    with pytest.raises(ValidationError):
        MessageCreate(content="   ")

    with pytest.raises(ValidationError):
        MessageCreate(content="x" * 4001)

    assert len(MessageCreate(content="x" * 4000).content) == 4000


def test_message_create_rejects_invalid_client_message_id() -> None:
    with pytest.raises(ValidationError):
        MessageCreate(content="hello", client_message_id="not-a-uuid")


def test_chat_create_parses_participant_id() -> None:
    participant_id = uuid4()

    assert ChatCreate(participant_id=str(participant_id)).participant_id == participant_id

    with pytest.raises(ValidationError):
        ChatCreate(participant_id="not-a-uuid")
