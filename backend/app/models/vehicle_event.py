"""
VehicleEvent ORM model.

Each ANPR detection creates one row here.
Old events are never overwritten; every sighting is a new record.

Change 4 (reliability upgrade):
  Added fields: confidence_tier, agreement_rate, valid_ocr_reads,
                matching_ocr_reads, vehicle_category
  These are nullable so existing rows remain valid (backward compatible).
  SQLite: new columns added via ALTER TABLE in migrate_v2() called from init_db().
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
        Index("ix_vehicle_events_plate_ts",   "plate_number", "timestamp"),
        Index("ix_vehicle_events_cam_ts",      "camera_id",    "timestamp"),
        Index("ix_vehicle_events_conf_tier",   "confidence_tier"),   # Change 4
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

    # ── Change 4: multi-frame OCR evidence fields ─────────────────────────────
    # All nullable so existing rows remain valid without data migration.

    # Confidence tier derived from multi-frame agreement: HIGH | MEDIUM | LOW
    # Thresholds defined in config.py (OCR_HIGH_AGREEMENT_THRESH, etc.)
    confidence_tier    = Column(String(10),  nullable=True, index=True)

    # Number of OCR reads that had enough characters to be considered valid
    # (char_count >= MIN_CHARS_PARTIAL)
    valid_ocr_reads    = Column(Integer,     nullable=True)

    # Number of valid reads that matched the consensus plate text exactly
    matching_ocr_reads = Column(Integer,     nullable=True)

    # agreement_rate = matching_ocr_reads / valid_ocr_reads  (0.0–1.0)
    # Stored for analytics and audit; NULL when valid_ocr_reads == 0
    agreement_rate     = Column(Float,       nullable=True)

    # Change 1: vehicle category tag ("car_commercial" | "two_wheeler" | "unknown")
    vehicle_category   = Column(String(20),  nullable=True)

    # Relationship – back to Camera
    camera = relationship("Camera", back_populates="events")

    def __repr__(self) -> str:
        return (
            f"<VehicleEvent id={self.id} plate={self.plate_number!r} "
            f"camera={self.camera_id!r} tier={self.confidence_tier!r} "
            f"ts={self.timestamp}>"
        )
