"""
Phase 7 Combined Alert Service â€” with Changes 5, 9, 10

Changes in this version:
  Change 5: Blacklist safety gate â€” LOW confidence plates do NOT auto-alert.
            They are sent to the manual review queue instead.
  Change 9: COMPLIANCE_ANOMALY alert generator added.
  Change 10: All alert types surfaced to the GET /alerts endpoint.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import List

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.detection import Detection
from app.models.vehicle_event import VehicleEvent
from app.schemas.p7_alerts import CombinedAlertItem, CombinedAlertsResponse
from app.services.analytics_service import get_traffic_density
from app.trajectory.engine import reconstruct
from app.trajectory.anomaly import MovementStatus
from app.utils.metadata_loader import is_blacklisted, load_blacklist

logger = logging.getLogger(__name__)

# Thresholds
_LOW_CONF_THRESHOLD       = 0.50
_FREQUENT_SIGHTINGS_LIMIT = 10


def _severity_rank(sev: str) -> int:
    return {"CRITICAL": 3, "WARNING": 2, "INFO": 1}.get(sev, 0)


# â”€â”€ Change 5: Blacklist alerts with confidence gate â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _blacklist_alerts(db: Session) -> List[CombinedAlertItem]:
    """
    Check every distinct plate seen in the last 24 hours against the demo blacklist.

    Change 5: LOW-confidence reads are SKIPPED here (they go to manual review).
    Only MEDIUM or HIGH confidence plates trigger a blacklist alert.
    """
    from app.services.manual_review_service import should_auto_alert, create_review_item
    from app.models.plate_result import ConsensuResult, PlateStatus

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    recent_events = (
        db.query(
            VehicleEvent.plate_number,
            VehicleEvent.camera_id,
            VehicleEvent.timestamp,
            VehicleEvent.confidence_tier,
            VehicleEvent.ocr_confidence,
            VehicleEvent.agreement_rate,
            VehicleEvent.valid_ocr_reads,
            VehicleEvent.matching_ocr_reads,
            VehicleEvent.vehicle_type,
            VehicleEvent.vehicle_category,
        )
        .filter(
            VehicleEvent.timestamp >= cutoff,
            VehicleEvent.plate_number.isnot(None),
        )
        .order_by(VehicleEvent.plate_number, VehicleEvent.timestamp.desc())
        .all()
    )

    seen: set = set()
    alerts: List[CombinedAlertItem] = []

    for row in recent_events:
        plate, cam_id, ts, tier, ocr_conf, agr, valid_r, match_r, vtype, vcat = row
        if plate in seen:
            continue
        seen.add(plate)

        entry = is_blacklisted(plate)
        if not entry:
            continue

        # Change 5 safety gate: resolve tier to "LOW" when unknown
        effective_tier = (tier or "LOW").upper()

        if not should_auto_alert(effective_tier):
            # LOW confidence â†’ send to manual review, not an auto-alert
            logger.info(
                "[AlertService] Blacklist match %r suppressed (tier=%s) â†’ manual review",
                plate, effective_tier,
            )
            # Attempt to create a manual review item (best-effort â€” may already exist)
            try:
                from app.models.manual_review import ManualReview
                existing = (
                    db.query(ManualReview)
                      .filter(
                          ManualReview.ocr_plate_text == plate,
                          ManualReview.review_status == "PENDING",
                          ManualReview.created_at >= cutoff,
                      )
                      .first()
                )
                if not existing:
                    # Build a minimal ConsensuResult for the review item
                    dummy = ConsensuResult(
                        track_id="alert_check",
                        plate_number=plate,
                        partial_text=None,
                        status=PlateStatus.LOW_CONFIDENCE,
                        ocr_confidence=ocr_conf or 0.0,
                        plate_confidence=0.0,
                        quality_score=0.0,
                        sightings=valid_r or 0,
                        supporting_frames=[],
                        preprocessing_method="unknown",
                        valid_ocr_reads=valid_r or 0,
                        matching_ocr_reads=match_r or 0,
                        agreement_rate=agr or 0.0,
                        confidence_tier=effective_tier,
                    )
                    create_review_item(
                        db=db,
                        camera_id=cam_id,
                        timestamp=ts,
                        vehicle_type=vtype,
                        vehicle_category=vcat,
                        consensus=dummy,
                        source_file="alert_engine",
                        frame_number=0,
                        reason="possible_blacklist_match",
                    )
            except Exception as exc:
                logger.warning("[AlertService] Could not create review item: %s", exc)
            continue

        # Confidence is sufficient â€” fire the alert
        alerts.append(
            CombinedAlertItem(
                alert_type   = "BLACKLISTED_VEHICLE",
                severity     = "CRITICAL",
                camera_id    = cam_id,
                plate_number = plate,
                message      = (
                    f"[DEMO] Blacklisted plate {plate} detected at {cam_id} "
                    f"(confidence={effective_tier}). "
                    f"Reason: {entry.get('reason', 'N/A')}"
                ),
                timestamp    = ts,
                demo_data    = True,
                metadata     = {**entry, "confidence_tier": effective_tier,
                                "agreement_rate": agr},
            )
        )

    return alerts


def _congestion_alerts(db: Session) -> List[CombinedAlertItem]:
    now    = datetime.now(timezone.utc)
    alerts : List[CombinedAlertItem] = []
    try:
        density = get_traffic_density(db, window_hours=1)
    except Exception as exc:
        logger.warning("[AlertService] Traffic density query failed: %s", exc)
        return alerts
    for item in density.items:
        if item.traffic_density == "HIGH":
            alerts.append(CombinedAlertItem(
                alert_type="CONGESTION", severity="WARNING",
                camera_id=item.camera_id, plate_number=None,
                message=f"High traffic density at {item.location_name} ({item.camera_id}): {item.vehicle_count} vehicles/h.",
                timestamp=now, demo_data=False,
                metadata={"vehicle_count": item.vehicle_count, "traffic_density": item.traffic_density},
            ))
        elif item.traffic_density == "SEVERE":
            alerts.append(CombinedAlertItem(
                alert_type="CONGESTION", severity="CRITICAL",
                camera_id=item.camera_id, plate_number=None,
                message=f"SEVERE congestion at {item.location_name} ({item.camera_id}): {item.vehicle_count} vehicles/h.",
                timestamp=now, demo_data=False,
                metadata={"vehicle_count": item.vehicle_count, "traffic_density": item.traffic_density},
            ))
    return alerts


def _trajectory_anomaly_alerts(db: Session) -> List[CombinedAlertItem]:
    alerts: List[CombinedAlertItem] = []
    plates = db.query(Detection.plate_number).distinct().all()
    for (plate,) in plates:
        try:
            traj = reconstruct(db, plate)
        except Exception:
            continue
        if traj.status == MovementStatus.IMPOSSIBLE:
            ts = traj.statistics.last_seen or datetime.now(timezone.utc)
            alerts.append(CombinedAlertItem(
                alert_type="IMPOSSIBLE_TRAJECTORY", severity="CRITICAL",
                camera_id=traj.statistics.cameras_visited[-1] if traj.statistics.cameras_visited else None,
                plate_number=plate,
                message=f"IMPOSSIBLE trajectory for {plate}: {traj.statistics.average_speed_kmh:.1f} km/h across {len(traj.statistics.cameras_visited)} cameras.",
                timestamp=ts, demo_data=False,
                metadata=traj.statistics.model_dump(),
            ))
        elif traj.status == MovementStatus.SUSPICIOUS:
            ts = traj.statistics.last_seen or datetime.now(timezone.utc)
            alerts.append(CombinedAlertItem(
                alert_type="SUSPICIOUS_TRAJECTORY", severity="WARNING",
                camera_id=traj.statistics.cameras_visited[-1] if traj.statistics.cameras_visited else None,
                plate_number=plate,
                message=f"Suspicious trajectory for {plate}: {traj.statistics.average_speed_kmh:.1f} km/h.",
                timestamp=ts, demo_data=False,
                metadata=traj.statistics.model_dump(),
            ))
    return alerts


def _low_confidence_alerts(db: Session) -> List[CombinedAlertItem]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
    alerts: List[CombinedAlertItem] = []
    rows = (
        db.query(VehicleEvent)
          .filter(
              VehicleEvent.timestamp >= cutoff,
              VehicleEvent.ocr_confidence.isnot(None),
              VehicleEvent.ocr_confidence < _LOW_CONF_THRESHOLD,
              VehicleEvent.plate_number.isnot(None),
          )
          .order_by(VehicleEvent.timestamp.desc())
          .limit(20).all()
    )
    for ev in rows:
        alerts.append(CombinedAlertItem(
            alert_type="LOW_CONFIDENCE_ANPR", severity="INFO",
            camera_id=ev.camera_id, plate_number=ev.plate_number,
            message=f"Low-confidence ANPR at {ev.camera_id}: '{ev.plate_number}' conf={ev.ocr_confidence:.2f}. Manual verification recommended.",
            timestamp=ev.timestamp, demo_data=False,
            metadata={"ocr_confidence": ev.ocr_confidence, "confidence_tier": ev.confidence_tier},
        ))
    return alerts


def _frequent_sightings_alerts(db: Session) -> List[CombinedAlertItem]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    alerts: List[CombinedAlertItem] = []
    rows = (
        db.query(Detection.plate_number, func.count(Detection.id).label("cnt"))
          .filter(Detection.timestamp >= cutoff)
          .group_by(Detection.plate_number)
          .having(func.count(Detection.id) >= _FREQUENT_SIGHTINGS_LIMIT)
          .all()
    )
    now = datetime.now(timezone.utc)
    for plate, cnt in rows:
        alerts.append(CombinedAlertItem(
            alert_type="FREQUENT_SIGHTINGS", severity="WARNING",
            camera_id=None, plate_number=plate,
            message=f"Plate {plate} seen {cnt} times in the last hour.",
            timestamp=now, demo_data=False,
            metadata={"sightings_in_last_hour": cnt},
        ))
    return alerts


# â”€â”€ Change 9: COMPLIANCE_ANOMALY alerts â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _compliance_anomaly_alerts(db: Session) -> List[CombinedAlertItem]:
    """
    Change 9: Generate COMPLIANCE_ANOMALY alerts for vehicles detected
    without any usable plate read within the last 6 hours.

    Trigger conditions:
      - VehicleEvent row exists (vehicle was detected)
      - plate_number IS NULL after pipeline processing
      - vehicle_type is not 'unknown' (rule out contour noise)

    Two reason codes:
      NO_PLATE_DETECTED          â€” pipeline ran, returned no plate region
      POSSIBLE_OBSCURED_PLATE    â€” plate region found but OCR produced nothing

    We do NOT claim a plate is illegal or missing â€” only that no plate
    was readable. The honest reason code is included.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
    alerts: List[CombinedAlertItem] = []

    rows = (
        db.query(VehicleEvent)
          .filter(
              VehicleEvent.timestamp >= cutoff,
              VehicleEvent.plate_number.is_(None),
              VehicleEvent.vehicle_type.isnot(None),
              VehicleEvent.vehicle_type != "unknown",
          )
          .order_by(VehicleEvent.timestamp.desc())
          .limit(30)
          .all()
    )

    for ev in rows:
        # Distinguish: was a plate region detected at all?
        # plate_confidence is set if the plate detector found a region
        if ev.plate_confidence is not None and ev.plate_confidence > 0:
            reason_code = "POSSIBLE_OBSCURED_OR_NONSTANDARD_PLATE"
            message = (
                f"Vehicle ({ev.vehicle_type}) detected at {ev.camera_id}: "
                f"plate region found (conf={ev.plate_confidence:.2f}) "
                f"but text could not be extracted. "
                f"Plate may be obscured, non-standard, or at an extreme angle."
            )
        else:
            reason_code = "NO_PLATE_DETECTED"
            message = (
                f"Vehicle ({ev.vehicle_type}) detected at {ev.camera_id}: "
                f"no license plate region detected. "
                f"Plate may be missing, obscured, or outside camera view."
            )

        alerts.append(CombinedAlertItem(
            alert_type   = "COMPLIANCE_ANOMALY",
            severity     = "WARNING",
            camera_id    = ev.camera_id,
            plate_number = None,
            message      = message,
            timestamp    = ev.timestamp,
            demo_data    = False,
            metadata     = {
                "reason_code"       : reason_code,
                "vehicle_type"      : ev.vehicle_type,
                "vehicle_category"  : ev.vehicle_category,
                "vehicle_confidence": ev.vehicle_confidence,
                "plate_confidence"  : ev.plate_confidence,
            },
        ))

    return alerts


# â”€â”€ public API â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def get_combined_alerts(db: Session, limit: int = 50) -> CombinedAlertsResponse:
    """
    Merge all alert sources, sort by severity (CRITICAL first).
    """
    all_alerts: List[CombinedAlertItem] = []

    generators = [
        ("blacklist",    _blacklist_alerts),
        ("congestion",   _congestion_alerts),
        ("trajectory",   _trajectory_anomaly_alerts),
        ("low_conf",     _low_confidence_alerts),
        ("frequent",     _frequent_sightings_alerts),
        ("compliance",   _compliance_anomaly_alerts),   # Change 9
    ]

    for name, fn in generators:
        try:
            all_alerts.extend(fn(db))
        except Exception as exc:
            logger.warning("[AlertService] %s alert generator failed: %s", name, exc)

    all_alerts.sort(key=lambda a: _severity_rank(a.severity), reverse=True)
    all_alerts = all_alerts[:limit]

    critical = sum(1 for a in all_alerts if a.severity == "CRITICAL")
    warning  = sum(1 for a in all_alerts if a.severity == "WARNING")
    info     = sum(1 for a in all_alerts if a.severity == "INFO")

    return CombinedAlertsResponse(
        total_alerts   = len(all_alerts),
        critical_count = critical,
        warning_count  = warning,
        info_count     = info,
        alerts         = all_alerts,
    )

