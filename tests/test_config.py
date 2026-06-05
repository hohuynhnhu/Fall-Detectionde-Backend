"""
tests/test_config.py — Test cấu hình hệ thống.

Endpoints:
    GET   /config/features
    PATCH /config/features
"""
from __future__ import annotations


class TestFeatureConfig:
    def test_get_defaults(self, client):
        """Giá trị mặc định đúng."""
        r = client.get("/config/features")
        assert r.status_code == 200
        data = r.json()
        assert data["enable_sound_detection"] is False
        assert data["enable_face_recognition"] is True
        assert data["sleep_as_fall"] is False
        assert data["sound_listen_seconds"] == 3.0

    def test_enable_sound_detection(self, client):
        """Bật sound detection."""
        r = client.patch("/config/features", json={"enable_sound_detection": True})
        assert r.status_code == 200
        assert r.json()["enable_sound_detection"] is True

    def test_enable_sound_persists(self, client):
        """Thay đổi được lưu lại."""
        client.patch("/config/features", json={"enable_sound_detection": True})
        assert client.get("/config/features").json()["enable_sound_detection"] is True

    def test_enable_sleep_as_fall(self, client):
        """Bật chế độ nằm lâu = té ngã."""
        r = client.patch("/config/features", json={"sleep_as_fall": True})
        assert r.status_code == 200
        assert r.json()["sleep_as_fall"] is True

    def test_partial_update(self, client):
        """Patch 1 field, các field khác giữ nguyên."""
        client.patch("/config/features", json={"enable_sound_detection": True})
        data = client.get("/config/features").json()
        assert data["enable_sound_detection"] is True
        assert data["enable_face_recognition"] is True  # không đổi

    def test_update_sound_listen_seconds(self, client):
        """Cập nhật thời gian nghe âm thanh."""
        r = client.patch("/config/features", json={"sound_listen_seconds": 5.0})
        assert r.json()["sound_listen_seconds"] == 5.0

    def test_disable_face_recognition(self, client):
        """Tắt nhận diện khuôn mặt."""
        r = client.patch("/config/features", json={"enable_face_recognition": False})
        assert r.json()["enable_face_recognition"] is False

    def test_disable_patient_notification(self, client):
        """Tắt thông báo tư thế bệnh nhân."""
        r = client.patch("/config/features",
                         json={"enable_patient_pose_notification": False})
        assert r.json()["enable_patient_pose_notification"] is False