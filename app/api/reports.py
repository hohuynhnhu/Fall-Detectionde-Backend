from __future__ import annotations

import math
import time
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import _VN_TZ
from ..db.database import get_db
from ..db.models import SupportReportDB, UserDB
from ..services.dependencies import get_current_user

router = APIRouter()

VALID_CATEGORIES = {"bug", "feature", "question", "other"}


# ── Schemas ────────────────────────────────────────────────────────────────────

class CreateReportRequest(BaseModel):
    category:    Literal["bug", "feature", "question", "other"]
    title:       str = Field(..., min_length=5, max_length=256)
    description: str = Field(..., min_length=10, max_length=2000)


class ReportResponse(BaseModel):
    id:          int
    category:    str
    title:       str
    description: str
    status:      str
    admin_reply: Optional[str]
    replied_at:  Optional[float]
    created_at:  float
    updated_at:  float
    datetime_vn: str

    class Config:
        from_attributes = True


class PaginatedReportResponse(BaseModel):
    ok:          bool = True
    items:       list[ReportResponse]
    total:       int
    page:        int
    page_size:   int
    total_pages: int


# ── Helpers ────────────────────────────────────────────────────────────────────

def _to_response(r: SupportReportDB) -> ReportResponse:
    return ReportResponse(
        id          = r.id,
        category    = r.category,
        title       = r.title,
        description = r.description,
        status      = r.status,
        admin_reply = r.admin_reply,
        replied_at  = r.replied_at,
        created_at  = r.created_at,
        updated_at  = r.updated_at,
        datetime_vn = datetime.fromtimestamp(r.created_at, tz=_VN_TZ).strftime("%H:%M %d/%m/%Y"),
    )


# ── Mobile endpoints ───────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED, response_model=ReportResponse,
             summary="Gửi báo cáo / yêu cầu hỗ trợ")
async def create_report(
    body: CreateReportRequest,
    user: UserDB = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    now = time.time()
    report = SupportReportDB(
        user_id     = user.id,
        category    = body.category,
        title       = body.title.strip(),
        description = body.description.strip(),
        status      = "pending",
        created_at  = now,
        updated_at  = now,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return _to_response(report)


@router.get("", response_model=PaginatedReportResponse,
            summary="Danh sách báo cáo của tôi")
async def list_my_reports(
    page:      int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    status_filter: Optional[str] = Query(None, alias="status",
                                         description="Lọc theo trạng thái: pending | in_progress | resolved | closed"),
    user: UserDB = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    base_q  = select(SupportReportDB).where(SupportReportDB.user_id == user.id)
    count_q = select(func.count()).select_from(SupportReportDB).where(SupportReportDB.user_id == user.id)

    if status_filter:
        base_q  = base_q.where(SupportReportDB.status == status_filter)
        count_q = count_q.where(SupportReportDB.status == status_filter)

    total       = (await db.execute(count_q)).scalar_one()
    total_pages = max(1, math.ceil(total / page_size))
    rows        = (await db.execute(
        base_q.order_by(SupportReportDB.created_at.desc())
               .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()

    return PaginatedReportResponse(
        items=[_to_response(r) for r in rows],
        total=total, page=page, page_size=page_size, total_pages=total_pages,
    )


@router.get("/{report_id}", response_model=ReportResponse,
            summary="Chi tiết một báo cáo của tôi")
async def get_my_report(
    report_id: int,
    user: UserDB = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    report = await db.get(SupportReportDB, report_id)
    if not report or report.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Báo cáo không tồn tại")
    return _to_response(report)
