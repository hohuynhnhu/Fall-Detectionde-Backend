"""
app/api/family_members.py

GET    /family-members/all    — desktop: toàn bộ thành viên có khuôn mặt (no auth)
POST   /family-members/register — mobile: đăng ký khuôn mặt + broadcast WS desktop
GET    /family-members        — mobile: danh sách thành viên của user hiện tại
POST   /family-members        — mobile: thêm thành viên
PATCH  /family-members/{id}   — mobile: cập nhật thành viên
DELETE /family-members/{id}   — mobile: xóa thành viên + broadcast WS desktop
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..db.models import FamilyMemberDB, UserDB
from ..schemas import (
    AddFamilyMemberPayload,
    FamilyMemberResponse,
    RegisterFaceRequest,
    RegisterFaceResponse,
    UpdateFamilyMemberPayload,
)
from ..services.dependencies import get_current_user
from ..services.websocket_manager import desktop_manager

router = APIRouter()


@router.get(
    "/all",
    response_model=list[FamilyMemberResponse],
    summary="[Desktop] Toàn bộ thành viên có khuôn mặt đã đăng ký — không cần auth",
)
async def list_all_members(db: AsyncSession = Depends(get_db)) -> list[FamilyMemberDB]:
    result = await db.execute(
        select(FamilyMemberDB)
        .where(FamilyMemberDB.face_image_url.isnot(None))
        .order_by(FamilyMemberDB.created_at)
    )
    return list(result.scalars().all())


@router.post(
    "/register",
    response_model=RegisterFaceResponse,
    status_code=201,
    summary="Đăng ký khuôn mặt thành viên — broadcast tới desktop qua WS /ws/desktop",
)
async def register_face(
    body: RegisterFaceRequest,
    current_user: UserDB = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RegisterFaceResponse:
    person_id = str(uuid.uuid4())

    member = FamilyMemberDB(
        user_id        = current_user.id,
        person_id      = person_id,
        name           = body.name,
        role           = body.role,
        is_patient     = body.is_patient,
        camera_id      = "cam_0",
        notify_on_fall = True,
        face_image_url = body.face_image_url,
    )
    db.add(member)
    await db.commit()

    await desktop_manager.broadcast({
        "type":           "new_member",
        "person_id":      person_id,
        "name":           body.name,
        "role":           body.role,
        "is_patient":     body.is_patient,
        "face_image_url": body.face_image_url,
    })

    return RegisterFaceResponse(
        person_id      = person_id,
        name           = body.name,
        role           = body.role,
        is_patient     = body.is_patient,
        face_image_url = body.face_image_url,
    )


@router.get(
    "",
    response_model=list[FamilyMemberResponse],
    summary="Danh sách thành viên gia đình",
)
async def list_family_members(
    current_user: UserDB = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[FamilyMemberDB]:
    result = await db.execute(
        select(FamilyMemberDB)
        .where(FamilyMemberDB.user_id == current_user.id)
        .order_by(FamilyMemberDB.created_at)
    )
    return list(result.scalars().all())


@router.post(
    "",
    response_model=FamilyMemberResponse,
    status_code=201,
    summary="Thêm thành viên gia đình",
)
async def add_family_member(
    body: AddFamilyMemberPayload,
    current_user: UserDB = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FamilyMemberDB:
    member = FamilyMemberDB(
        user_id        = current_user.id,
        name           = body.name,
        phone_number   = body.phone_number,
        email          = body.email,
        relationship   = body.relationship,
        notify_on_fall = body.notify_on_fall,
        is_patient     = body.is_patient,
        camera_id      = body.camera_id,
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


@router.patch(
    "/{member_id}",
    response_model=FamilyMemberResponse,
    summary="Cập nhật thông tin thành viên (bật/tắt theo dõi bệnh nhân, gán camera, ...)",
)
async def update_family_member(
    member_id: int,
    body: UpdateFamilyMemberPayload,
    current_user: UserDB = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FamilyMemberDB:
    member = (await db.execute(
        select(FamilyMemberDB).where(
            FamilyMemberDB.id      == member_id,
            FamilyMemberDB.user_id == current_user.id,
        )
    )).scalars().first()
    if member is None:
        raise HTTPException(status_code=404, detail="Thành viên không tồn tại")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(member, field, value)

    await db.commit()
    await db.refresh(member)

    await desktop_manager.broadcast({
        "type":           "update_member",
        "person_id":      member.person_id,
        "name":           member.name,
        "role":           member.role,
        "is_patient":     member.is_patient,
        "notify_on_fall": member.notify_on_fall,
        "face_image_url": member.face_image_url,
    })

    return member


@router.delete(
    "/{member_id}",
    status_code=204,
    summary="Xóa thành viên gia đình — broadcast remove_member tới desktop",
)
async def delete_family_member(
    member_id: int,
    current_user: UserDB = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    member = (await db.execute(
        select(FamilyMemberDB).where(
            FamilyMemberDB.id      == member_id,
            FamilyMemberDB.user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Thành viên không tồn tại")

    person_id = member.person_id
    await db.execute(
        delete(FamilyMemberDB).where(FamilyMemberDB.id == member_id)
    )
    await db.commit()

    if person_id:
        await desktop_manager.broadcast({
            "type":      "remove_member",
            "person_id": person_id,
        })
