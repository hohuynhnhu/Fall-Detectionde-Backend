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

from ..services.websocket_manager import desktop_manager, manager

log = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/live")
async def live_ws(ws: WebSocket) -> None:
    await manager.connect(ws)
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.warning("WS error: %s", exc)
    finally:
        await manager.disconnect(ws)


@router.websocket("/desktop")
async def desktop_ws(ws: WebSocket) -> None:
    await desktop_manager.connect(ws)
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.warning("Desktop WS error: %s", exc)
    finally:
        await desktop_manager.disconnect(ws)