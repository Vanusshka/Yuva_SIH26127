"""
Phase 7 Combined Alert Service

Merges three alert sources:
  1. Blacklisted vehicles  – from data/metadata/blacklist.json (DEMO DATA)
  2. Congestion alerts     – from Phase-5 analytics (HIGH/SEVERE cameras)
  3. Trajectory anomalies  – from Phase-4 trajectory engine (SUSPICIOUS/IMPOSSIBLE)
  4. Low-confidence ANPR   – from Phase-3 VehicleEvent table
  5. Frequent sightings    – plate seen >= threshold times in 1 hour

Does NOT modify any existing Phase-5 alert logic.
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
_FREQUENT_SIGHTINGS_LIMIT = 10       # same plate >= N times in 1 hour → alert


# ── helper ────────────────────────────────────────────────────────────────────

def _severity_rank(sev: str) -> int:
    return {"CRITICAL": 3, "WARNING": 2, "INFO": 1}.get(sev, 0)


# ── alert generators ──────────────────────────────────────────────────────────

def _blacklist_alerts(db: Session) -> List[CombinedAlertItem]:
    """
    Check every distinct plate seen in the last 24 hours against the demo blacklist.
    Marked demo_data=True – these are SIMULATED records.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    recent_plates = (
        db.query(Detection.plate_number, Detection.camera_id, Detection.timestamp)
          .filter(Detection.timestamp >= cutoff)
          .order_by(Detection.plate_number, Detection.timestamp.desc())
          .all()
    )

    seen: set = set()
    alerts: List[CombinedAlertItem] = []

    for plate, cam_id, ts in recent_plates:
        if plate in seen:
            continue
        seen.add(plate)

        entry = is_blacklisted(plate)
        if entry:
            alerts.append(
                CombinedAlertItem(
                    alert_type   = "BLACKLISTED_VEHICLE",
                    severity     = "CRITICAL",
                    camera_id    = cam_id,
                    plate_number = plate,
                    message      = (
                        f"[DEMO] Blacklisted plate {plate} detected at {cam_id}. "
                        f"Reason: {entry.get('reason', 'N/A')} "
                        f"(Category: {entry.get('category', 'N/A')}, "
                        f"Priority: {entry.get('priority', 'N/A')})"
                    ),
                    timestamp    = ts,
                    demo_data    = True,
                    metadata     = entry,
                )
            )

    return alerts


def _congestion_alerts(db: Session) -> List[CombinedAlertItem]:
    """
    Re-uses Phase-5 traffic density to generate congestion alerts.
    HIGH → WARNING, SEVERE → CRITICAL.
    """
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
                alert_type   = "CONGESTION",
                severity     = "WARNING",
                camera_id    = item.camera_id,
                plate_number = None,
                message      = (
                    f"High traffic density at {item.location_name} ({item.camera_id}): "
                    f"{item.vehicle_count} vehicles in last hour."
                ),
                timestamp    = now,
                demo_data    = False,
                metadata     = {
                    "vehicle_count"  : item.vehicle_count,
                    "traffic_density": item.traffic_density,
                    "location_name"  : item.location_name,
                },
            ))
        elif item.traffic_density == "SEVERE":
            alerts.append(CombinedAlertItem(
                alert_type   = "CONGESTION",
                severity     = "CRITICAL",
                camera_id    = item.camera_id,
                plate_number = None,
                message      = (
                    f"SEVERE traffic congestion at {item.location_name} ({item.camera_id}): "
                    f"{item.vehicle_count} vehicles in last hour."
                ),
                timestamp    = now,
                demo_data    = False,
                metadata     = {
                    "vehicle_count"  : item.vehicle_count,
                    "traffic_density": item.traffic_density,
                    "location_name"  : item.location_name,
                },
            ))

    return alerts


def _trajectory_anomaly_alerts(db: Session) -> List[CombinedAlertItem]:
    """
    Run trajectory reconstruction on every distinct plate and generate
    alerts for SUSPICIOUS and IMPOSSIBLE movements.
    """
    alerts: List[CombinedAlertItem] = []

    plates = (
        db.query(Detection.plate_number)
          .distinct()
          .all()
    )

    for (plate,) in plates:
        try:
            traj = reconstruct(db, plate)
        except Exception:
            continue

        if traj.status == MovementStatus.IMPOSSIBLE:
            ts = traj.statistics.last_seen or datetime.now(timezone.utc)
            alerts.append(CombinedAlertItem(
                alert_type   = "IMPOSSIBLE_TRAJECTORY",
                severity     = "CRITICAL",
                camera_id    = traj.statistics.cameras_visited[-1] if traj.statistics.cameras_visited else None,
                plate_number = plate,
                message      = (
                    f"IMPOSSIBLE trajectory for {plate}: "
                    f"speed {traj.statistics.average_speed_kmh:.1f} km/h or negative time gap. "
                    f"Visited {len(traj.statistics.cameras_visited)} cameras in "
                    f"{traj.statistics.total_duration_minutes:.1f} minutes."
                ),
                timestamp    = ts,
                demo_data    = False,
                metadata     = traj.statistics.model_dump(),
            ))
        elif traj.status == MovementStatus.SUSPICIOUS:
            ts = traj.statistics.last_seen or datetime.now(timezone.utc)
            alerts.append(CombinedAlertItem(
                alert_type   = "SUSPICIOUS_TRAJECTORY",
                severity     = "WARNING",
                camera_id    = traj.statistics.cameras_visited[-1] if traj.statistics.cameras_visited else None,
                plate_number = plate,
                message      = (
                    f"Suspicious trajectory for {plate}: "
                    f"avg speed {traj.statistics.average_speed_kmh:.1f} km/h across "
                    f"{len(traj.statistics.cameras_visited)} cameras."
                ),
                timestamp    = ts,
                demo_data    = False,
                metadata     = traj.statistics.model_dump(),
            ))

    return alerts


def _low_confidence_alerts(db: Session) -> List[CombinedAlertItem]:
    """
    Flag recent vehicle events where OCR confidence was below threshold.
    """
    cutoff  = datetime.now(timezone.utc) - timedelta(hours=6)
    alerts  : List[CombinedAlertItem] = []

    rows = (
        db.query(VehicleEvent)
          .filter(
              VehicleEvent.timestamp >= cutoff,
              VehicleEvent.ocr_confidence.isnot(None),
              VehicleEvent.ocr_confidence < _LOW_CONF_THRESHOLD,
              VehicleEvent.plate_number.isnot(None),
          )
          .order_by(VehicleEvent.timestamp.desc())
          .limit(20)
          .all()
    )

    for ev in rows:
        alerts.append(CombinedAlertItem(
            alert_type   = "LOW_CONFIDENCE_ANPR",
            severity     = "INFO",
            camera_id    = ev.camera_id,
            plate_number = ev.plate_number,
            message      = (
                f"Low-confidence ANPR read at {ev.camera_id}: "
                f"plate '{ev.plate_number}' with OCR confidence "
                f"{ev.ocr_confidence:.2f} (< {_LOW_CONF_THRESHOLD}). "
                "Manual verification recommended."
            ),
            timestamp    = ev.timestamp,
            demo_data    = False,
            metadata     = {
                "ocr_confidence"    : ev.ocr_confidence,
                "plate_confidence"  : ev.plate_confidence,
                "vehicle_type"      : ev.vehicle_type,
            },
        ))

    return alerts


def _frequent_sightings_alerts(db: Session) -> List[CombinedAlertItem]:
    """
    Alert when a plate is seen >= _FREQUENT_SIGHTINGS_LIMIT times in 1 hour.
    This could indicate a vehicle circling or a camera malfunction.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    alerts : List[CombinedAlertItem] = []

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
            alert_type   = "FREQUENT_SIGHTINGS",
            severity     = "WARNING",
            camera_id    = None,
            plate_number = plate,
            message      = (
                f"Plate {plate} seen {cnt} times in the last hour "
                f"(threshold: {_FREQUENT_SIGHTINGS_LIMIT}). "
                "Possible circling vehicle or duplicate detection."
            ),
            timestamp    = now,
            demo_data    = False,
            metadata     = {"sightings_in_last_hour": cnt, "threshold": _FREQUENT_SIGHTINGS_LIMIT},
        ))

    return alerts


# ── public API ────────────────────────────────────────────────────────────────

def get_combined_alerts(db: Session, limit: int = 50) -> CombinedAlertsResponse:
    """
    Merge all alert sources, sort by severity (CRITICAL first), and return up to `limit`.
    """
    all_alerts: List[CombinedAlertItem] = []

    generators = [
        ("blacklist",   _blacklist_alerts),
        ("congestion",  _congestion_alerts),
        ("trajectory",  _trajectory_anomaly_alerts),
        ("low_conf",    _low_confidence_alerts),
        ("frequent",    _frequent_sightings_alerts),
    ]

    for name, fn in generators:
        try:
            all_alerts.extend(fn(db))
        except Exception as exc:
            logger.warning("[AlertService] %s alert generator failed: %s", name, exc)

    # Sort: CRITICAL first, then WARNING, then INFO; within severity by timestamp desc
    all_alerts.sort(
        key=lambda a: (_severity_rank(a.severity) * -1, a.timestamp),
        reverse=False,
    )
    # Correctly: highest severity first
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
