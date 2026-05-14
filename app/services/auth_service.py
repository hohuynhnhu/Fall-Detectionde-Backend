from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import UserCameraDB, UserDB


async def upsert_user(db: AsyncSession, decoded: dict) -> UserDB:
    uid = decoded["uid"]
    result = await db.execute(select(UserDB).where(UserDB.firebase_uid == uid))
    user = result.scalar_one_or_none()

    if user is None:
        user = UserDB(
            firebase_uid=uid,
            email=decoded.get("email"),
            phone_number=decoded.get("phone_number"),
            display_name=decoded.get("name"),
        )
        db.add(user)
    else:
        if decoded.get("email"):
            user.email = decoded["email"]
        if decoded.get("phone_number"):
            user.phone_number = decoded["phone_number"]
        if decoded.get("name"):
            user.display_name = decoded["name"]

    await db.commit()
    await db.refresh(user)
    return user


async def get_user_by_uid(db: AsyncSession, firebase_uid: str) -> UserDB | None:
    result = await db.execute(select(UserDB).where(UserDB.firebase_uid == firebase_uid))
    return result.scalar_one_or_none()


async def add_camera(db: AsyncSession, user_id: int, camera_id: str, label: str | None = None) -> UserCameraDB:
    existing = await db.execute(
        select(UserCameraDB).where(
            UserCameraDB.user_id == user_id,
            UserCameraDB.camera_id == camera_id,
        )
    )
    uc = existing.scalar_one_or_none()

    if uc:
        uc.label = label
    else:
        uc = UserCameraDB(user_id=user_id, camera_id=camera_id, label=label)
        db.add(uc)

    await db.commit()
    await db.refresh(uc)
    return uc


async def remove_camera(db: AsyncSession, user_id: int, camera_id: str) -> bool:
    result = await db.execute(
        delete(UserCameraDB).where(
            UserCameraDB.user_id == user_id,
            UserCameraDB.camera_id == camera_id,
        )
    )
    await db.commit()
    return result.rowcount > 0


async def get_user_cameras(db: AsyncSession, user_id: int) -> list[UserCameraDB]:
    result = await db.execute(select(UserCameraDB).where(UserCameraDB.user_id == user_id))
    return list(result.scalars().all())
