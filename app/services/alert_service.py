"""
app/services/alert_service.py
Gửi SMS và gọi điện (phát ghi âm) qua điện thoại Android kết nối USB (ADB).

Luồng gọi điện:
  1. Push file mp4/mp3 lên /sdcard/
  2. Gọi đến số cần báo
  3. Chờ bên kia bắt máy (CALL_STATE_OFFHOOK)
  4. Bật loa ngoài → phát ghi âm
  5. Khi ghi âm kết thúc → cúp máy tự động
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Đường dẫn file ghi âm mặc định (mp3/mp4/ogg đều được)
DEFAULT_AUDIO = Path(__file__).parent.parent / "assets" / "fall_alert.mp3"
DEVICE_AUDIO_PATH = "/sdcard/fall_alert_adb.mp3"

# Thời gian tối đa chờ bên kia bắt máy (giây)
ANSWER_TIMEOUT = 30
# Thời gian tối đa phát ghi âm (giây) — fallback nếu không đọc được duration
MAX_AUDIO_DURATION = 30


# ── ADB core ──────────────────────────────────────────────────────────────────

def _adb_available() -> bool:
    return shutil.which("adb") is not None


def _run_adb(args: list[str], timeout: int = 15) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["adb", *args],
            capture_output=True, text=True, timeout=timeout,
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
    """
    Trả về trạng thái cuộc gọi:
      IDLE     — không có cuộc gọi
      RINGING  — đang đổ chuông
      OFFHOOK  — đang nghe máy (bên kia bắt)
    """
    ok, out = _run_adb(["shell", "dumpsys", "telephony.registry"])
    for line in out.splitlines():
        if "mCallState" in line:
            val = line.strip().split("=")[-1].strip()
            # 0=IDLE, 1=RINGING, 2=OFFHOOK
            return {"0": "IDLE", "1": "RINGING", "2": "OFFHOOK"}.get(val, "UNKNOWN")
    return "UNKNOWN"


def _end_call() -> None:
    """Cúp máy."""
    _run_adb(["shell", "input", "keyevent", "6"])   # KEYCODE_ENDCALL


def _enable_speaker() -> None:
    """Bật loa ngoài trong lúc đang gọi."""
    # Nhấn nút Speaker trên UI (nếu có) — hoặc dùng telecom service
    _run_adb(["shell", "input", "keyevent", "227"])  # KEYCODE_CALL toggle speaker


def _get_audio_duration(local_path: str | Path) -> float:
    """
    Đọc duration (giây) của file audio bằng ffprobe.
    Fallback về MAX_AUDIO_DURATION nếu ffprobe không có.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(local_path),
            ],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        log.warning("Không đọc được duration — dùng fallback %ds", MAX_AUDIO_DURATION)
        return MAX_AUDIO_DURATION


def _push_audio(local_path: str | Path) -> bool:
    """Push file âm thanh lên /sdcard/ của thiết bị."""
    ok, out = _run_adb(["push", str(local_path), DEVICE_AUDIO_PATH], timeout=30)
    if not ok:
        log.error("Push audio thất bại: %s", out)
    return ok


def _play_audio_on_device() -> None:
    """Phát file âm thanh trên thiết bị (qua loa ngoài)."""
    _run_adb([
        "shell", "am", "start",
        "-a", "android.intent.action.VIEW",
        "-d", f"file://{DEVICE_AUDIO_PATH}",
        "-t", "audio/mpeg",
        "--ez", "OneShot", "true",
    ])


def _stop_audio_on_device() -> None:
    """Dừng phát âm thanh (bằng cách tắt media player)."""
    _run_adb(["shell", "am", "force-stop", "com.android.music"])
    _run_adb(["shell", "am", "force-stop", "com.google.android.music"])
    _run_adb(["shell", "am", "force-stop", "com.spotify.music"])


# ── Main: gọi điện + phát ghi âm + tự cúp ───────────────────────────────────

def make_call_with_audio(
    phone_number: str,
    audio_path: str | Path | None = None,
) -> bool:
    """
    1. Gọi đến phone_number
    2. Chờ bên kia bắt máy
    3. Bật loa ngoài → phát ghi âm
    4. Sau khi ghi âm xong → cúp máy tự động

    audio_path: đường dẫn file mp3/mp4 trên máy tính.
                Nếu None → dùng DEFAULT_AUDIO.
    """
    if not _adb_available():
        log.error("ADB không khả dụng")
        return False

    audio = Path(audio_path) if audio_path else DEFAULT_AUDIO
    if not audio.exists():
        log.error("File ghi âm không tồn tại: %s", audio)
        return False

    phone = phone_number.strip().replace(" ", "")
    duration = _get_audio_duration(audio)
    log.info("Duration ghi âm: %.1fs", duration)

    # B1: Push file lên thiết bị
    if not _push_audio(audio):
        return False

    # B2: Thực hiện cuộc gọi
    ok, _ = _run_adb([
        "shell", "am", "start",
        "-a", "android.intent.action.CALL",
        "-d", f"tel:{phone}",
    ])
    if not ok:
        log.error("Không thể gọi đến %s", phone)
        return False

    log.info("Đang gọi đến %s — chờ bắt máy...", phone)

    # B3: Chờ bên kia bắt máy (OFFHOOK)
    deadline = time.time() + ANSWER_TIMEOUT
    answered = False
    while time.time() < deadline:
        state = _get_call_state()
        if state == "OFFHOOK":
            answered = True
            log.info("Bên kia đã bắt máy!")
            break
        if state == "IDLE":
            log.info("Cuộc gọi kết thúc trước khi bắt máy")
            return False
        time.sleep(1)

    if not answered:
        log.warning("Hết %ds chờ — cúp máy", ANSWER_TIMEOUT)
        _end_call()
        return False

    # B4: Bật loa ngoài + phát ghi âm
    time.sleep(1)              # cho cuộc gọi ổn định
    _enable_speaker()
    time.sleep(0.5)
    _play_audio_on_device()

    log.info("Đang phát ghi âm (%.1fs)...", duration)
    time.sleep(duration + 1)   # +1s buffer

    # B5: Cúp máy tự động
    _stop_audio_on_device()
    _end_call()
    log.info("Đã cúp máy sau khi phát xong ghi âm")
    return True


async def make_call_with_audio_async(
    phone_number: str,
    audio_path: str | Path | None = None,
) -> bool:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, make_call_with_audio, phone_number, audio_path
    )


# ── SMS ───────────────────────────────────────────────────────────────────────

def send_sms(phone_number: str, message: str) -> bool:
    if not _adb_available():
        return False

    phone = phone_number.strip().replace(" ", "")
    safe_msg = message.replace('"', '\\"')

    ok, out = _run_adb([
        "shell", "service", "call", "isms", "5",
        "s16", "com.android.mms.service",
        "s16", "null",
        "s16", phone,
        "s16", "null",
        "s16", safe_msg,
        "s16", "null", "s16", "null",
        "i32", "0", "i64", "0",
    ])

    if ok and "result" in out.lower():
        log.info("SMS gửi thành công đến %s", phone)
        return True

    # Fallback intent
    ok2, _ = _run_adb([
        "shell", "am", "start",
        "-a", "android.intent.action.SENDTO",
        "-d", f"smsto:{phone}",
        "--es", "sms_body", safe_msg,
        "--ez", "exit_on_sent", "true",
    ])
    return ok2


async def send_sms_async(phone_number: str, message: str) -> bool:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, send_sms, phone_number, message)


# ── HIGH-LEVEL: Cảnh báo té ngã ───────────────────────────────────────────────

async def alert_fall_via_adb(
    contacts: list[dict],
    camera_id: str = "cam_0",
    audio_path: str | Path | None = None,
    extra_msg: Optional[str] = None,
) -> None:
    """
    Với mỗi liên hệ:
      1. Gửi SMS cảnh báo
      2. Gọi điện + phát ghi âm + tự cúp
    """
    status = get_device_status()
    if not status["connected"]:
        log.warning("Không có thiết bị Android kết nối — bỏ qua ADB alert")
        return

    message = extra_msg or (
        f"[CẢNH BÁO] Phát hiện té ngã từ camera {camera_id}! Vui lòng kiểm tra ngay."
    )

    for contact in contacts:
        phone = contact.get("phone", "").strip()
        name  = contact.get("name", "")
        if not phone:
            continue

        log.info("Cảnh báo té ngã → %s (%s)", name, phone)

        # SMS trước
        await send_sms_async(phone, message)
        await asyncio.sleep(1)

        # Gọi điện + phát ghi âm
        await make_call_with_audio_async(phone, audio_path)

        # Chờ 5s trước khi gọi liên hệ tiếp theo
        await asyncio.sleep(5)
