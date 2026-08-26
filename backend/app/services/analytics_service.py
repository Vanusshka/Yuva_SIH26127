"""
Analytics Service – Phase 5.

Queries the Detection + TrajectoryCamera tables to produce
traffic statistics, congestion levels, peak-hour data, and alerts.
Does NOT touch the ANPR pipeline.
"""

from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.detection import Detection
from app.models.trajectory_camera import TrajectoryCamera
from app.schemas.analytics import (
    OverviewResponse,
    TrafficDensityItem, TrafficDensityResponse,
    CongestionItem, CongestionResponse,
    PeakHourItem, PeakHoursResponse,
    AlertItem, AlertsResponse,
)
from app.trajectory.haversine import average_speed_kmh, time_diff_minutes
from app.trajectory.anomaly import MovementStatus
from app.trajectory.engine import reconstruct
from app.config import SPEED_FAST_KMPH, SPEED_SUSPICIOUS_KMPH, SPEED_IMPOSSIBLE_KMPH


# ── density / congestion thresholds ──────────────────────────────────────────
_DENSITY_THRESHOLDS = [
    (1,  "LOW"),
    (5,  "MEDIUM"),
    (10, "HIGH"),
]   # >= 11 → SEVERE

_CONGESTION_SPEED   = [
    (60, "LOW"),
    (40, "MEDIUM"),
    (20, "HIGH"),
]   # < 20 km/h → SEVERE


def _density_label(count: int) -> str:
    for threshold, label in _DENSITY_THRESHOLDS:
        if count <= threshold:
            return label
    return "SEVERE"


def _congestion_label(avg_speed: float) -> str:
    for speed, label in _CONGESTION_SPEED:
        if avg_speed >= speed:
            return label
    return "SEVERE"


# ── Overview ──────────────────────────────────────────────────────────────────

def get_overview(db: Session) -> OverviewResponse:
    total_cameras   = db.query(func.count(TrajectoryCamera.id)).scalar() or 0
    total_det       = db.query(func.count(Detection.id)).scalar() or 0
    unique_plates   = db.query(func.count(func.distinct(Detection.plate_number))).scalar() or 0

    # Suspicious = plates whose latest trajectory status is not NORMAL
    suspicious = _count_suspicious_plates(db)
    congested  = _count_congested_cameras(db)

    return OverviewResponse(
        total_active_cameras     = total_cameras,
        total_detections         = total_det,
        suspicious_vehicle_count = suspicious,
        congested_locations_count= congested,
        total_unique_plates      = unique_plates,
    )


def _count_suspicious_plates(db: Session) -> int:
    plates = (
        db.query(Detection.plate_number)
          .distinct()
          .all()
    )
    count = 0
    for (plate,) in plates:
        try:
            traj = reconstruct(db, plate)
            if traj.status in (MovementStatus.SUSPICIOUS, MovementStatus.IMPOSSIBLE):
                count += 1
        except Exception:
            pass
    return count


def _count_congested_cameras(db: Session, window_hours: int = 1) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    rows = (
        db.query(Detection.camera_id, func.count(Detection.id).label("cnt"))
          .filter(Detection.timestamp >= cutoff)
          .group_by(Detection.camera_id)
          .all()
    )
    return sum(1 for _, cnt in rows if cnt >= 5)


# ── Traffic density ───────────────────────────────────────────────────────────

def get_traffic_density(db: Session, window_hours: int = 1) -> TrafficDensityResponse:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    rows = (
        db.query(Detection.camera_id, func.count(Detection.id).label("cnt"))
          .filter(Detection.timestamp >= cutoff)
          .group_by(Detection.camera_id)
          .all()
    )
    # Also include cameras with 0 detections in window
    all_cameras = {c.camera_id: c for c in db.query(TrajectoryCamera).all()}
    count_map   = {r.camera_id: r.cnt for r in rows}

    items: List[TrafficDensityItem] = []
    for cam_id, cam in all_cameras.items():
        cnt = count_map.get(cam_id, 0)
        items.append(
            TrafficDensityItem(
                camera_id      = cam_id,
                location_name  = cam.location_name,
                latitude       = cam.latitude,
                longitude      = cam.longitude,
                vehicle_count  = cnt,
                traffic_density= _density_label(cnt),
            )
        )

    items.sort(key=lambda x: x.vehicle_count, reverse=True)
    return TrafficDensityResponse(window_hours=window_hours, items=items)


# ── Congestion ────────────────────────────────────────────────────────────────

def get_congestion(db: Session, window_hours: int = 1) -> CongestionResponse:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    all_cameras = {c.camera_id: c for c in db.query(TrajectoryCamera).all()}

    # For each camera compute: vehicle count + average speed of vehicles passing through
    cam_detections: dict[str, list[Detection]] = defaultdict(list)
    dets = db.query(Detection).filter(Detection.timestamp >= cutoff).order_by(
        Detection.plate_number, Detection.timestamp
    ).all()
    for d in dets:
        cam_detections[d.camera_id].append(d)

    items: List[CongestionItem] = []
    for cam_id, cam in all_cameras.items():
        local_dets = cam_detections.get(cam_id, [])
        count      = len(local_dets)

        # Estimate avg speed: use detections from the same plate at this camera
        # and the next camera it visits
        avg_speed = _estimate_camera_avg_speed(db, cam_id, cutoff)

        items.append(
            CongestionItem(
                camera_id        = cam_id,
                location_name    = cam.location_name,
                latitude         = cam.latitude,
                longitude        = cam.longitude,
                vehicle_count    = count,
                avg_speed_kmh    = round(avg_speed, 2),
                congestion_level = _congestion_label(avg_speed),
                road_name        = cam.road_name,
            )
        )

    items.sort(key=lambda x: x.vehicle_count, reverse=True)
    return CongestionResponse(items=items)


def _estimate_camera_avg_speed(db: Session, camera_id: str, since: datetime) -> float:
    """
    For all plates seen at this camera since `since`, find their next detection
    at any camera and compute speed. Average across all such hops.
    Returns 30.0 km/h as default (city traffic) if no consecutive pairs found.
    """
    from app.trajectory.haversine import haversine_km

    dets_at_cam = (
        db.query(Detection)
          .filter(Detection.camera_id == camera_id, Detection.timestamp >= since)
          .all()
    )

    speeds: list[float] = []
    cam_lookup = {c.camera_id: c for c in db.query(TrajectoryCamera).all()}
    cam_here   = cam_lookup.get(camera_id)
    if cam_here is None:
        return 30.0

    for det in dets_at_cam:
        # find the very next detection for this plate after this timestamp
        nxt = (
            db.query(Detection)
              .filter(
                  Detection.plate_number == det.plate_number,
                  Detection.timestamp    >  det.timestamp,
                  Detection.camera_id   != camera_id,
              )
              .order_by(Detection.timestamp.asc())
              .first()
        )
        if nxt is None:
            continue
        cam_next = cam_lookup.get(nxt.camera_id)
        if cam_next is None:
            continue
        dist    = haversine_km(cam_here.latitude, cam_here.longitude,
                               cam_next.latitude, cam_next.longitude)
        t_min   = time_diff_minutes(det.timestamp, nxt.timestamp)
        speed   = average_speed_kmh(dist, t_min)
        if 0 < speed < 300:   # sanity filter
            speeds.append(speed)

    return sum(speeds) / len(speeds) if speeds else 30.0


# ── Peak hours ────────────────────────────────────────────────────────────────

def get_peak_hours(db: Session) -> PeakHoursResponse:
    rows = (
        db.query(
            func.strftime("%H", Detection.timestamp).label("hr"),
            func.count(Detection.id).label("cnt"),
        )
        .group_by("hr")
        .all()
    )

    hour_map: dict[int, int] = {int(r.hr): r.cnt for r in rows if r.hr is not None}
    hours = [
        PeakHourItem(hour=h, vehicle_count=hour_map.get(h, 0))
        for h in range(24)
    ]
    return PeakHoursResponse(hours=hours)


# ── Alerts ────────────────────────────────────────────────────────────────────

def get_alerts(db: Session, limit: int = 50) -> AlertsResponse:
    alerts: List[AlertItem] = []
    now    = datetime.now(timezone.utc)

    # 1. Congestion alerts (HIGH or SEVERE cameras)
    density = get_traffic_density(db, window_hours=1)
    for item in density.items:
        if item.traffic_density in ("HIGH", "SEVERE"):
            alerts.append(AlertItem(
                alert_type   = "CONGESTION",
                severity     = "CRITICAL" if item.traffic_density == "SEVERE" else "WARNING",
                camera_id    = item.camera_id,
                plate_number = None,
                message      = (
                    f"{item.traffic_density} traffic at {item.location_name} – "
                    f"{item.vehicle_count} vehicles in last hour"
                ),
                timestamp    = now,
            ))

    # 2. Suspicious / impossible trajectory alerts
    plates = db.query(Detection.plate_number).distinct().all()
    for (plate,) in plates:
        try:
            traj = reconstruct(db, plate)
            if traj.status == MovementStatus.IMPOSSIBLE:
                alerts.append(AlertItem(
                    alert_type   = "IMPOSSIBLE",
                    severity     = "CRITICAL",
                    camera_id    = None,
                    plate_number = plate,
                    message      = (
                        f"IMPOSSIBLE trajectory for {plate}: "
                        f"avg speed {traj.statistics.average_speed_kmh:.0f} km/h"
                    ),
                    timestamp    = now,
                ))
            elif traj.status == MovementStatus.SUSPICIOUS:
                alerts.append(AlertItem(
                    alert_type   = "SUSPICIOUS",
                    severity     = "WARNING",
                    camera_id    = None,
                    plate_number = plate,
                    message      = f"Suspicious movement detected for vehicle {plate}",
                    timestamp    = now,
                ))
        except Exception:
            pass

    # Sort: CRITICAL first, then WARNING
    alerts.sort(key=lambda a: (0 if a.severity == "CRITICAL" else 1))
    return AlertsResponse(alerts=alerts[:limit])
