"""
app/api/websocket.py
WebSocket endpoint — streams all fall alerts and state updates to connected clients.

Connect: ws(s)://<host>/ws/live
On connect: receives a one-time "snapshot" of all current camera states.
Ongoing:    receives "fall_alert" and "state_update" messages as they arrive.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..services.websocket_manager import manager

log = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/live")
async def live_ws(ws: WebSocket) -> None:
    await manager.connect(ws)
    try:
        while True:
            # Keep the connection alive; clients may send pings as plain text
            await ws.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(ws)
    except Exception as exc:
        log.warning("WS error: %s", exc)
        await manager.disconnect(ws)