# Fall Detection Backend — API Reference

**Base URL:** `https://<your-domain>`  
**Auth:** Header `Authorization: Bearer <id_token>` (Firebase JWT)

---

## Mobile App API

### Auth

#### Đăng ký
```
POST /auth/register
```
```json
{ "email": "user@example.com", "password": "123456", "display_name": "Nguyễn A" }
```
→ `201` UserResponse

---

#### Đăng nhập email/password
```
POST /auth/login
```
```json
{ "email": "user@example.com", "password": "123456" }
```
→ `200`
```json
{
  "id_token": "eyJ...",
  "refresh_token": "AMf...",
  "expires_in": "3600",
  "user": { "id": 1, "email": "...", "display_name": "...", "email_verified": false }
}
```

---

#### Đăng nhập phone (sau khi Firebase OTP xác minh phía client)
```
POST /auth/phone/login
```
```json
{ "id_token": "eyJ..." }
```
→ `200` LoginResponse

---

#### Đăng xuất
```
POST /auth/logout
Authorization: Bearer <id_token>
```
→ `200 { "ok": true, "message": "Đã đăng xuất thành công" }`

> Thu hồi tất cả refresh tokens. Client cần xóa token lưu cục bộ.

---

#### Gửi OTP xác thực email (sau đăng ký)
```
POST /auth/send-otp
```
```json
{ "email": "user@example.com", "purpose": "email_verification" }
```
→ `200 { "ok": true, "message": "OTP đã được gửi đến email của bạn" }`

---

#### Xác thực email bằng OTP
```
POST /auth/verify-email
```
```json
{ "email": "user@example.com", "code": "483920" }
```
→ `200 { "ok": true, "message": "Email đã được xác thực thành công" }`

> OTP có hiệu lực 10 phút, dùng 1 lần.

---

#### Quên mật khẩu — gửi OTP
```
POST /auth/forgot-password
```
```json
{ "email": "user@example.com" }
```
→ `200 { "ok": true, "message": "Nếu email tồn tại, OTP đã được gửi" }`

---

#### Đặt lại mật khẩu bằng OTP
```
POST /auth/reset-password
```
```json
{ "email": "user@example.com", "code": "374821", "new_password": "newpass123" }
```
→ `200 { "ok": true, "message": "Mật khẩu đã được đặt lại thành công" }`

---

#### Đổi mật khẩu (đã đăng nhập)
```
POST /auth/change-password
Authorization: Bearer <id_token>
```
```json
{ "new_password": "newpass123" }
```
→ `200 { "ok": true, "message": "Đổi mật khẩu thành công" }`

---

#### Cập nhật hồ sơ cá nhân
```
PATCH /auth/profile
Authorization: Bearer <id_token>
```
```json
{ "display_name": "Nguyễn B", "avatar_url": "https://..." }
```
→ `200` UserResponse

---

#### Xem thông tin bản thân
```
GET /auth/me
Authorization: Bearer <id_token>
```
→ `200` UserResponse

```json
{
  "id": 1,
  "firebase_uid": "abc123",
  "email": "user@example.com",
  "phone_number": null,
  "display_name": "Nguyễn A",
  "avatar_url": null,
  "email_verified": true,
  "is_active": true
}
```

---

### Thiết bị & Thông báo

#### Đăng ký FCM token
```
POST /devices/register
Authorization: Bearer <id_token>
```
```json
{ "token": "fcm-device-token", "platform": "android" }
```
→ `200 { "ok": true }`

> Gọi sau khi đăng nhập để liên kết FCM token với tài khoản. Backend dùng token này để gửi thông báo đúng người.

#### Hủy FCM token
```
DELETE /devices/unregister
Authorization: Bearer <id_token>
```
```json
{ "token": "fcm-device-token" }
```
→ `200 { "ok": true }`

> Gọi khi đăng xuất để tránh nhận thông báo sau khi thoát.

---

### Thành viên gia đình

#### Danh sách thành viên
```
GET /family-members
Authorization: Bearer <id_token>
```
→ `200 [ FamilyMemberResponse, ... ]`

#### Thêm thành viên
```
POST /family-members
Authorization: Bearer <id_token>
```
```json
{
  "name": "Nguyễn Văn A",
  "phone_number": "0901234567",
  "email": "a@example.com",
  "relationship": "Cha",
  "notify_on_fall": true,
  "is_patient": true,
  "camera_id": "cam_0"
}
```
→ `201` FamilyMemberResponse

#### Cập nhật thành viên
```
PATCH /family-members/{id}
Authorization: Bearer <id_token>
```
→ `200` FamilyMemberResponse

#### Xóa thành viên
```
DELETE /family-members/{id}
Authorization: Bearer <id_token>
```
→ `200 { "ok": true }`

---

### Liên hệ khẩn cấp

#### Danh sách liên hệ
```
GET /api/contacts
Authorization: Bearer <id_token>
```
→ `200 [ EmergencyContactResponse, ... ]`

#### Thêm liên hệ (tối đa 5)
```
POST /api/contacts
Authorization: Bearer <id_token>
```
```json
{ "name": "Nguyễn B", "phone": "0907654321", "relation": "Con gái" }
```
→ `201` EmergencyContactResponse

#### Cập nhật liên hệ
```
PATCH /api/contacts/{id}
Authorization: Bearer <id_token>
```

#### Xóa liên hệ
```
DELETE /api/contacts/{id}
Authorization: Bearer <id_token>
```

---

### Sự kiện & Live state

#### Lịch sử té ngã (phân trang)
```
GET /events/falls?page=1&page_size=20&camera_id=cam_0
Authorization: Bearer <id_token>
```
→ `200` PaginatedResponse

```json
{
  "ok": true,
  "items": [
    {
      "id": 1,
      "camera_id": "cam_0",
      "timestamp": 1716300000.0,
      "state_before": "STANDING",
      "velocity": 120.5,
      "max_velocity": 150.2,
      "body_angle": 75.3,
      "confidence": 0.92,
      "acknowledged": false,
      "clip_url": null,
      "datetime_vn": "2025-05-21 15:00:00"
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 20,
  "total_pages": 3
}
```

#### Trạng thái live (REST fallback)
```
GET /events/live
```
→ `200 [ LiveCameraState, ... ]`

---

### Báo cáo & Hỗ trợ

#### Gửi báo cáo mới
```
POST /reports
Authorization: Bearer <id_token>
```
```json
{
  "category": "bug",
  "title": "Ứng dụng bị crash khi mở tab lịch sử",
  "description": "Khi nhấn vào tab lịch sử, ứng dụng tự đóng sau 2 giây..."
}
```

| Field | Kiểu | Bắt buộc | Giá trị |
|-------|------|----------|---------|
| `category` | string | ✅ | `bug` \| `feature` \| `question` \| `other` |
| `title` | string | ✅ | 5–256 ký tự |
| `description` | string | ✅ | 10–2000 ký tự |

**Response `201`:**
```json
{
  "id": 1,
  "category": "bug",
  "title": "Ứng dụng bị crash khi mở tab lịch sử",
  "description": "Khi nhấn vào tab lịch sử, ứng dụng tự đóng sau 2 giây...",
  "status": "pending",
  "admin_reply": null,
  "replied_at": null,
  "created_at": 1748000000.0,
  "updated_at": 1748000000.0,
  "datetime_vn": "08:00 23/05/2026"
}
```

---

#### Danh sách báo cáo của tôi
```
GET /reports
GET /reports?status=pending&page=1&page_size=20
Authorization: Bearer <id_token>
```

**Query params (tùy chọn):**

| Param | Kiểu | Mô tả |
|-------|------|-------|
| `status` | string | Lọc: `pending` \| `in_progress` \| `resolved` \| `closed` |
| `page` | int | Mặc định: 1 |
| `page_size` | int | Mặc định: 20, tối đa 50 |

**Response `200`:**
```json
{
  "ok": true,
  "items": [ ],
  "total": 5,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

---

#### Chi tiết một báo cáo
```
GET /reports/{id}
Authorization: Bearer <id_token>
```
→ `200` ReportResponse | `404` nếu không tồn tại hoặc không phải của mình

---

**Trạng thái vòng đời:**
```
pending → in_progress → resolved
                     ↘ closed
```

| Status | Ý nghĩa |
|--------|---------|
| `pending` | Mới gửi, chờ admin xem |
| `in_progress` | Admin đang xử lý / đã phản hồi |
| `resolved` | Đã giải quyết |
| `closed` | Đã đóng |

---

### WebSocket — Real-time

```
WS /ws/live
```

Sau khi kết nối, server gửi ngay snapshot trạng thái hiện tại, rồi broadcast khi có sự kiện mới.

| type | Mô tả |
|------|-------|
| `state_update` | Heartbeat mới — trạng thái pose hiện tại |
| `fall_alert` | Phát hiện té ngã |

**fall_alert:**
```json
{
  "type": "fall_alert",
  "camera_id": "cam_0",
  "timestamp": 1716300000.0,
  "velocity": 130.5,
  "body_angle": 78.2,
  "confidence": 0.95,
  "clip_url": null
}
```

**state_update:**
```json
{
  "type": "state_update",
  "camera_id": "cam_0",
  "state": "STANDING",
  "velocity": 0.0,
  "body_angle": 12.3,
  "fps": 29.8,
  "timestamp": 1716300010.0
}
```

---

## Web Admin API

> Tất cả endpoint `/admin/*` yêu cầu `Authorization: Bearer <id_token>` của tài khoản có `role = "admin"`.  
> Trả về `403` nếu user thường cố gọi.

---

### Đăng nhập Admin

Admin dùng chung endpoint đăng nhập của mobile. Sau khi đăng nhập, kiểm tra `role == "admin"` trong response để xác nhận quyền.

```
POST /auth/login
Content-Type: application/json
```
**Body:**
```json
{
  "email": "admin@example.com",
  "password": "yourpassword"
}
```
**Response `200`:**
```json
{
  "id_token": "eyJhbGci...",
  "refresh_token": "AMf...",
  "expires_in": "3600",
  "user": {
    "id": 1,
    "firebase_uid": "abc123",
    "email": "admin@example.com",
    "phone_number": null,
    "display_name": "Admin",
    "avatar_url": null,
    "email_verified": true,
    "role": "admin",
    "is_active": true
  }
}
```

> Nếu `role != "admin"` → frontend từ chối cho vào trang admin.  
> Token hết hạn sau 3600 giây, cần refresh hoặc đăng nhập lại.

---

### Xác nhận quyền Admin

```
GET /admin/me
Authorization: Bearer <admin_token>
```
**Response `200`:**
```json
{
  "id": 1,
  "firebase_uid": "abc123",
  "email": "admin@example.com",
  "phone_number": null,
  "display_name": "Admin",
  "avatar_url": null,
  "email_verified": true,
  "role": "admin",
  "is_active": true,
  "created_at": 1716300000.0
}
```

> Gọi endpoint này khi app khởi động để kiểm tra token còn hợp lệ và đúng quyền admin.

---

### Quản lý người dùng

#### Danh sách tất cả user

```
GET /admin/users
Authorization: Bearer <admin_token>
```

**Query params (tùy chọn):**

| Param | Kiểu | Mô tả |
|---|---|---|
| `page` | int | Trang, mặc định `1` |
| `page_size` | int | Số item/trang, mặc định `20`, tối đa `100` |
| `role` | string | Lọc theo role: `user` hoặc `admin` |
| `email` | string | Tìm kiếm email (contains, không phân biệt hoa thường) |
| `is_active` | bool | Lọc theo trạng thái: `true` hoặc `false` |

**Ví dụ:** `GET /admin/users?page=1&page_size=20&role=user&email=nguyen&is_active=true`

**Response `200`:**
```json
{
  "ok": true,
  "items": [
    {
      "id": 1,
      "firebase_uid": "abc123",
      "email": "user@example.com",
      "phone_number": null,
      "display_name": "Nguyễn A",
      "avatar_url": null,
      "email_verified": true,
      "role": "user",
      "is_active": true,
      "created_at": 1716300000.0
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 20,
  "total_pages": 3
}
```

---

#### Xem chi tiết một user

```
GET /admin/users/{user_id}
Authorization: Bearer <admin_token>
```

**Response `200`:**
```json
{
  "id": 5,
  "firebase_uid": "xyz789",
  "email": "user@example.com",
  "phone_number": "0901234567",
  "display_name": "Nguyễn B",
  "avatar_url": "https://...",
  "email_verified": true,
  "role": "user",
  "is_active": true,
  "created_at": 1716300000.0
}
```

---

#### Thay đổi role người dùng

```
PATCH /admin/users/{user_id}/role
Authorization: Bearer <admin_token>
Content-Type: application/json
```
**Body:**
```json
{ "role": "admin" }
```
> Giá trị hợp lệ: `"user"` hoặc `"admin"`.  
> Không thể tự thay đổi role của chính mình → `400`.

**Response `200`:** AdminUserResponse (xem trên)

---

#### Kích hoạt tài khoản

```
PATCH /admin/users/{user_id}/activate
Authorization: Bearer <admin_token>
```
**Response `200`:** AdminUserResponse

---

#### Vô hiệu hóa tài khoản

```
PATCH /admin/users/{user_id}/deactivate
Authorization: Bearer <admin_token>
```
**Response `200`:** AdminUserResponse

> User bị deactivate sẽ nhận `403` khi gọi bất kỳ API nào.

---

#### Xóa người dùng

```
DELETE /admin/users/{user_id}
Authorization: Bearer <admin_token>
```
**Response `200`:**
```json
{ "ok": true, "message": "Đã xóa người dùng #5" }
```

> Xóa cả bản ghi PostgreSQL lẫn tài khoản Firebase. Không thể hoàn tác.

---

### Quản lý hồ sơ người dùng

#### Xem hồ sơ đầy đủ

```
GET /admin/users/{user_id}/profile
Authorization: Bearer <admin_token>
```

**Response `200`:**
```json
{
  "user": {
    "id": 5,
    "firebase_uid": "xyz789",
    "email": "user@example.com",
    "phone_number": "0901234567",
    "display_name": "Nguyễn B",
    "avatar_url": null,
    "email_verified": true,
    "role": "user",
    "is_active": true,
    "created_at": 1716300000.0
  },
  "family_members": [
    {
      "id": 1,
      "name": "Nguyễn Văn C",
      "phone_number": "0912345678",
      "email": null,
      "relationship": "Cha",
      "notify_on_fall": true,
      "is_patient": true,
      "camera_id": "cam_0",
      "created_at": 1716300100.0
    }
  ],
  "emergency_contacts": [
    {
      "id": 2,
      "name": "Trần Thị D",
      "phone": "0987654321",
      "relation": "Con gái",
      "is_active": true,
      "created_at": 1716300200.0
    }
  ]
}
```

---

#### Cập nhật thông tin người dùng (admin sửa)

```
PATCH /admin/users/{user_id}/profile
Authorization: Bearer <admin_token>
Content-Type: application/json
```
**Body (tất cả optional):**
```json
{
  "display_name": "Nguyễn B (đã sửa)",
  "avatar_url": "https://example.com/avatar.jpg"
}
```

**Response `200`:** AdminUserResponse

---

#### Lịch sử té ngã của người dùng

```
GET /admin/users/{user_id}/falls
Authorization: Bearer <admin_token>
```

**Query params (tùy chọn):**

| Param | Kiểu | Mô tả |
|---|---|---|
| `page` | int | Trang, mặc định `1` |
| `page_size` | int | Số item/trang, mặc định `20`, tối đa `100` |

> Trả về fall events của camera_id thuộc bệnh nhân (`is_patient=true`) của user này.  
> Nếu user chưa thiết lập bệnh nhân → `items: []`.

**Response `200`:**
```json
{
  "ok": true,
  "items": [
    {
      "id": 10,
      "camera_id": "cam_0",
      "timestamp": 1716300000.0,
      "datetime_vn": "15:30 21/05/2025",
      "state_before": "STANDING",
      "velocity": 110.5,
      "max_velocity": 145.2,
      "body_angle": 78.3,
      "confidence": 0.93,
      "acknowledged": false,
      "clip_url": null
    }
  ],
  "total": 7,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

---

### Thống kê

#### Tổng quan hệ thống

```
GET /admin/stats/overview
Authorization: Bearer <admin_token>
```

**Response `200`:**
```json
{
  "total_users": 120,
  "active_users": 115,
  "total_falls_today": 3,
  "total_falls_this_month": 47,
  "total_falls_all_time": 312
}
```

> `today` và `this_month` tính theo múi giờ Việt Nam (UTC+7).

---

#### Danh sách fall có lọc

```
GET /admin/stats/falls
Authorization: Bearer <admin_token>
```

**Query params (tùy chọn):**

| Param | Kiểu | Mô tả |
|---|---|---|
| `from_ts` | float | Từ thời điểm (unix timestamp) |
| `to_ts` | float | Đến thời điểm (unix timestamp) |
| `camera_id` | string | Lọc theo camera |
| `page` | int | Trang, mặc định `1` |
| `page_size` | int | Số item/trang, mặc định `20`, tối đa `100` |

**Ví dụ:** `GET /admin/stats/falls?from_ts=1716300000&to_ts=1716386400&camera_id=cam_0`

**Response `200`:** (giống `GET /admin/users/{id}/falls`)

---

#### Biểu đồ fall theo thời gian

```
GET /admin/stats/falls/timeline
Authorization: Bearer <admin_token>
```

**Query params (tùy chọn):**

| Param | Kiểu | Mô tả |
|---|---|---|
| `from_ts` | float | Từ thời điểm (unix timestamp) |
| `to_ts` | float | Đến thời điểm (unix timestamp) |
| `group_by` | string | Nhóm theo: `day` (mặc định) \| `week` \| `month` |

**Response `200` — group_by=day:**
```json
{
  "group_by": "day",
  "labels": ["19/05/2025", "20/05/2025", "21/05/2025"],
  "counts": [2, 0, 5]
}
```

**Response `200` — group_by=week:**
```json
{
  "group_by": "week",
  "labels": ["W20/2025", "W21/2025"],
  "counts": [8, 14]
}
```

**Response `200` — group_by=month:**
```json
{
  "group_by": "month",
  "labels": ["03/2025", "04/2025", "05/2025"],
  "counts": [30, 52, 47]
}
```

> Chỉ trả về các mốc thời gian có ít nhất 1 sự kiện, đã sắp xếp tăng dần theo thời gian.

---

### Quản lý báo cáo & Hỗ trợ

#### Danh sách tất cả báo cáo
```
GET /admin/reports
Authorization: Bearer <admin_token>
```

**Query params (tùy chọn):**

| Param | Kiểu | Mô tả |
|-------|------|-------|
| `status` | string | Lọc: `pending` \| `in_progress` \| `resolved` \| `closed` |
| `category` | string | Lọc: `bug` \| `feature` \| `question` \| `other` |
| `user_id` | int | Lọc theo user cụ thể |
| `page` | int | Mặc định: 1 |
| `page_size` | int | Mặc định: 20, tối đa 100 |

**Response `200`:**
```json
{
  "ok": true,
  "items": [
    {
      "id": 1,
      "user_id": 5,
      "user_email": "nguyenvana@gmail.com",
      "user_name": "Nguyễn Văn A",
      "category": "bug",
      "title": "Ứng dụng bị crash khi mở tab lịch sử",
      "description": "Khi nhấn vào tab lịch sử...",
      "status": "pending",
      "admin_reply": null,
      "replied_by": null,
      "replied_at": null,
      "created_at": 1748000000.0,
      "updated_at": 1748000000.0,
      "datetime_vn": "08:00 23/05/2026"
    }
  ],
  "total": 10,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

---

#### Chi tiết một báo cáo
```
GET /admin/reports/{id}
Authorization: Bearer <admin_token>
```
→ `200` AdminReportResponse (cùng cấu trúc một item ở trên) | `404`

---

#### Cập nhật trạng thái báo cáo
```
PATCH /admin/reports/{id}/status
Authorization: Bearer <admin_token>
```
```json
{ "status": "resolved" }
```
→ `200` AdminReportResponse

---

#### Phản hồi báo cáo
```
POST /admin/reports/{id}/reply
Authorization: Bearer <admin_token>
```
```json
{ "reply": "Chúng tôi đã ghi nhận lỗi, sẽ fix trong phiên bản tiếp theo." }
```
→ `200` AdminReportResponse

> Sau khi reply thành công, backend tự động gửi FCM đến thiết bị của user với:
> ```json
> {
>   "type": "report_reply",
>   "report_id": "1",
>   "title": "Ứng dụng bị crash khi mở tab lịch sử",
>   "reply": "Chúng tôi đã ghi nhận lỗi..."
> }
> ```
> Nếu báo cáo đang `pending` → tự động chuyển sang `in_progress`.

---

### Gửi thông báo đến người dùng

```
POST /admin/notifications/send
Authorization: Bearer <admin_token>
```
```json
{
  "title": "Thông báo bảo trì",
  "body": "Hệ thống sẽ bảo trì lúc 2:00 AM ngày 24/05.",
  "user_id": null
}
```

| Field | Kiểu | Mô tả |
|-------|------|-------|
| `title` | string | Tiêu đề thông báo, tối đa 100 ký tự |
| `body` | string | Nội dung thông báo, tối đa 500 ký tự |
| `user_id` | int \| null | ID user cụ thể. `null` = gửi tất cả |

**Response `200`:**
```json
{ "ok": true, "sent": 42, "failed": 1 }
```

> Mobile nhận FCM với `data.type == "admin_notification"` để hiển thị hoặc điều hướng.

---

### Cấu hình hệ thống (Admin)

> Admin quản lý cấu hình hệ thống và theo dõi tổng quan.

### Cấu hình ngưỡng phát hiện

#### Lấy cấu hình
```
GET /config/thresholds?camera_id=cam_0
```
→ `200` ThresholdConfig

```json
{
  "body_angle_lying": 65.0,
  "body_angle_sitting": 45.0,
  "aspect_ratio_lying": 0.55,
  "fall_velocity_threshold": 80.0,
  "fall_confirm_frames": 5,
  "fall_history_window": 30,
  "sleep_confirm_frames": 60,
  "walk_velocity_threshold": 20.0,
  "walk_knee_lift_threshold": 0.08,
  "walk_alternating_window": 15,
  "camera_index": 0,
  "flip_horizontal": true,
  "model_complexity": 1
}
```

#### Cập nhật một phần
```
PATCH /config/thresholds
```
```json
{ "fall_velocity_threshold": 90.0, "fall_confirm_frames": 7 }
```
→ `200` ThresholdConfig

#### Cập nhật toàn bộ
```
PUT /config/thresholds
```
→ `200` ThresholdConfig

#### Reset về mặc định
```
POST /config/thresholds/reset?camera_id=cam_0
```
→ `200` ThresholdConfig

---

### Cấu hình tính năng

#### Lấy cấu hình
```
GET /config/features?camera_id=cam_0
```
→ `200` FeatureConfig

```json
{
  "enable_face_recognition": true,
  "enable_sound_detection": false,
  "sleep_as_fall": false,
  "sound_listen_seconds": 3.0
}
```

#### Cập nhật tính năng
```
PATCH /config/features
```
```json
{ "sleep_as_fall": true }
```
→ `200` FeatureConfig

---

### Dashboard

```
GET /dashboard/
```
→ HTML — thống kê tổng quan, event log, cấu hình hệ thống

---

### Health Check

```
GET /health
```
→ `200 { "status": "ok", "version": "2.1.0", "db": "postgresql" }`

---

## Luồng sử dụng điển hình

### Đăng ký & xác thực email
```
1. POST /auth/register        → tạo tài khoản (email_verified = false)
2. POST /auth/send-otp        → gửi OTP (purpose: "email_verification")
3. POST /auth/verify-email    → nhập OTP → email_verified = true
4. POST /auth/login           → đăng nhập, lấy id_token
```

### Quên mật khẩu
```
1. POST /auth/forgot-password → gửi OTP reset password
2. POST /auth/reset-password  → nhập OTP + mật khẩu mới
3. POST /auth/login           → đăng nhập lại
```

### Mobile app theo dõi bệnh nhân
```
1. POST /auth/login           → lấy id_token
2. POST /devices/register     → đăng ký FCM token
3. GET  /family-members       → xem danh sách, thiết lập is_patient = true
4. WS   /ws/live              → nhận cảnh báo fall_alert real-time
5. GET  /events/falls         → xem lịch sử té ngã
```

### Web Admin

```
1.  POST  /auth/login                             → đăng nhập, kiểm tra role == "admin"
2.  GET   /admin/me                               → xác nhận quyền admin khi app khởi động
3.  GET   /admin/stats/overview                   → hiển thị dashboard tổng quan
4.  GET   /admin/stats/falls/timeline?group_by=day → vẽ biểu đồ fall
5.  GET   /admin/users?page=1&page_size=20        → danh sách người dùng
6.  GET   /admin/users/{id}/profile               → xem hồ sơ đầy đủ của user
7.  GET   /admin/users/{id}/falls                 → xem lịch sử fall của user
8.  PATCH /admin/users/{id}/role                  → nâng/hạ quyền
9.  PATCH /admin/users/{id}/deactivate            → khóa tài khoản
10. DELETE /admin/users/{id}                      → xóa tài khoản
11. GET   /admin/reports?status=pending           → xem báo cáo chờ xử lý
12. POST  /admin/reports/{id}/reply               → phản hồi báo cáo → FCM tự gửi
13. PATCH /admin/reports/{id}/status              → cập nhật trạng thái báo cáo
14. POST  /admin/notifications/send               → gửi thông báo đến user hoặc tất cả
```

### Mobile app gửi báo cáo
```
1. POST /auth/login           → lấy id_token
2. POST /reports              → gửi báo cáo mới
3. GET  /reports              → xem danh sách báo cáo của mình
4. GET  /reports/{id}         → xem chi tiết + phản hồi của admin
   (FCM type: "report_reply"  → điều hướng vào màn hình chi tiết báo cáo)
```

---

## FCM Notification Types

Mobile app bắt `data.type` để xử lý từng loại thông báo:

| `data.type` | Khi nào | Điều hướng gợi ý |
|-------------|---------|-----------------|
| `fall_alert` | Desktop phát hiện té ngã | Màn hình chi tiết fall |
| `pose_update` | Bệnh nhân thay đổi tư thế | Màn hình live monitor |
| `report_reply` | Admin phản hồi báo cáo | Màn hình chi tiết báo cáo (`report_id`) |
| `admin_notification` | Admin gửi thông báo chung | Hiển thị popup / in-app notification |

---

## Mã lỗi phổ biến

| Code | Ý nghĩa |
|------|---------|
| 400 | Dữ liệu không hợp lệ (OTP sai, mật khẩu ngắn, ...) |
| 401 | Chưa xác thực hoặc token hết hạn / đã bị thu hồi |
| 403 | Tài khoản bị vô hiệu hoá hoặc không đủ quyền |
| 404 | Tài nguyên không tồn tại |
| 409 | Conflict (số điện thoại đã đăng ký, ...) |
| 503 | FCM chưa khởi tạo |
| 500 | Lỗi server (email không gửi được, ...) |
