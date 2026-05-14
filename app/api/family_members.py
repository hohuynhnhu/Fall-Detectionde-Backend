"""
app/api/family_members.py

GET    /family-members        — danh sách thành viên gia đình
POST   /family-members        — thêm thành viên
DELETE /family-members/{id}   — xóa thành viên
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..db.models import FamilyMemberDB
from ..schemas import AddFamilyMemberPayload, FamilyMemberResponse

router = APIRouter()


@router.get(
    "",
    response_model=list[FamilyMemberResponse],
    summary="Danh sách thành viên gia đình",
)
async def list_family_members(db: AsyncSession = Depends(get_db)) -> list[FamilyMemberDB]:
    result = await db.execute(select(FamilyMemberDB).order_by(FamilyMemberDB.created_at))
    return list(result.scalars().all())


@router.post(
    "",
    response_model=FamilyMemberResponse,
    status_code=201,
    summary="Thêm thành viên gia đình",
)
async def add_family_member(
    body: AddFamilyMemberPayload,
    db: AsyncSession = Depends(get_db),
) -> FamilyMemberDB:
    member = FamilyMemberDB(
        name           = body.name,
        phone_number   = body.phone_number,
        email          = body.email,
        relationship   = body.relationship,
        notify_on_fall = body.notify_on_fall,
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


@router.delete(
    "/{member_id}",
    status_code=204,
    summary="Xóa thành viên gia đình",
)
async def delete_family_member(
    member_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(
        delete(FamilyMemberDB).where(FamilyMemberDB.id == member_id)
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Thành viên không tồn tại")
