"""
app/schemas.py — Pydantic schemas for Fall Detection Backend
Covers: inbound events from desktop, outbound API responses, config, WebSocket messages.
"""
from __future__ import annotations

from enum import Enum
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

# ── Enums ─────────────────────────────────────────────────────────────────────

class PoseState(str, Enum):
    STANDING = "STANDING"
    SITTING  = "SITTING"
    LYING    = "LYING"
    FALLING  = "FALLING"
    WALKING  = "WALKING"
    UNKNOWN  = "UNKNOWN"


class EventType(str, Enum):
    POSE_CHANGE = "pose_change"
    FALL        = "fall"
    WALKING     = "walking"
    RECOVERY    = "recovery"
    HEARTBEAT   = "heartbeat"


# ── Config ────────────────────────────────────────────────────────────────────

class ThresholdConfig(BaseModel):
    body_angle_lying:         float = Field(65.0,  description="Max body angle (°) to classify as LYING")
    body_angle_sitting:       float = Field(45.0,  description="Max body angle (°) to classify as SITTING")
    aspect_ratio_lying:       float = Field(0.55,  description="H/W bounding-box ratio threshold for LYING")
    fall_velocity_threshold:  float = Field(80.0,  description="Min downward velocity (px/s) to trigger fall")
    fall_confirm_frames:      int   = Field(5,     description="Consecutive frames needed to confirm fall")
    fall_history_window:      int   = Field(30,    description="Sliding window size (frames) for fall history")
    sleep_confirm_frames:     int   = Field(60,    description="Frames of LYING before classifying as sleep")
    walk_velocity_threshold:  float = Field(20.0,  description="Min velocity (px/s) to detect walking")
    walk_knee_lift_threshold: float = Field(0.08,  description="Relative knee-lift ratio for walk detection")
    walk_alternating_window:  int   = Field(15,    description="Window (frames) for alternating-step check")
    camera_index:             int   = Field(0,     description="OS camera index")
    flip_horizontal:          bool  = Field(True,  description="Mirror the camera feed")
    model_complexity:         int   = Field(1,     ge=0, le=2, description="MediaPipe model complexity")

    model_config = {"from_attributes": True}


class ThresholdConfigUpdate(BaseModel):
    """Partial update schema for PATCH /config/thresholds — all fields optional."""
    body_angle_lying:         Optional[float] = None
    body_angle_sitting:       Optional[float] = None
    aspect_ratio_lying:       Optional[float] = None
    fall_velocity_threshold:  Optional[float] = None
    fall_confirm_frames:      Optional[int]   = None
    fall_history_window:      Optional[int]   = None
    sleep_confirm_frames:     Optional[int]   = None
    walk_velocity_threshold:  Optional[float] = None
    walk_knee_lift_threshold: Optional[float] = None
    walk_alternating_window:  Optional[int]   = None
    camera_index:             Optional[int]   = None
    flip_horizontal:          Optional[bool]  = None
    model_complexity:         Optional[int]   = Field(None, ge=0, le=2)


class FeatureConfig(BaseModel):
    enable_face_recognition: bool  = Field(True,  description="Enable face recognition pipeline")
    enable_sound_detection:  bool  = Field(False, description="Enable microphone-based sound detection")
    sleep_as_fall:           bool  = Field(False, description="Treat prolonged LYING (sleep) as a fall event")
    sound_listen_seconds:    float = Field(3.0,   description="Duration (s) to listen for sound after motion")

    model_config = {"from_attributes": True}


class FeatureConfigUpdate(BaseModel):
    """Partial update schema for PATCH /config/features — all fields optional."""
    enable_face_recognition: Optional[bool]  = None
    enable_sound_detection:  Optional[bool]  = None
    sleep_as_fall:           Optional[bool]  = None
    sound_listen_seconds:    Optional[float] = None


# ── Inbound payloads (desktop → backend) ─────────────────────────────────────

class BodyMetricsPayload(BaseModel):
    body_angle:   float = 0.0
    aspect_ratio: float = 0.0
    center_x:     float = 0.0
    center_y:     float = 0.0
    confidence:   float = 0.0
    hip_y:        float = 0.0
    shoulder_y:   float = 0.0
    ankle_y:      float = 0.0


class FallEvent(BaseModel):
    event_type:       EventType     = EventType.FALL
    camera_id:        str           = "cam_0"
    timestamp:        float         = 0.0
    state:            PoseState     = PoseState.FALLING
    state_before:     PoseState     = PoseState.STANDING
    velocity_px_per_s: float        = 0.0
    max_velocity:     float         = 0.0
    body_angle:       float         = 0.0
    confidence:       float         = 0.0
    frame_id:         int           = 0
    clip_url:         Optional[str] = None


class PoseEvent(BaseModel):
    event_type:       EventType         = EventType.POSE_CHANGE
    camera_id:        str               = "cam_0"
    timestamp:        float             = 0.0
    state:            PoseState         = PoseState.UNKNOWN
    prev_state:       PoseState         = PoseState.UNKNOWN
    velocity_px_per_s: float            = 0.0
    metrics:          BodyMetricsPayload = Field(default_factory=BodyMetricsPayload)
    frame_id:         int               = 0


class HeartbeatEvent(BaseModel):
    event_type: EventType = EventType.HEARTBEAT
    camera_id:  str       = "cam_0"
    timestamp:  float     = 0.0
    fps:        float     = 0.0
    state:      PoseState = PoseState.UNKNOWN


class PersonDetectedPayload(BaseModel):
    camera_id:    str   = "cam_0"
    timestamp:    float = 0.0
    confidence:   float = 0.0
    person_count: int   = 1
    frame_id:     int   = 0


# ── Outbound API responses ────────────────────────────────────────────────────

class FallEventResponse(BaseModel):
    """One fall event as returned by GET /events/falls."""
    id:           int
    camera_id:    str
    timestamp:    float
    state_before: Optional[str]
    velocity:     Optional[float]   = Field(None, description="velocity_px_s at detection")
    max_velocity: Optional[float]
    body_angle:   Optional[float]
    confidence:   Optional[float]
    acknowledged: bool
    clip_url:     Optional[str]     = None
    datetime_vn:  Optional[str]     = None

    model_config = {"from_attributes": True}


T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated envelope used by list endpoints."""
    ok:          bool       = True
    items:       List[T]
    total:       int
    page:        int
    page_size:   int
    total_pages: int


class LiveCameraState(BaseModel):
    """Latest known state for one camera — returned by GET /events/live."""
    camera_id:  str
    state:      PoseState
    velocity:   float
    body_angle: float
    fps:        float
    timestamp:  float


# ── WebSocket broadcast messages ──────────────────────────────────────────────

# ── Family members ────────────────────────────────────────────────────────────

class AddFamilyMemberPayload(BaseModel):
    name:           str
    phone_number:   Optional[str] = None
    email:          Optional[str] = None
    relationship:   Optional[str] = None
    notify_on_fall: bool          = True


class FamilyMemberResponse(BaseModel):
    id:             int
    name:           str
    phone_number:   Optional[str]
    email:          Optional[str]
    relationship:   Optional[str]
    notify_on_fall: bool
    created_at:     float

    model_config = {"from_attributes": True}


# ── WebSocket broadcast messages ──────────────────────────────────────────────

class WsFallAlert(BaseModel):
    type:       str           = "fall_alert"
    camera_id:  str
    timestamp:  float
    velocity:   float
    body_angle: float
    confidence: float
    clip_url:   Optional[str] = None


class WsStateUpdate(BaseModel):
    type:       str       = "state_update"
    camera_id:  str
    state:      PoseState
    velocity:   float
    body_angle: float
    fps:        float
    timestamp:  float
