from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserPublic
from app.services.users import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserPublic)
async def get_me(current_user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic.model_validate(current_user)


@router.get("/search", response_model=list[UserPublic])
async def search_users(
    q: str = Query(min_length=1, max_length=32),
    limit: int = Query(default=20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[UserPublic]:
    users = await UserService(session).search(q, current_user, limit=limit)
    return [UserPublic.model_validate(user) for user in users]
