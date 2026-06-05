"""
tests/test_schemas.py — Test Pydantic schema validation.

Kiểm tra:
    - FallEvent: field types, defaults, constraints
    - WsFallAlert: sound fields, defaults
    - FeatureConfig: defaults
    - PoseState / EventType enums
"""
from __future__ import annotations

import time
import pytest
from pydantic import ValidationError

from conftest import (
    FallEvent, WsFallAlert, FeatureConfig,
    PoseState, EventType, PatientPoseEvent, PoseEvent,
)


class TestFallEventSchema:
    def test_valid_full(self):
        event = FallEvent(
            camera_id="cam_0",
            confidence=0.95,
            max_velocity=120.0,
            sound_detected=True,
            sound_class="groan",
            sound_confidence=0.87,
        )
        assert event.confidence == 0.95
        assert event.sound_detected is True
        assert event.sound_class == "groan"

    def test_confidence_over_1(self):
        with pytest.raises(ValidationError):
            FallEvent(confidence=1.5)

    def test_confidence_negative(self):
        with pytest.raises(ValidationError):
            FallEvent(confidence=-0.1)

    def test_confidence_boundary_valid(self):
        """confidence = 0.0 và 1.0 đều hợp lệ."""
        FallEvent(confidence=0.0)
        FallEvent(confidence=1.0)

    def test_defaults(self):
        event = FallEvent()
        assert event.camera_id == "cam_0"
        assert event.sound_detected is False
        assert event.sound_class == ""
        assert event.sound_confidence == 0.0
        assert event.clip_url is None
        assert event.frame_id == 0

    def test_state_enum(self):
        event = FallEvent(state=PoseState.FALLING, state_before=PoseState.STANDING)
        assert event.state == PoseState.FALLING
        assert event.state_before == PoseState.STANDING

    def test_clip_url_optional(self):
        event = FallEvent(clip_url=None)
        assert event.clip_url is None
        event2 = FallEvent(clip_url="https://example.com/clip.mp4")
        assert event2.clip_url == "https://example.com/clip.mp4"


class TestWsFallAlertSchema:
    def test_with_sound(self):
        alert = WsFallAlert(
            camera_id="cam_0",
            timestamp=time.time(),
            velocity=120.0,
            body_angle=75.0,
            confidence=0.92,
            sound_detected=True,
            sound_class="crash",
            sound_confidence=0.88,
        )
        assert alert.type == "fall_alert"
        assert alert.sound_detected is True
        assert alert.sound_class == "crash"

    def test_defaults(self):
        alert = WsFallAlert(
            camera_id="cam_0",
            timestamp=time.time(),
            velocity=0.0,
            body_angle=0.0,
            confidence=0.0,
        )
        assert alert.sound_detected is False
        assert alert.sound_class == ""
        assert alert.sound_confidence == 0.0
        assert alert.clip_url is None

    def test_type_is_fall_alert(self):
        alert = WsFallAlert(
            camera_id="cam_0", timestamp=0.0,
            velocity=0.0, body_angle=0.0, confidence=0.0,
        )
        assert alert.type == "fall_alert"


class TestFeatureConfigSchema:
    def test_defaults(self):
        feat = FeatureConfig()
        assert feat.enable_sound_detection is False
        assert feat.enable_face_recognition is True
        assert feat.enable_patient_pose_notification is True
        assert feat.sleep_as_fall is False
        assert feat.sound_listen_seconds == 3.0

    def test_override(self):
        feat = FeatureConfig(
            enable_sound_detection=True,
            sleep_as_fall=True,
            sound_listen_seconds=5.0,
        )
        assert feat.enable_sound_detection is True
        assert feat.sleep_as_fall is True
        assert feat.sound_listen_seconds == 5.0


class TestPoseStateEnum:
    def test_values(self):
        assert PoseState.STANDING == "STANDING"
        assert PoseState.SITTING  == "SITTING"
        assert PoseState.LYING    == "LYING"
        assert PoseState.WALKING  == "WALKING"
        assert PoseState.FALLING  == "FALLING"
        assert PoseState.UNKNOWN  == "UNKNOWN"

    def test_all_members(self):
        members = {e.value for e in PoseState}
        assert members == {"STANDING", "SITTING", "LYING", "WALKING", "FALLING", "UNKNOWN"}


class TestEventTypeEnum:
    def test_values(self):
        assert EventType.FALL         == "fall"
        assert EventType.POSE_CHANGE  == "pose_change"
        assert EventType.HEARTBEAT    == "heartbeat"
        assert EventType.PATIENT_POSE == "patient_pose"


class TestPoseEventSchema:
    def test_valid(self):
        event = PoseEvent(
            camera_id="cam_0",
            state=PoseState.LYING,
            prev_state=PoseState.STANDING,
        )
        assert event.state == PoseState.LYING

    def test_defaults(self):
        event = PoseEvent()
        assert event.camera_id == "cam_0"
        assert event.state == PoseState.UNKNOWN


class TestPatientPoseEventSchema:
    def test_valid(self):
        event = PatientPoseEvent(
            person_id="pid_001",
            person_name="Nguyễn Văn A",
            state=PoseState.LYING,
            prev_state=PoseState.SITTING,
        )
        assert event.person_id == "pid_001"
        assert event.state == PoseState.LYING

    def test_defaults(self):
        event = PatientPoseEvent()
        assert event.camera_id == "cam_0"
        assert event.person_id == ""
        assert event.state == PoseState.UNKNOWN