# Fall Detection Backend — Tóm tắt & Đánh giá Code

## 1. Tổng quan

Backend hệ thống phát hiện té ngã thời gian thực cho người cao tuổi, phục vụ 3 client:

| Client | Vai trò |
|---|---|
| **Desktop** (Raspberry Pi / PC) | Gửi sự kiện té ngã, tư thế, heartbeat qua HTTP POST |
| **Mobile** (Android) | Nhận thông báo FCM, xem lịch sử qua REST, stream trạng thái qua WebSocket |
| **Admin** (web/app) | Quản lý user, xem thống kê, phản hồi báo cáo |

**Stack:** FastAPI + SQLAlchemy async + PostgreSQL + Firebase Auth + FCM + ADB (SMS/call)

---

## 2. Cấu trúc project

```
app/
├── main.py                    # FastAPI app, lifespan, router mount
├── schemas.py                 # Toàn bộ Pydantic schemas (in + out + WS)
├── db/
│   ├── database.py            # Engine, session, init_db (tích hợp migration thủ công)
│   └── models.py              # 11 SQLAlchemy models
├── api/
│   ├── auth.py                # Đăng ký/login/OTP/profile
│   ├── events.py              # Ingest fall/pose/heartbeat + query history
│   ├── admin.py               # Quản trị user, thống kê, báo cáo
│   ├── devices.py             # Device token (FCM)
│   ├── family_members.py      # Thành viên gia đình + đăng ký khuôn mặt
│   ├── face_logs.py           # Log nhận diện khuôn mặt
│   ├── contacts.py            # Liên hệ khẩn cấp
│   ├── reports.py             # Báo cáo hỗ trợ (user side)
│   ├── config.py              # Threshold & feature config per camera
│   ├── dashboard.py           # Dashboard nhanh
│   └── websocket.py           # WS /ws/mobile + /ws/desktop
└── services/
    ├── auth_service.py        # upsert_user (Firebase → local DB)
    ├── dependencies.py        # get_current_user, get_current_admin
    ├── fcm.py                 # Firebase Cloud Messaging (fall/pose/reply/admin)
    ├── firebase_service.py    # Firebase Admin SDK wrappers
    ├── alert_service.py       # ADB: SMS + gọi điện qua Android USB
    ├── email_service.py       # OTP email (aiosmtplib)
    └── websocket_manager.py   # WebSocketManager singleton + live-state cache
```

---

## 3. Luồng nghiệp vụ chính

```
Desktop ──POST /events/fall──► backend ──► lưu DB
                                       ──► broadcast WS (fall_alert)
                                       ──► FCM push (tất cả device token)
                                       ──► ADB SMS + gọi điện (background task)

Desktop ──POST /events/heartbeat──► manager.update_live_state()
                                ──► broadcast WS (state_update)

Mobile  ──GET /events/live──► lấy snapshot từ memory (không query DB)
Mobile  ──WS /ws/mobile────► nhận real-time stream

Desktop ──WS /ws/desktop───► nhận lệnh đăng ký khuôn mặt từ backend
```

---

## 4. Database — 11 bảng

| Bảng | Mục đích |
|---|---|
| `users` | Tài khoản (Firebase uid + local id) |
| `fall_events` | Sự kiện té ngã |
| `pose_events` | Thay đổi tư thế (có person_id nếu nhận diện được) |
| `person_detected_events` | Phát hiện người (không định danh) |
| `threshold_configs` | Ngưỡng phát hiện per camera |
| `feature_configs` | Feature flags per camera |
| `device_tokens` | FCM token của thiết bị mobile |
| `family_members` | Thành viên gia đình / bệnh nhân (có face_image_url) |
| `emergency_contacts` | Liên hệ khẩn cấp |
| `face_recognition_logs` | Lịch sử nhận diện khuôn mặt |
| `otp_codes` | OTP xác thực email / reset mật khẩu |
| `support_reports` | Báo cáo lỗi / yêu cầu hỗ trợ |

---

## 5. Đánh giá độ clean

### Điểm tốt

- **Phân tầng rõ ràng:** `api/` chỉ xử lý HTTP, `services/` chứa logic, `db/` tách biệt hoàn toàn. Không có DB query thô nào nằm trong services tầng nghiệp vụ.
- **Schema nhất quán:** Toàn bộ Pydantic schema tập trung một file `schemas.py`, enum dùng `str, Enum` để serialize đúng. Generic `PaginatedResponse[T]` tái sử dụng tốt.
- **Async đúng:** Dùng `asyncpg` + `async_sessionmaker`, FCM và ADB blocking được wrap qua `run_in_executor`. Background task dùng `asyncio.create_task` với set tracking tránh bị GC.
- **Security cơ bản đủ:** `forgot_password` không lộ email tồn tại, OTP có TTL + invalidate cũ, admin check tự thao tác chính mình.
- **WebSocket manager sạch:** Lock đúng chỗ, dead connection tự cleanup, gửi snapshot ngay khi kết nối.
- **FCM tự dọn invalid token:** Sau mỗi lần gửi, token lỗi bị xóa khỏi DB ngay.

### Vấn đề cần lưu ý

| Vấn đề | Mức độ | Chi tiết |
|---|---|---|
| **Migration thủ công trong `init_db`** | Trung bình | `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` viết thẳng trong code, không có Alembic. Khi schema phát triển thêm sẽ khó kiểm soát. |
| **Schema lặp giữa `admin.py` và `schemas.py`** | Nhỏ | `AdminUserResponse`, `FamilyMemberItem`, `FallItem`... định nghĩa trong `admin.py` thay vì `schemas.py` trung tâm. Tương tự trong `auth.py` (`UserResponse`, `LoginResponse`). |
| **`CORS allow_origins=["*"]`** | Trung bình | Chấp nhận được khi phát triển, nhưng cần khóa lại trước khi deploy production. |
| **`send_fall_notification` gửi đến tất cả token** | Nhỏ | `select(DeviceTokenDB)` không lọc theo user, mọi device đều nhận — có thể là thiết kế cố ý nhưng nên ghi chú rõ. |
| **ADB blocking `time.sleep` trong async context** | Nhỏ | `make_call_with_audio` có `time.sleep` nhưng đã được bọc đúng bằng `run_in_executor` → an toàn, nhưng thread pool bị chiếm lâu khi gọi điện. |
| **`database.py` hardcode `ssl="require"`** | Nhỏ | Không hoạt động với SQLite local hoặc dev DB không có SSL. Cần đọc từ env. |
| **Không có test** | Cao | Không có file test nào trong project. |
| **`_VN_TZ` định nghĩa nhiều chỗ** | Nhỏ | `events.py` và `admin.py` đều khai báo `_VN_TZ = timezone(timedelta(hours=7))` riêng. |

### Tổng kết điểm

| Tiêu chí | Điểm |
|---|---|
| Cấu trúc & phân tầng | 8/10 |
| Schema & type safety | 8/10 |
| Async correctness | 9/10 |
| Bảo mật | 6/10 |
| Khả năng maintain | 6/10 |
| Test coverage | 1/10 |
| **Tổng** | **~6.5/10** |

Project có nền tảng tốt cho một đồ án, code async đúng kỹ thuật và luồng nghiệp vụ rõ ràng. Điểm yếu chính là thiếu test, migration chưa được tổ chức, và một số schema bị phân tán ra nhiều file thay vì tập trung.
