from __future__ import annotations

import time

from sqlalchemy import Boolean, Column, Float, Integer, String

from .database import Base


class FallEventDB(Base):
    __tablename__ = "fall_events"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    camera_id     = Column(String(32), nullable=False, index=True)
    timestamp     = Column(Float, nullable=False, index=True)
    state_before  = Column(String(16))
    velocity_px_s = Column(Float)
    max_velocity  = Column(Float)
    body_angle    = Column(Float)
    confidence    = Column(Float)
    frame_id      = Column(Integer)
    clip_url      = Column(String(512), nullable=True)
    acknowledged  = Column(Boolean, default=False, nullable=False)


class PoseEventDB(Base):
    __tablename__ = "pose_events"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    camera_id     = Column(String(32), nullable=False, index=True)
    timestamp     = Column(Float, nullable=False, index=True)
    state         = Column(String(16))
    prev_state    = Column(String(16))
    velocity_px_s = Column(Float)
    body_angle    = Column(Float)
    confidence    = Column(Float)
    person_id     = Column(String(36), nullable=True, index=True)
    person_name   = Column(String(128), nullable=True)
    frame_id      = Column(Integer, nullable=True)


class ThresholdConfigDB(Base):
    __tablename__ = "threshold_configs"

    id                       = Column(Integer, primary_key=True, autoincrement=True)
    camera_id                = Column(String(32), unique=True, nullable=False, index=True)
    body_angle_lying         = Column(Float,   default=65.0)
    body_angle_sitting       = Column(Float,   default=45.0)
    aspect_ratio_lying       = Column(Float,   default=0.55)
    fall_velocity_threshold  = Column(Float,   default=80.0)
    fall_confirm_frames      = Column(Integer, default=5)
    fall_history_window      = Column(Integer, default=30)
    sleep_confirm_frames     = Column(Integer, default=60)
    walk_velocity_threshold  = Column(Float,   default=20.0)
    walk_knee_lift_threshold = Column(Float,   default=0.08)
    walk_alternating_window  = Column(Integer, default=15)
    camera_index             = Column(Integer, default=0)
    flip_horizontal          = Column(Boolean, default=True)
    model_complexity         = Column(Integer, default=1)


class FeatureConfigDB(Base):
    __tablename__ = "feature_configs"

    id                      = Column(Integer, primary_key=True, autoincrement=True)
    camera_id               = Column(String(32), unique=True, nullable=False, index=True)
    enable_face_recognition = Column(Boolean, default=True)
    enable_sound_detection  = Column(Boolean, default=False)
    sleep_as_fall           = Column(Boolean, default=False)
    sound_listen_seconds    = Column(Float,   default=3.0)


class DeviceTokenDB(Base):
    __tablename__ = "device_tokens"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    user_id    = Column(Integer, nullable=True, index=True)
    token      = Column(String(256), unique=True, nullable=False, index=True)
    platform   = Column(String(8), default="android")
    created_at = Column(Float, default=time.time, nullable=False)


class UserDB(Base):
    __tablename__ = "users"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    firebase_uid   = Column(String(128), unique=True, nullable=False, index=True)
    email          = Column(String(256), nullable=True)
    phone_number   = Column(String(32), nullable=True)
    display_name   = Column(String(128), nullable=True)
    avatar_url     = Column(String(512), nullable=True)
    email_verified = Column(Boolean, default=False, nullable=False)
    role           = Column(String(16), default="user", nullable=False)  # "user" | "admin"
    is_active      = Column(Boolean, default=True, nullable=False)
    created_at     = Column(Float, default=time.time, nullable=False)


class OTPCodeDB(Base):
    __tablename__ = "otp_codes"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    email      = Column(String(256), nullable=False, index=True)
    code       = Column(String(6), nullable=False)
    purpose    = Column(String(30), nullable=False)  # email_verification | password_reset
    expires_at = Column(Float, nullable=False)
    used       = Column(Boolean, default=False, nullable=False)
    created_at = Column(Float, default=time.time, nullable=False)


class PersonDetectedDB(Base):
    __tablename__ = "person_detected_events"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    camera_id    = Column(String(32), nullable=False, index=True)
    timestamp    = Column(Float, nullable=False, index=True)
    confidence   = Column(Float)
    person_count = Column(Integer, default=1)
    frame_id     = Column(Integer)


class FamilyMemberDB(Base):
    __tablename__ = "family_members"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    user_id        = Column(Integer, nullable=True, index=True)
    person_id      = Column(String(36), unique=True, nullable=True, index=True)
    name           = Column(String(128), nullable=False)
    role           = Column(String(16), nullable=True)   # family | caregiver
    face_image_url = Column(String(512), nullable=True)
    phone_number   = Column(String(32), nullable=True)
    email          = Column(String(256), nullable=True)
    relationship   = Column(String(64), nullable=True)
    notify_on_fall = Column(Boolean, default=True, nullable=False)
    is_patient     = Column(Boolean, default=False, nullable=False)
    camera_id      = Column(String(32), nullable=True)
    created_at     = Column(Float, default=time.time, nullable=False)


class EmergencyContactDB(Base):
    __tablename__ = "emergency_contacts"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    user_id    = Column(Integer, nullable=False, index=True)
    name       = Column(String(128), nullable=False)
    phone      = Column(String(32), nullable=False)
    relation   = Column(String(64), nullable=True)
    is_active  = Column(Boolean, default=True, nullable=False)
    created_at = Column(Float, default=time.time, nullable=False)


class FaceRecognitionLogDB(Base):
    __tablename__ = "face_recognition_logs"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    user_id       = Column(Integer, nullable=True,  index=True)
    person_id     = Column(String(36), nullable=False, index=True)
    name          = Column(String(128), nullable=False)
    is_patient    = Column(Boolean, default=False, nullable=False)
    recognized_at = Column(Float, nullable=False, index=True)
    camera_id     = Column(String(32), nullable=False)
    confidence    = Column(Float, nullable=True)


class SupportReportDB(Base):
    __tablename__ = "support_reports"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    user_id     = Column(Integer, nullable=False, index=True)
    category    = Column(String(64), nullable=False)   # bug | feature | question | other
    title       = Column(String(256), nullable=False)
    description = Column(String(2000), nullable=False)
    status      = Column(String(16), default="pending", nullable=False)  # pending | in_progress | resolved | closed
    admin_reply = Column(String(2000), nullable=True)
    replied_by  = Column(Integer, nullable=True)
    replied_at  = Column(Float, nullable=True)
    created_at  = Column(Float, default=time.time, nullable=False)
    updated_at  = Column(Float, default=time.time, nullable=False)