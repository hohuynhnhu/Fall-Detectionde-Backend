"""
app/services/alert_service.py
Gọi điện (phát mp3 qua loa laptop) khi phát hiện té ngã, sử dụng ADB.

Luồng gọi điện:
  1. Gọi đến số liên hệ khẩn cấp
  2. Chờ OFFHOOK (đổ chuông)
  3. Chờ 6s cho bên kia bắt máy
  4. Phát mp3 qua loa laptop → micro điện thoại thu → bên kia nghe
  5. Cúp máy tự động
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

import pygame

log = logging.getLogger(__name__)

DEFAULT_AUDIO = Path(__file__).parent.parent / "assets" / "fall_alert.mp3"

ANSWER_TIMEOUT = 30


# ── ADB core ──────────────────────────────────────────────────────────────────

def _adb_available() -> bool:
    return shutil.which("adb") is not None


def _run_adb(args: list[str], timeout: int = 15) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["adb", *args],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="ignore",
        )
        output = result.stdout.strip() or result.stderr.strip()
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        log.error("ADB timeout: %s", args)
        return False, "timeout"
    except FileNotFoundError:
        log.error("ADB không tìm thấy — hãy cài ADB và thêm vào PATH")
        return False, "adb not found"
    except Exception as e:
        log.error("ADB error: %s", e)
        return False, str(e)


def get_device_status() -> dict:
    ok, output = _run_adb(["devices"])
    lines = [l for l in output.splitlines() if l and "List of" not in l]
    devices = [l.split("\t") for l in lines if "\t" in l]
    connected = [{"id": d[0], "status": d[1]} for d in devices if d[1] == "device"]
    return {
        "adb_available": _adb_available(),
        "devices": connected,
        "connected": len(connected) > 0,
    }


# ── Call state helpers ────────────────────────────────────────────────────────

def _get_call_state() -> str:
    ok, out = _run_adb(["shell", "dumpsys", "telephony.registry"])
    for line in out.splitlines():
        if "mCallState" in line:
            val = line.strip().split("=")[-1].strip()
            return {"0": "IDLE", "1": "RINGING", "2": "OFFHOOK"}.get(val, "UNKNOWN")
    return "UNKNOWN"


def _end_call() -> None:
    _run_adb(["shell", "input", "keyevent", "6"])


# ── Main: gọi điện + phát mp3 trên laptop ────────────────────────────────────

def make_call_with_audio(
    phone_number: str,
    audio_path: str | Path | None = None,
) -> bool:
    if not _adb_available():
        log.error("ADB không khả dụng")
        return False

    audio = Path(audio_path) if audio_path else DEFAULT_AUDIO
    if not audio.exists():
        log.error("File ghi âm không tồn tại: %s", audio)
        return False

    phone = phone_number.strip().replace(" ", "")

    # B1: Gọi điện
    ok, _ = _run_adb([
        "shell", "am", "start",
        "-a", "android.intent.action.CALL",
        "-d", f"tel:{phone}",
    ])
    if not ok:
        log.error("Không thể gọi đến %s", phone)
        return False

    log.info("Đang gọi đến %s...", phone)

    # B2: Chờ OFFHOOK
    offhook = False
    for _ in range(ANSWER_TIMEOUT):
        state = _get_call_state()
        log.info("Call state: %s", state)
        if state == "OFFHOOK":
            offhook = True
            log.info("Đang đổ chuông, chờ 6s để bắt máy...")
            break
        if state == "IDLE":
            log.warning("Cuộc gọi kết thúc sớm")
            return False
        time.sleep(1)

    if not offhook:
        log.warning("Không kết nối được — cúp máy")
        _end_call()
        return False

    # B3: Chờ 6s cho bên kia bắt máy
    time.sleep(6)

    # B4: Phát mp3 trên laptop
    try:
        pygame.mixer.init()
        pygame.mixer.music.load(str(audio))
        pygame.mixer.music.play()
        log.info("Đang phát mp3 trên laptop...")
        time.sleep(8)
        pygame.mixer.music.stop()
    except Exception as e:
        log.error("Lỗi phát mp3: %s", e)

    # B5: Cúp máy
    _end_call()
    log.info("Đã cúp máy")
    return True


async def make_call_with_audio_async(
    phone_number: str,
    audio_path: str | Path | None = None,
) -> bool:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, make_call_with_audio, phone_number, audio_path
    )


# ── HIGH-LEVEL: Cảnh báo té ngã ───────────────────────────────────────────────

async def alert_fall_via_adb(
    contacts: list[dict],
    camera_id: str = "cam_0",
    audio_path: str | Path | None = None,
    extra_msg: Optional[str] = None,
) -> None:
    status = get_device_status()
    if not status["connected"]:
        log.warning("Không có thiết bị Android kết nối — bỏ qua ADB alert")
        return

    for contact in contacts:
        phone = contact.get("phone", "").strip()
        name  = contact.get("name", "")
        if not phone:
            continue

        log.info("Cảnh báo té ngã → %s (%s)", name, phone)

        await make_call_with_audio_async(phone, audio_path)

        await asyncio.sleep(5)