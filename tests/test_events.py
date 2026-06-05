"""
tests/test_events.py — Test các endpoint nhận sự kiện từ desktop + query mobile.

Endpoints:
    POST /events/fall
    POST /events/pose
    POST /events/heartbeat
    POST /events/patient-pose
    GET  /events/falls
    GET  /events/live
"""
from __future__ import annotations
import time
import pytest


# ══════════════════════════════════════════════════════════════════════════════
# POST /events/fall
# ══════════════════════════════════════════════════════════════════════════════

class TestReceiveFall:
    def test_basic(self, client):
        """Gửi fall event cơ bản — trả về ok và id."""
        r = client.post("/events/fall", json={
            "camera_id":    "cam_0",
            "timestamp":    time.time(),
            "state_before": "STANDING",
            "max_velocity": 120.5,
            "body_angle":   75.0,
            "confidence":   0.92,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["id"] == 1

    def test_with_sound_detected(self, client):
        """Fall event kèm âm thanh phát hiện được."""
        r = client.post("/events/fall", json={
            "sound_detected":   True,
            "sound_class":      "groan",
            "sound_confidence": 0.87,
            "confidence":       0.95,
        })
        assert r.status_code == 200
        item = client.get("/events/falls").json()["items"][0]
        assert item["sound_detected"] is True
        assert item["sound_class"] == "groan"
        assert abs(item["sound_confidence"] - 0.87) < 0.001

    def test_without_sound(self, client):
        """Fall event không có âm thanh — mặc định False."""
        client.post("/events/fall", json={"camera_id": "cam_1"})
        item = client.get("/events/falls").json()["items"][0]
        assert item["sound_detected"] is False
        assert item["sound_class"] == ""

    def test_with_clip_url(self, client):
        """Fall event kèm clip_url từ Cloudinary."""
        url = "https://res.cloudinary.com/test/video/upload/fall_001.mp4"
        client.post("/events/fall", json={"clip_url": url})
        item = client.get("/events/falls").json()["items"][0]
        assert item["clip_url"] == url

    def test_confidence_upper_boundary(self, client):
        """confidence = 1.0 hợp lệ."""
        r = client.post("/events/fall", json={"confidence": 1.0})
        assert r.status_code == 200

    def test_confidence_over_limit(self, client):
        """confidence > 1.0 → 422."""
        r = client.post("/events/fall", json={"confidence": 1.5})
        assert r.status_code == 422

    def test_confidence_negative(self, client):
        """confidence < 0 → 422."""
        r = client.post("/events/fall", json={"confidence": -0.1})
        assert r.status_code == 422

    def test_multiple_increments_id(self, client):
        """Nhiều fall events có id tăng dần."""
        for _ in range(3):
            client.post("/events/fall", json={})
        ids = [item["id"] for item in client.get("/events/falls").json()["items"]]
        assert ids == [1, 2, 3]

    def test_default_values(self, client):
        """Body rỗng → dùng default."""
        client.post("/events/fall", json={})
        item = client.get("/events/falls").json()["items"][0]
        assert item["camera_id"] == "cam_0"
        assert item["acknowledged"] is False
        assert item["clip_url"] is None


# ══════════════════════════════════════════════════════════════════════════════
# GET /events/falls — phân trang + filter
# ══════════════════════════════════════════════════════════════════════════════

class TestListFalls:
    def _seed(self, client, n: int, camera_id: str = "cam_0"):
        for i in range(n):
            client.post("/events/fall", json={
                "camera_id": camera_id,
                "timestamp": time.time() + i,
            })

    def test_empty(self, client):
        r = client.get("/events/falls")
        data = r.json()
        assert data["ok"] is True
        assert data["items"] == []
        assert data["total"] == 0
        assert data["total_pages"] == 1

    def test_pagination_page1(self, client):
        """25 events, page_size=10 → trang 1 có 10 items."""
        self._seed(client, 25)
        data = client.get("/events/falls?page=1&page_size=10").json()
        assert data["total"] == 25
        assert data["total_pages"] == 3
        assert len(data["items"]) == 10

    def test_pagination_page2(self, client):
        """Trang 2 có đủ 10 items."""
        self._seed(client, 25)
        data = client.get("/events/falls?page=2&page_size=10").json()
        assert len(data["items"]) == 10
        assert data["page"] == 2

    def test_pagination_last_page(self, client):
        """Trang cuối ít hơn page_size."""
        self._seed(client, 25)
        data = client.get("/events/falls?page=3&page_size=10").json()
        assert len(data["items"]) == 5

    def test_filter_by_camera(self, client):
        """Lọc theo camera_id."""
        self._seed(client, 3, "cam_0")
        self._seed(client, 2, "cam_1")
        data = client.get("/events/falls?camera_id=cam_0").json()
        assert data["total"] == 3
        assert all(item["camera_id"] == "cam_0" for item in data["items"])

    def test_filter_camera_no_match(self, client):
        """Camera không tồn tại → rỗng."""
        self._seed(client, 3, "cam_0")
        data = client.get("/events/falls?camera_id=cam_99").json()
        assert data["total"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# POST /events/pose
# ══════════════════════════════════════════════════════════════════════════════

class TestReceivePose:
    def test_basic(self, client):
        r = client.post("/events/pose", json={
            "camera_id":  "cam_0",
            "state":      "LYING",
            "prev_state": "STANDING",
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_all_valid_states(self, client):
        """Tất cả PoseState hợp lệ."""
        for state in ["STANDING", "SITTING", "LYING", "WALKING", "FALLING", "UNKNOWN"]:
            r = client.post("/events/pose", json={"state": state})
            assert r.status_code == 200, f"State {state} thất bại"

    def test_invalid_state(self, client):
        """State không hợp lệ → 422."""
        r = client.post("/events/pose", json={"state": "RUNNING"})
        assert r.status_code == 422


# ══════════════════════════════════════════════════════════════════════════════
# POST /events/heartbeat
# ══════════════════════════════════════════════════════════════════════════════

class TestHeartbeat:
    def test_basic(self, client):
        r = client.post("/events/heartbeat", json={
            "camera_id": "cam_0",
            "fps":       29.5,
            "state":     "STANDING",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "server_time" in data

    def test_updates_live_state(self, client):
        """Heartbeat cập nhật live state."""
        client.post("/events/heartbeat", json={
            "camera_id": "cam_0",
            "fps":       30.0,
            "state":     "WALKING",
        })
        live = client.get("/events/live").json()
        assert len(live) == 1
        assert live[0]["state"] == "WALKING"
        assert live[0]["fps"] == 30.0

    def test_multiple_cameras(self, client):
        """Nhiều camera có live state độc lập."""
        for i in range(3):
            client.post("/events/heartbeat", json={
                "camera_id": f"cam_{i}",
                "state":     "STANDING",
            })
        live = client.get("/events/live").json()
        assert len(live) == 3

    def test_overwrite_same_camera(self, client):
        """Heartbeat cùng camera ghi đè state cũ."""
        client.post("/events/heartbeat", json={"camera_id": "cam_0", "state": "STANDING"})
        client.post("/events/heartbeat", json={"camera_id": "cam_0", "state": "LYING"})
        live = client.get("/events/live?camera_id=cam_0").json()
        assert len(live) == 1
        assert live[0]["state"] == "LYING"


# ══════════════════════════════════════════════════════════════════════════════
# GET /events/live
# ══════════════════════════════════════════════════════════════════════════════

class TestLiveState:
    def test_empty(self, client):
        assert client.get("/events/live").json() == []

    def test_filter_by_camera(self, client):
        client.post("/events/heartbeat", json={"camera_id": "cam_0", "state": "STANDING"})
        client.post("/events/heartbeat", json={"camera_id": "cam_1", "state": "LYING"})
        data = client.get("/events/live?camera_id=cam_1").json()
        assert len(data) == 1
        assert data[0]["state"] == "LYING"


# ══════════════════════════════════════════════════════════════════════════════
# POST /events/patient-pose
# ══════════════════════════════════════════════════════════════════════════════

class TestPatientPose:
    def test_basic(self, client):
        r = client.post("/events/patient-pose", json={
            "person_id":   "pid_abc123",
            "person_name": "Nguyễn Văn A",
            "state":       "LYING",
            "prev_state":  "SITTING",
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_unknown_state_accepted(self, client):
        """UNKNOWN state vẫn hợp lệ."""
        r = client.post("/events/patient-pose", json={
            "person_id": "pid_001",
            "state":     "UNKNOWN",
        })
        assert r.status_code == 200