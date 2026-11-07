from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.models.chat import Chat
from app.models.message import (
    MESSAGE_TYPE_AUDIO,
    MESSAGE_TYPE_IMAGE,
    MESSAGE_TYPE_VIDEO_NOTE,
    Message,
)
from app.models.user import User
from app.repositories.chat_members import ChatMemberRepository
from app.repositories.chats import ChatRepository
from app.repositories.messages import MessageRepository
from app.schemas.message import MessageCreate
from app.services.chats import ChatService
from app.services.images import ImageStorage, normalize_caption
from app.services.media import AudioStorage, VideoNoteStorage, normalize_duration


class MessageService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.messages = MessageRepository(session)
        self.chats = ChatRepository(session)
        self.members = ChatMemberRepository(session)
        self.chat_service = ChatService(session)

    async def send(
        self,
        current_user: User,
        chat_id: UUID,
        payload: MessageCreate,
        *,
        expected_type: str | None = None,
    ) -> tuple[Message, Chat]:
        chat, membership = await self.chat_service.get_member_chat(
            current_user, chat_id, expected_type=expected_type
        )
        self.chat_service.ensure_can_post(chat, membership)

        if payload.client_message_id is not None:
            existing = await self.messages.get_by_client_id(
                chat_id=chat.id,
                sender_id=current_user.id,
                client_message_id=payload.client_message_id,
            )
            if existing is not None:
                return existing, chat

        try:
            message = await self.messages.create(
                chat_id=chat.id,
                sender_id=current_user.id,
                content=payload.content,
                client_message_id=payload.client_message_id,
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if payload.client_message_id is not None:
                existing = await self.messages.get_by_client_id(
                    chat_id=chat.id,
                    sender_id=current_user.id,
                    client_message_id=payload.client_message_id,
                )
                if existing is not None:
                    return existing, chat
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Message could not be saved"
            ) from exc

        await self.session.refresh(message)
        return message, chat

    async def send_image(
        self,
        current_user: User,
        chat_id: UUID,
        upload: UploadFile,
        caption: str | None,
        client_message_id: UUID | None,
        *,
        expected_type: str | None = None,
    ) -> tuple[Message, Chat]:
        chat, membership = await self.chat_service.get_member_chat(
            current_user, chat_id, expected_type=expected_type
        )
        self.chat_service.ensure_can_post(chat, membership)
        content = normalize_caption(caption)

        if client_message_id is not None:
            existing = await self.messages.get_by_client_id(
                chat_id=chat.id,
                sender_id=current_user.id,
                client_message_id=client_message_id,
            )
            if existing is not None:
                return existing, chat

        storage = ImageStorage()
        stored = await storage.save(upload)
        try:
            message = await self.messages.create(
                chat_id=chat.id,
                sender_id=current_user.id,
                content=content,
                client_message_id=client_message_id,
                message_type=MESSAGE_TYPE_IMAGE,
                image_url=stored.url,
                image_mime_type=stored.mime_type,
                image_size_bytes=stored.size_bytes,
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            await storage.delete(stored)
            if client_message_id is not None:
                existing = await self.messages.get_by_client_id(
                    chat_id=chat.id,
                    sender_id=current_user.id,
                    client_message_id=client_message_id,
                )
                if existing is not None:
                    return existing, chat
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Message could not be saved"
            ) from exc
        except Exception:
            await self.session.rollback()
            await storage.delete(stored)
            raise

        await self.session.refresh(message)
        return message, chat

    async def send_audio(
        self,
        current_user: User,
        chat_id: UUID,
        upload: UploadFile,
        duration_seconds: float | None,
        client_message_id: UUID | None,
        *,
        expected_type: str | None = None,
    ) -> tuple[Message, Chat]:
        return await self._send_media(
            current_user,
            chat_id,
            upload,
            AudioStorage(),
            message_type=MESSAGE_TYPE_AUDIO,
            duration_seconds=duration_seconds,
            client_message_id=client_message_id,
            expected_type=expected_type,
        )

    async def send_video_note(
        self,
        current_user: User,
        chat_id: UUID,
        upload: UploadFile,
        duration_seconds: float | None,
        client_message_id: UUID | None,
        *,
        expected_type: str | None = None,
    ) -> tuple[Message, Chat]:
        return await self._send_media(
            current_user,
            chat_id,
            upload,
            VideoNoteStorage(),
            message_type=MESSAGE_TYPE_VIDEO_NOTE,
            duration_seconds=duration_seconds,
            client_message_id=client_message_id,
            expected_type=expected_type,
        )

    async def _send_media(
        self,
        current_user: User,
        chat_id: UUID,
        upload: UploadFile,
        storage: AudioStorage | VideoNoteStorage,
        *,
        message_type: str,
        duration_seconds: float | None,
        client_message_id: UUID | None,
        expected_type: str | None,
    ) -> tuple[Message, Chat]:
        chat, membership = await self.chat_service.get_member_chat(
            current_user, chat_id, expected_type=expected_type
        )
        self.chat_service.ensure_can_post(chat, membership)
        duration = normalize_duration(duration_seconds)

        if client_message_id is not None:
            existing = await self.messages.get_by_client_id(
                chat_id=chat.id,
                sender_id=current_user.id,
                client_message_id=client_message_id,
            )
            if existing is not None:
                return existing, chat

        stored = await storage.save(upload)
        try:
            message = await self.messages.create(
                chat_id=chat.id,
                sender_id=current_user.id,
                content="",
                client_message_id=client_message_id,
                message_type=message_type,
                media_url=stored.url,
                media_mime_type=stored.mime_type,
                media_size_bytes=stored.size_bytes,
                media_duration_seconds=duration,
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            await storage.delete(stored)
            if client_message_id is not None:
                existing = await self.messages.get_by_client_id(
                    chat_id=chat.id,
                    sender_id=current_user.id,
                    client_message_id=client_message_id,
                )
                if existing is not None:
                    return existing, chat
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Message could not be saved"
            ) from exc
        except Exception:
            await self.session.rollback()
            await storage.delete(stored)
            raise

        await self.session.refresh(message)
        return message, chat

    async def history(
        self,
        current_user: User,
        chat_id: UUID,
        limit: int,
        before: datetime | None,
        *,
        expected_type: str | None = None,
    ) -> list[Message]:
        await self.chat_service.get_participant_chat(
            current_user, chat_id, expected_type=expected_type
        )
        return await self.messages.history(chat_id, limit=limit, before=before)

    async def mark_read(
        self,
        current_user: User,
        chat_id: UUID,
        *,
        expected_type: str | None = None,
    ) -> int:
        chat, membership = await self.chat_service.get_member_chat(
            current_user, chat_id, expected_type=expected_type
        )
        if chat.is_direct():
            updated = await self.messages.mark_read(chat.id, current_user.id)
        else:
            read_at = membership.last_read_at if membership else None
            updated = await self.chats.count_unread_since(chat.id, current_user.id, read_at)
            await self.members.mark_read(chat.id, current_user.id, utcnow())
        await self.session.commit()
        return updated
