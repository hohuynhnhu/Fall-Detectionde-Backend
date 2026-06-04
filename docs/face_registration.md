# Tính năng đăng ký khuôn mặt

## Tổng quan flow

```
Mobile ──upload ảnh──► Cloudinary ──trả URL──► Mobile
Mobile ──POST /family-members/register──► Backend
Backend ──lưu DB + broadcast WS──► Desktop
Desktop ──download ảnh từ URL──► dlib extract encoding
```

---

## Database — FamilyMemberDB (cột mới)

| Cột | Type | Mô tả |
|---|---|---|
| `person_id` | VARCHAR(36) | UUID do backend tạo, định danh khuôn mặt |
| `role` | VARCHAR(16) | `"family"` hoặc `"caregiver"` |
| `face_image_url` | VARCHAR(512) | URL ảnh từ Cloudinary |

---

## API Mobile

### Đăng ký khuôn mặt

```
POST /family-members/register
Authorization: Bearer <id_token>
Content-Type: application/json
```

**Request:**
```json
{
  "name":           "Nguyễn Văn A",
  "role":           "family",
  "is_patient":     true,
  "face_image_url": "https://res.cloudinary.com/demo/image/upload/abc123.jpg"
}
```

| Field | Type | Bắt buộc | Mô tả |
|---|---|---|---|
| `name` | string | ✓ | Tên thành viên |
| `role` | `"family"` \| `"caregiver"` | ✓ | Vai trò |
| `is_patient` | bool | ✓ | `true` = người được theo dõi bởi camera |
| `face_image_url` | string | ✓ | URL ảnh đã upload lên Cloudinary |

**Response 201:**
```json
{
  "person_id":      "550e8400-e29b-41d4-a716-446655440000",
  "name":           "Nguyễn Văn A",
  "role":           "family",
  "is_patient":     true,
  "face_image_url": "https://res.cloudinary.com/demo/image/upload/abc123.jpg"
}
```

---

### Xem danh sách thành viên

```
GET /family-members
Authorization: Bearer <id_token>
```

**Response:**
```json
[
  {
    "id":             1,
    "person_id":      "550e8400-e29b-41d4-a716-446655440000",
    "name":           "Nguyễn Văn A",
    "role":           "family",
    "is_patient":     true,
    "notify_on_fall": true,
    "camera_id":      "cam_0",
    "face_image_url": "https://res.cloudinary.com/demo/image/upload/abc123.jpg",
    "created_at":     1748123456.0
  }
]
```

---

### Cập nhật thành viên

```
PATCH /family-members/{id}
Authorization: Bearer <id_token>
Content-Type: application/json
```

```json
{
  "is_patient":     true,
  "notify_on_fall": false
}
```

---

### Xóa thành viên

```
DELETE /family-members/{id}
Authorization: Bearer <id_token>
```

Response: `204 No Content`

> Khi xóa, backend tự động broadcast `remove_member` qua WebSocket tới desktop.

---

## API Desktop

### Lấy danh sách khi khởi động

```
GET /family-members/all
```

*(Không cần auth)*

Chỉ trả về thành viên đã có `face_image_url`. Desktop dùng danh sách này để download ảnh và extract face encoding.

**Response:**
```json
[
  {
    "id":             1,
    "person_id":      "550e8400-e29b-41d4-a716-446655440000",
    "name":           "Nguyễn Văn A",
    "role":           "family",
    "is_patient":     true,
    "notify_on_fall": true,
    "camera_id":      "cam_0",
    "face_image_url": "https://res.cloudinary.com/demo/image/upload/abc123.jpg",
    "created_at":     1748123456.0
  }
]
```

---

### WebSocket nhận sự kiện real-time

```
WS /ws/desktop
```

*(Không cần auth)*

Desktop kết nối vào đây và lắng nghe 2 loại message:

#### Thành viên mới (`new_member`)

Gửi khi mobile POST `/family-members/register` thành công.

```json
{
  "type":           "new_member",
  "person_id":      "550e8400-e29b-41d4-a716-446655440000",
  "name":           "Nguyễn Văn A",
  "role":           "family",
  "is_patient":     true,
  "face_image_url": "https://res.cloudinary.com/demo/image/upload/abc123.jpg"
}
```

→ Desktop download ảnh từ `face_image_url` → dlib extract encoding → thêm vào dict `{ person_id: encoding }`

---

#### Thành viên bị xóa (`remove_member`)

Gửi khi mobile DELETE `/family-members/{id}` thành công.

```json
{
  "type":      "remove_member",
  "person_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

→ Desktop xóa encoding của `person_id` khỏi dict

---

## Flow xử lý ở Desktop

```python
# 1. Khởi động: load danh sách từ backend
members = GET /family-members/all
for member in members:
    img = download(member["face_image_url"])
    encoding = dlib.extract(img)
    face_db[member["person_id"]] = {
        "encoding": encoding,
        "name":     member["name"],
        "is_patient": member["is_patient"],
    }

# 2. Kết nối WS và lắng nghe
ws = connect("ws://localhost:8000/ws/desktop")
on_message:
    if msg["type"] == "new_member":
        img = download(msg["face_image_url"])
        encoding = dlib.extract(img)
        face_db[msg["person_id"]] = { ... }

    elif msg["type"] == "remove_member":
        del face_db[msg["person_id"]]

# 3. Mỗi frame camera
for face in detected_faces:
    match = compare(face.encoding, face_db)
    if match:
        print(f"Nhận diện: {match['name']}")
```

---

## Bật/tắt nhận diện khuôn mặt

```
GET  /config/features?camera_id=cam_0   — xem trạng thái
PATCH /config/features?camera_id=cam_0  — thay đổi
```

```json
{ "enable_face_recognition": true }
```

Desktop phải kiểm tra flag này trước khi chạy dlib.

---

## Tóm tắt endpoint

| Endpoint | Auth | Ai dùng | Mục đích |
|---|---|---|---|
| `POST /family-members/register` | Bearer | Mobile | Đăng ký khuôn mặt |
| `GET /family-members` | Bearer | Mobile | Xem danh sách thành viên |
| `PATCH /family-members/{id}` | Bearer | Mobile | Cập nhật is_patient, notify_on_fall |
| `DELETE /family-members/{id}` | Bearer | Mobile | Xóa + broadcast remove_member |
| `GET /family-members/all` | Không | Desktop | Load toàn bộ khi khởi động |
| `WS /ws/desktop` | Không | Desktop | Nhận new_member / remove_member |
| `GET /config/features` | Không | Desktop/Mobile | Xem trạng thái tính năng |
| `PATCH /config/features` | Không | Mobile | Bật/tắt nhận diện khuôn mặt |
