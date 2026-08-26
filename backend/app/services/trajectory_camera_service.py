"""
CRUD helpers for TrajectoryCamera (Phase 4).
"""

from __future__ import annotations
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException

from app.models.trajectory_camera import TrajectoryCamera
from app.schemas.trajectory import TrajectoryCameraCreate


def create_trajectory_camera(db: Session, data: TrajectoryCameraCreate) -> TrajectoryCamera:
    cam = TrajectoryCamera(
        camera_id     = data.camera_id.upper(),
        location_name = data.location_name,
        road_name     = data.road_name,
        direction     = data.direction,
        latitude      = data.latitude,
        longitude     = data.longitude,
    )
    db.add(cam)
    try:
        db.commit()
        db.refresh(cam)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Trajectory camera '{data.camera_id}' already exists.",
        )
    return cam


def get_all_trajectory_cameras(db: Session) -> List[TrajectoryCamera]:
    return db.query(TrajectoryCamera).order_by(TrajectoryCamera.camera_id).all()


def get_trajectory_camera_or_404(db: Session, camera_id: str) -> TrajectoryCamera:
    cam = (
        db.query(TrajectoryCamera)
          .filter(TrajectoryCamera.camera_id == camera_id.upper())
          .first()
    )
    if cam is None:
        raise HTTPException(
            status_code=404,
            detail=f"Trajectory camera '{camera_id}' not found.",
        )
    return cam
