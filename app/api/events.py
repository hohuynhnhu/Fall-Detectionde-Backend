"""
app/api/events.py

POST /events/fall        — desktop → backend (ingest fall event)
POST /events/pose        — desktop → backend (ingest pose-change event)
POST /events/heartbeat   — desktop → backend (heartbeat / live state)
GET  /events/falls       — mobile  ← backend (paginated fall history)
GET  /events/live        — mobile  ← backend (latest state per camera)
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import _VN_TZ
from ..db.database import AsyncSessionLocal, get_db
from ..db.models import FallEventDB, FamilyMemberDB, PersonDetectedDB, PoseEventDB, UserDB
from ..schemas import (
    FallEvent,
    FallEventResponse,
    HeartbeatEvent,
    LiveCameraState,
    PaginatedResponse,
    PatientPoseEvent,
    PersonDetectedPayload,
    PoseEvent,
    PoseEventResponse,
    PoseState,
    WsFallAlert,
    WsPatientPoseUpdate,
    WsStateUpdate,
)
from ..services.websocket_manager import manager
from ..services.fcm import send_fall_notification, send_pose_notification
from ..services.dependencies import get_current_user, get_optional_user
from ..services.alert_service import alert_fall_via_adb
from ..services.email_service import send_report_reply_email
from ..db.models import EmergencyContactDB
logger = logging.getLogger(__name__)
router = APIRouter()


_background_tasks: set[asyncio.Task] = set()


def _create_tracked_task(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _dispatch_pose_notifications(camera_id: str, state: str, timestamp: float, event_id: int | None = None) -> None:
    """Background task: gửi FCM về trạng thái bệnh nhân cho mọi bệnh nhân đang được theo dõi bởi camera này."""
    try:
        async with AsyncSessionLocal() as db:
            patients = (await db.execute(
                select(FamilyMemberDB).where(
                    FamilyMemberDB.camera_id  == camera_id,
                    FamilyMemberDB.is_patient == True,  # noqa: E712
                )
            )).scalars().all()
            for patient in patients:
                await send_pose_notification(db, patient.name, camera_id, state, timestamp, event_id=event_id)
    except Exception:
        logger.exception("Pose notification task failed for camera %s", camera_id)

async def _dispatch_single_patient_notification(
    person_id: str, person_name: str,
    camera_id: str, state: str,
    timestamp: float, event_id: int | None = None,
    prev_state: str | None = None, 
) -> None:
    """Gửi FCM cho đúng 1 bệnh nhân theo person_id."""
    try:
        async with AsyncSessionLocal() as db:
            patient = (await db.execute(
                select(FamilyMemberDB).where(
                    FamilyMemberDB.person_id  == person_id,
                    FamilyMemberDB.is_patient == True,
                )
            )).scalar_one_or_none()

            if patient is None:
                return

            await send_pose_notification(
                db, patient.name, camera_id,
                state, timestamp, event_id=event_id,
                prev_state=prev_state,
            )
    except Exception:
        logger.exception("Single patient notification failed for %s", person_id)

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
        clip_url      = event.clip_url,
        latitude      = event.gps.latitude if event.gps else None,
        longitude     = event.gps.longitude if event.gps else None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    # Broadcast fall alert to all WebSocket clients
    alert = WsFallAlert(
        camera_id        = event.camera_id,
        timestamp        = ts,
        velocity         = event.max_velocity,
        body_angle       = event.body_angle,
        confidence       = event.confidence,
        clip_url         = event.clip_url,
        latitude         = event.gps.latitude if event.gps else None,
        longitude        = event.gps.longitude if event.gps else None,
        sound_detected   = event.sound_detected,
        sound_class      = event.sound_class,
        sound_confidence = event.sound_confidence,
    )
    await manager.broadcast(alert.model_dump())

    await send_fall_notification(
        db               = db,
        camera_id        = event.camera_id,
        timestamp        = ts,
        max_velocity     = event.max_velocity,
        body_angle       = event.body_angle,
        confidence       = event.confidence,
        event_id         = row.id,
        clip_url         = event.clip_url,
        latitude         = event.gps.latitude if event.gps else None,
        longitude        = event.gps.longitude if event.gps else None,
        sound_detected   = event.sound_detected,
        sound_class      = event.sound_class,
        sound_confidence = event.sound_confidence,
    )
    # Gửi email cho tất cả user active
    from sqlalchemy import select as _select
    time_str = datetime.fromtimestamp(ts, tz=_VN_TZ).strftime("%H:%M:%S %d/%m/%Y")
    all_users = (await db.execute(
        _select(UserDB).where(
            UserDB.email.isnot(None),
            UserDB.is_active == True,  # noqa: E712
        )
    )).scalars().all()
    for user in all_users:
        if user.email:
            await send_report_reply_email(
                to_email     = user.email,
                user_name    = user.display_name or user.email,
                report_title = f"⚠️ Phát hiện té ngã lúc {time_str}",
                reply        = f"Camera {event.camera_id} phát hiện té ngã lúc {time_str}.\n\nVận tốc: {round(event.max_velocity, 1)} px/s\nĐộ tin cậy: {round(event.confidence * 100, 1)}%",
            )
            
    contacts_rows = (await db.execute(
        select(EmergencyContactDB).where(
            EmergencyContactDB.is_active == True,  # noqa: E712
        )  
    )).scalars().all()
    contacts = [
        {"name": c.name, "phone": c.phone}
        for c in contacts_rows
        if c.phone
    ]
    if contacts:
        _create_tracked_task(
            alert_fall_via_adb(contacts, camera_id=event.camera_id)
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
    await db.refresh(row)

    # FCM push chỉ cho đúng bệnh nhân này, không phải tất cả
    # _create_tracked_task(_dispatch_pose_notifications(event.camera_id, event.state.value, ts, event_id=row.id))

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
    current_user: UserDB | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[FallEventResponse]:

    # Nếu mobile có token → chỉ lấy falls của bệnh nhân thuộc tài khoản này
    patient_camera_ids: list[str] | None = None
    if current_user:
        patient_rows = (await db.execute(
            select(FamilyMemberDB.camera_id).where(
                FamilyMemberDB.user_id    == current_user.id,
                FamilyMemberDB.is_patient == True,
                FamilyMemberDB.camera_id.isnot(None),
            )
        )).scalars().all()
        patient_camera_ids = list(set(patient_rows))

    base_q = select(FallEventDB).order_by(desc(FallEventDB.timestamp))
    count_q = select(func.count()).select_from(FallEventDB)

    if camera_id:
        base_q  = base_q.where(FallEventDB.camera_id == camera_id)
        count_q = count_q.where(FallEventDB.camera_id == camera_id)
    elif patient_camera_ids:
        base_q  = base_q.where(FallEventDB.camera_id.in_(patient_camera_ids))
        count_q = count_q.where(FallEventDB.camera_id.in_(patient_camera_ids))

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
            clip_url     = r.clip_url,
            latitude     = r.latitude,
            longitude    = r.longitude,
            datetime_vn  = datetime.fromtimestamp(r.timestamp, tz=_VN_TZ).strftime("%H:%M %d/%m/%Y"),
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
    "/falls/{event_id}",
    response_model=FallEventResponse,
    summary="Get single fall event by ID",
)
async def get_fall_by_id(
    event_id: int,
    db: AsyncSession = Depends(get_db),
) -> FallEventResponse:
    from sqlalchemy import select as _select
    r = (await db.execute(
        _select(FallEventDB).where(FallEventDB.id == event_id)
    )).scalar_one_or_none()

    if r is None:
        raise HTTPException(status_code=404, detail="Fall event not found")

    return FallEventResponse(
        id           = r.id,
        camera_id    = r.camera_id,
        timestamp    = r.timestamp,
        state_before = r.state_before,
        velocity     = r.velocity_px_s,
        max_velocity = r.max_velocity,
        body_angle   = r.body_angle,
        confidence   = r.confidence,
        acknowledged = r.acknowledged,
        clip_url     = r.clip_url,
        latitude     = r.latitude,
        longitude    = r.longitude,
        datetime_vn  = datetime.fromtimestamp(r.timestamp, tz=_VN_TZ).strftime("%H:%M %d/%m/%Y"),
    )


_patient_pose_last_sent: dict[str, tuple[str, float]] = {}
_PATIENT_POSE_DEBOUNCE = 15.0

@router.post("/patient-pose", summary="[Desktop] Nhận sự kiện tư thế bệnh nhân (có nhận diện khuôn mặt)")
async def receive_patient_pose(
    event: PatientPoseEvent,
    db:    AsyncSession = Depends(get_db),
) -> dict:
    ts = event.timestamp or time.time()
    pid = event.person_id
    new_state = event.state.value

    # Debounce: bỏ qua nếu cùng state trong 15 giây
    last_state, last_ts = _patient_pose_last_sent.get(pid, (None, 0.0))
    print(f"[PatientPose] pid={pid[:8]} state={new_state} last={last_state} gap={ts-last_ts:.1f}s")
    if last_state == new_state and (ts - last_ts) < _PATIENT_POSE_DEBOUNCE:
        print(f"[PatientPose] SKIPPED debounce")
        return {"ok": True, "skipped": True}

    _patient_pose_last_sent[pid] = (new_state, ts)

    row = PoseEventDB(
        camera_id   = event.camera_id,
        timestamp   = ts,
        state       = new_state,
        prev_state  = event.prev_state.value if event.prev_state else None,
        person_id   = pid,
        person_name = event.person_name,
        frame_id    = event.frame_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    print(f"[PatientPose] SEND FCM pid={pid[:8]} state={new_state} event_id={row.id}")
    _create_tracked_task(_dispatch_single_patient_notification(
        pid, event.person_name, event.camera_id,
        new_state, ts, event_id=row.id,
        prev_state=event.prev_state.value if event.prev_state else None,
    ))

    return {"ok": True, "id": row.id}

@router.get(
    "/patient-poses",
    response_model=PaginatedResponse[PoseEventResponse],
    summary="[Mobile] Lịch sử tư thế bệnh nhân — phân trang",
)
async def list_patient_poses(
    page:      int          = Query(1,    ge=1),
    page_size: int          = Query(20,   ge=1, le=100),
    person_id: str | None   = Query(None, description="Lọc theo person_id"),
    date_from: float | None = Query(None, description="Unix timestamp — từ"),
    date_to:   float | None = Query(None, description="Unix timestamp — đến"),
    current_user: UserDB       = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
) -> PaginatedResponse[PoseEventResponse]:

    member_pids: list[str] = (await db.execute(
        select(FamilyMemberDB.person_id).where(
            FamilyMemberDB.user_id    == current_user.id,
            FamilyMemberDB.person_id.isnot(None),
        )
    )).scalars().all()

    base_q = (
        select(PoseEventDB)
        .where(PoseEventDB.person_id.in_(member_pids))
        .order_by(desc(PoseEventDB.timestamp))
    )
    count_q = (
        select(func.count())
        .select_from(PoseEventDB)
        .where(PoseEventDB.person_id.in_(member_pids))
    )

    if person_id:
        base_q  = base_q.where(PoseEventDB.person_id  == person_id)
        count_q = count_q.where(PoseEventDB.person_id == person_id)
    if date_from is not None:
        base_q  = base_q.where(PoseEventDB.timestamp >= date_from)
        count_q = count_q.where(PoseEventDB.timestamp >= date_from)
    if date_to is not None:
        base_q  = base_q.where(PoseEventDB.timestamp <  date_to)
        count_q = count_q.where(PoseEventDB.timestamp <  date_to)

    total: int       = (await db.execute(count_q)).scalar() or 0
    total_pages: int = max(1, math.ceil(total / page_size))
    offset: int      = (page - 1) * page_size

    rows = (await db.execute(base_q.offset(offset).limit(page_size))).scalars().all()

    return PaginatedResponse(
        ok          = True,
        items       = [
            PoseEventResponse(
                id          = r.id,
                camera_id   = r.camera_id,
                timestamp   = r.timestamp,
                state       = r.state,
                prev_state  = r.prev_state,
                person_id   = r.person_id,
                person_name = r.person_name,
                frame_id    = r.frame_id,
                datetime_vn = datetime.fromtimestamp(r.timestamp, tz=_VN_TZ)
                              .strftime("%H:%M %d/%m/%Y"),
            )
            for r in rows
        ],
        total       = total,
        page        = page,
        page_size   = page_size,
        total_pages = total_pages,
    )
@router.patch("/fall/{event_id}", summary="Cập nhật clip_url cho fall event")
async def update_fall_clip(
    event_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await db.get(FallEventDB, event_id)
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Event not found")
    if "clip_url" in body:
        row.clip_url = body["clip_url"]
    await db.commit()
    return {"ok": True}

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
            online     = s.get("online", False),
        )
        for s in states
    ]
