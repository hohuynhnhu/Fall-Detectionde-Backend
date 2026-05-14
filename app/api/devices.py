from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..db.models import DeviceTokenDB

router = APIRouter()


class RegisterRequest(BaseModel):
    token:    str
    platform: str = "android"


class UnregisterRequest(BaseModel):
    token: str


@router.post("/register")
async def register_token(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> dict:
    existing = (
        await db.execute(select(DeviceTokenDB).where(DeviceTokenDB.token == body.token))
    ).scalar_one_or_none()

    if existing:
        existing.platform = body.platform
    else:
        db.add(DeviceTokenDB(token=body.token, platform=body.platform))

    await db.commit()
    return {"ok": True}


@router.delete("/unregister")
async def unregister_token(body: UnregisterRequest, db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(
        delete(DeviceTokenDB).where(DeviceTokenDB.token == body.token)
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Token not found")
    return {"ok": True}