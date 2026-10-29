from uuid import UUID

from app.models.message import Message
from app.schemas.message import MessagePublic


def new_message_event(message: Message) -> dict:
    return {
        "type": "new_message",
        "data": MessagePublic.model_validate(message).model_dump(mode="json"),
    }


def user_status_event(user_id: UUID, status: str) -> dict:
    return {
        "type": "user_status",
        "data": {"user_id": str(user_id), "status": status},
    }


def typing_event(chat_id: UUID, user_id: UUID, is_typing: bool) -> dict:
    return {
        "type": "typing",
        "data": {"chat_id": str(chat_id), "user_id": str(user_id), "is_typing": is_typing},
    }
