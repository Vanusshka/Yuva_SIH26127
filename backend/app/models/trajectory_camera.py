"""
TrajectoryCamera ORM model – Phase 4

Extended camera model specifically for trajectory reconstruction.
Adds road_name, direction, and location_name fields that Phase 3's
basic Camera model omits.  Lives in a separate table so Phase 3 is
untouched.
"""

from __future__ import annotations
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Float, DateTime,
    Enum as SAEnum, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class TrajectoryCamera(Base):
    __tablename__ = "trajectory_cameras"
    __table_args__ = (
        UniqueConstraint("camera_id", name="uq_traj_camera_id"),
    )

    id            = Column(Integer,       primary_key=True, autoincrement=True)
    camera_id     = Column(String(50),    nullable=False, unique=True, index=True)
    location_name = Column(String(200),   nullable=False)
    road_name     = Column(String(200),   nullable=True)
    direction     = Column(String(50),    nullable=True)   # e.g. "NORTH", "SOUTH_BOUND"
    latitude      = Column(Float,         nullable=False)
    longitude     = Column(Float,         nullable=False)
    created_at    = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Back-reference from Detection
    detections = relationship(
        "Detection",
        back_populates="camera",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    def __repr__(self) -> str:
        return f"<TrajectoryCamera {self.camera_id!r} @ {self.location_name!r}>"
