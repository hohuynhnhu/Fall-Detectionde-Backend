from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from functools import partial

import firebase_admin
from firebase_admin import credentials, messaging
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import DeviceTokenDB

log = logging.getLogger(__name__)

_firebase_app: firebase_admin.App | None = None


def init_fcm() -> None:
    global _firebase_app

    cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
    cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON")

    if not cred_path and not cred_json:
        log.warning("FCM disabled — set FIREBASE_CREDENTIALS_PATH or FIREBASE_CREDENTIALS_JSON")
        return

    try:
        cred = (
            credentials.Certificate(cred_path)
            if cred_path
            else credentials.Certificate(json.loads(cred_json))
        )
        _firebase_app = firebase_admin.initialize_app(cred)
        log.info("FCM initialised")
    except ValueError:
        _firebase_app = firebase_admin.get_app()
    except Exception as e:
        log.error("FCM init failed: %s", e)


async def send_fall_notification(
    db: AsyncSession,
    camera_id: str,
    timestamp: float,
    max_velocity: float,
    body_angle: float,
    confidence: float,
) -> None:
    if _firebase_app is None:
        return

    result = await db.execute(select(DeviceTokenDB))
    tokens = [r.token for r in result.scalars().all()]
    if not tokens:
        return

    time_str = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")

    message = messaging.MulticastMessage(
        tokens=tokens,
        notification=messaging.Notification(
            title="Phát hiện té ngã!",
            body=f"Camera {camera_id} lúc {time_str}",
        ),
        data={
            "type":         "fall_alert",
            "camera_id":    camera_id,
            "timestamp":    str(timestamp),
            "max_velocity": str(round(max_velocity, 2)),
            "body_angle":   str(round(body_angle, 2)),
            "confidence":   str(round(confidence, 2)),
        },
        android=messaging.AndroidConfig(
            priority="high",
            notification=messaging.AndroidNotification(sound="default"),
        ),
        apns=messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(sound="default", badge=1)
            )
        ),
    )

    loop = asyncio.get_event_loop()
    try:
        response: messaging.BatchResponse = await loop.run_in_executor(
            None, partial(messaging.send_each_for_multicast, message)
        )
    except Exception as e:
        log.error("FCM send error: %s", e)
        return

    log.info("FCM: %d success / %d fail", response.success_count, response.failure_count)

    invalid: list[str] = []
    for i, r in enumerate(response.responses):
        if not r.success:
            code = getattr(r.exception, "code", "")
            if code in ("registration-token-not-registered", "invalid-registration-token"):
                invalid.append(tokens[i])

    if invalid:
        await db.execute(delete(DeviceTokenDB).where(DeviceTokenDB.token.in_(invalid)))
        await db.commit()
        log.info("FCM: removed %d invalid token(s)", len(invalid))