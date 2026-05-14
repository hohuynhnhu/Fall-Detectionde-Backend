# Fall Detection Backend — API Reference

Base URL: `http://localhost:8000`  
Docs: `http://localhost:8000/docs`

---

## Setup

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**.env**
```
DATABASE_URL=postgresql+asyncpg://user:pass@ep-xxx.neon.tech/dbname?ssl=require
FIREBASE_CREDENTIALS_PATH=firebase-service-account.json
```

---

## REST API

### Events

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| `GET` | `/events/falls` | Lịch sử té ngã (có phân trang) |
| `GET` | `/events/live` | Trạng thái hiện tại mỗi camera |
| `POST` | `/events/fall` | _(desktop)_ Gửi fall event |
| `POST` | `/events/heartbeat` | _(desktop)_ Gửi heartbeat |

**GET /events/falls**
```
GET /events/falls?camera_id=cam_0&page=1&page_size=20
```
```json
{
  "ok": true,
  "items": [
    {
      "id": 1,
      "camera_id": "cam_0",
      "timestamp": 1713200000.0,
      "state_before": "STANDING",
      "velocity": 120.0,
      "max_velocity": 150.0,
      "body_angle": 75.0,
      "confidence": 0.92,
      "acknowledged": false
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 20,
  "total_pages": 3
}
```

**GET /events/live**
```
GET /events/live
GET /events/live?camera_id=cam_0
```
```json
[
  {
    "camera_id": "cam_0",
    "state": "STANDING",
    "velocity": 0.0,
    "body_angle": 12.5,
    "fps": 30.0,
    "timestamp": 1713200010.0
  }
]
```

---

### Config Thresholds

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| `GET` | `/config/thresholds` | Lấy config của camera |
| `PUT` | `/config/thresholds` | Cập nhật config |
| `POST` | `/config/thresholds/reset` | Reset về mặc định |

```
GET  /config/thresholds?camera_id=cam_0
PUT  /config/thresholds?camera_id=cam_0
POST /config/thresholds/reset?camera_id=cam_0
```

Body PUT:
```json
{
  "fall_velocity_threshold": 80.0,
  "body_angle_lying": 65.0,
  "body_angle_sitting": 45.0,
  "aspect_ratio_lying": 0.55,
  "fall_confirm_frames": 5,
  "fall_history_window": 30,
  "walk_velocity_threshold": 20.0,
  "walk_knee_lift_threshold": 0.08,
  "walk_alternating_window": 15,
  "camera_index": 0,
  "flip_horizontal": true,
  "model_complexity": 1
}
```

---

### Device Tokens (FCM)

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| `POST` | `/devices/register` | Đăng ký FCM token |
| `DELETE` | `/devices/unregister` | Huỷ đăng ký |

```json
POST /devices/register
{ "token": "fcm_device_token", "platform": "android" }

DELETE /devices/unregister
{ "token": "fcm_device_token" }
```

---

## WebSocket

```
ws://localhost:8000/ws/live
```

Kết nối xong nhận ngay **snapshot** trạng thái hiện tại, sau đó nhận real-time:

**fall_alert** — khi phát hiện té ngã:
```json
{
  "type": "fall_alert",
  "camera_id": "cam_0",
  "timestamp": 1713200000.0,
  "velocity": 150.0,
  "body_angle": 75.0,
  "confidence": 0.92
}
```

**state_update** — mỗi heartbeat từ desktop:
```json
{
  "type": "state_update",
  "camera_id": "cam_0",
  "state": "STANDING",
  "velocity": 0.0,
  "body_angle": 12.5,
  "fps": 30.0,
  "timestamp": 1713200010.0
}
```

**snapshot** — gửi 1 lần ngay khi connect:
```json
{
  "type": "snapshot",
  "states": [ ...state_update objects... ]
}
```

---

## FCM Push Notification

Tự động gửi tới tất cả thiết bị đã đăng ký khi nhận `POST /events/fall`.

**Payload nhận được trên mobile:**
```json
{
  "notification": {
    "title": "Phát hiện té ngã!",
    "body": "Camera cam_0 lúc 10:30:05"
  },
  "data": {
    "type": "fall_alert",
    "camera_id": "cam_0",
    "timestamp": "1713200000.0",
    "max_velocity": "150.0",
    "body_angle": "75.0",
    "confidence": "0.92"
  }
}
```

---

## Pose States

| Value | Nghĩa |
|-------|-------|
| `STANDING` | Đứng |
| `SITTING` | Ngồi |
| `LYING` | Nằm |
| `FALLING` | Đang té |
| `WALKING` | Đi bộ |
| `UNKNOWN` | Không xác định |

---

## Database Tables

| Table | Nội dung |
|-------|---------|
| `fall_events` | Lịch sử té ngã |
| `pose_events` | Lịch sử thay đổi tư thế |
| `threshold_configs` | Config ngưỡng per camera |
| `device_tokens` | FCM token của mobile |