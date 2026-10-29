import asyncio
import logging
from uuid import UUID

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """In-memory registry of active WebSocket sessions keyed by user id."""

    def __init__(self) -> None:
        self._connections: dict[UUID, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: UUID, websocket: WebSocket) -> bool:
        """Register a connection and report whether this is the user's first session."""
        async with self._lock:
            connections = self._connections.setdefault(user_id, set())
            connections.add(websocket)
            return len(connections) == 1

    async def disconnect(self, user_id: UUID, websocket: WebSocket) -> bool:
        """Remove a connection and report whether the user has no sessions left."""
        async with self._lock:
            connections = self._connections.get(user_id)
            if connections is None:
                return False
            connections.discard(websocket)
            if connections:
                return False
            self._connections.pop(user_id, None)
            return True

    async def send_to_user(self, user_id: UUID, payload: dict) -> None:
        connections = list(self._connections.get(user_id, ()))
        for websocket in connections:
            try:
                await websocket.send_json(payload)
            except Exception:
                logger.debug("Dropping dead websocket for user %s", user_id)
                await self.disconnect(user_id, websocket)

    async def broadcast(self, user_ids, payload: dict) -> None:
        for user_id in set(user_ids):
            await self.send_to_user(user_id, payload)


manager = ConnectionManager()
