"""
CRUD helpers for Detection (Phase 4).
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.detection import Detection
from app.schemas.trajectory import DetectionCreate


def create_detection(db: Session, data: DetectionCreate) -> Detection:
    """
    Persist one ANPR detection for trajectory tracking.
    Timestamps without timezone info are treated as UTC.
    """
    ts = data.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    det = Detection(
        plate_number         = data.plate_number.strip().upper(),
        camera_id            = data.camera_id.upper(),
        timestamp            = ts,
        detection_confidence = data.detection_confidence,
    )
    db.add(det)
    db.commit()
    db.refresh(det)
    return det


def get_detections(
    db           : Session,
    plate_number : Optional[str] = None,
    camera_id    : Optional[str] = None,
    limit        : int           = 200,
) -> List[Detection]:
    q = db.query(Detection)
    if plate_number:
        q = q.filter(Detection.plate_number == plate_number.strip().upper())
    if camera_id:
        q = q.filter(Detection.camera_id == camera_id.upper())
    return q.order_by(Detection.timestamp.asc()).limit(min(limit, 1000)).all()


def get_detection_or_404(db: Session, detection_id: int) -> Detection:
    det = db.query(Detection).filter(Detection.id == detection_id).first()
    if det is None:
        raise HTTPException(status_code=404, detail=f"Detection id={detection_id} not found.")
    return det
