from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_username(self, username: str) -> User | None:
        return await self.session.scalar(select(User).where(User.username == username))

    async def create(self, username: str, password_hash: str, display_name: str) -> User:
        user = User(username=username, password_hash=password_hash, display_name=display_name)
        self.session.add(user)
        await self.session.flush()
        return user

    async def search(self, query: str, exclude_id: UUID, limit: int = 20) -> list[User]:
        stmt = (
            select(User)
            .where(User.id != exclude_id, User.username.icontains(query, autoescape=True))
            .order_by(User.username)
            .limit(limit)
        )
        result = await self.session.scalars(stmt)
        return list(result)
