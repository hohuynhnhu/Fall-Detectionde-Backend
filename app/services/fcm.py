#services/fcm.py
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
    event_id: int | None = None,
    clip_url: str | None = None,
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
            **({"event_id": str(event_id)} if event_id is not None else {}),
            **({"clip_url": clip_url} if clip_url else {}),
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

    loop = asyncio.get_running_loop()
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


_POSE_STATE_VN: dict[str, str] = {
    "STANDING": "đang đứng",
    "SITTING":  "đang ngồi",
    "LYING":    "đang nằm",
    "WALKING":  "đang đi lại",
}


async def send_pose_notification(
    db: AsyncSession,
    patient_name: str,
    camera_id: str,
    state: str,
    timestamp: float,
    event_id: int | None = None,
    prev_state: str | None = None,
) -> None:
    state_vn = _POSE_STATE_VN.get(state)
    if state_vn is None:
        return

    if _firebase_app is None:
        return

    result = await db.execute(select(DeviceTokenDB))
    tokens = [r.token for r in result.scalars().all()]
    if not tokens:
        return

    time_str = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")

    # Tạo body notification — ẩn UNKNOWN
    prev_vn = _POSE_STATE_VN.get(prev_state, "") if prev_state else ""
    if prev_vn and prev_state not in ("UNKNOWN", ""):
        body_text = f"{patient_name}: {prev_vn} → {state_vn} lúc {time_str}"
    else:
        body_text = f"{patient_name} {state_vn} lúc {time_str}"

    message = messaging.MulticastMessage(
        tokens=tokens,
        notification=messaging.Notification(
            title=f"{patient_name} - cập nhật trạng thái",
            body=body_text,
        ),
        data={
            "type":         "pose_update",
            "camera_id":    camera_id,
            "patient_name": patient_name,
            "state":        state,
            "prev_state":   prev_state or "",
            "timestamp":    str(timestamp),
            **({"event_id": str(event_id)} if event_id is not None else {}),
        },
        android=messaging.AndroidConfig(
            priority="hight",
            notification=messaging.AndroidNotification(sound="default"),
        ),
        apns=messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(sound="default")
            )
        ),
    )

    loop = asyncio.get_running_loop()
    try:
        response: messaging.BatchResponse = await loop.run_in_executor(
            None, partial(messaging.send_each_for_multicast, message)
        )
    except Exception as e:
        log.error("FCM pose send error: %s", e)
        return

    log.info("FCM pose (%s/%s): %d ok / %d fail",
             patient_name, state, response.success_count, response.failure_count)

    invalid: list[str] = []
    for i, r in enumerate(response.responses):
        if not r.success:
            code = getattr(r.exception, "code", "")
            if code in ("registration-token-not-registered", "invalid-registration-token"):
                invalid.append(tokens[i])

    if invalid:
        await db.execute(delete(DeviceTokenDB).where(DeviceTokenDB.token.in_(invalid)))
        await db.commit()


async def send_report_reply_notification(
    db:        AsyncSession,
    user_id:   int,
    report_id: int,
    title:     str,
    reply:     str,
) -> None:
    if _firebase_app is None:
        return

    result = await db.execute(
        select(DeviceTokenDB).where(DeviceTokenDB.user_id == user_id)
    )
    tokens = [r.token for r in result.scalars().all()]
    if not tokens:
        return

    preview = reply[:100] + "..." if len(reply) > 100 else reply

    message = messaging.MulticastMessage(
        tokens=tokens,
        notification=messaging.Notification(
            title="Admin đã phản hồi báo cáo của bạn",
            body=preview,
        ),
        data={
            "type":      "report_reply",
            "report_id": str(report_id),
            "title":     title,
            "reply":     reply,
        },
        android=messaging.AndroidConfig(
            priority="normal",
            notification=messaging.AndroidNotification(sound="default"),
        ),
        apns=messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(sound="default")
            )
        ),
    )

    loop = asyncio.get_running_loop()
    try:
        response: messaging.BatchResponse = await loop.run_in_executor(
            None, partial(messaging.send_each_for_multicast, message)
        )
    except Exception as e:
        log.error("FCM report reply send error: %s", e)
        return

    log.info("FCM report reply (user=%d): %d ok / %d fail",
             user_id, response.success_count, response.failure_count)

    invalid: list[str] = []
    for i, r in enumerate(response.responses):
        if not r.success:
            code = getattr(r.exception, "code", "")
            if code in ("registration-token-not-registered", "invalid-registration-token"):
                invalid.append(tokens[i])

    if invalid:
        await db.execute(delete(DeviceTokenDB).where(DeviceTokenDB.token.in_(invalid)))
        await db.commit()


async def send_admin_notification(
    db:      AsyncSession,
    title:   str,
    body:    str,
    user_id: int | None = None,
) -> dict:
    """Gửi thông báo từ admin. user_id=None → broadcast tất cả user."""
    if _firebase_app is None:
        return {"ok": False, "reason": "FCM not initialised"}

    query = select(DeviceTokenDB)
    if user_id is not None:
        query = query.where(DeviceTokenDB.user_id == user_id)

    result = await db.execute(query)
    tokens = [r.token for r in result.scalars().all()]
    if not tokens:
        return {"ok": True, "sent": 0, "failed": 0}

    message = messaging.MulticastMessage(
        tokens=tokens,
        notification=messaging.Notification(title=title, body=body),
        data={"type": "admin_notification", "title": title, "body": body},
        android=messaging.AndroidConfig(
            priority="normal",
            notification=messaging.AndroidNotification(sound="default"),
        ),
        apns=messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(sound="default")
            )
        ),
    )

    loop = asyncio.get_running_loop()
    try:
        response: messaging.BatchResponse = await loop.run_in_executor(
            None, partial(messaging.send_each_for_multicast, message)
        )
    except Exception as e:
        log.error("FCM admin notification error: %s", e)
        return {"ok": False, "reason": str(e)}

    log.info("FCM admin notification: %d ok / %d fail",
             response.success_count, response.failure_count)

    invalid: list[str] = []
    for i, r in enumerate(response.responses):
        if not r.success:
            code = getattr(r.exception, "code", "")
            if code in ("registration-token-not-registered", "invalid-registration-token"):
                invalid.append(tokens[i])

    if invalid:
        await db.execute(delete(DeviceTokenDB).where(DeviceTokenDB.token.in_(invalid)))
        await db.commit()

    return {
        "ok":     True,
        "sent":   response.success_count,
        "failed": response.failure_count,
    }