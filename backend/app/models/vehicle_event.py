"""
VehicleEvent ORM model.

Each ANPR detection creates one row here.
Old events are never overwritten; every sighting is a new record.
"""

from __future__ import annotations
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Index,
)
from sqlalchemy.orm import relationship

from app.database import Base


class VehicleEvent(Base):
    __tablename__ = "vehicle_events"
    __table_args__ = (
        # Fast lookup: all sightings of a plate, ordered by time
        Index("ix_vehicle_events_plate_ts", "plate_number", "timestamp"),
        # Fast lookup: all events from a camera
        Index("ix_vehicle_events_cam_ts",   "camera_id",    "timestamp"),
    )

    id                 = Column(Integer, primary_key=True, index=True, autoincrement=True)
    plate_number       = Column(String(20),  nullable=True,  index=True)
    camera_id          = Column(
        String(50),
        ForeignKey("cameras.camera_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    timestamp          = Column(DateTime(timezone=True), nullable=False, index=True)
    vehicle_type       = Column(String(30),  nullable=True)
    vehicle_confidence = Column(Float,       nullable=True)
    plate_confidence   = Column(Float,       nullable=True)
    ocr_confidence     = Column(Float,       nullable=True)
    image_path         = Column(String(500), nullable=True)
    created_at         = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationship – back to Camera
    camera = relationship("Camera", back_populates="events")

    def __repr__(self) -> str:
        return (
            f"<VehicleEvent id={self.id} plate={self.plate_number!r} "
            f"camera={self.camera_id!r} ts={self.timestamp}>"
        )
