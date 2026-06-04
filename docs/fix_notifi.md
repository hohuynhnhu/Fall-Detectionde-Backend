# Fix: FCM & WebSocket Notification

> Ngày: 2026-05-28

---

## Những gì đã sửa

### FCM-03 — `get_event_loop()` deprecated

**File:** `app/services/fcm.py`, `app/services/firebase_service.py`

Thay toàn bộ `asyncio.get_event_loop()` bằng `asyncio.get_running_loop()`.

Đây là bug nghiêm trọng nhất — trên Python 3.10+, `get_event_loop()` có thể tạo event loop mới thay vì dùng loop hiện tại, khiến FCM call không bao giờ thực thi mà không có lỗi nào được log.

---

### FCM-05 — Background task FCM bị mất khi shutdown

**File:** `app/api/events.py`

Thêm helper `_create_tracked_task()` để lưu tham chiếu task vào một set:

```python
_background_tasks: set[asyncio.Task] = set()

def _create_tracked_task(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task
```

Thay toàn bộ `asyncio.create_task(...)` bằng `_create_tracked_task(...)`. Tránh trường hợp FCM task bị drop silently khi server shutdown.

---

### WS-04 — `receive_text()` crash khi nhận binary frame

**File:** `app/api/websocket.py`

Thay `ws.receive_text()` bằng `ws.receive()` ở cả `/ws/live` và `/ws/desktop`.

```python
# Trước
while True:
    await ws.receive_text()  # crash nếu client gửi binary ping

# Sau
while True:
    msg = await ws.receive()
    if msg["type"] == "websocket.disconnect":
        break
```

Thêm `finally` block đảm bảo `disconnect()` luôn được gọi dù lỗi gì xảy ra.

---

### WS-03 — Live state cache không có TTL

**File:** `app/services/websocket_manager.py`, `app/schemas.py`, `app/api/events.py`

Thêm `last_seen` timestamp khi cập nhật live state. Khi camera không gửi heartbeat quá 30 giây thì `online = false`.

```python
# websocket_manager.py
_ONLINE_TTL = 30  # seconds

def update_live_state(self, camera_id, state):
    self._live_states[camera_id] = {**state, "camera_id": camera_id, "last_seen": time.time()}

def get_live_states(self):
    now = time.time()
    return [
        {**s, "online": (now - s.get("last_seen", 0)) < self._ONLINE_TTL}
        for s in self._live_states.values()
    ]
```

Thêm field `online: bool` vào schema `LiveCameraState`. Mobile app dùng field này để hiển thị badge "Camera đang hoạt động / Mất kết nối".

---

### Thêm `event_id` vào FCM payload

**File:** `app/services/fcm.py`, `app/api/events.py`

Thêm `event_id` vào data payload của cả fall và pose notification. Mobile app dùng để deep-link vào màn hình chi tiết khi user bấm vào notification.

```json
// Fall notification payload
{
  "type": "fall_alert",
  "event_id": "42",
  "camera_id": "cam_0",
  "timestamp": "1234567890.0",
  "max_velocity": "1.23",
  "body_angle": "45.0",
  "confidence": "0.95",
  "clip_url": "https://..."
}

// Pose notification payload
{
  "type": "pose_update",
  "event_id": "17",
  "camera_id": "cam_0",
  "patient_name": "Nguyễn Văn A",
  "state": "LYING",
  "timestamp": "1234567890.0"
}
```

Đồng thời fix `receive_pose` thiếu `await db.refresh(row)` khiến `row.id` trả về `None`.

---

## Không thay đổi database

Tất cả thay đổi đều là logic code và in-memory cache. Không có migration nào cần chạy.

---

## Mobile app nên làm

| Tình huống | Hành động |
|-----------|-----------|
| App đóng, nhận FCM | Lưu notification vào local storage |
| User bấm vào notification | Đọc `event_id` → mở màn hình chi tiết |
| App mở lên | Fetch `GET /events/falls` + `GET /events/patient-poses` để lấy lịch sử |
| Vào màn hình monitor | Kết nối `WebSocket /ws/live` |
| Thoát màn hình monitor | Ngắt WebSocket (tránh tốn battery) |
| Hiển thị trạng thái camera | Đọc field `online` từ `GET /events/live` |
