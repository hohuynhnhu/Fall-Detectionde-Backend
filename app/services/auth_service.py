from __future__ import annotations

import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import UserDB

# Danh sách email được tự động cấp quyền admin (cách nhau bởi dấu phẩy)
_ADMIN_EMAILS: set[str] = {
    e.strip().lower()
    for e in os.getenv("ADMIN_EMAILS", "").split(",")
    if e.strip()
}


async def upsert_user(db: AsyncSession, decoded: dict) -> UserDB:
    uid = decoded["uid"]
    result = await db.execute(select(UserDB).where(UserDB.firebase_uid == uid))
    user = result.scalar_one_or_none()

    email = decoded.get("email") or ""

    if user is None:
        role = "admin" if email.lower() in _ADMIN_EMAILS else "user"
        user = UserDB(
            firebase_uid=uid,
            email=email or None,
            phone_number=decoded.get("phone_number"),
            display_name=decoded.get("name"),
            role=role,
        )
        db.add(user)
    else:
        if decoded.get("email"):
            user.email = decoded["email"]
        if decoded.get("phone_number"):
            user.phone_number = decoded["phone_number"]
        if decoded.get("name"):
            user.display_name = decoded["name"]
        # Tự động nâng cấp admin nếu email nằm trong ADMIN_EMAILS
        if email.lower() in _ADMIN_EMAILS and user.role != "admin":
            user.role = "admin"

    await db.commit()
    await db.refresh(user)
    return user


async def get_user_by_uid(db: AsyncSession, firebase_uid: str) -> UserDB | None:
    result = await db.execute(select(UserDB).where(UserDB.firebase_uid == firebase_uid))
    return result.scalar_one_or_none()
