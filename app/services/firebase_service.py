from __future__ import annotations

import asyncio
import os
from functools import partial

import httpx
import firebase_admin
from firebase_admin import auth, credentials


def _get_app() -> firebase_admin.App:
    try:
        return firebase_admin.get_app()
    except ValueError:
        cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "firebase-service-account.json")
        cred = credentials.Certificate(cred_path)
        return firebase_admin.initialize_app(cred)


async def verify_id_token(token: str) -> dict:
    _get_app()
    loop = asyncio.get_event_loop()
    decoded = await loop.run_in_executor(None, partial(auth.verify_id_token, token, clock_skew_seconds=10))
    return decoded


async def create_email_user(email: str, password: str, display_name: str | None = None) -> dict:
    _get_app()
    loop = asyncio.get_event_loop()

    kwargs: dict = {"email": email, "password": password}
    if display_name:
        kwargs["display_name"] = display_name

    user_record = await loop.run_in_executor(None, partial(auth.create_user, **kwargs))
    return {"uid": user_record.uid, "email": user_record.email, "display_name": user_record.display_name}


async def sign_in_with_email(email: str, password: str) -> dict:
    api_key = os.getenv("FIREBASE_WEB_API_KEY")
    if not api_key:
        raise RuntimeError("FIREBASE_WEB_API_KEY không được cấu hình")

    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            json={"email": email, "password": password, "returnSecureToken": True},
        )

    if resp.status_code != 200:
        detail = resp.json().get("error", {}).get("message", "INVALID_CREDENTIALS")
        raise ValueError(detail)

    return resp.json()


async def update_user_password(firebase_uid: str, new_password: str) -> None:
    _get_app()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, partial(auth.update_user, firebase_uid, password=new_password))


async def delete_firebase_user(firebase_uid: str) -> None:
    _get_app()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, partial(auth.delete_user, firebase_uid))
