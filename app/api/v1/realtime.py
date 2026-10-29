import json
import logging
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import update

from app.core.security import InvalidTokenError, decode_access_token
from app.db.base import utcnow
from app.db.session import async_session_factory
from app.models.chat import Chat
from app.models.user import User
from app.realtime import manager, typing_event, user_status_event
from app.repositories.chats import ChatRepository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["realtime"])


async def _user_exists(user_id: UUID) -> bool:
    async with async_session_factory() as session:
        return await session.get(User, user_id) is not None


async def _partner_ids(user_id: UUID) -> set[UUID]:
    async with async_session_factory() as session:
        return await ChatRepository(session).partner_ids_for_user(user_id)


async def _chat_partner_id(user_id: UUID, chat_id: UUID) -> UUID | None:
    async with async_session_factory() as session:
        chat = await session.get(Chat, chat_id)
        if chat is None or user_id not in chat.participant_ids():
            return None
        return chat.partner_id(user_id)


async def _touch_last_seen(user_id: UUID) -> None:
    async with async_session_factory() as session:
        await session.execute(update(User).where(User.id == user_id).values(last_seen=utcnow()))
        await session.commit()


async def _send_error(websocket: WebSocket, detail: str) -> None:
    await websocket.send_json({"type": "error", "data": {"detail": detail}})


async def _handle_client_event(websocket: WebSocket, user_id: UUID, raw: str) -> None:
    raw = raw.strip()
    if raw.lower() == "ping":
        await websocket.send_json({"type": "pong"})
        return

    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        await _send_error(websocket, "Invalid JSON")
        return

    if not isinstance(event, dict):
        await _send_error(websocket, "Event must be a JSON object")
        return

    event_type = event.get("type")
    if event_type == "ping":
        await websocket.send_json({"type": "pong"})
        return

    if event_type == "typing":
        data = event.get("data") or {}
        try:
            chat_id = UUID(str(data.get("chat_id")))
        except (TypeError, ValueError):
            await _send_error(websocket, "Invalid chat_id")
            return

        partner_id = await _chat_partner_id(user_id, chat_id)
        if partner_id is None:
            await _send_error(websocket, "Chat not found")
            return

        is_typing = bool(data.get("is_typing", True))
        await manager.send_to_user(partner_id, typing_event(chat_id, user_id, is_typing))
        return

    await _send_error(websocket, "Unknown event type")


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str | None = Query(default=None)) -> None:
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        user_id = decode_access_token(token)
    except InvalidTokenError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if not await _user_exists(user_id):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    is_first_session = await manager.connect(user_id, websocket)
    if is_first_session:
        await manager.broadcast(await _partner_ids(user_id), user_status_event(user_id, "online"))

    try:
        while True:
            raw = await websocket.receive_text()
            await _handle_client_event(websocket, user_id, raw)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket session failed for user %s", user_id)
    finally:
        went_offline = await manager.disconnect(user_id, websocket)
        if went_offline:
            await _touch_last_seen(user_id)
            await manager.broadcast(
                await _partner_ids(user_id), user_status_event(user_id, "offline")
            )
