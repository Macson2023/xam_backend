from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_client_id(
        self, chat_id: UUID, sender_id: UUID, client_message_id: UUID
    ) -> Message | None:
        stmt = select(Message).where(
            Message.chat_id == chat_id,
            Message.sender_id == sender_id,
            Message.client_message_id == client_message_id,
        )
        return await self.session.scalar(stmt)

    async def create(
        self,
        chat_id: UUID,
        sender_id: UUID,
        content: str,
        client_message_id: UUID | None,
        *,
        message_type: str = "text",
        image_url: str | None = None,
        image_mime_type: str | None = None,
        image_size_bytes: int | None = None,
    ) -> Message:
        message = Message(
            chat_id=chat_id,
            sender_id=sender_id,
            content=content,
            client_message_id=client_message_id,
            message_type=message_type,
            image_url=image_url,
            image_mime_type=image_mime_type,
            image_size_bytes=image_size_bytes,
        )
        self.session.add(message)
        await self.session.flush()
        return message

    async def history(
        self, chat_id: UUID, limit: int, before: datetime | None = None
    ) -> list[Message]:
        stmt = select(Message).where(Message.chat_id == chat_id)
        if before is not None:
            stmt = stmt.where(Message.created_at < before)
        stmt = stmt.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit)
        result = await self.session.scalars(stmt)
        return list(result)

    async def mark_read(self, chat_id: UUID, reader_id: UUID) -> int:
        stmt = (
            update(Message)
            .where(
                Message.chat_id == chat_id,
                Message.sender_id != reader_id,
                Message.is_read.is_(False),
            )
            .values(is_read=True)
        )
        result = await self.session.execute(stmt)
        return result.rowcount or 0
