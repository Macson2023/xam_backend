from datetime import UTC, datetime
from uuid import uuid4

from app.models.message import Message
from app.realtime.events import new_message_event, typing_event, user_status_event
from app.realtime.manager import ConnectionManager


class FakeWebSocket:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        if self.fail:
            raise RuntimeError("connection is closed")
        self.sent.append(payload)


async def test_connect_reports_only_first_session() -> None:
    manager = ConnectionManager()
    user_id = uuid4()
    first = FakeWebSocket()
    second = FakeWebSocket()

    assert await manager.connect(user_id, first) is True
    assert await manager.connect(user_id, second) is False


async def test_disconnect_reports_last_session_only() -> None:
    manager = ConnectionManager()
    user_id = uuid4()
    first = FakeWebSocket()
    second = FakeWebSocket()
    await manager.connect(user_id, first)
    await manager.connect(user_id, second)

    assert await manager.disconnect(user_id, first) is False
    assert await manager.disconnect(user_id, second) is True
    assert await manager.disconnect(user_id, second) is False


async def test_disconnect_unknown_user_returns_false() -> None:
    manager = ConnectionManager()

    assert await manager.disconnect(uuid4(), FakeWebSocket()) is False


async def test_send_to_user_delivers_to_all_sessions_and_drops_dead_socket() -> None:
    manager = ConnectionManager()
    user_id = uuid4()
    alive = FakeWebSocket()
    dead = FakeWebSocket(fail=True)
    await manager.connect(user_id, alive)
    await manager.connect(user_id, dead)

    await manager.send_to_user(user_id, {"type": "first"})
    await manager.send_to_user(user_id, {"type": "second"})

    assert alive.sent == [{"type": "first"}, {"type": "second"}]
    assert dead.sent == []
    assert manager._connections[user_id] == {alive}


async def test_broadcast_deduplicates_user_ids() -> None:
    manager = ConnectionManager()
    first_user = uuid4()
    second_user = uuid4()
    first_socket = FakeWebSocket()
    second_socket = FakeWebSocket()
    await manager.connect(first_user, first_socket)
    await manager.connect(second_user, second_socket)

    await manager.broadcast([first_user, first_user, second_user], {"type": "event"})

    assert first_socket.sent == [{"type": "event"}]
    assert second_socket.sent == [{"type": "event"}]


async def test_broadcast_to_unknown_users_does_nothing() -> None:
    manager = ConnectionManager()

    await manager.broadcast([uuid4(), uuid4()], {"type": "event"})

    assert manager._connections == {}


def test_new_message_event_is_json_serializable() -> None:
    message = Message(
        id=uuid4(),
        chat_id=uuid4(),
        sender_id=uuid4(),
        content="hello",
        client_message_id=None,
        created_at=datetime.now(UTC),
        is_read=False,
    )

    event = new_message_event(message)

    assert event["type"] == "new_message"
    assert event["data"]["id"] == str(message.id)
    assert event["data"]["content"] == "hello"
    assert event["data"]["is_read"] is False


def test_user_status_and_typing_events() -> None:
    user_id = uuid4()
    chat_id = uuid4()

    assert user_status_event(user_id, "online") == {
        "type": "user_status",
        "data": {"user_id": str(user_id), "status": "online"},
    }
    assert typing_event(chat_id, user_id, False) == {
        "type": "typing",
        "data": {"chat_id": str(chat_id), "user_id": str(user_id), "is_typing": False},
    }
