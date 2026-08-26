"""
Detection ORM model – Phase 4

Stores raw ANPR detections fed into the trajectory engine.
Separate from Phase 3's VehicleEvent so the trajectory pipeline
can be tested and seeded independently.
"""

from __future__ import annotations
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Index,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Detection(Base):
    __tablename__ = "detections"
    __table_args__ = (
        Index("ix_det_plate_ts",  "plate_number", "timestamp"),
        Index("ix_det_cam_ts",    "camera_id",    "timestamp"),
    )

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    plate_number        = Column(String(20),  nullable=False, index=True)
    camera_id           = Column(
        String(50),
        ForeignKey("trajectory_cameras.camera_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    timestamp           = Column(DateTime(timezone=True), nullable=False, index=True)
    detection_confidence= Column(Float, nullable=True)
    created_at          = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    camera = relationship("TrajectoryCamera", back_populates="detections")

    def __repr__(self) -> str:
        return (
            f"<Detection id={self.id} plate={self.plate_number!r} "
            f"cam={self.camera_id!r} ts={self.timestamp}>"
        )
