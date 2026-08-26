"""
ManualReview ORM model — Change 6

Stores plate reads that require human verification before any
automated action (e.g. blacklist alert) can be triggered.

Populated when:
  - confidence_tier == LOW
  - A LOW-confidence plate resembles a blacklisted plate
  - Any detection flagged by the compliance anomaly engine

Review workflow:
  PENDING   → operator reviews evidence
  CONFIRMED → operator confirmed the plate text
  REJECTED  → operator rejected (plate not readable / wrong)
  EDITED    → operator manually corrected the plate text

A CONFIRMED or EDITED item with the corrected plate is then eligible
for blacklist matching.  A REJECTED item is never matched.

All fields come from real pipeline data — never fabricated.
"""

from __future__ import annotations
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Index
from app.database import Base


class ManualReview(Base):
    __tablename__ = "manual_reviews"
    __table_args__ = (
        Index("ix_mr_status",      "review_status"),
        Index("ix_mr_camera_ts",   "camera_id", "created_at"),
        Index("ix_mr_plate",       "ocr_plate_text"),
    )

    id               = Column(Integer, primary_key=True, autoincrement=True)

    # ── Source evidence ────────────────────────────────────────────────────────
    camera_id        = Column(String(50),  nullable=False, index=True)
    timestamp        = Column(DateTime(timezone=True), nullable=False)
    vehicle_type     = Column(String(30),  nullable=True)
    vehicle_category = Column(String(20),  nullable=True)  # car_commercial | two_wheeler

    # OCR result from pipeline (NOT operator-edited)
    ocr_plate_text   = Column(String(20),  nullable=True)
    ocr_confidence   = Column(Float,       nullable=True)
    confidence_tier  = Column(String(10),  nullable=False)  # LOW | MEDIUM | HIGH
    agreement_rate   = Column(Float,       nullable=True)
    valid_ocr_reads  = Column(Integer,     nullable=True)
    matching_ocr_reads = Column(Integer,   nullable=True)

    # Source reference for audit (frame number, source video)
    source_file      = Column(String(200), nullable=True)
    frame_number     = Column(Integer,     nullable=True)
    track_id         = Column(String(20),  nullable=True)

    # Reason why this item entered manual review
    # e.g. "low_confidence", "possible_blacklist_match", "compliance_anomaly"
    reason           = Column(String(50),  nullable=False, default="low_confidence")

    # ── Review outcome ─────────────────────────────────────────────────────────
    # PENDING | CONFIRMED | REJECTED | EDITED
    review_status    = Column(String(20),  nullable=False, default="PENDING", index=True)

    # Plate text after operator review (may differ from ocr_plate_text)
    # Only populated when review_status IN ('CONFIRMED', 'EDITED')
    reviewed_plate   = Column(String(20),  nullable=True)

    # Free-text notes from the reviewer
    reviewer_notes   = Column(Text,        nullable=True)

    reviewed_at      = Column(DateTime(timezone=True), nullable=True)
    created_at       = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return (
            f"<ManualReview id={self.id} plate={self.ocr_plate_text!r} "
            f"tier={self.confidence_tier!r} status={self.review_status!r}>"
        )
