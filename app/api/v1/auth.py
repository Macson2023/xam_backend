from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserPublic
from app.services.auth import AuthService, issue_token

router = APIRouter(prefix="/auth", tags=["auth"])


def build_token_response(user) -> TokenResponse:
    token, expires_in = issue_token(user)
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserPublic.model_validate(user),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest, session: AsyncSession = Depends(get_db)
) -> TokenResponse:
    user = await AuthService(session).register(payload)
    return build_token_response(user)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = await AuthService(session).login(payload)
    return build_token_response(user)
