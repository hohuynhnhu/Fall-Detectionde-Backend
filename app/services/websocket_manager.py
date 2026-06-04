"""
app/services/websocket_manager.py
Thread-safe WebSocket manager with per-camera live-state cache.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Dict, List

from fastapi import WebSocket

log = logging.getLogger(__name__)


class WebSocketManager:
    """
    Manages all active WebSocket connections and broadcasts messages to them.
    Also maintains a live-state snapshot per camera_id for REST polling.
    """

    def __init__(self) -> None:
        self._active: List[WebSocket] = []
        # camera_id → latest state dict (for GET /events/live)
        self._live_states: Dict[str, dict] = {}
        self._lock = asyncio.Lock()

    # ── Connection lifecycle ──────────────────────────────────────────────────

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._active.append(ws)
        log.info("WS client connected — total=%d", len(self._active))

        # Send current live snapshot immediately so the client is not blind
        if self._live_states:
            snapshot = {
                "type":   "snapshot",
                "states": self.get_live_states(),
            }
            try:
                await ws.send_text(json.dumps(snapshot))
            except Exception:
                pass

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._active = [c for c in self._active if c is not ws]
        log.info("WS client disconnected — total=%d", len(self._active))

    # ── Broadcasting ──────────────────────────────────────────────────────────

    async def broadcast(self, data: dict) -> None:
        """Send *data* (serialised to JSON) to every connected client."""
        if not self._active:
            return

        msg = json.dumps(data)
        dead: List[WebSocket] = []

        async with self._lock:
            clients = list(self._active)

        for ws in clients:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                self._active = [c for c in self._active if c not in dead]
            log.warning("Removed %d dead WS client(s)", len(dead))

    # ── Live-state cache ──────────────────────────────────────────────────────

    _ONLINE_TTL = 30  # seconds without heartbeat → offline

    def update_live_state(self, camera_id: str, state: dict) -> None:
        self._live_states[camera_id] = {**state, "camera_id": camera_id, "last_seen": time.time()}

    def get_live_states(self) -> List[dict]:
        now = time.time()
        return [
            {**s, "online": (now - s.get("last_seen", 0)) < self._ONLINE_TTL}
            for s in self._live_states.values()
        ]

    def get_live_state(self, camera_id: str) -> dict | None:
        s = self._live_states.get(camera_id)
        if s is None:
            return None
        return {**s, "online": (time.time() - s.get("last_seen", 0)) < self._ONLINE_TTL}

    @property
    def connection_count(self) -> int:
        return len(self._active)


# Singleton shared across the application
manager = WebSocketManager()

# Separate manager for desktop clients (face registration events)
desktop_manager = WebSocketManager()