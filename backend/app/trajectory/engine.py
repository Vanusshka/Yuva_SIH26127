"""
Trajectory Reconstruction Engine – Phase 4.

Given a plate number, retrieves all detections from the DB,
sorts them chronologically, joins camera metadata, calculates
per-hop spatial + temporal metrics, classifies movement, and
returns a fully structured TrajectoryResponse.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException

from app.models.detection import Detection
from app.models.trajectory_camera import TrajectoryCamera
from app.schemas.trajectory import (
    TrajectoryPoint,
    HopMetrics,
    TrajectoryStatistics,
    TrajectoryResponse,
)
from app.trajectory.haversine import haversine_km, time_diff_minutes, average_speed_kmh
from app.trajectory.anomaly import classify_hop, worst_status, MovementStatus


def reconstruct(db: Session, plate_number: str) -> TrajectoryResponse:
    """
    Full trajectory reconstruction pipeline for one plate number.

    Steps
    -----
    1. Fetch all detections for the plate, sorted by timestamp ASC
    2. Enrich each point with camera lat/lon/location
    3. For every consecutive pair calculate distance, time, speed
    4. Classify each hop → classify overall trajectory
    5. Aggregate total distance, duration, average speed
    6. Return TrajectoryResponse
    """
    plate_upper = plate_number.strip().upper()

    detections: List[Detection] = (
        db.query(Detection)
          .options(joinedload(Detection.camera))
          .filter(Detection.plate_number == plate_upper)
          .order_by(Detection.timestamp.asc())
          .all()
    )

    if not detections:
        raise HTTPException(
            status_code=404,
            detail=f"No detections found for plate '{plate_upper}'.",
        )

    # ── Build trajectory points ───────────────────────────────────────────────
    points: List[TrajectoryPoint] = []
    for det in detections:
        cam: Optional[TrajectoryCamera] = det.camera
        points.append(
            TrajectoryPoint(
                detection_id        = det.id,
                camera_id           = det.camera_id,
                location_name       = cam.location_name if cam else "Unknown",
                road_name           = cam.road_name     if cam else None,
                direction           = cam.direction     if cam else None,
                latitude            = cam.latitude      if cam else 0.0,
                longitude           = cam.longitude     if cam else 0.0,
                timestamp           = det.timestamp,
                detection_confidence= det.detection_confidence,
            )
        )

    # ── Calculate hop metrics ─────────────────────────────────────────────────
    hops: List[HopMetrics] = []
    hop_statuses: List[MovementStatus] = []

    for i in range(1, len(points)):
        prev = points[i - 1]
        curr = points[i]

        dist_km   = haversine_km(prev.latitude, prev.longitude,
                                  curr.latitude, curr.longitude)
        t_minutes = time_diff_minutes(prev.timestamp, curr.timestamp)
        speed     = average_speed_kmh(dist_km, t_minutes)
        same_cam  = prev.camera_id == curr.camera_id

        status = classify_hop(
            distance_km  = dist_km,
            time_minutes = t_minutes,
            speed_kmh    = speed,
            same_camera  = same_cam,
        )
        hop_statuses.append(status)

        hops.append(
            HopMetrics(
                from_camera_id          = prev.camera_id,
                to_camera_id            = curr.camera_id,
                from_timestamp          = prev.timestamp,
                to_timestamp            = curr.timestamp,
                distance_km             = round(dist_km, 4),
                time_difference_minutes = round(t_minutes, 4),
                average_speed_kmh       = round(speed, 2),
                status                  = status,
            )
        )

    # ── Aggregate statistics ──────────────────────────────────────────────────
    total_distance_km   = sum(h.distance_km for h in hops)
    total_duration_min  = (
        time_diff_minutes(points[0].timestamp, points[-1].timestamp)
        if len(points) >= 2 else 0.0
    )
    overall_speed       = average_speed_kmh(total_distance_km, total_duration_min)
    overall_status      = worst_status(hop_statuses) if hop_statuses else MovementStatus.NORMAL

    stats = TrajectoryStatistics(
        total_detections        = len(points),
        total_hops              = len(hops),
        total_distance_km       = round(total_distance_km, 4),
        total_duration_minutes  = round(total_duration_min, 4),
        average_speed_kmh       = round(overall_speed, 2),
        first_seen              = points[0].timestamp  if points else None,
        last_seen               = points[-1].timestamp if points else None,
        cameras_visited         = list(dict.fromkeys(p.camera_id for p in points)),
    )

    return TrajectoryResponse(
        plate_number = plate_upper,
        trajectory   = points,
        hops         = hops,
        statistics   = stats,
        status       = overall_status,
    )
