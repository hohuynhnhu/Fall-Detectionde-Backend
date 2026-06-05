import subprocess
import time
import pygame

PHONE_NUMBER = "0332174585"
MP3_PATH = r"D:\luan_van\fall-detection-backend\app\assets\fall_alert.mp3"

def get_call_state():
    result = subprocess.run(
        ["adb", "shell", "dumpsys", "telephony.registry"],
        capture_output=True, text=True,
        encoding="utf-8", errors="ignore"
    )
    for line in result.stdout.splitlines():
        if "mCallState" in line:
            val = line.strip().split("=")[-1].strip()
            return {"0": "IDLE", "1": "RINGING", "2": "OFFHOOK"}.get(val, "UNKNOWN")
    return "UNKNOWN"

# Gọi điện
subprocess.run(["adb", "shell", "am", "start",
    "-a", "android.intent.action.CALL",
    "-d", f"tel:{PHONE_NUMBER}"])
print("Đang gọi...")

# Chờ OFFHOOK
offhook = False
for i in range(30):
    state = get_call_state()
    print(f"Call state: {state}")
    if state == "OFFHOOK":
        offhook = True
        print("Đang đổ chuông, chờ bắt máy...")
        break
    time.sleep(1)

if offhook:
    # Chờ 3s cho bên kia bắt máy
    time.sleep(8)

    # Phát mp3 trên laptop
    pygame.mixer.init()
    pygame.mixer.music.load(MP3_PATH)
    pygame.mixer.music.play()
    print("Đang phát mp3...")

    time.sleep(5)
    pygame.mixer.music.stop()

    subprocess.run(["adb", "shell", "input", "keyevent", "6"])
    print("Xong!")
else:
    print("Không gọi được — cúp máy")
    subprocess.run(["adb", "shell", "input", "keyevent", "6"])