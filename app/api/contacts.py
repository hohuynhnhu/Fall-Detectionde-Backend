"""
app/api/contacts.py

POST   /api/contacts              — thêm contact (max 5, no duplicate phone)
GET    /api/contacts              — danh sách contacts của user
PATCH  /api/contacts/{contact_id} — sửa fields / toggle is_active
DELETE /api/contacts/{contact_id} — xóa
"""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..db.models import EmergencyContactDB, UserDB
from ..services.dependencies import get_current_user

router = APIRouter()

MAX_CONTACTS = 5


def _validate_phone_vn(phone: str) -> bool:
    return bool(re.match(r"^(0[3|5|7|8|9])\d{8}$", phone))


# ── Schemas ───────────────────────────────────────────────────────────────────

class ContactIn(BaseModel):
    name:     str
    phone:    str
    relation: Optional[str] = None


class ContactPatch(BaseModel):
    name:      Optional[str]  = None
    phone:     Optional[str]  = None
    relation:  Optional[str]  = None
    is_active: Optional[bool] = None


class ContactOut(BaseModel):
    id:         int
    user_id:    int
    name:       str
    phone:      str
    relation:   Optional[str]
    is_active:  bool
    created_at: float

    model_config = {"from_attributes": True}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", response_model=ContactOut, status_code=201, summary="Thêm số người thân")
async def add_contact(
    body: ContactIn,
    current_user: UserDB = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContactOut:
    if not _validate_phone_vn(body.phone):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Số điện thoại không hợp lệ (phải bắt đầu 03/05/07/08/09, đủ 10 số)",
        )

    count: int = (
        await db.execute(
            select(func.count()).select_from(EmergencyContactDB)
            .where(EmergencyContactDB.user_id == current_user.id)
        )
    ).scalar() or 0
    if count >= MAX_CONTACTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tối đa {MAX_CONTACTS} số liên hệ mỗi tài khoản",
        )

    existing = (
        await db.execute(
            select(EmergencyContactDB).where(
                EmergencyContactDB.user_id == current_user.id,
                EmergencyContactDB.phone   == body.phone,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Số điện thoại này đã được đăng ký",
        )

    contact = EmergencyContactDB(
        user_id  = current_user.id,
        name     = body.name,
        phone    = body.phone,
        relation = body.relation,
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


@router.get("", response_model=list[ContactOut], summary="Danh sách số người thân")
async def list_contacts(
    current_user: UserDB = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ContactOut]:
    result = await db.execute(
        select(EmergencyContactDB)
        .where(EmergencyContactDB.user_id == current_user.id)
        .order_by(EmergencyContactDB.created_at)
    )
    return list(result.scalars().all())


@router.patch("/{contact_id}", response_model=ContactOut, summary="Sửa contact / toggle is_active")
async def update_contact(
    contact_id: int,
    body: ContactPatch,
    current_user: UserDB = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContactOut:
    contact = (
        await db.execute(
            select(EmergencyContactDB).where(
                EmergencyContactDB.id      == contact_id,
                EmergencyContactDB.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Liên hệ không tồn tại")

    if body.phone is not None:
        if not _validate_phone_vn(body.phone):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Số điện thoại không hợp lệ",
            )
        dup = (
            await db.execute(
                select(EmergencyContactDB).where(
                    EmergencyContactDB.user_id == current_user.id,
                    EmergencyContactDB.phone   == body.phone,
                    EmergencyContactDB.id      != contact_id,
                )
            )
        ).scalar_one_or_none()
        if dup:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Số điện thoại này đã được đăng ký",
            )
        contact.phone = body.phone

    if body.name is not None:
        contact.name = body.name
    if body.relation is not None:
        contact.relation = body.relation
    if body.is_active is not None:
        contact.is_active = body.is_active

    await db.commit()
    await db.refresh(contact)
    return contact


@router.delete("/{contact_id}", status_code=204, summary="Xóa số người thân")
async def delete_contact(
    contact_id: int,
    current_user: UserDB = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        delete(EmergencyContactDB).where(
            EmergencyContactDB.id      == contact_id,
            EmergencyContactDB.user_id == current_user.id,
        )
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Liên hệ không tồn tại")
