from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.users import UserRepository


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def search(self, query: str, current_user: User, limit: int = 20) -> list[User]:
        query = query.strip()
        if not query:
            return []
        return await self.users.search(query, exclude_id=current_user.id, limit=limit)
