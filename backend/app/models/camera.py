"""
Camera ORM model.

Represents a physical ANPR camera installed at a city location.
One camera → many VehicleEvents.
"""

from __future__ import annotations
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Enum as SAEnum, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class CameraStatus(str, enum.Enum):
    ACTIVE   = "ACTIVE"
    INACTIVE = "INACTIVE"


class Camera(Base):
    __tablename__ = "cameras"
    __table_args__ = (
        UniqueConstraint("camera_id", name="uq_camera_camera_id"),
    )

    id         = Column(Integer, primary_key=True, index=True, autoincrement=True)
    camera_id  = Column(String(50),  nullable=False, unique=True, index=True)
    name       = Column(String(200), nullable=False)
    latitude   = Column(Float,       nullable=False)
    longitude  = Column(Float,       nullable=False)
    address    = Column(String(500), nullable=True)
    status     = Column(
        SAEnum(CameraStatus, name="camera_status"),
        nullable=False,
        default=CameraStatus.ACTIVE,
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationship – back-populated from VehicleEvent
    events = relationship(
        "VehicleEvent",
        back_populates="camera",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    def __repr__(self) -> str:
        return f"<Camera id={self.id} camera_id={self.camera_id!r} status={self.status}>"
