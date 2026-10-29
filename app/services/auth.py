import logging

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.repositories.users import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest

logger = logging.getLogger(__name__)

INVALID_CREDENTIALS = "Invalid username or password"


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def register(self, payload: RegisterRequest) -> User:
        if await self.users.get_by_username(payload.username) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Username already taken"
            )

        try:
            password_hash = hash_password(payload.password)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Password is too long",
            ) from exc

        try:
            user = await self.users.create(
                username=payload.username,
                password_hash=password_hash,
                display_name=payload.display_name,
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Username already taken"
            ) from exc

        await self.session.refresh(user)
        return user

    async def login(self, payload: LoginRequest) -> User:
        user = await self.users.get_by_username(payload.username)
        if user is None or not verify_password(payload.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=INVALID_CREDENTIALS,
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user


def issue_token(user: User) -> tuple[str, int]:
    token = create_access_token(user.id)
    return token, settings.access_token_expire_minutes * 60
