"""
Phase 7 Extended Analytics Service

Provides vehicle type breakdown and per-camera statistics endpoints.
Reuses Phase-3 VehicleEvent and Phase-4 Detection + TrajectoryCamera tables.
Does NOT modify any existing Phase-5 analytics functions.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.vehicle_event import VehicleEvent
from app.models.detection import Detection
from app.models.trajectory_camera import TrajectoryCamera
from app.schemas.p7_analytics import (
    VehicleTypeCount,
    VehicleBreakdownResponse,
    CameraStatItem,
    CameraStatsResponse,
)
from app.services.analytics_service import (
    _density_label,
    _congestion_label,
    _estimate_camera_avg_speed,
)

logger = logging.getLogger(__name__)

# Baseline vehicle capacity per hour per camera for congestion score
_MAX_HOURLY_CAPACITY = 500


# ── Vehicle type breakdown ─────────────────────────────────────────────────────

def get_vehicle_type_breakdown(
    db           : Session,
    window_hours : int = 24,
) -> VehicleBreakdownResponse:
    """
    Returns counts per vehicle type from the Phase-3 VehicleEvent table
    within the specified time window.

    Congestion score formula
    -----------------------
    congestion_score = round(
        total_detections / (MAX_HOURLY_CAPACITY * window_hours), 2
    )
    where MAX_HOURLY_CAPACITY = 500 vehicles/hour (city-road baseline).
    Score > 1.0 means demand exceeds baseline capacity.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    rows = (
        db.query(
            VehicleEvent.vehicle_type,
            func.count(VehicleEvent.id).label("cnt"),
        )
        .filter(VehicleEvent.timestamp >= cutoff)
        .group_by(VehicleEvent.vehicle_type)
        .all()
    )

    type_map: Dict[str, int] = {}
    for row in rows:
        vtype = (row.vehicle_type or "unknown").lower()
        type_map[vtype] = type_map.get(vtype, 0) + row.cnt

    total = sum(type_map.values())

    breakdown: List[VehicleTypeCount] = []
    for vtype, cnt in sorted(type_map.items(), key=lambda x: x[1], reverse=True):
        pct = round((cnt / total * 100), 2) if total > 0 else 0.0
        breakdown.append(VehicleTypeCount(vehicle_type=vtype, count=cnt, percentage=pct))

    most_common = breakdown[0].vehicle_type if breakdown else None

    # Congestion score
    capacity    = _MAX_HOURLY_CAPACITY * window_hours
    cong_score  = round(total / capacity, 2) if capacity > 0 else 0.0

    return VehicleBreakdownResponse(
        window_hours     = window_hours,
        total_detections = total,
        breakdown        = breakdown,
        most_common_type = most_common,
        congestion_score = cong_score,
    )


# ── Per-camera statistics ──────────────────────────────────────────────────────

def get_camera_stats(
    db           : Session,
    window_hours : int = 24,
) -> CameraStatsResponse:
    """
    Returns per-camera detection statistics within the time window,
    combining Phase-4 trajectory_cameras and detections tables.
    """
    cutoff      = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    all_cameras = db.query(TrajectoryCamera).all()

    # Count detections per camera in window
    count_rows = (
        db.query(Detection.camera_id, func.count(Detection.id).label("cnt"))
        .filter(Detection.timestamp >= cutoff)
        .group_by(Detection.camera_id)
        .all()
    )
    count_map: Dict[str, int] = {r.camera_id: r.cnt for r in count_rows}

    # Count unique plates per camera in window
    unique_rows = (
        db.query(Detection.camera_id, func.count(func.distinct(Detection.plate_number)).label("uq"))
        .filter(Detection.timestamp >= cutoff)
        .group_by(Detection.camera_id)
        .all()
    )
    unique_map: Dict[str, int] = {r.camera_id: r.uq for r in unique_rows}

    items: List[CameraStatItem] = []
    for cam in all_cameras:
        cnt     = count_map.get(cam.camera_id, 0)
        uq      = unique_map.get(cam.camera_id, 0)
        avg_spd = _estimate_camera_avg_speed(db, cam.camera_id, cutoff)

        items.append(
            CameraStatItem(
                camera_id       = cam.camera_id,
                location_name   = cam.location_name,
                road_name       = cam.road_name,
                latitude        = cam.latitude,
                longitude       = cam.longitude,
                vehicle_count   = cnt,
                unique_plates   = uq,
                traffic_density = _density_label(cnt),
                congestion_level= _congestion_label(avg_spd),
            )
        )

    items.sort(key=lambda x: x.vehicle_count, reverse=True)
    most_active = items[0].camera_id if items else None

    return CameraStatsResponse(
        window_hours       = window_hours,
        total_cameras      = len(items),
        most_active_camera = most_active,
        cameras            = items,
    )
