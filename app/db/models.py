from __future__ import annotations

import time

from sqlalchemy import Boolean, Column, Float, Integer, String, UniqueConstraint

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
    token      = Column(String(256), unique=True, nullable=False, index=True)
    platform   = Column(String(8), default="android")
    created_at = Column(Float, default=time.time, nullable=False)


class UserDB(Base):
    __tablename__ = "users"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    firebase_uid = Column(String(128), unique=True, nullable=False, index=True)
    email        = Column(String(256), nullable=True)
    phone_number = Column(String(32), nullable=True)
    display_name = Column(String(128), nullable=True)
    is_active    = Column(Boolean, default=True, nullable=False)
    created_at   = Column(Float, default=time.time, nullable=False)


class UserCameraDB(Base):
    __tablename__ = "user_cameras"
    __table_args__ = (UniqueConstraint("user_id", "camera_id"),)

    id        = Column(Integer, primary_key=True, autoincrement=True)
    user_id   = Column(Integer, nullable=False, index=True)
    camera_id = Column(String(32), nullable=False)
    label     = Column(String(128), nullable=True)


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
    name           = Column(String(128), nullable=False)
    phone_number   = Column(String(32), nullable=True)
    email          = Column(String(256), nullable=True)
    relationship   = Column(String(64), nullable=True)
    notify_on_fall = Column(Boolean, default=True, nullable=False)
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