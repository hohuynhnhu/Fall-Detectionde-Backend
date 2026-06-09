# GPS trong Fall Alert — mobile implement

Backend nay da them toa do GPS vao fall event. Desktop gui GPS kem `POST /events/fall`, backend tra ve qua tat ca cac kenh.

---

## 1. FCM Push Notification

Payload co them 2 field moi trong `data`:

```json
{
  "notification": {
    "title": "Phát hiện té ngã!",
    "body": "Camera cam_0 lúc 10:30:05"
  },
  "data": {
    "type": "fall_alert",
    "camera_id": "cam_0",
    "timestamp": "1716300000.0",
    "max_velocity": "150.0",
    "body_angle": "75.0",
    "confidence": "0.92",
    "latitude": "21.0285", // <-- MOI
    "longitude": "105.8542", // <-- MOI
    "event_id": "42",
    "clip_url": "https://...",
    "sound_detected": "true",
    "sound_class": "scream",
    "sound_confidence": "0.85"
  }
}
```

> `latitude` va `longitude` la string, co the khong ton tai (null) neu desktop khong lay duoc GPS. Luon check `!= null` truoc khi dung.

---

## 2. WebSocket `fall_alert`

Message `fall_alert` co them 2 field:

```json
{
  "type": "fall_alert",
  "camera_id": "cam_0",
  "timestamp": 1716300000.0,
  "velocity": 130.5,
  "body_angle": 78.2,
  "confidence": 0.95,
  "clip_url": null,
  "latitude": 21.0285, // <-- MOI (float | null)
  "longitude": 105.8542, // <-- MOI (float | null)
  "sound_detected": false,
  "sound_class": "",
  "sound_confidence": 0.0
}
```

---

## 3. REST `GET /events/falls`

Response moi item co them `latitude`, `longitude`:

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
      "latitude": 21.0285, // <-- MOI (float | null)
      "longitude": 105.8542 // <-- MOI (float | null)
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 20,
  "total_pages": 3
}
```

---

## Luu y

- GPS lay qua IP → do chinh xac ~1-5 km (thanh pho), khong phai GPS thiet bi.
- Ca 3 kenh (FCM, WebSocket, REST) deu co the tra ve `null` neu khong co GPS.
- Chi co `fall_alert` moi co GPS, cac event khac (`state_update`, `patient_pose`, ...) khong bi anh huong.
