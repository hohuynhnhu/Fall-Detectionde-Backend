from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..db.models import DeviceTokenDB, UserDB
from ..services.dependencies import get_current_user
from ..services.alert_service import get_device_status, make_call_with_audio  # bỏ send_sms

router = APIRouter()


class RegisterRequest(BaseModel):
    token:    str
    platform: str = "android"


class UnregisterRequest(BaseModel):
    token: str


@router.post("/register")
async def register_token(
    body:         RegisterRequest,
    current_user: UserDB = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
) -> dict:
    existing = (
        await db.execute(select(DeviceTokenDB).where(DeviceTokenDB.token == body.token))
    ).scalar_one_or_none()

    if existing:
        existing.platform = body.platform
        existing.user_id  = current_user.id
    else:
        db.add(DeviceTokenDB(
            user_id  = current_user.id,
            token    = body.token,
            platform = body.platform,
        ))

    await db.commit()
    return {"ok": True}


@router.delete("/unregister")
async def unregister_token(
    body:         UnregisterRequest,
    current_user: UserDB = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        delete(DeviceTokenDB).where(
            DeviceTokenDB.token   == body.token,
            DeviceTokenDB.user_id == current_user.id,
        )
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Token not found")
    return {"ok": True}


# ── ADB endpoints ─────────────────────────────────────────────────────────────

@router.get("/adb/status", summary="Kiểm tra thiết bị Android kết nối USB")
async def adb_status(
    current_user: UserDB = Depends(get_current_user),
) -> dict:
    return get_device_status()


class CallRequest(BaseModel):
    phone:      str
    audio_path: str | None = None


@router.post("/adb/call", summary="Gọi điện + phát mp3 qua loa laptop + tự cúp")
async def adb_make_call(
    body:         CallRequest,
    current_user: UserDB = Depends(get_current_user),
) -> dict:
    loop = asyncio.get_event_loop()
    ok = await loop.run_in_executor(
        None, make_call_with_audio, body.phone, body.audio_path
    )
    return {"ok": ok}