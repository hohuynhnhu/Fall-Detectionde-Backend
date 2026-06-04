# Bug & Vấn đề kỹ thuật: FCM và WebSocket

> Cập nhật: 2026-05-27

---

## FCM (Firebase Cloud Messaging)

### BUG-FCM-01 — Fall/Pose notification gửi cho **tất cả** user, không phân biệt camera

**File:** `app/services/fcm.py:59` (`send_fall_notification`), `app/services/fcm.py:138` (`send_pose_notification`)

```python
# Hiện tại — lấy toàn bộ token trong DB
result = await db.execute(select(DeviceTokenDB))
tokens = [r.token for r in result.scalars().all()]
```

**Hậu quả:** User A đang theo dõi bệnh nhân ở `cam_0`, nhưng User B (không liên quan) cũng nhận thông báo té ngã / thay đổi tư thế của cùng camera đó.

**Cách sửa:** JOIN với `FamilyMemberDB` để chỉ lấy token của user có bệnh nhân gắn với `camera_id` tương ứng:

```python
result = await db.execute(
    select(DeviceTokenDB)
    .join(FamilyMemberDB, FamilyMemberDB.user_id == DeviceTokenDB.user_id)
    .where(FamilyMemberDB.camera_id == camera_id)
    .distinct()
)
```

---

### BUG-FCM-02 — `_dispatch_pose_notifications` lọc đúng bệnh nhân nhưng FCM vẫn broadcast tất cả

**File:** `app/api/events.py:51-64`, `app/services/fcm.py:124`

`_dispatch_pose_notifications` lấy đúng danh sách bệnh nhân theo `camera_id`, nhưng sau đó gọi `send_pose_notification` — hàm này lại gửi cho **tất cả token** trong DB (xem BUG-FCM-01). Logic lọc bệnh nhân ở tầng trên hoàn toàn vô nghĩa.

---

### BUG-FCM-03 — `asyncio.get_event_loop()` deprecated từ Python 3.10+

**File:** `app/services/fcm.py:92`, `169`, `294`

```python
loop = asyncio.get_event_loop()  # deprecated
```

Trong context `async`, phải dùng `asyncio.get_running_loop()`. `get_event_loop()` có thể raise `DeprecationWarning` hoặc tạo event loop mới không liên quan đến loop hiện tại, gây lỗi khó debug.

**Cách sửa:**
```python
loop = asyncio.get_running_loop()
```

---

### BUG-FCM-04 — Endpoint ingest (`/events/fall`, `/events/pose`, `/events/heartbeat`) không có xác thực

**File:** `app/api/events.py:69`, `115`, `139`

Các endpoint nhận dữ liệu từ desktop không có `Depends(get_current_user)`. Bất kỳ ai biết URL đều có thể:
- Inject fall event giả → trigger FCM + WebSocket broadcast toàn bộ user
- Spam heartbeat để làm nhiễu live state cache

**Cách sửa:** Dùng API key cố định hoặc JWT riêng cho desktop app, kiểm tra trong Depends.

---

### BUG-FCM-05 — Background task FCM không được track, bị mất khi shutdown

**File:** `app/api/events.py:134`, `287`

```python
asyncio.create_task(_dispatch_pose_notifications(...))
```

Task tạo ra không được lưu tham chiếu. Nếu server shutdown hoặc event loop bị hủy trước khi task hoàn thành, toàn bộ FCM call bị drop silently — không có log, không có retry.

**Cách sửa:** Lưu task vào một set và xóa khi done:

```python
_background_tasks: set[asyncio.Task] = set()

task = asyncio.create_task(_dispatch_pose_notifications(...))
_background_tasks.add(task)
task.add_done_callback(_background_tasks.discard)
```

---

## WebSocket

### BUG-WS-01 — Không có xác thực trên `/ws/live` và `/ws/desktop`

**File:** `app/api/websocket.py:22`, `36`

Bất kỳ client nào cũng có thể kết nối và nhận toàn bộ fall alerts, state updates, và snapshot trạng thái tất cả camera — không cần token hay auth.

**Cách sửa:** Nhận JWT qua query param khi handshake và verify trước khi `accept()`:

```python
@router.websocket("/live")
async def live_ws(ws: WebSocket, token: str = Query(...)) -> None:
    user = verify_token(token)  # raise nếu invalid
    await manager.connect(ws)
    ...
```

---

### BUG-WS-02 — Broadcast không phân biệt user

**File:** `app/services/websocket_manager.py:56`

`manager.broadcast()` gửi toàn bộ dữ liệu cho tất cả client đang kết nối. Không có cơ chế gửi event chỉ cho user liên quan đến camera cụ thể. Kết hợp với BUG-WS-01, bất kỳ client ẩn danh nào cũng nhận được mọi thông tin.

---

### BUG-WS-03 — Live state cache không có TTL, camera offline vẫn hiển thị trạng thái cũ

**File:** `app/services/websocket_manager.py:80-82`

```python
def update_live_state(self, camera_id: str, state: dict) -> None:
    self._live_states[camera_id] = {**state, "camera_id": camera_id}
```

`_live_states` không bao giờ được xóa. Khi camera mất kết nối, `GET /events/live` vẫn trả về trạng thái cuối cùng ghi nhận — có thể là dữ liệu cũ vài giờ hoặc vài ngày. Mobile app không thể phân biệt camera đang hoạt động hay đã offline.

**Cách sửa:** Lưu kèm `last_seen` timestamp và đánh dấu `online: false` nếu quá ngưỡng (ví dụ 30 giây không có heartbeat).

---

### BUG-WS-04 — `receive_text()` không xử lý binary frame, gây disconnect bất ngờ

**File:** `app/api/websocket.py:27`, `41`

```python
while True:
    await ws.receive_text()  # chỉ nhận text
```

Nếu client gửi binary frame hoặc ping frame không hợp lệ, FastAPI/Starlette sẽ raise exception → `disconnect()` ngay lập tức. Client mobile hoặc browser đôi khi gửi binary ping để giữ kết nối.

**Cách sửa:** Dùng `receive()` tổng quát và bỏ qua message type không cần xử lý:

```python
while True:
    msg = await ws.receive()
    if msg["type"] == "websocket.disconnect":
        break
```

---

### BUG-WS-05 — Snapshot gửi ngay khi connect, trước khi xác thực hoàn tất

**File:** `app/services/websocket_manager.py:38-47`

```python
async def connect(self, ws: WebSocket) -> None:
    await ws.accept()
    # ... thêm vào _active
    if self._live_states:
        await ws.send_text(json.dumps(snapshot))  # gửi luôn
```

Snapshot trạng thái tất cả camera được gửi ngay sau khi `accept()`, trước khi có bất kỳ kiểm tra auth nào (hiện tại không có auth — xem BUG-WS-01). Khi thêm auth sau này, cần chuyển logic gửi snapshot ra ngoài `connect()` và chỉ gửi sau khi verify xong.

---

## Tóm tắt mức độ ưu tiên

| ID | Mô tả ngắn | Mức độ |
|----|-----------|--------|
| BUG-FCM-01 | Fall/Pose FCM gửi broadcast tất cả user | Cao |
| BUG-WS-01 | WebSocket không có auth | Cao |
| BUG-FCM-04 | Ingest endpoints không có auth | Cao |
| BUG-WS-02 | WS broadcast không phân biệt user | Cao |
| BUG-FCM-02 | Logic lọc bệnh nhân vô hiệu do FCM-01 | Trung bình |
| BUG-WS-03 | Live state cache không có TTL | Trung bình |
| BUG-FCM-05 | Background task FCM không được track | Trung bình |
| BUG-WS-04 | `receive_text()` không xử lý binary frame | Thấp |
| BUG-FCM-03 | `get_event_loop()` deprecated | Thấp |
| BUG-WS-05 | Snapshot gửi trước khi auth hoàn tất | Thấp |
