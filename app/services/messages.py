from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Chat
from app.models.message import MESSAGE_TYPE_IMAGE, Message
from app.models.user import User
from app.repositories.chats import ChatRepository
from app.repositories.messages import MessageRepository
from app.schemas.message import MessageCreate
from app.services.chats import ChatService
from app.services.images import ImageStorage, normalize_caption


class MessageService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.messages = MessageRepository(session)
        self.chats = ChatRepository(session)
        self.chat_service = ChatService(session)

    async def send(
        self, current_user: User, chat_id: UUID, payload: MessageCreate
    ) -> tuple[Message, Chat]:
        chat = await self.chat_service.get_participant_chat(current_user, chat_id)

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
    ) -> tuple[Message, Chat]:
        chat = await self.chat_service.get_participant_chat(current_user, chat_id)
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

    async def history(
        self,
        current_user: User,
        chat_id: UUID,
        limit: int,
        before: datetime | None,
    ) -> list[Message]:
        await self.chat_service.get_participant_chat(current_user, chat_id)
        return await self.messages.history(chat_id, limit=limit, before=before)

    async def mark_read(self, current_user: User, chat_id: UUID) -> int:
        await self.chat_service.get_participant_chat(current_user, chat_id)
        updated = await self.messages.mark_read(chat_id, current_user.id)
        await self.session.commit()
        return updated
