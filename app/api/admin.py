from __future__ import annotations

import math
import time
from collections import defaultdict
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import _VN_TZ
from ..db.database import get_db
from ..db.models import EmergencyContactDB, FallEventDB, FamilyMemberDB, SupportReportDB, UserDB
from ..schemas import (
    AdminReportResponse,
    AdminUpdateProfileRequest,
    AdminUserListResponse,
    AdminUserResponse,
    ChangeRoleRequest,
    EmergencyContactItem,
    FallItem,
    FallTimelineResponse,
    FamilyMemberItem,
    PaginatedAdminReportResponse,
    PaginatedFallResponse,
    ReplyReportRequest,
    SendNotificationRequest,
    SendNotificationResponse,
    StatsOverviewResponse,
    UpdateReportStatusRequest,
    UserProfileResponse,
)
from ..services.dependencies import get_current_admin
from ..services.fcm import send_admin_notification, send_report_reply_notification
from ..services.firebase_service import delete_firebase_user

router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fall_item(r: FallEventDB) -> FallItem:
    return FallItem(
        id           = r.id,
        camera_id    = r.camera_id,
        timestamp    = r.timestamp,
        datetime_vn  = datetime.fromtimestamp(r.timestamp, tz=_VN_TZ).strftime("%H:%M %d/%m/%Y"),
        state_before = r.state_before,
        velocity     = r.velocity_px_s,
        max_velocity = r.max_velocity,
        body_angle   = r.body_angle,
        confidence   = r.confidence,
        acknowledged = r.acknowledged,
        clip_url     = r.clip_url,
    )


# ── Admin identity ─────────────────────────────────────────────────────────────

@router.get("/me", response_model=AdminUserResponse,
            summary="Xác nhận và lấy thông tin admin hiện tại")
async def admin_me(admin: UserDB = Depends(get_current_admin)):
    return admin


# ── User management ────────────────────────────────────────────────────────────

@router.get("/users", response_model=AdminUserListResponse,
            summary="Danh sách tất cả người dùng")
async def list_users(
    page:      int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    role:      Optional[str]  = Query(None, description="Lọc theo role: user | admin"),
    email:     Optional[str]  = Query(None, description="Tìm kiếm theo email (contains)"),
    is_active: Optional[bool] = Query(None, description="Lọc theo trạng thái hoạt động"),
    _admin: UserDB = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    query       = select(UserDB)
    count_query = select(func.count()).select_from(UserDB)

    if role:
        query       = query.where(UserDB.role == role)
        count_query = count_query.where(UserDB.role == role)
    if email:
        like        = f"%{email}%"
        query       = query.where(UserDB.email.ilike(like))
        count_query = count_query.where(UserDB.email.ilike(like))
    if is_active is not None:
        query       = query.where(UserDB.is_active == is_active)
        count_query = count_query.where(UserDB.is_active == is_active)

    total       = (await db.execute(count_query)).scalar_one()
    total_pages = max(1, math.ceil(total / page_size))
    query       = query.order_by(UserDB.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    users       = (await db.execute(query)).scalars().all()

    return AdminUserListResponse(
        items=users, total=total, page=page,
        page_size=page_size, total_pages=total_pages,
    )


@router.get("/users/{user_id}", response_model=AdminUserResponse,
            summary="Xem chi tiết một người dùng")
async def get_user(
    user_id: int,
    _admin: UserDB = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(UserDB, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Người dùng không tồn tại")
    return user


@router.patch("/users/{user_id}/role", response_model=AdminUserResponse,
              summary="Thay đổi role người dùng (user ↔ admin)")
async def change_role(
    user_id: int,
    body:    ChangeRoleRequest,
    admin:   UserDB = Depends(get_current_admin),
    db:      AsyncSession = Depends(get_db),
):
    if user_id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Không thể tự thay đổi role của chính mình")
    user = await db.get(UserDB, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Người dùng không tồn tại")
    user.role = body.role
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/users/{user_id}/activate", response_model=AdminUserResponse,
              summary="Kích hoạt tài khoản người dùng")
async def activate_user(
    user_id: int,
    admin:   UserDB = Depends(get_current_admin),
    db:      AsyncSession = Depends(get_db),
):
    if user_id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Không thể tự thay đổi trạng thái của chính mình")
    user = await db.get(UserDB, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Người dùng không tồn tại")
    user.is_active = True
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/users/{user_id}/deactivate", response_model=AdminUserResponse,
              summary="Vô hiệu hóa tài khoản người dùng")
async def deactivate_user(
    user_id: int,
    admin:   UserDB = Depends(get_current_admin),
    db:      AsyncSession = Depends(get_db),
):
    if user_id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Không thể tự vô hiệu hóa chính mình")
    user = await db.get(UserDB, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Người dùng không tồn tại")
    user.is_active = False
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=200,
               summary="Xóa người dùng (xóa cả tài khoản Firebase)")
async def delete_user(
    user_id: int,
    admin:   UserDB = Depends(get_current_admin),
    db:      AsyncSession = Depends(get_db),
):
    if user_id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Không thể tự xóa chính mình")
    user = await db.get(UserDB, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Người dùng không tồn tại")

    firebase_uid = user.firebase_uid
    await db.delete(user)
    await db.commit()

    try:
        await delete_firebase_user(firebase_uid)
    except Exception:
        pass

    return {"ok": True, "message": f"Đã xóa người dùng #{user_id}"}


# ── User profile management ────────────────────────────────────────────────────

@router.get("/users/{user_id}/profile", response_model=UserProfileResponse,
            summary="Xem hồ sơ đầy đủ: thông tin user + thành viên gia đình + liên hệ khẩn cấp")
async def get_user_profile(
    user_id: int,
    _admin:  UserDB = Depends(get_current_admin),
    db:      AsyncSession = Depends(get_db),
):
    user = await db.get(UserDB, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Người dùng không tồn tại")

    family_members = (await db.execute(
        select(FamilyMemberDB).where(FamilyMemberDB.user_id == user_id)
    )).scalars().all()

    contacts = (await db.execute(
        select(EmergencyContactDB).where(EmergencyContactDB.user_id == user_id)
    )).scalars().all()

    return UserProfileResponse(
        user=AdminUserResponse.model_validate(user),
        family_members=[FamilyMemberItem.model_validate(m) for m in family_members],
        emergency_contacts=[EmergencyContactItem.model_validate(c) for c in contacts],
    )


@router.patch("/users/{user_id}/profile", response_model=AdminUserResponse,
              summary="Admin cập nhật thông tin cá nhân của người dùng")
async def update_user_profile(
    user_id: int,
    body:    AdminUpdateProfileRequest,
    _admin:  UserDB = Depends(get_current_admin),
    db:      AsyncSession = Depends(get_db),
):
    user = await db.get(UserDB, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Người dùng không tồn tại")

    if body.display_name is not None:
        user.display_name = body.display_name
    if body.avatar_url is not None:
        user.avatar_url = body.avatar_url

    await db.commit()
    await db.refresh(user)
    return user


@router.get("/users/{user_id}/falls", response_model=PaginatedFallResponse,
            summary="Lịch sử té ngã của người dùng (qua camera_id của bệnh nhân)")
async def get_user_falls(
    user_id:   int,
    page:      int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _admin:    UserDB = Depends(get_current_admin),
    db:        AsyncSession = Depends(get_db),
):
    user = await db.get(UserDB, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Người dùng không tồn tại")

    patients = (await db.execute(
        select(FamilyMemberDB).where(
            FamilyMemberDB.user_id    == user_id,
            FamilyMemberDB.is_patient == True,  # noqa: E712
        )
    )).scalars().all()

    camera_ids = [p.camera_id for p in patients if p.camera_id]

    if not camera_ids:
        return PaginatedFallResponse(items=[], total=0, page=page,
                                     page_size=page_size, total_pages=1)

    base_q  = select(FallEventDB).where(FallEventDB.camera_id.in_(camera_ids)).order_by(FallEventDB.timestamp.desc())
    count_q = select(func.count()).select_from(FallEventDB).where(FallEventDB.camera_id.in_(camera_ids))

    total       = (await db.execute(count_q)).scalar_one()
    total_pages = max(1, math.ceil(total / page_size))
    rows        = (await db.execute(base_q.offset((page - 1) * page_size).limit(page_size))).scalars().all()

    return PaginatedFallResponse(
        items=[_fall_item(r) for r in rows],
        total=total, page=page, page_size=page_size, total_pages=total_pages,
    )


# ── Statistics ─────────────────────────────────────────────────────────────────

@router.get("/stats/overview", response_model=StatsOverviewResponse,
            summary="Tổng quan hệ thống: số user, số fall hôm nay / tháng này / tổng")
async def stats_overview(
    _admin: UserDB = Depends(get_current_admin),
    db:     AsyncSession = Depends(get_db),
):
    now         = datetime.now(_VN_TZ)
    today_start = datetime(now.year, now.month, now.day, tzinfo=_VN_TZ).timestamp()
    month_start = datetime(now.year, now.month, 1,       tzinfo=_VN_TZ).timestamp()

    total_users  = (await db.execute(select(func.count()).select_from(UserDB))).scalar_one()
    active_users = (await db.execute(
        select(func.count()).select_from(UserDB).where(UserDB.is_active == True)  # noqa: E712
    )).scalar_one()

    falls_today = (await db.execute(
        select(func.count()).select_from(FallEventDB).where(FallEventDB.timestamp >= today_start)
    )).scalar_one()

    falls_month = (await db.execute(
        select(func.count()).select_from(FallEventDB).where(FallEventDB.timestamp >= month_start)
    )).scalar_one()

    falls_total = (await db.execute(
        select(func.count()).select_from(FallEventDB)
    )).scalar_one()

    return StatsOverviewResponse(
        total_users            = total_users,
        active_users           = active_users,
        total_falls_today      = falls_today,
        total_falls_this_month = falls_month,
        total_falls_all_time   = falls_total,
    )


@router.get("/stats/falls", response_model=PaginatedFallResponse,
            summary="Danh sách fall có lọc theo thời gian và camera")
async def stats_falls(
    from_ts:   Optional[float] = Query(None, description="Từ timestamp (unix)"),
    to_ts:     Optional[float] = Query(None, description="Đến timestamp (unix)"),
    camera_id: Optional[str]   = Query(None, description="Lọc theo camera_id"),
    page:      int             = Query(1, ge=1),
    page_size: int             = Query(20, ge=1, le=100),
    _admin:    UserDB          = Depends(get_current_admin),
    db:        AsyncSession    = Depends(get_db),
):
    base_q  = select(FallEventDB).order_by(FallEventDB.timestamp.desc())
    count_q = select(func.count()).select_from(FallEventDB)

    if from_ts is not None:
        base_q  = base_q.where(FallEventDB.timestamp >= from_ts)
        count_q = count_q.where(FallEventDB.timestamp >= from_ts)
    if to_ts is not None:
        base_q  = base_q.where(FallEventDB.timestamp <= to_ts)
        count_q = count_q.where(FallEventDB.timestamp <= to_ts)
    if camera_id:
        base_q  = base_q.where(FallEventDB.camera_id == camera_id)
        count_q = count_q.where(FallEventDB.camera_id == camera_id)

    total       = (await db.execute(count_q)).scalar_one()
    total_pages = max(1, math.ceil(total / page_size))
    rows        = (await db.execute(base_q.offset((page - 1) * page_size).limit(page_size))).scalars().all()

    return PaginatedFallResponse(
        items=[_fall_item(r) for r in rows],
        total=total, page=page, page_size=page_size, total_pages=total_pages,
    )


@router.get("/stats/falls/timeline", response_model=FallTimelineResponse,
            summary="Biểu đồ số lần fall theo ngày / tuần / tháng")
async def stats_falls_timeline(
    from_ts:  Optional[float]                 = Query(None, description="Từ timestamp (unix)"),
    to_ts:    Optional[float]                 = Query(None, description="Đến timestamp (unix)"),
    group_by: Literal["day", "week", "month"] = Query("day", description="Nhóm theo: day | week | month"),
    _admin:   UserDB                          = Depends(get_current_admin),
    db:       AsyncSession                    = Depends(get_db),
):
    query = select(FallEventDB.timestamp)
    if from_ts is not None:
        query = query.where(FallEventDB.timestamp >= from_ts)
    if to_ts is not None:
        query = query.where(FallEventDB.timestamp <= to_ts)

    timestamps = (await db.execute(query)).scalars().all()

    counts:     dict[tuple, int] = defaultdict(int)
    labels_map: dict[tuple, str] = {}

    for ts in timestamps:
        dt = datetime.fromtimestamp(ts, tz=_VN_TZ)
        if group_by == "day":
            key   = (dt.year, dt.month, dt.day)
            label = dt.strftime("%d/%m/%Y")
        elif group_by == "week":
            iso   = dt.isocalendar()
            key   = (iso[0], iso[1])
            label = f"W{iso[1]}/{iso[0]}"
        else:
            key   = (dt.year, dt.month)
            label = dt.strftime("%m/%Y")
        counts[key]    += 1
        labels_map[key] = label

    sorted_keys = sorted(counts.keys())
    return FallTimelineResponse(
        group_by = group_by,
        labels   = [labels_map[k] for k in sorted_keys],
        counts   = [counts[k]     for k in sorted_keys],
    )


# ── Support Reports (Admin) ────────────────────────────────────────────────────

def _admin_report_item(r: SupportReportDB, user: Optional[UserDB]) -> AdminReportResponse:
    return AdminReportResponse(
        id          = r.id,
        user_id     = r.user_id,
        user_email  = user.email if user else None,
        user_name   = user.display_name if user else None,
        category    = r.category,
        title       = r.title,
        description = r.description,
        status      = r.status,
        admin_reply = r.admin_reply,
        replied_by  = r.replied_by,
        replied_at  = r.replied_at,
        created_at  = r.created_at,
        updated_at  = r.updated_at,
        datetime_vn = datetime.fromtimestamp(r.created_at, tz=_VN_TZ).strftime("%H:%M %d/%m/%Y"),
    )


@router.get("/reports", response_model=PaginatedAdminReportResponse,
            summary="Danh sách tất cả báo cáo / yêu cầu hỗ trợ")
async def admin_list_reports(
    page:          int           = Query(1, ge=1),
    page_size:     int           = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status",
                                         description="Lọc theo trạng thái: pending | in_progress | resolved | closed"),
    category:      Optional[str] = Query(None, description="Lọc theo loại: bug | feature | question | other"),
    user_id:       Optional[int] = Query(None, description="Lọc theo user"),
    _admin: UserDB       = Depends(get_current_admin),
    db:     AsyncSession = Depends(get_db),
):
    base_q  = select(SupportReportDB)
    count_q = select(func.count()).select_from(SupportReportDB)

    if status_filter:
        base_q  = base_q.where(SupportReportDB.status == status_filter)
        count_q = count_q.where(SupportReportDB.status == status_filter)
    if category:
        base_q  = base_q.where(SupportReportDB.category == category)
        count_q = count_q.where(SupportReportDB.category == category)
    if user_id is not None:
        base_q  = base_q.where(SupportReportDB.user_id == user_id)
        count_q = count_q.where(SupportReportDB.user_id == user_id)

    total       = (await db.execute(count_q)).scalar_one()
    total_pages = max(1, math.ceil(total / page_size))
    rows        = (await db.execute(
        base_q.order_by(SupportReportDB.created_at.desc())
               .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()

    user_ids  = list({r.user_id for r in rows})
    users_map: dict[int, UserDB] = {}
    if user_ids:
        user_rows = (await db.execute(select(UserDB).where(UserDB.id.in_(user_ids)))).scalars().all()
        users_map = {u.id: u for u in user_rows}

    return PaginatedAdminReportResponse(
        items=[_admin_report_item(r, users_map.get(r.user_id)) for r in rows],
        total=total, page=page, page_size=page_size, total_pages=total_pages,
    )


@router.get("/reports/{report_id}", response_model=AdminReportResponse,
            summary="Chi tiết một báo cáo")
async def admin_get_report(
    report_id: int,
    _admin: UserDB       = Depends(get_current_admin),
    db:     AsyncSession = Depends(get_db),
):
    report = await db.get(SupportReportDB, report_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Báo cáo không tồn tại")
    user = await db.get(UserDB, report.user_id)
    return _admin_report_item(report, user)


@router.patch("/reports/{report_id}/status", response_model=AdminReportResponse,
              summary="Cập nhật trạng thái báo cáo")
async def admin_update_report_status(
    report_id: int,
    body:      UpdateReportStatusRequest,
    admin:     UserDB       = Depends(get_current_admin),
    db:        AsyncSession = Depends(get_db),
):
    report = await db.get(SupportReportDB, report_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Báo cáo không tồn tại")
    report.status     = body.status
    report.updated_at = time.time()
    await db.commit()
    await db.refresh(report)
    user = await db.get(UserDB, report.user_id)
    return _admin_report_item(report, user)


@router.post("/reports/{report_id}/reply", response_model=AdminReportResponse,
             summary="Phản hồi báo cáo của người dùng")
async def admin_reply_report(
    report_id: int,
    body:      ReplyReportRequest,
    admin:     UserDB       = Depends(get_current_admin),
    db:        AsyncSession = Depends(get_db),
):
    report = await db.get(SupportReportDB, report_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Báo cáo không tồn tại")

    now = time.time()
    report.admin_reply = body.reply.strip()
    report.replied_by  = admin.id
    report.replied_at  = now
    report.updated_at  = now
    if report.status == "pending":
        report.status = "in_progress"

    await db.commit()
    await db.refresh(report)
    user = await db.get(UserDB, report.user_id)

    await send_report_reply_notification(
        db        = db,
        user_id   = report.user_id,
        report_id = report.id,
        title     = report.title,
        reply     = report.admin_reply,
    )

    return _admin_report_item(report, user)


# ── Admin push notifications ───────────────────────────────────────────────────

@router.post("/notifications/send", response_model=SendNotificationResponse,
             summary="Gửi thông báo đến user (hoặc tất cả)")
async def admin_send_notification(
    body:   SendNotificationRequest,
    _admin: UserDB       = Depends(get_current_admin),
    db:     AsyncSession = Depends(get_db),
):
    if body.user_id is not None:
        user = await db.get(UserDB, body.user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="Người dùng không tồn tại")

    result = await send_admin_notification(
        db      = db,
        title   = body.title.strip(),
        body    = body.body.strip(),
        user_id = body.user_id,
    )

    if not result.get("ok"):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=result.get("reason", "FCM error"))

    return SendNotificationResponse(
        ok     = True,
        sent   = result["sent"],
        failed = result["failed"],
    )
