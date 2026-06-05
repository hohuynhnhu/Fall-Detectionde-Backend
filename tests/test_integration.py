"""
tests/test_integration.py — Test luồng nghiệp vụ đầy đủ (end-to-end).

Mô phỏng các kịch bản thực tế:
    1. Phát hiện té ngã kèm âm thanh
    2. Mobile bật tính năng → desktop gửi kết quả
    3. Quản lý liên hệ khẩn cấp + té ngã
    4. Nhiều camera hoạt động độc lập
    5. Workflow cấu hình hệ thống
    6. Bệnh nhân thay đổi tư thế
"""
from __future__ import annotations
import time


class TestFallDetectionFlow:
    def test_full_fall_with_sound(self, client):
        """
        Kịch bản đầy đủ:
        1. Desktop gửi heartbeat (người đứng)
        2. Desktop gửi fall event (té + có tiếng rên)
        3. Mobile query lịch sử và live state
        """
        # Bước 1: Heartbeat — người đứng
        client.post("/events/heartbeat", json={
            "camera_id": "cam_0",
            "fps":       29.0,
            "state":     "STANDING",
        })

        # Bước 2: Fall event kèm âm thanh
        client.post("/events/fall", json={
            "camera_id":        "cam_0",
            "timestamp":        time.time(),
            "state_before":     "STANDING",
            "max_velocity":     145.0,
            "confidence":       0.94,
            "sound_detected":   True,
            "sound_class":      "thud",
            "sound_confidence": 0.82,
        })

        # Bước 3: Mobile xem lịch sử
        falls = client.get("/events/falls").json()
        assert falls["total"] == 1
        fall = falls["items"][0]
        assert fall["sound_detected"] is True
        assert fall["sound_class"] == "thud"
        assert fall["state_before"] == "STANDING"

        # Bước 4: Live state vẫn còn từ heartbeat
        live = client.get("/events/live?camera_id=cam_0").json()
        assert len(live) == 1
        assert live[0]["state"] == "STANDING"

    def test_fall_without_sound(self, client):
        """Té ngã không có âm thanh — sound_detected=False."""
        client.post("/events/fall", json={
            "camera_id":  "cam_0",
            "confidence": 0.88,
        })
        fall = client.get("/events/falls").json()["items"][0]
        assert fall["sound_detected"] is False
        assert fall["sound_class"] == ""


class TestSoundDetectionFlow:
    def test_mobile_enables_sound_then_fall(self, client):
        """
        Mobile bật sound detection →
        Desktop phát hiện té + âm thanh →
        Mobile thấy kết quả đúng.
        """
        # Mobile bật sound detection
        client.patch("/config/features", json={"enable_sound_detection": True})
        assert client.get("/config/features").json()["enable_sound_detection"] is True

        # Desktop phát hiện té + âm thanh
        client.post("/events/fall", json={
            "sound_detected":   True,
            "sound_class":      "scream",
            "sound_confidence": 0.91,
            "confidence":       0.96,
        })

        # Mobile xem lịch sử
        fall = client.get("/events/falls").json()["items"][0]
        assert fall["sound_detected"] is True
        assert fall["sound_class"] == "scream"

    def test_sound_disabled_fall_still_works(self, client):
        """Sound tắt — fall event vẫn gửi được, sound_detected=False."""
        client.patch("/config/features", json={"enable_sound_detection": False})
        r = client.post("/events/fall", json={"confidence": 0.9})
        assert r.status_code == 200

        fall = client.get("/events/falls").json()["items"][0]
        assert fall["sound_detected"] is False


class TestEmergencyContactFlow:
    def test_add_contacts_then_fall(self, client):
        """
        Thêm liên hệ khẩn cấp →
        Phát hiện fall →
        Liên hệ có trong hệ thống để ADB gọi.
        """
        # Thêm 2 liên hệ
        client.post("/contacts", json={"name": "Mẹ",  "phone": "0901111111"})
        client.post("/contacts", json={"name": "Ba",  "phone": "0902222222"})

        contacts = client.get("/contacts").json()
        assert len(contacts) == 2
        assert all(c["is_active"] for c in contacts)

        # Gửi fall event
        client.post("/events/fall", json={"camera_id": "cam_0", "confidence": 0.9})

        # Fall được ghi nhận
        assert client.get("/events/falls").json()["total"] == 1

    def test_delete_contact_then_add_new(self, client):
        """Xóa liên hệ cũ, thêm liên hệ mới."""
        client.post("/contacts", json={"name": "Cũ",  "phone": "0901111111"})
        client.delete("/contacts/1")
        client.post("/contacts", json={"name": "Mới", "phone": "0909999999"})

        contacts = client.get("/contacts").json()
        assert len(contacts) == 1
        assert contacts[0]["name"] == "Mới"


class TestMultipleCamerasFlow:
    def test_cameras_independent(self, client):
        """Nhiều camera hoạt động độc lập."""
        for cam in ["cam_0", "cam_1", "cam_2"]:
            client.post("/events/heartbeat", json={
                "camera_id": cam,
                "state":     "STANDING",
                "fps":       30.0,
            })
            client.post("/events/fall", json={"camera_id": cam})

        # Mỗi camera có 1 fall
        for cam in ["cam_0", "cam_1", "cam_2"]:
            data = client.get(f"/events/falls?camera_id={cam}").json()
            assert data["total"] == 1

        # Tổng 3 falls
        assert client.get("/events/falls").json()["total"] == 3

    def test_live_state_per_camera(self, client):
        """Live state mỗi camera độc lập."""
        client.post("/events/heartbeat", json={"camera_id": "cam_0", "state": "STANDING"})
        client.post("/events/heartbeat", json={"camera_id": "cam_1", "state": "LYING"})

        cam0 = client.get("/events/live?camera_id=cam_0").json()
        cam1 = client.get("/events/live?camera_id=cam_1").json()
        assert cam0[0]["state"] == "STANDING"
        assert cam1[0]["state"] == "LYING"


class TestConfigWorkflow:
    def test_read_update_verify(self, client):
        """Workflow: đọc → cập nhật → xác nhận."""
        # Đọc config mặc định
        feat   = client.get("/config/features").json()
        thresh = client.get("/config/thresholds").json()
        assert feat["sleep_as_fall"] is False
        assert thresh["fall_velocity_threshold"] == 80.0

        # Cập nhật
        client.patch("/config/features",   json={"sleep_as_fall": True})
        client.patch("/config/thresholds", json={"fall_velocity_threshold": 60.0})

        # Xác nhận
        assert client.get("/config/features").json()["sleep_as_fall"] is True
        assert client.get("/config/thresholds").json()["fall_velocity_threshold"] == 60.0

    def test_sensitive_threshold_affects_detection(self, client):
        """
        Giảm ngưỡng velocity → hệ thống nhạy hơn.
        (Mô phỏng logic cấu hình, không test AI thực tế)
        """
        # Đặt ngưỡng thấp (nhạy)
        client.patch("/config/thresholds", json={"fall_velocity_threshold": 40.0})
        thresh = client.get("/config/thresholds").json()
        assert thresh["fall_velocity_threshold"] == 40.0

        # Gửi fall với velocity thấp (vẫn được ghi nhận vì backend không filter)
        client.post("/events/fall", json={"max_velocity": 45.0, "confidence": 0.85})
        assert client.get("/events/falls").json()["total"] == 1


class TestPatientMonitoringFlow:
    def test_patient_pose_changes(self, client):
        """Bệnh nhân thay đổi tư thế — desktop gửi chuỗi sự kiện."""
        transitions = [
            ("STANDING", "UNKNOWN"),
            ("SITTING",  "STANDING"),
            ("LYING",    "SITTING"),
        ]
        for state, prev in transitions:
            r = client.post("/events/patient-pose", json={
                "person_id":   "pid_patient_001",
                "person_name": "Nguyễn Thị Nhu",
                "state":       state,
                "prev_state":  prev,
            })
            assert r.status_code == 200

    def test_fall_after_patient_pose(self, client):
        """Bệnh nhân đang nằm → phát hiện té ngã."""
        # Gửi tư thế nằm
        client.post("/events/patient-pose", json={
            "person_id": "pid_001",
            "state":     "LYING",
            "prev_state":"STANDING",
        })

        # Gửi fall event
        client.post("/events/fall", json={
            "camera_id":    "cam_0",
            "state_before": "STANDING",
            "confidence":   0.93,
        })

        # Xác nhận fall được ghi nhận
        assert client.get("/events/falls").json()["total"] == 1