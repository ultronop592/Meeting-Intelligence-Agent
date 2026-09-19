import asyncio
import json
import logging
from typing import Any
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketConnectionManager:
    """Manages active WebSocket connections subscribed to meeting pipeline processing jobs."""

    def __init__(self) -> None:
        # Maps job_id -> list of active WebSocket connections
        self._connections: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, job_id: str, websocket: WebSocket) -> None:
        """Accept incoming connection and register under job_id."""
        await websocket.accept()
        async with self._lock:
            if job_id not in self._connections:
                self._connections[job_id] = []
            self._connections[job_id].append(websocket)
        logger.info("WebSocket client connected for job '%s' (active: %d)", job_id, len(self._connections[job_id]))

    async def disconnect(self, job_id: str, websocket: WebSocket) -> None:
        """Unregister connection on close or disconnect."""
        async with self._lock:
            if job_id in self._connections:
                if websocket in self._connections[job_id]:
                    self._connections[job_id].remove(websocket)
                if not self._connections[job_id]:
                    del self._connections[job_id]
        logger.info("WebSocket client disconnected for job '%s'", job_id)

    async def broadcast(self, job_id: str, message: dict[str, Any]) -> None:
        """Broadcast a JSON message to all clients connected to job_id."""
        async with self._lock:
            sockets = list(self._connections.get(job_id, []))

        if not sockets:
            return

        payload_str = json.dumps(message)
        dead_sockets: list[WebSocket] = []

        for ws in sockets:
            try:
                await ws.send_text(payload_str)
            except Exception as exc:
                logger.debug("Failed sending WebSocket message to client on job '%s': %s", job_id, exc)
                dead_sockets.append(ws)

        if dead_sockets:
            async with self._lock:
                if job_id in self._connections:
                    for ws in dead_sockets:
                        if ws in self._connections[job_id]:
                            self._connections[job_id].remove(ws)
                    if not self._connections[job_id]:
                        del self._connections[job_id]


ws_manager = WebSocketConnectionManager()
