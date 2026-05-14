"""
app/api/events.py

POST /events/fall        — desktop → backend (ingest fall event)
POST /events/pose        — desktop → backend (ingest pose-change event)
POST /events/heartbeat   — desktop → backend (heartbeat / live state)
GET  /events/falls       — mobile  ← backend (paginated fall history)
GET  /events/live        — mobile  ← backend (latest state per camera)
"""
from __future__ import annotations

import math
import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..db.models import FallEventDB, PersonDetectedDB, PoseEventDB
from ..schemas import (
    FallEvent,
    FallEventResponse,
    HeartbeatEvent,
    LiveCameraState,
    PaginatedResponse,
    PersonDetectedPayload,
    PoseEvent,
    PoseState,
    WsFallAlert,
    WsStateUpdate,
)
from ..services.websocket_manager import manager
from ..services.fcm import send_fall_notification

router = APIRouter()


# ── Ingest endpoints (desktop → backend) ─────────────────────────────────────

@router.post("/fall", summary="Receive fall event from desktop app")
async def receive_fall(
    event: FallEvent,
    db: AsyncSession = Depends(get_db),
) -> dict:
    ts = event.timestamp or time.time()

    row = FallEventDB(
        camera_id     = event.camera_id,
        timestamp     = ts,
        state_before  = event.state_before,
        velocity_px_s = event.velocity_px_per_s,
        max_velocity  = event.max_velocity,
        body_angle    = event.body_angle,
        confidence    = event.confidence,
        frame_id      = event.frame_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    # Broadcast fall alert to all WebSocket clients
    alert = WsFallAlert(
        camera_id  = event.camera_id,
        timestamp  = ts,
        velocity   = event.max_velocity,
        body_angle = event.body_angle,
        confidence = event.confidence,
    )
    await manager.broadcast(alert.model_dump())

    await send_fall_notification(
        db          = db,
        camera_id   = event.camera_id,
        timestamp   = ts,
        max_velocity= event.max_velocity,
        body_angle  = event.body_angle,
        confidence  = event.confidence,
    )

    return {"ok": True, "id": row.id}


@router.post("/pose", summary="Receive pose-change event from desktop app")
async def receive_pose(
    event: PoseEvent,
    db: AsyncSession = Depends(get_db),
) -> dict:
    ts = event.timestamp or time.time()

    row = PoseEventDB(
        camera_id     = event.camera_id,
        timestamp     = ts,
        state         = event.state,
        prev_state    = event.prev_state,
        velocity_px_s = event.velocity_px_per_s,
        body_angle    = event.metrics.body_angle if event.metrics else 0.0,
        confidence    = event.metrics.confidence if event.metrics else 0.0,
    )
    db.add(row)
    await db.commit()

    return {"ok": True}


@router.post("/heartbeat", summary="Receive heartbeat / live state from desktop app")
async def receive_heartbeat(event: HeartbeatEvent) -> dict:
    ts = event.timestamp or time.time()

    # Update the live-state cache so GET /events/live can serve it
    manager.update_live_state(
        event.camera_id,
        {
            "state":      event.state,
            "velocity":   0.0,
            "body_angle": 0.0,
            "fps":        event.fps,
            "timestamp":  ts,
        },
    )

    # Broadcast state update to WebSocket clients
    update = WsStateUpdate(
        camera_id  = event.camera_id,
        state      = event.state,
        velocity   = 0.0,
        body_angle = 0.0,
        fps        = event.fps,
        timestamp  = ts,
    )
    await manager.broadcast(update.model_dump())

    return {"ok": True, "server_time": time.time()}


@router.post("/person-detected", summary="Receive person detected event from desktop app")
async def receive_person_detected(
    event: PersonDetectedPayload,
    db: AsyncSession = Depends(get_db),
) -> dict:
    ts = event.timestamp or time.time()

    row = PersonDetectedDB(
        camera_id    = event.camera_id,
        timestamp    = ts,
        confidence   = event.confidence,
        person_count = event.person_count,
        frame_id     = event.frame_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    await manager.broadcast({
        "type":         "person_detected",
        "camera_id":    event.camera_id,
        "timestamp":    ts,
        "confidence":   event.confidence,
        "person_count": event.person_count,
    })

    return {"ok": True, "id": row.id}


# ── Query endpoints (mobile ← backend) ───────────────────────────────────────

@router.get(
    "/falls",
    response_model=PaginatedResponse[FallEventResponse],
    summary="Paginated fall history",
)
async def list_falls(
    camera_id: str | None = Query(None, description="Filter by camera ID"),
    page:      int        = Query(1,    ge=1,  description="1-indexed page number"),
    page_size: int        = Query(20,   ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[FallEventResponse]:

    base_q = select(FallEventDB).order_by(desc(FallEventDB.timestamp))
    count_q = select(func.count()).select_from(FallEventDB)

    if camera_id:
        base_q  = base_q.where(FallEventDB.camera_id == camera_id)
        count_q = count_q.where(FallEventDB.camera_id == camera_id)

    total: int = (await db.execute(count_q)).scalar() or 0
    total_pages = max(1, math.ceil(total / page_size))

    offset = (page - 1) * page_size
    rows = (
        await db.execute(base_q.offset(offset).limit(page_size))
    ).scalars().all()

    items = [
        FallEventResponse(
            id           = r.id,
            camera_id    = r.camera_id,
            timestamp    = r.timestamp,
            state_before = r.state_before,
            velocity     = r.velocity_px_s,
            max_velocity = r.max_velocity,
            body_angle   = r.body_angle,
            confidence   = r.confidence,
            acknowledged = r.acknowledged,
        )
        for r in rows
    ]

    return PaginatedResponse(
        ok          = True,
        items       = items,
        total       = total,
        page        = page,
        page_size   = page_size,
        total_pages = total_pages,
    )


@router.get(
    "/live",
    response_model=list[LiveCameraState],
    summary="Latest state per camera (REST polling alternative to WebSocket)",
)
async def get_live_states(
    camera_id: str | None = Query(None, description="Return only this camera; omit for all"),
) -> list[LiveCameraState]:
    states = manager.get_live_states()

    if camera_id:
        states = [s for s in states if s.get("camera_id") == camera_id]

    return [
        LiveCameraState(
            camera_id  = s["camera_id"],
            state      = PoseState(s.get("state", PoseState.UNKNOWN)),
            velocity   = s.get("velocity", 0.0),
            body_angle = s.get("body_angle", 0.0),
            fps        = s.get("fps", 0.0),
            timestamp  = s.get("timestamp", 0.0),
        )
        for s in states
    ]
