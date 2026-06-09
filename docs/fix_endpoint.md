# Thay doi Backend — GPS + phan quyen fall history

## 1. GPS trong Fall Alert

Desktop app gui them toa do GPS kem `POST /events/fall`. Backend tra ve qua 3 kenh.

### File da sua

| File | Thay doi |
|------|----------|
| `app/schemas.py:85-89` | Them class `GpsLocation` (latitude, longitude) |
| `app/schemas.py:108` | `FallEvent` them field `gps: Optional[GpsLocation]` |
| `app/schemas.py:165-166` | `FallEventResponse` them `latitude`, `longitude` |
| `app/schemas.py:337-338` | `WsFallAlert` them `latitude`, `longitude` |
| `app/schemas.py:455-456` | `FallItem` (admin) them `latitude`, `longitude` |
| `app/db/models.py:24-25` | `FallEventDB` them 2 cot `latitude`, `longitude` (nullable) |
| `app/db/database.py:57-62` | Migration `ALTER TABLE fall_events ADD COLUMN` |
| `app/api/events.py:123-124` | `receive_fall` luu GPS vao DB |
| `app/api/events.py:137-139` | WebSocket `WsFallAlert` kem GPS |
| `app/api/events.py:153-156` | Goi FCM kem GPS |
| `app/api/events.py:322-323` | `list_falls` tra ve GPS |
| `app/api/admin.py:58-59` | `_fall_item` tra ve GPS |
| `app/api/admin.py:394-395` | `_fall_item_with_user` tra ve GPS |
| `app/services/fcm.py:56-57` | `send_fall_notification` nhan param `latitude`, `longitude` |
| `app/services/fcm.py:93-94` | FCM data payload kem `latitude`, `longitude` |

### Mobile can doc

| Kenh | Kieu du lieu | Ghi chu |
|------|-------------|---------|
| WebSocket `fall_alert` | `latitude: float \| null`, `longitude: float \| null` | Real-time |
| FCM push `data` | `latitude: string \| khong co key`, `longitude: string \| khong co key` | Notification |
| REST `GET /events/falls` | `latitude: float \| null`, `longitude: float \| null` | Lich su |

---

## 2. GET /events/falls — loc theo tai khoan mobile

Truoc day `GET /events/falls` tra ve tat ca falls (khong phan quyen). Gio:

- **Co token** (mobile) → chi tra ve falls cua benh nhan thuoc tai khoan do
- **Khong token** (desktop) → van hoat dong nhu cu

### File da sua

| File | Thay doi |
|------|----------|
| `app/services/dependencies.py:36-53` | Them `get_optional_user` — tra ve `UserDB` neu co token hop le, khong thi `None` |
| `app/api/events.py:42` | Import `get_optional_user` |
| `app/api/events.py:288-305` | `list_falls` nhan `current_user` optional, loc theo `camera_id` cua benh nhan |

### Mobile cach dung

```
GET /events/falls?page=1&page_size=20
Authorization: Bearer <id_token>
```

Response:

```json
{
  "ok": true,
  "items": [
    {
      "id": 1,
      "camera_id": "cam_0",
      "timestamp": 1716300000.0,
      "datetime_vn": "15:00 21/05/2025",
      "state_before": "STANDING",
      "velocity": 120.5,
      "max_velocity": 150.2,
      "body_angle": 75.3,
      "confidence": 0.92,
      "acknowledged": false,
      "clip_url": null,
      "latitude": 21.0285,
      "longitude": 105.8542
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 20,
  "total_pages": 3
}
```

`total` chinh la tong so lan te cua tai khoan do.

---

## 3. Loi GET /events/falls/{id}

Desktop goi `GET /events/falls/84` → **404 Not Found**. Route nay khong ton tai.

Route dung de lay danh sach: `GET /events/falls?camera_id=cam_0&page=1` (co dau `?`, khong co `/{id}`).

Desktop can sua lai URL.
