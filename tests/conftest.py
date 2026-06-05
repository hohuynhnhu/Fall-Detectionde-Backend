"""
tests/conftest.py — Fixtures và Mock App dùng chung cho toàn bộ test suite.
"""
from __future__ import annotations

import time
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional

# ══════════════════════════════════════════════════════════════════════════════
# ENUMS & SCHEMAS
# ══════════════════════════════════════════════════════════════════════════════

class PoseState(str, Enum):
    STANDING = "STANDING"
    SITTING  = "SITTING"
    LYING    = "LYING"
    FALLING  = "FALLING"
    WALKING  = "WALKING"
    UNKNOWN  = "UNKNOWN"


class EventType(str, Enum):
    FALL         = "fall"
    POSE_CHANGE  = "pose_change"
    HEARTBEAT    = "heartbeat"
    PATIENT_POSE = "patient_pose"


class FallEvent(BaseModel):
    event_type:        EventType     = EventType.FALL
    camera_id:         str           = "cam_0"
    timestamp:         float         = 0.0
    state:             PoseState     = PoseState.FALLING
    state_before:      PoseState     = PoseState.UNKNOWN
    velocity_px_per_s: float         = 0.0
    max_velocity:      float         = 0.0
    body_angle:        float         = 0.0
    confidence:        float         = Field(0.0, ge=0, le=1)
    frame_id:          int           = 0
    clip_url:          Optional[str] = None
    sound_detected:    bool          = False
    sound_class:       str           = ""
    sound_confidence:  float         = 0.0


class PoseEvent(BaseModel):
    event_type:        EventType  = EventType.POSE_CHANGE
    camera_id:         str        = "cam_0"
    timestamp:         float      = 0.0
    state:             PoseState  = PoseState.UNKNOWN
    prev_state:        PoseState  = PoseState.UNKNOWN
    velocity_px_per_s: float      = 0.0
    frame_id:          int        = 0


class HeartbeatEvent(BaseModel):
    camera_id: str       = "cam_0"
    timestamp: float     = 0.0
    fps:       float     = 0.0
    state:     PoseState = PoseState.UNKNOWN


class PatientPoseEvent(BaseModel):
    camera_id:   str       = "cam_0"
    timestamp:   float     = 0.0
    person_id:   str       = ""
    person_name: str       = ""
    state:       PoseState = PoseState.UNKNOWN
    prev_state:  PoseState = PoseState.UNKNOWN
    frame_id:    int       = 0


class FeatureConfig(BaseModel):
    enable_face_recognition:          bool  = True
    enable_sound_detection:           bool  = False
    enable_patient_pose_notification: bool  = True
    sleep_as_fall:                    bool  = False
    sound_listen_seconds:             float = 3.0


class ThresholdConfig(BaseModel):
    fall_velocity_threshold: float = 80.0
    fall_confirm_frames:     int   = 5
    body_angle_lying:        float = 65.0
    min_confidence:          float = 0.5


class WsFallAlert(BaseModel):
    type:             str           = "fall_alert"
    camera_id:        str
    timestamp:        float
    velocity:         float
    body_angle:       float
    confidence:       float
    clip_url:         Optional[str] = None
    sound_detected:   bool          = False
    sound_class:      str           = ""
    sound_confidence: float         = 0.0


class ContactCreate(BaseModel):
    name:     str
    phone:    str
    relation: Optional[str] = None


# ══════════════════════════════════════════════════════════════════════════════
# IN-MEMORY STORE
# ══════════════════════════════════════════════════════════════════════════════

_store = {
    "fall_events":        [],
    "pose_events":        [],
    "live_states":        {},
    "contacts":           [],
    "features":           FeatureConfig().model_dump(),
    "thresholds":         ThresholdConfig().model_dump(),
    "fall_id_counter":    0,
    "contact_id_counter": 0,
}


def reset_store():
    _store["fall_events"]        = []
    _store["pose_events"]        = []
    _store["live_states"]        = {}
    _store["contacts"]           = []
    _store["features"]           = FeatureConfig().model_dump()
    _store["thresholds"]         = ThresholdConfig().model_dump()
    _store["fall_id_counter"]    = 0
    _store["contact_id_counter"] = 0


# ══════════════════════════════════════════════════════════════════════════════
# MOCK APP
# ══════════════════════════════════════════════════════════════════════════════

app = FastAPI(title="Fall Detection Backend — Test")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/events/fall")
async def receive_fall(event: FallEvent):
    _store["fall_id_counter"] += 1
    ts = event.timestamp or time.time()
    _store["fall_events"].append({
        "id":               _store["fall_id_counter"],
        "camera_id":        event.camera_id,
        "timestamp":        ts,
        "state_before":     event.state_before.value,
        "max_velocity":     event.max_velocity,
        "body_angle":       event.body_angle,
        "confidence":       event.confidence,
        "acknowledged":     False,
        "clip_url":         event.clip_url,
        "sound_detected":   event.sound_detected,
        "sound_class":      event.sound_class,
        "sound_confidence": event.sound_confidence,
    })
    return {"ok": True, "id": _store["fall_id_counter"]}


@app.post("/events/pose")
async def receive_pose(event: PoseEvent):
    _store["pose_events"].append({
        "camera_id":  event.camera_id,
        "timestamp":  event.timestamp or time.time(),
        "state":      event.state.value,
        "prev_state": event.prev_state.value,
    })
    return {"ok": True}


@app.post("/events/heartbeat")
async def receive_heartbeat(event: HeartbeatEvent):
    ts = event.timestamp or time.time()
    _store["live_states"][event.camera_id] = {
        "camera_id": event.camera_id,
        "state":     event.state.value,
        "fps":       event.fps,
        "timestamp": ts,
        "online":    True,
    }
    return {"ok": True, "server_time": time.time()}


@app.post("/events/patient-pose")
async def receive_patient_pose(event: PatientPoseEvent):
    return {"ok": True}


@app.get("/events/falls")
async def list_falls(
    page:      int = 1,
    page_size: int = 20,
    camera_id: Optional[str] = None,
):
    items = _store["fall_events"]
    if camera_id:
        items = [e for e in items if e["camera_id"] == camera_id]
    total       = len(items)
    total_pages = max(1, (total + page_size - 1) // page_size)
    offset      = (page - 1) * page_size
    return {
        "ok": True, "items": items[offset: offset + page_size],
        "total": total, "page": page,
        "page_size": page_size, "total_pages": total_pages,
    }


@app.get("/events/live")
async def get_live_states(camera_id: Optional[str] = None):
    states = list(_store["live_states"].values())
    if camera_id:
        states = [s for s in states if s["camera_id"] == camera_id]
    return states


@app.get("/config/features")
async def get_features():
    return _store["features"]


@app.patch("/config/features")
async def update_features(body: dict):
    _store["features"].update(
        {k: v for k, v in body.items() if k in _store["features"]}
    )
    return _store["features"]


@app.get("/config/thresholds")
async def get_thresholds():
    return _store["thresholds"]


@app.patch("/config/thresholds")
async def update_thresholds(body: dict):
    _store["thresholds"].update(
        {k: v for k, v in body.items() if k in _store["thresholds"]}
    )
    return _store["thresholds"]


@app.get("/contacts")
async def list_contacts():
    return _store["contacts"]


@app.post("/contacts", status_code=201)
async def create_contact(body: ContactCreate):
    _store["contact_id_counter"] += 1
    contact = {
        "id":        _store["contact_id_counter"],
        "name":      body.name,
        "phone":     body.phone,
        "relation":  body.relation,
        "is_active": True,
    }
    _store["contacts"].append(contact)
    return contact


@app.delete("/contacts/{contact_id}")
async def delete_contact(contact_id: int):
    before = len(_store["contacts"])
    _store["contacts"] = [c for c in _store["contacts"] if c["id"] != contact_id]
    if len(_store["contacts"]) == before:
        raise HTTPException(status_code=404, detail="Contact not found")
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def clean_store():
    """Reset store trước mỗi test."""
    reset_store()
    yield


@pytest.fixture
def client():
    return TestClient(app)