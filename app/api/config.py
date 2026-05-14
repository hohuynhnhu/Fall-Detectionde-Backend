"""
app/api/config.py

GET   /config/thresholds         — fetch current thresholds for a camera
PUT   /config/thresholds         — replace all thresholds
PATCH /config/thresholds         — partial update (mobile app)
POST  /config/thresholds/reset   — reset to factory defaults

GET   /config/features           — fetch current feature flags
PATCH /config/features           — partial update (mobile app)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..db.models import FeatureConfigDB, ThresholdConfigDB
from ..schemas import (
    FeatureConfig,
    FeatureConfigUpdate,
    ThresholdConfig,
    ThresholdConfigUpdate,
)

router = APIRouter()


# ── Threshold helpers ──────────────────────────────────────────────────────────

async def _get_or_create_threshold(db: AsyncSession, camera_id: str) -> ThresholdConfigDB:
    result = await db.execute(
        select(ThresholdConfigDB).where(ThresholdConfigDB.camera_id == camera_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = ThresholdConfigDB(camera_id=camera_id)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


# ── Feature helpers ────────────────────────────────────────────────────────────

async def _get_or_create_feature(db: AsyncSession, camera_id: str) -> FeatureConfigDB:
    result = await db.execute(
        select(FeatureConfigDB).where(FeatureConfigDB.camera_id == camera_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = FeatureConfigDB(camera_id=camera_id)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


# ── Threshold endpoints ────────────────────────────────────────────────────────

@router.get(
    "/thresholds",
    response_model=ThresholdConfig,
    summary="Get current detection thresholds",
)
async def get_thresholds(
    camera_id: str = Query("cam_0"),
    db: AsyncSession = Depends(get_db),
) -> ThresholdConfig:
    row = await _get_or_create_threshold(db, camera_id)
    return ThresholdConfig.model_validate(row)


@router.put(
    "/thresholds",
    summary="Replace all detection thresholds",
)
async def update_thresholds(
    cfg: ThresholdConfig,
    camera_id: str = Query("cam_0"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await _get_or_create_threshold(db, camera_id)
    for field, value in cfg.model_dump().items():
        if hasattr(row, field):
            setattr(row, field, value)
    await db.commit()
    return {"ok": True, "camera_id": camera_id, "message": "Thresholds updated"}


@router.patch(
    "/thresholds",
    summary="Partial update of detection thresholds (mobile app)",
)
async def patch_thresholds(
    update: ThresholdConfigUpdate,
    camera_id: str = Query("cam_0"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await _get_or_create_threshold(db, camera_id)
    for field, value in update.model_dump(exclude_none=True).items():
        if hasattr(row, field):
            setattr(row, field, value)
    await db.commit()
    await db.refresh(row)
    return {"ok": True, "thresholds": ThresholdConfig.model_validate(row).model_dump()}


@router.post(
    "/thresholds/reset",
    summary="Reset thresholds to factory defaults",
)
async def reset_thresholds(
    camera_id: str = Query("cam_0"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await _get_or_create_threshold(db, camera_id)
    defaults = ThresholdConfig()
    for field, value in defaults.model_dump().items():
        if hasattr(row, field):
            setattr(row, field, value)
    await db.commit()
    return {"ok": True, "camera_id": camera_id, "message": "Reset to defaults"}


# ── Feature endpoints ──────────────────────────────────────────────────────────

@router.get(
    "/features",
    response_model=FeatureConfig,
    summary="Get current feature flags",
)
async def get_features(
    camera_id: str = Query("cam_0"),
    db: AsyncSession = Depends(get_db),
) -> FeatureConfig:
    row = await _get_or_create_feature(db, camera_id)
    return FeatureConfig.model_validate(row)


@router.patch(
    "/features",
    summary="Partial update of feature flags (mobile app)",
)
async def patch_features(
    update: FeatureConfigUpdate,
    camera_id: str = Query("cam_0"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await _get_or_create_feature(db, camera_id)
    for field, value in update.model_dump(exclude_none=True).items():
        if hasattr(row, field):
            setattr(row, field, value)
    await db.commit()
    await db.refresh(row)
    return {"ok": True, "features": FeatureConfig.model_validate(row).model_dump()}
