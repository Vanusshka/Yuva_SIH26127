"""
Pipeline Orchestration Service – Phase 8
==========================================

Central coordinator for the complete SIH26127 pipeline:

  Input (image/video)
    → Vehicle Detection       (Phase 2 – VehicleDetector, reused)
    → Plate Detection         (Phase 2 – PlateDetector, reused)
    → OCR / ANPR              (Phase 2 – OCREngine, reused)
    → Plate Normalisation     (Phase 7 – normalise_plate, reused)
    → Detection Storage       (Phase 3 – VehicleEvent + Phase 4 – Detection)
    → Cross-Camera Matching   (Phase 4 – Detection table lookup)
    → Trajectory Reconstruction (Phase 4 – engine.reconstruct)
    → Traffic Analytics       (Phase 5 + Phase 7 analytics services)
    → Alert Generation        (Phase 7 – p7_alert_service)

This module DOES NOT duplicate any existing logic.  It wraps and composes
existing service functions into frontend-ready response shapes.

All functions are safe to call with an in-memory DB for testing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.detection import Detection
from app.models.vehicle_event import VehicleEvent
from app.models.trajectory_camera import TrajectoryCamera

# Reused Phase 2-7 services
from app.trajectory.engine import reconstruct
from app.trajectory.anomaly import MovementStatus
from app.services.analytics_service import (
    get_overview,
    get_traffic_density,
    get_congestion,
    get_peak_hours,
)
from app.services.p7_analytics_service import (
    get_vehicle_type_breakdown,
    get_camera_stats,
)
from app.services.p7_alert_service import get_combined_alerts

# Phase 8 schemas
from app.schemas.p8_frontend import (
    VehicleRecord,
    VehicleListResponse,
    FrontendTrajectoryResponse,
    TrajectoryStop,
    TrajectoryHop,
    UnifiedAnalyticsResponse,
    VehicleCategoryItem,
    CongestionZone,
    TrafficTrendPoint,
    FrontendAlertItem,
    FrontendAlertsResponse,
    Phase8HealthResponse,
)
from app.utils.metadata_loader import is_blacklisted

logger = logging.getLogger(__name__)

# ── anomaly score mapping ─────────────────────────────────────────────────────
_ANOMALY_SCORES = {
    MovementStatus.NORMAL     : 0.0,
    MovementStatus.FAST       : 0.33,
    MovementStatus.SUSPICIOUS : 0.67,
    MovementStatus.IMPOSSIBLE : 1.0,
}


def _status_str(s: MovementStatus) -> str:
    """Convert MovementStatus enum to plain string for JSON."""
    return s.value if hasattr(s, "value") else str(s).split(".")[-1]


# ═══════════════════════════════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════════════════════════════

def get_health(db: Session, version: str = "0.8.0") -> Phase8HealthResponse:
    """
    Extended health check including live DB stats.
    Called by GET /health (Phase 8 overrides the Phase 2 response).
    """
    try:
        total_cameras    = db.query(func.count(TrajectoryCamera.id)).scalar() or 0
        total_detections = db.query(func.count(Detection.id)).scalar() or 0
        db_status        = "connected"
    except Exception as exc:
        logger.error("[Pipeline] Health DB query failed: %s", exc)
        total_cameras    = 0
        total_detections = 0
        db_status        = f"error: {exc}"

    return Phase8HealthResponse(
        status           = "running",
        version          = version,
        database         = db_status,
        total_cameras    = total_cameras,
        total_detections = total_detections,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# VEHICLE LIST  (GET /vehicles)
# ═══════════════════════════════════════════════════════════════════════════════

def _derive_vehicle_status(movement_status: Optional[MovementStatus]) -> str:
    """Map trajectory MovementStatus → frontend vehicle status string."""
    if movement_status is None:
        return "unknown"
    mapping = {
        MovementStatus.NORMAL     : "active",
        MovementStatus.FAST       : "active",
        MovementStatus.SUSPICIOUS : "suspicious",
        MovementStatus.IMPOSSIBLE : "impossible",
    }
    return mapping.get(movement_status, "unknown")


def get_vehicle_list(
    db          : Session,
    limit       : int = 100,
    offset      : int = 0,
    status_filter: Optional[str] = None,
) -> VehicleListResponse:
    """
    Return a paginated list of every unique plate seen in the system.

    For each plate collects:
    - Most common vehicle_type (from vehicle_events table)
    - Highest detection confidence
    - First / last seen timestamps
    - Distinct camera count
    - Total sightings
    - Movement status (from trajectory reconstruction)
    - Blacklist status
    """
    # All distinct plates from Phase-4 Detection table
    all_plates_q = (
        db.query(Detection.plate_number)
          .distinct()
          .order_by(Detection.plate_number)
    )
    total_count  = all_plates_q.count()
    plates       = [row[0] for row in all_plates_q.offset(offset).limit(limit).all()]

    # Preload vehicle_events for type + confidence data (Phase-3 table)
    event_rows = (
        db.query(
            VehicleEvent.plate_number,
            VehicleEvent.vehicle_type,
            VehicleEvent.vehicle_confidence,
        )
        .filter(VehicleEvent.plate_number.in_(plates))
        .all()
    )

    # Group events by plate
    from collections import defaultdict, Counter
    events_by_plate: dict[str, list] = defaultdict(list)
    for plate, vtype, vconf in event_rows:
        if plate:
            events_by_plate[plate].append((vtype, vconf))

    records: List[VehicleRecord] = []

    for plate in plates:
        # Detection-level stats
        det_rows = (
            db.query(
                func.min(Detection.timestamp).label("first_seen"),
                func.max(Detection.timestamp).label("last_seen"),
                func.count(Detection.id).label("total"),
                func.count(func.distinct(Detection.camera_id)).label("cam_count"),
            )
            .filter(Detection.plate_number == plate)
            .first()
        )

        first_seen   = det_rows.first_seen  if det_rows else None
        last_seen    = det_rows.last_seen   if det_rows else None
        total_sight  = det_rows.total       if det_rows else 0
        cam_count    = det_rows.cam_count   if det_rows else 0

        # Last camera seen at
        last_det = (
            db.query(Detection)
              .filter(Detection.plate_number == plate)
              .order_by(Detection.timestamp.desc())
              .first()
        )
        last_cam_id  = last_det.camera_id if last_det else None

        # Location of last camera from TrajectoryCamera table
        last_location = None
        if last_cam_id:
            tc = db.query(TrajectoryCamera).filter(
                TrajectoryCamera.camera_id == last_cam_id
            ).first()
            if tc:
                last_location = tc.location_name

        # Vehicle type (most common from Phase-3 events)
        ev_list   = events_by_plate.get(plate, [])
        vtype_ctr = Counter(vt for vt, _ in ev_list if vt)
        vehicle_type = vtype_ctr.most_common(1)[0][0] if vtype_ctr else "unknown"

        # Confidence (max)
        confidences = [vc for _, vc in ev_list if vc is not None]
        confidence  = round(max(confidences), 4) if confidences else 0.0

        # Trajectory status — SKIP in list view (too expensive for large datasets).
        # Status is computed on-demand in get_vehicle_detail() only.
        movement_status: Optional[MovementStatus] = None
        status_str = "active"  # default for list view

        # Blacklist
        bl_entry    = is_blacklisted(plate)
        is_bl       = bl_entry is not None
        bl_reason   = bl_entry.get("reason") if bl_entry else None

        record = VehicleRecord(
            plate_number    = plate,
            vehicle_type    = vehicle_type,
            confidence      = confidence,
            first_seen      = first_seen,
            last_seen       = last_seen,
            camera_count    = cam_count,
            total_sightings = total_sight,
            status          = status_str,
            last_camera_id  = last_cam_id,
            last_location   = last_location,
            is_blacklisted  = is_bl,
            blacklist_reason= bl_reason,
        )

        if status_filter is None or record.status == status_filter:
            records.append(record)

    return VehicleListResponse(
        total      = total_count,
        vehicles   = records,
        generated_at = datetime.now(timezone.utc),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLE VEHICLE  (GET /vehicles/{plate})
# ═══════════════════════════════════════════════════════════════════════════════

def get_vehicle_detail(db: Session, plate_number: str) -> VehicleRecord:
    """
    Return a single VehicleRecord for the given plate.
    Raises HTTP 404 if no detections exist.
    """
    plate_upper = plate_number.strip().upper()

    det_count = (
        db.query(func.count(Detection.id))
          .filter(Detection.plate_number == plate_upper)
          .scalar() or 0
    )
    if det_count == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No detections found for plate '{plate_upper}'.",
        )

    # Reuse the list builder with exact match
    result = get_vehicle_list(db, limit=1, offset=0)

    # Find this plate in a targeted way (list builder paginates by offset, not filter)
    # Use direct query instead
    from collections import Counter, defaultdict

    det_rows = (
        db.query(
            func.min(Detection.timestamp).label("first_seen"),
            func.max(Detection.timestamp).label("last_seen"),
            func.count(Detection.id).label("total"),
            func.count(func.distinct(Detection.camera_id)).label("cam_count"),
        )
        .filter(Detection.plate_number == plate_upper)
        .first()
    )

    event_rows = (
        db.query(VehicleEvent.vehicle_type, VehicleEvent.vehicle_confidence)
          .filter(VehicleEvent.plate_number == plate_upper)
          .all()
    )
    vtype_ctr    = Counter(vt for vt, _ in event_rows if vt)
    vehicle_type = vtype_ctr.most_common(1)[0][0] if vtype_ctr else "unknown"
    confidences  = [vc for _, vc in event_rows if vc is not None]
    confidence   = round(max(confidences), 4) if confidences else 0.0

    last_det = (
        db.query(Detection)
          .filter(Detection.plate_number == plate_upper)
          .order_by(Detection.timestamp.desc())
          .first()
    )
    last_cam_id   = last_det.camera_id if last_det else None
    last_location = None
    if last_cam_id:
        tc = db.query(TrajectoryCamera).filter(
            TrajectoryCamera.camera_id == last_cam_id
        ).first()
        if tc:
            last_location = tc.location_name

    movement_status = None
    if (det_rows.total or 0) >= 2:
        try:
            traj = reconstruct(db, plate_upper)
            movement_status = traj.status
        except Exception:
            pass

    bl_entry = is_blacklisted(plate_upper)

    return VehicleRecord(
        plate_number    = plate_upper,
        vehicle_type    = vehicle_type,
        confidence      = confidence,
        first_seen      = det_rows.first_seen  if det_rows else None,
        last_seen       = det_rows.last_seen   if det_rows else None,
        camera_count    = det_rows.cam_count   if det_rows else 0,
        total_sightings = det_rows.total       if det_rows else 0,
        status          = _derive_vehicle_status(movement_status),
        last_camera_id  = last_cam_id,
        last_location   = last_location,
        is_blacklisted  = bl_entry is not None,
        blacklist_reason= bl_entry.get("reason") if bl_entry else None,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TRAJECTORY  (GET /trajectory/{plate}  – frontend-ready version)
# ═══════════════════════════════════════════════════════════════════════════════

def get_frontend_trajectory(
    db          : Session,
    plate_number: str,
) -> FrontendTrajectoryResponse:
    """
    Wraps the Phase-4 reconstruct() engine output into the Phase 8
    FrontendTrajectoryResponse shape.

    The Phase-4 /trajectory/{plate_number} endpoint is preserved unchanged.
    This function is called by the new GET /trajectory/{plate} Phase 8 route.
    """
    plate_upper = plate_number.strip().upper()
    traj = reconstruct(db, plate_upper)   # raises 404 if no detections

    stops: List[TrajectoryStop] = [
        TrajectoryStop(
            camera_id  = pt.camera_id,
            location   = pt.location_name,
            road_name  = pt.road_name,
            direction  = pt.direction,
            latitude   = pt.latitude,
            longitude  = pt.longitude,
            timestamp  = pt.timestamp,
            confidence = pt.detection_confidence,
        )
        for pt in traj.trajectory
    ]

    hops: List[TrajectoryHop] = [
        TrajectoryHop(
            from_camera  = h.from_camera_id,
            to_camera    = h.to_camera_id,
            distance_km  = h.distance_km,
            duration_min = h.time_difference_minutes,
            speed_kmh    = h.average_speed_kmh,
            anomaly      = _status_str(h.status),
        )
        for h in traj.hops
    ]

    anomaly_score = _ANOMALY_SCORES.get(traj.status, 0.0)

    return FrontendTrajectoryResponse(
        plate_number        = traj.plate_number,
        total_observations  = traj.statistics.total_detections,
        total_distance_km   = traj.statistics.total_distance_km,
        travel_duration_min = traj.statistics.total_duration_minutes,
        average_speed_kmh   = traj.statistics.average_speed_kmh,
        anomaly_score       = anomaly_score,
        overall_status      = _status_str(traj.status),
        first_seen          = traj.statistics.first_seen,
        last_seen           = traj.statistics.last_seen,
        cameras_visited     = traj.statistics.cameras_visited,
        stops               = stops,
        hops                = hops,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYTICS  (GET /analytics – unified dashboard endpoint)
# ═══════════════════════════════════════════════════════════════════════════════

def get_unified_analytics(
    db           : Session,
    window_hours : int = 24,
) -> UnifiedAnalyticsResponse:
    """
    Assembles a single analytics payload by calling existing Phase 5 + 7
    analytics functions.  No new DB queries are introduced.
    """
    overview   = get_overview(db)
    veh_bd     = get_vehicle_type_breakdown(db, window_hours=window_hours)
    cam_stats  = get_camera_stats(db, window_hours=window_hours)
    congestion = get_congestion(db, window_hours=1)
    peak_hours = get_peak_hours(db)

    # Vehicle distribution
    distribution = [
        VehicleCategoryItem(
            category   = item.vehicle_type,
            count      = item.count,
            percentage = item.percentage,
        )
        for item in veh_bd.breakdown
    ]

    # Overall density label (worst camera)
    density_labels = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "SEVERE": 3}
    worst_density  = "LOW"
    if cam_stats.cameras:
        worst_density = max(
            (c.traffic_density for c in cam_stats.cameras),
            key=lambda x: density_labels.get(x, 0),
            default="LOW",
        )

    # Average speed (mean of all cameras with data)
    speeds = [c.avg_speed_kmh for c in congestion.items if c.vehicle_count > 0]
    avg_speed = round(sum(speeds) / len(speeds), 2) if speeds else 30.0

    # Congestion zones (HIGH + SEVERE cameras)
    congestion_zones = [
        CongestionZone(
            camera_id       = c.camera_id,
            location        = c.location_name,
            latitude        = c.latitude,
            longitude       = c.longitude,
            vehicle_count   = c.vehicle_count,
            avg_speed_kmh   = c.avg_speed_kmh,
            congestion_level= c.congestion_level,
        )
        for c in congestion.items
        if c.congestion_level in ("HIGH", "SEVERE")
    ]

    # Traffic trends (last 24h hourly from peak_hours)
    trends = [
        TrafficTrendPoint(hour=h.hour, vehicle_count=h.vehicle_count)
        for h in peak_hours.hours
    ]

    # Most active camera
    most_active_cam  = cam_stats.most_active_camera
    most_active_loc  = None
    if most_active_cam and cam_stats.cameras:
        for c in cam_stats.cameras:
            if c.camera_id == most_active_cam:
                most_active_loc = c.location_name
                break

    # Active alerts count — use a small limit to avoid triggering heavy
    # trajectory reconstruction for all plates (that's done lazily per-request)
    try:
        alerts_resp  = get_combined_alerts(db, limit=10)
        active_alerts = alerts_resp.total_alerts
    except Exception:
        active_alerts = 0

    return UnifiedAnalyticsResponse(
        total_vehicles        = overview.total_detections,
        total_unique_plates   = overview.total_unique_plates,
        total_cameras         = overview.total_active_cameras,
        active_alerts         = active_alerts,
        suspicious_vehicles   = overview.suspicious_vehicle_count,
        vehicle_distribution  = distribution,
        traffic_density_label = worst_density,
        average_speed_kmh     = avg_speed,
        congestion_score      = veh_bd.congestion_score,
        congestion_zones      = congestion_zones,
        traffic_trends        = trends,
        most_active_camera    = most_active_cam,
        most_active_location  = most_active_loc,
        generated_at          = datetime.now(timezone.utc),
        window_hours          = window_hours,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ALERTS  (GET /alerts – Phase 8 frontend-ready version)
# ═══════════════════════════════════════════════════════════════════════════════

def get_frontend_alerts(
    db    : Session,
    limit : int = 50,
) -> FrontendAlertsResponse:
    """
    Wraps Phase-7 get_combined_alerts() into the Phase-8 FrontendAlertsResponse
    shape, adding alert_id, location, and status fields.
    """
    combined = get_combined_alerts(db, limit=limit)

    # Build camera_id → location_name lookup
    cam_map: dict[str, str] = {}
    try:
        for tc in db.query(TrajectoryCamera).all():
            cam_map[tc.camera_id] = tc.location_name
    except Exception:
        pass

    frontend_alerts: List[FrontendAlertItem] = []
    for a in combined.alerts:
        location = cam_map.get(a.camera_id, None) if a.camera_id else None
        frontend_alerts.append(
            FrontendAlertItem(
                alert_type   = a.alert_type,
                severity     = a.severity,
                plate_number = a.plate_number,
                location     = location,
                camera_id    = a.camera_id,
                timestamp    = a.timestamp,
                message      = a.message,
                demo_data    = a.demo_data,
                # status defaults to "open"
            )
        )

    return FrontendAlertsResponse(
        total_alerts   = combined.total_alerts,
        critical_count = combined.critical_count,
        warning_count  = combined.warning_count,
        info_count     = combined.info_count,
        alerts         = frontend_alerts,
        generated_at   = datetime.now(timezone.utc),
    )
