from fastapi import APIRouter

from app.api.v1 import auth, channels, chats, groups, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(chats.router)
api_router.include_router(groups.router)
api_router.include_router(channels.router)
