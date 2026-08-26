"""
Camera CRUD service.
All database logic for cameras lives here; routes stay thin.
"""

from __future__ import annotations
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException

from app.models.camera import Camera, CameraStatus
from app.schemas.camera import CameraCreate, CameraUpdate


def create_camera(db: Session, data: CameraCreate) -> Camera:
    """Insert a new camera. Raises 409 if camera_id already exists."""
    cam = Camera(
        camera_id = data.camera_id,
        name      = data.name,
        latitude  = data.latitude,
        longitude = data.longitude,
        address   = data.address,
        status    = CameraStatus(data.status),
    )
    db.add(cam)
    try:
        db.commit()
        db.refresh(cam)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Camera with camera_id '{data.camera_id}' already exists.",
        )
    return cam


def get_all_cameras(db: Session) -> List[Camera]:
    return db.query(Camera).order_by(Camera.camera_id).all()


def get_camera_by_camera_id(db: Session, camera_id: str) -> Optional[Camera]:
    return db.query(Camera).filter(Camera.camera_id == camera_id).first()


def get_camera_or_404(db: Session, camera_id: str) -> Camera:
    cam = get_camera_by_camera_id(db, camera_id)
    if cam is None:
        raise HTTPException(
            status_code=404,
            detail=f"Camera '{camera_id}' not found.",
        )
    return cam


def update_camera(db: Session, camera_id: str, data: CameraUpdate) -> Camera:
    cam = get_camera_or_404(db, camera_id)
    for field, value in data.model_dump(exclude_none=True).items():
        if field == "status":
            value = CameraStatus(value)
        setattr(cam, field, value)
    db.commit()
    db.refresh(cam)
    return cam


def delete_camera(db: Session, camera_id: str) -> None:
    cam = get_camera_or_404(db, camera_id)
    db.delete(cam)
    db.commit()
