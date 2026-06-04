"""
app/api/face_logs.py

POST /face-logs         — Desktop gửi log nhận diện (không cần auth)
GET  /face-logs/summary — Mobile: số lần xuất hiện hôm nay theo từng thành viên
GET  /face-logs         — Mobile: lịch sử phân trang (filter: person_id, date_from, date_to)
"""
from __future__ import annotations

import math
import time
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import _VN_TZ
from ..db.database import get_db
from ..db.models import FaceRecognitionLogDB, FamilyMemberDB, UserDB
from ..schemas import (
    FaceLogCreate,
    FaceLogResponse,
    FaceLogSummaryItem,
    FaceLogSummaryResponse,
    PaginatedResponse,
)
from ..services.dependencies import get_current_user

router = APIRouter()


# ── Ingest (desktop → backend) ────────────────────────────────────────────────

@router.post(
    "",
    status_code=201,
    summary="[Desktop] Ghi nhận lượt nhận diện khuôn mặt thành công",
)
async def create_face_log(
    body: FaceLogCreate,
    db:   AsyncSession = Depends(get_db),
) -> dict:
    ts = body.recognized_at if body.recognized_at > 0 else time.time()

    # Tìm user_id từ person_id để sau này lọc theo user (best-effort)
    member = (await db.execute(
        select(FamilyMemberDB)
        .where(FamilyMemberDB.person_id == body.person_id)
        .limit(1)
    )).scalar_one_or_none()
    user_id = member.user_id if member else None

    row = FaceRecognitionLogDB(
        user_id       = user_id,
        person_id     = body.person_id,
        name          = body.name,
        is_patient    = body.is_patient,
        recognized_at = ts,
        camera_id     = body.camera_id,
        confidence    = body.confidence if body.confidence > 0 else None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"ok": True, "id": row.id}


# ── Query (mobile ← backend) ──────────────────────────────────────────────────

@router.get(
    "/summary",
    response_model=FaceLogSummaryResponse,
    summary="Số lần xuất hiện hôm nay theo từng thành viên gia đình",
)
async def face_log_summary(
    current_user: UserDB       = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
) -> FaceLogSummaryResponse:
    now_vn      = datetime.now(_VN_TZ)
    today_start = now_vn.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    today_end   = today_start + 86400.0

    member_pids: list[str] = (await db.execute(
        select(FamilyMemberDB.person_id).where(
            FamilyMemberDB.user_id    == current_user.id,
            FamilyMemberDB.person_id.isnot(None),
        )
    )).scalars().all()

    rows = (await db.execute(
        select(
            FaceRecognitionLogDB.person_id,
            FaceRecognitionLogDB.name,
            FaceRecognitionLogDB.is_patient,
            func.count(FaceRecognitionLogDB.id).label("count_today"),
        )
        .where(
            FaceRecognitionLogDB.person_id.in_(member_pids),
            FaceRecognitionLogDB.recognized_at >= today_start,
            FaceRecognitionLogDB.recognized_at <  today_end,
        )
        .group_by(
            FaceRecognitionLogDB.person_id,
            FaceRecognitionLogDB.name,
            FaceRecognitionLogDB.is_patient,
        )
        .order_by(desc("count_today"))
    )).all()

    return FaceLogSummaryResponse(
        date    = now_vn.strftime("%d/%m/%Y"),
        members = [
            FaceLogSummaryItem(
                person_id   = r.person_id,
                name        = r.name,
                is_patient  = r.is_patient,
                count_today = r.count_today,
            )
            for r in rows
        ],
    )


@router.get(
    "",
    response_model=PaginatedResponse[FaceLogResponse],
    summary="Lịch sử nhận diện khuôn mặt — phân trang",
)
async def list_face_logs(
    page:      int          = Query(1,    ge=1),
    limit:     int          = Query(20,   ge=1, le=100),
    person_id: str | None   = Query(None, description="Lọc theo person_id"),
    date_from: float | None = Query(None, description="Unix timestamp — từ thời điểm"),
    date_to:   float | None = Query(None, description="Unix timestamp — đến thời điểm"),
    current_user: UserDB       = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
) -> PaginatedResponse[FaceLogResponse]:

    member_pids: list[str] = (await db.execute(
        select(FamilyMemberDB.person_id).where(
            FamilyMemberDB.user_id    == current_user.id,
            FamilyMemberDB.person_id.isnot(None),
        )
    )).scalars().all()

    base_q  = (
        select(FaceRecognitionLogDB)
        .where(FaceRecognitionLogDB.person_id.in_(member_pids))
        .order_by(desc(FaceRecognitionLogDB.recognized_at))
    )
    count_q = (
        select(func.count())
        .select_from(FaceRecognitionLogDB)
        .where(FaceRecognitionLogDB.person_id.in_(member_pids))
    )

    if person_id:
        base_q  = base_q.where(FaceRecognitionLogDB.person_id  == person_id)
        count_q = count_q.where(FaceRecognitionLogDB.person_id == person_id)
    if date_from is not None:
        base_q  = base_q.where(FaceRecognitionLogDB.recognized_at >= date_from)
        count_q = count_q.where(FaceRecognitionLogDB.recognized_at >= date_from)
    if date_to is not None:
        base_q  = base_q.where(FaceRecognitionLogDB.recognized_at <  date_to)
        count_q = count_q.where(FaceRecognitionLogDB.recognized_at <  date_to)

    total:       int = (await db.execute(count_q)).scalar() or 0
    total_pages: int = max(1, math.ceil(total / limit))
    offset:      int = (page - 1) * limit

    rows = (await db.execute(base_q.offset(offset).limit(limit))).scalars().all()

    return PaginatedResponse(
        ok          = True,
        items       = [
            FaceLogResponse(
                id            = r.id,
                person_id     = r.person_id,
                name          = r.name,
                is_patient    = r.is_patient,
                confidence    = r.confidence,
                camera_id     = r.camera_id,
                recognized_at = r.recognized_at,
                datetime_vn   = datetime.fromtimestamp(r.recognized_at, tz=_VN_TZ)
                                .strftime("%H:%M %d/%m/%Y"),
            )
            for r in rows
        ],
        total       = total,
        page        = page,
        page_size   = limit,
        total_pages = total_pages,
    )
