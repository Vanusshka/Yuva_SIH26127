"""
VehicleEvent CRUD service.
All database logic for detection events lives here.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException

from app.models.vehicle_event import VehicleEvent
from app.models.camera import Camera
from app.schemas.vehicle_event import VehicleHistoryResponse, VehicleHistoryEvent


# ── Create ─────────────────────────────────────────────────────────────────────

def create_event(
    db            : Session,
    camera_id     : str,
    timestamp     : datetime,
    plate_number  : Optional[str]   = None,
    vehicle_type  : Optional[str]   = None,
    vehicle_conf  : Optional[float] = None,
    plate_conf    : Optional[float] = None,
    ocr_conf      : Optional[float] = None,
    image_path    : Optional[str]   = None,
) -> VehicleEvent:
    """
    Persist one ANPR detection event.
    Each call always creates a new row (append-only, no upsert).
    """
    event = VehicleEvent(
        plate_number       = plate_number or None,
        camera_id          = camera_id,
        timestamp          = timestamp,
        vehicle_type       = vehicle_type,
        vehicle_confidence = vehicle_conf,
        plate_confidence   = plate_conf,
        ocr_confidence     = ocr_conf,
        image_path         = image_path,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


# ── Query ──────────────────────────────────────────────────────────────────────

def get_events(
    db           : Session,
    plate_number : Optional[str]      = None,
    camera_id    : Optional[str]      = None,
    start_time   : Optional[datetime] = None,
    end_time     : Optional[datetime] = None,
    limit        : int                = 100,
) -> List[VehicleEvent]:
    """
    Flexible event query with optional filters.
    Results ordered by timestamp ascending.
    """
    q = db.query(VehicleEvent)

    if plate_number:
        q = q.filter(VehicleEvent.plate_number == plate_number.upper())
    if camera_id:
        q = q.filter(VehicleEvent.camera_id == camera_id)
    if start_time:
        q = q.filter(VehicleEvent.timestamp >= start_time)
    if end_time:
        q = q.filter(VehicleEvent.timestamp <= end_time)

    return (
        q.order_by(VehicleEvent.timestamp.asc())
         .limit(min(limit, 500))
         .all()
    )


def get_event_by_id(db: Session, event_id: int) -> VehicleEvent:
    ev = db.query(VehicleEvent).filter(VehicleEvent.id == event_id).first()
    if ev is None:
        raise HTTPException(status_code=404, detail=f"Event id={event_id} not found.")
    return ev


def get_vehicle_history(db: Session, plate_number: str) -> VehicleHistoryResponse:
    """
    Return all detection events for a plate, chronologically,
    enriched with camera location data.
    Does NOT calculate trajectories (Phase 4 concern).
    """
    plate_upper = plate_number.upper()

    events = (
        db.query(VehicleEvent)
          .options(joinedload(VehicleEvent.camera))
          .filter(VehicleEvent.plate_number == plate_upper)
          .order_by(VehicleEvent.timestamp.asc())
          .all()
    )

    history_events: List[VehicleHistoryEvent] = []
    for ev in events:
        cam: Optional[Camera] = ev.camera
        history_events.append(
            VehicleHistoryEvent(
                event_id    = ev.id,
                camera_id   = ev.camera_id,
                camera_name = cam.name      if cam else "Unknown",
                latitude    = cam.latitude  if cam else 0.0,
                longitude   = cam.longitude if cam else 0.0,
                address     = cam.address   if cam else None,
                timestamp   = ev.timestamp,
                vehicle_type= ev.vehicle_type,
            )
        )

    return VehicleHistoryResponse(
        plate_number     = plate_upper,
        total_detections = len(history_events),
        events           = history_events,
    )
