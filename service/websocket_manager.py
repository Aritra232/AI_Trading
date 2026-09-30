import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from starlette.websockets import WebSocket, WebSocketState

logger = logging.getLogger("websocket_manager")


class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.connection_sessions: Dict[WebSocket, Optional[str]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, session_id: Optional[str] = None):
        await websocket.accept()
        async with self._lock:
            if websocket not in self.active_connections:
                self.active_connections.append(websocket)
            self.connection_sessions[websocket] = session_id
        logger.info(f"[WS] Client connected. Total active: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
            self.connection_sessions.pop(websocket, None)
        logger.info(f"[WS] Client disconnected. Total active: {len(self.active_connections)}")

    async def connections(self) -> List[Tuple[WebSocket, Optional[str]]]:
        async with self._lock:
            return [
                (connection, self.connection_sessions.get(connection))
                for connection in list(self.active_connections)
            ]

    async def send(self, websocket: WebSocket, message: Dict[str, Any]):
        payload = json.dumps(message, default=str)
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_text(payload)
                return True
        except Exception:
            pass

        await self.disconnect(websocket)
        return False

    async def broadcast(self, message: Dict[str, Any]):
        if not self.active_connections:
            return

        connections = await self.connections()
        for connection, _session_id in connections:
            await self.send(connection, message)

    def count(self) -> int:
        return len(self.active_connections)