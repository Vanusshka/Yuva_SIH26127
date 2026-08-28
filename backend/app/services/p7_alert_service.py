"""
Phase 7 Combined Alert Service

Only meaningful, actionable alerts are generated:
  - BLACKLISTED_VEHICLE  : plate matches demo blacklist (medium/high confidence)
  - CONGESTION           : high/severe traffic density at a camera
  - IMPOSSIBLE_TRAJECTORY: physically impossible multi-camera speed
  - SUSPICIOUS_TRAJECTORY: suspicious multi-camera movement
  - FREQUENT_SIGHTINGS   : same plate seen >= 10 times in one hour
  - COMPLIANCE_ANOMALY   : plate region detected but unreadable (max 5, one per camera)

Suppressed (noise):
  - LOW_CONFIDENCE_ANPR  : already routed to manual review queue
  - Compliance alerts with no plate region (too common, low signal)
  - Duplicate compliance alerts for the same camera
"""

from __future__ import annotations

import logging
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
from app.utils.metadata_loader import is_blacklisted

logger = logging.getLogger(__name__)

_LOW_CONF_THRESHOLD       = 0.50
_FREQUENT_SIGHTINGS_LIMIT = 10


def _severity_rank(sev: str) -> int:
    return {"CRITICAL": 3, "WARNING": 2, "INFO": 1}.get(sev, 0)


# --------------------------------------------------------------------------- #
#  Blacklist alerts (confidence-gated)                                         #
# --------------------------------------------------------------------------- #

def _blacklist_alerts(db: Session) -> List[CombinedAlertItem]:
    """
    Check every distinct plate seen in the last 24 hours against the blacklist.
    LOW-confidence reads are skipped (routed to manual review instead).
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

        effective_tier = (tier or "LOW").upper()

        if not should_auto_alert(effective_tier):
            logger.info(
                "[AlertService] Blacklist match %r suppressed (tier=%s) -> manual review",
                plate, effective_tier,
            )
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


# --------------------------------------------------------------------------- #
#  Congestion alerts                                                            #
# --------------------------------------------------------------------------- #

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
                message=(
                    f"High traffic density at {item.location_name} "
                    f"({item.camera_id}): {item.vehicle_count} vehicles/h."
                ),
                timestamp=now, demo_data=False,
                metadata={"vehicle_count": item.vehicle_count,
                          "traffic_density": item.traffic_density},
            ))
        elif item.traffic_density == "SEVERE":
            alerts.append(CombinedAlertItem(
                alert_type="CONGESTION", severity="CRITICAL",
                camera_id=item.camera_id, plate_number=None,
                message=(
                    f"SEVERE congestion at {item.location_name} "
                    f"({item.camera_id}): {item.vehicle_count} vehicles/h."
                ),
                timestamp=now, demo_data=False,
                metadata={"vehicle_count": item.vehicle_count,
                          "traffic_density": item.traffic_density},
            ))
    return alerts


# --------------------------------------------------------------------------- #
#  Trajectory anomaly alerts                                                   #
# --------------------------------------------------------------------------- #

def _trajectory_anomaly_alerts(db: Session) -> List[CombinedAlertItem]:
    """
    Only check plates seen at >= 2 distinct cameras in the last 24 h.
    Caps at 20 candidates to prevent timeouts.
    """
    alerts: List[CombinedAlertItem] = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    multi_cam_plates = (
        db.query(Detection.plate_number)
          .filter(Detection.timestamp >= cutoff)
          .group_by(Detection.plate_number)
          .having(func.count(func.distinct(Detection.camera_id)) >= 2)
          .all()
    )

    for (plate,) in multi_cam_plates[:20]:
        try:
            traj = reconstruct(db, plate)
        except Exception:
            continue
        if traj.status == MovementStatus.IMPOSSIBLE:
            ts = traj.statistics.last_seen or datetime.now(timezone.utc)
            alerts.append(CombinedAlertItem(
                alert_type="IMPOSSIBLE_TRAJECTORY", severity="CRITICAL",
                camera_id=(
                    traj.statistics.cameras_visited[-1]
                    if traj.statistics.cameras_visited else None
                ),
                plate_number=plate,
                message=(
                    f"IMPOSSIBLE trajectory for {plate}: "
                    f"{traj.statistics.average_speed_kmh:.1f} km/h across "
                    f"{len(traj.statistics.cameras_visited)} cameras."
                ),
                timestamp=ts, demo_data=False,
                metadata=traj.statistics.model_dump(),
            ))
        elif traj.status == MovementStatus.SUSPICIOUS:
            ts = traj.statistics.last_seen or datetime.now(timezone.utc)
            alerts.append(CombinedAlertItem(
                alert_type="SUSPICIOUS_TRAJECTORY", severity="WARNING",
                camera_id=(
                    traj.statistics.cameras_visited[-1]
                    if traj.statistics.cameras_visited else None
                ),
                plate_number=plate,
                message=(
                    f"Suspicious trajectory for {plate}: "
                    f"{traj.statistics.average_speed_kmh:.1f} km/h."
                ),
                timestamp=ts, demo_data=False,
                metadata=traj.statistics.model_dump(),
            ))
    return alerts


# --------------------------------------------------------------------------- #
#  Frequent sightings                                                          #
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
#  Compliance anomaly — meaningful only (max 5, one per camera)               #
# --------------------------------------------------------------------------- #

def _compliance_anomaly_alerts(db: Session) -> List[CombinedAlertItem]:
    """
    Only fire when a plate REGION was detected but text could not be read.
    This is the genuinely suspicious case (obscured/dirty/non-standard plate).

    Rules to keep list clean:
      - plate_confidence > 0.30  : a real plate region was found
      - vehicle_confidence >= 0.60: trust the vehicle detection
      - One alert per camera     : no duplicate spam
      - Max 5 alerts             : never floods the list
    """
    cutoff            = datetime.now(timezone.utc) - timedelta(hours=6)
    _MIN_VEHICLE_CONF = 0.60
    _MAX_ALERTS       = 5

    alerts: List[CombinedAlertItem] = []
    seen_cameras: set = set()

    rows = (
        db.query(VehicleEvent)
          .filter(
              VehicleEvent.timestamp >= cutoff,
              VehicleEvent.plate_number.is_(None),
              VehicleEvent.vehicle_type.isnot(None),
              VehicleEvent.vehicle_type != "unknown",
              VehicleEvent.plate_confidence.isnot(None),
              VehicleEvent.plate_confidence > 0.30,
              VehicleEvent.vehicle_confidence.isnot(None),
              VehicleEvent.vehicle_confidence >= _MIN_VEHICLE_CONF,
          )
          .order_by(VehicleEvent.timestamp.desc())
          .limit(50)
          .all()
    )

    for ev in rows:
        if len(alerts) >= _MAX_ALERTS:
            break
        if ev.camera_id in seen_cameras:
            continue
        seen_cameras.add(ev.camera_id)

        alerts.append(CombinedAlertItem(
            alert_type   = "COMPLIANCE_ANOMALY",
            severity     = "WARNING",
            camera_id    = ev.camera_id,
            plate_number = None,
            message      = (
                f"Vehicle ({ev.vehicle_type}) at {ev.camera_id}: "
                f"plate region found (conf={ev.plate_confidence:.2f}) "
                f"but text unreadable — may be obscured or non-standard."
            ),
            timestamp    = ev.timestamp,
            demo_data    = False,
            metadata     = {
                "reason_code"       : "PLATE_REGION_UNREADABLE",
                "vehicle_type"      : ev.vehicle_type,
                "vehicle_confidence": ev.vehicle_confidence,
                "plate_confidence"  : ev.plate_confidence,
            },
        ))

    return alerts


# --------------------------------------------------------------------------- #
#  Public API                                                                  #
# --------------------------------------------------------------------------- #

def get_combined_alerts(db: Session, limit: int = 50) -> CombinedAlertsResponse:
    """
    Merge all alert sources, sort by severity (CRITICAL first), cap at limit.
    """
    all_alerts: List[CombinedAlertItem] = []

    generators = [
        ("blacklist",   _blacklist_alerts),
        ("congestion",  _congestion_alerts),
        ("trajectory",  _trajectory_anomaly_alerts),
        ("frequent",    _frequent_sightings_alerts),
        ("compliance",  _compliance_anomaly_alerts),
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
