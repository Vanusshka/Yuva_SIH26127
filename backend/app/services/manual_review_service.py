"""
Manual Review Service — Changes 5+6

Handles:
  1. Creating manual review items for LOW-confidence plate reads
  2. Querying pending reviews
  3. Submitting review decisions (CONFIRMED / REJECTED / EDITED)

Rules (Change 5):
  LOW-confidence reads NEVER auto-trigger blacklist alerts.
  They enter this queue for human verification.
  Only after a CONFIRMED or EDITED decision can blacklist matching happen.

No fake data: every review item traces back to a real detection event.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.manual_review import ManualReview
from app.models.plate_result  import ConsensuResult, PlateStatus

logger = logging.getLogger(__name__)

# Valid review statuses
REVIEW_PENDING   = "PENDING"
REVIEW_CONFIRMED = "CONFIRMED"
REVIEW_REJECTED  = "REJECTED"
REVIEW_EDITED    = "EDITED"


# ── Create a review item ──────────────────────────────────────────────────────

def create_review_item(
    db              : Session,
    camera_id       : str,
    timestamp       : datetime,
    vehicle_type    : Optional[str],
    vehicle_category: Optional[str],
    consensus       : ConsensuResult,
    source_file     : str,
    frame_number    : int,
    reason          : str = "low_confidence",
) -> ManualReview:
    """
    Insert a new manual review item.
    Called whenever a LOW-confidence read is detected so it doesn't auto-alert.
    """
    item = ManualReview(
        camera_id          = camera_id,
        timestamp          = timestamp,
        vehicle_type       = vehicle_type,
        vehicle_category   = vehicle_category,
        ocr_plate_text     = consensus.display_text,
        ocr_confidence     = consensus.ocr_confidence,
        confidence_tier    = consensus.confidence_tier,
        agreement_rate     = consensus.agreement_rate,
        valid_ocr_reads    = consensus.valid_ocr_reads,
        matching_ocr_reads = consensus.matching_ocr_reads,
        source_file        = source_file,
        frame_number       = frame_number,
        track_id           = consensus.track_id,
        reason             = reason,
        review_status      = REVIEW_PENDING,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    logger.info(
        "[ManualReview] Created review id=%d plate=%r tier=%s reason=%s",
        item.id, item.ocr_plate_text, item.confidence_tier, reason,
    )
    return item


# ── Query reviews ─────────────────────────────────────────────────────────────

def get_pending_reviews(
    db      : Session,
    limit   : int = 50,
    offset  : int = 0,
) -> List[ManualReview]:
    """Return all PENDING review items, newest first."""
    return (
        db.query(ManualReview)
          .filter(ManualReview.review_status == REVIEW_PENDING)
          .order_by(ManualReview.created_at.desc())
          .offset(offset)
          .limit(limit)
          .all()
    )


def get_all_reviews(
    db      : Session,
    status  : Optional[str] = None,
    limit   : int = 100,
    offset  : int = 0,
) -> List[ManualReview]:
    """Return review items with optional status filter."""
    q = db.query(ManualReview)
    if status:
        q = q.filter(ManualReview.review_status == status.upper())
    return q.order_by(ManualReview.created_at.desc()).offset(offset).limit(limit).all()


def get_review_by_id(db: Session, review_id: int) -> Optional[ManualReview]:
    return db.query(ManualReview).filter(ManualReview.id == review_id).first()


# ── Submit a decision ─────────────────────────────────────────────────────────

def submit_decision(
    db           : Session,
    review_id    : int,
    decision     : str,           # CONFIRMED | REJECTED | EDITED
    reviewed_plate: Optional[str] = None,
    notes        : Optional[str]  = None,
) -> ManualReview:
    """
    Record a reviewer decision.

    Parameters
    ----------
    review_id     : ID of the ManualReview row
    decision      : CONFIRMED | REJECTED | EDITED
    reviewed_plate: Required when decision == EDITED (corrected plate text)
    notes         : Optional reviewer notes

    Raises ValueError on invalid decision or missing plate for EDITED.
    """
    decision = decision.upper()
    if decision not in (REVIEW_CONFIRMED, REVIEW_REJECTED, REVIEW_EDITED):
        raise ValueError(f"Invalid decision '{decision}'")
    if decision == REVIEW_EDITED and not reviewed_plate:
        raise ValueError("reviewed_plate is required when decision is EDITED")

    item = get_review_by_id(db, review_id)
    if item is None:
        raise ValueError(f"Review id={review_id} not found")
    if item.review_status != REVIEW_PENDING:
        raise ValueError(f"Review id={review_id} is already {item.review_status}")

    item.review_status = decision
    item.reviewed_plate = reviewed_plate or (
        item.ocr_plate_text if decision == REVIEW_CONFIRMED else None
    )
    item.reviewer_notes = notes
    item.reviewed_at    = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    logger.info(
        "[ManualReview] Decision id=%d: %s → plate=%r",
        review_id, decision, item.reviewed_plate,
    )
    return item


# ── Blacklist safety gate (Change 5) ─────────────────────────────────────────

def should_auto_alert(confidence_tier: str) -> bool:
    """
    Change 5: Return True only when the confidence tier meets the minimum
    threshold for automatic blacklist alerting.

    LOW-confidence reads MUST NOT auto-trigger alerts.
    The threshold is configured in config.py as BLACKLIST_MIN_TIER_FOR_ALERT.

    Tier hierarchy: LOW < MEDIUM < HIGH

    Examples with default config (BLACKLIST_MIN_TIER_FOR_ALERT = "MEDIUM"):
      HIGH   → True   (allowed to auto-alert)
      MEDIUM → True   (allowed to auto-alert)
      LOW    → False  (goes to manual review queue)
    """
    from app.config import BLACKLIST_MIN_TIER_FOR_ALERT
    _TIER_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    min_rank = _TIER_RANK.get(BLACKLIST_MIN_TIER_FOR_ALERT.upper(), 1)
    item_rank = _TIER_RANK.get(confidence_tier.upper(), 0)
    return item_rank >= min_rank
