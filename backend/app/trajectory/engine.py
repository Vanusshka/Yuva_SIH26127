"""
Trajectory Reconstruction Engine – Phase 4 + Changes 7+8.

Change 7 — Fuzzy plate matching:
  reconstruct_fuzzy() accepts near-identical OCR variations using
  Levenshtein distance <= TRAJECTORY_FUZZY_MAX_EDIT_DISTANCE.
  Fuzzy hops are labelled SUSPICIOUS regardless of speed.

Change 8 — Travel-time feasibility:
  classify_hop() now also calls is_travel_time_feasible() from
  trajectory/fuzzy.py. Physically impossible hops (too fast given
  the GPS distance) are classified as IMPOSSIBLE even if the speed
  calculation is within SPEED_IMPOSSIBLE_KMPH due to rounding.

Original reconstruct() is preserved unchanged for backward compatibility.
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
from app.trajectory.fuzzy import (
    plates_possibly_match,
    is_travel_time_feasible,
    find_fuzzy_plate_candidates,
)


def reconstruct(db: Session, plate_number: str) -> TrajectoryResponse:
    """
    Full trajectory reconstruction pipeline for one plate number.
    EXACT string match — original behaviour preserved.
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

    return _build_trajectory(plate_upper, detections)


def reconstruct_fuzzy(db: Session, plate_number: str) -> TrajectoryResponse:
    """
    Change 7+8: Trajectory reconstruction with fuzzy plate matching
    and travel-time feasibility validation.

    Finds all detections where the plate matches within
    TRAJECTORY_FUZZY_MAX_EDIT_DISTANCE edit distance.
    Fuzzy-matched hops (edit_distance > 0) are marked SUSPICIOUS.
    Hops that fail travel-time feasibility are marked IMPOSSIBLE.

    Returns the same TrajectoryResponse schema as reconstruct().
    """
    plate_upper = plate_number.strip().upper()

    # Find all distinct plates in the DB that are within fuzzy distance
    all_plates_q = db.query(Detection.plate_number).distinct().all()
    all_plates   = [row[0] for row in all_plates_q if row[0]]

    candidates = find_fuzzy_plate_candidates(plate_upper, all_plates)
    if not candidates:
        raise HTTPException(
            status_code=404,
            detail=f"No detections found for plate '{plate_upper}' (fuzzy search).",
        )

    # Collect detections for all fuzzy-matching plates
    matched_plates = [p for p, _ in candidates]
    edit_dist_map  = {p: d for p, d in candidates}

    detections: List[Detection] = (
        db.query(Detection)
          .options(joinedload(Detection.camera))
          .filter(Detection.plate_number.in_(matched_plates))
          .order_by(Detection.timestamp.asc())
          .all()
    )

    if not detections:
        raise HTTPException(
            status_code=404,
            detail=f"No detections found for plate '{plate_upper}'.",
        )

    return _build_trajectory(
        plate_upper, detections, edit_dist_map=edit_dist_map
    )


def _build_trajectory(
    label       : str,
    detections  : List[Detection],
    edit_dist_map: Optional[dict] = None,
) -> TrajectoryResponse:
    """
    Shared trajectory builder used by both reconstruct() and reconstruct_fuzzy().
    edit_dist_map: plate → edit_distance (None = exact match only).
    """
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

        # Change 8: travel-time feasibility check
        if not is_travel_time_feasible(dist_km, t_minutes):
            status = MovementStatus.IMPOSSIBLE
        else:
            status = classify_hop(
                distance_km  = dist_km,
                time_minutes = t_minutes,
                speed_kmh    = speed,
                same_camera  = same_cam,
            )

        # Change 7: fuzzy-matched hops are at minimum SUSPICIOUS
        if edit_dist_map is not None:
            det_prev_plate = detections[i - 1].plate_number
            det_curr_plate = detections[i].plate_number
            prev_dist = edit_dist_map.get(det_prev_plate, 0)
            curr_dist = edit_dist_map.get(det_curr_plate, 0)
            if (prev_dist > 0 or curr_dist > 0) and status == MovementStatus.NORMAL:
                status = MovementStatus.SUSPICIOUS  # fuzzy match = at least suspicious

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

    total_distance_km  = sum(h.distance_km for h in hops)
    total_duration_min = (
        time_diff_minutes(points[0].timestamp, points[-1].timestamp)
        if len(points) >= 2 else 0.0
    )
    overall_speed  = average_speed_kmh(total_distance_km, total_duration_min)
    overall_status = worst_status(hop_statuses) if hop_statuses else MovementStatus.NORMAL

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
        plate_number = label,
        trajectory   = points,
        hops         = hops,
        statistics   = stats,
        status       = overall_status,
    )
