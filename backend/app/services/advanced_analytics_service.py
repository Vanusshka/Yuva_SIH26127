"""
Advanced Analytics Service — C3 Heatmap · C4 OD Matrix · C5 Bottlenecks

Three pure-SQL / aggregation functions that build on the existing Detection
and TrajectoryCamera tables.  No ML model, no new DB schema.

C3  get_heatmap()      — per-camera vehicle density with GeoJSON FeatureCollection
C4  get_od_matrix()    — origin→destination pair flows from plate trajectories
C5  get_bottlenecks()  — sustained-congestion ranking using sub-window persistence
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.detection import Detection
from app.models.trajectory_camera import TrajectoryCamera
from app.schemas.c3_c5 import (
    HeatmapPoint,
    HeatmapResponse,
    ODPair,
    ODMatrixResponse,
    BottleneckItem,
    BottleneckResponse,
)
from app.services.analytics_service import (
    _density_label,
    _congestion_label,
    _estimate_camera_avg_speed,
)
from app.trajectory.haversine import haversine_km

logger = logging.getLogger(__name__)

# ── density threshold constants (mirrors analytics_service) ──────────────────
_HIGH_DENSITY_MIN  = 6   # vehicle count >= this → HIGH in _density_label()
# (LOW ≤1, MEDIUM ≤5, HIGH ≤10, SEVERE >10)


# =============================================================================
# C3 — Traffic Heatmap
# =============================================================================

def get_heatmap(
    db          : Session,
    window_hours: int = 1,
) -> HeatmapResponse:
    """
    C3: Per-camera vehicle density heatmap.

    Returns both a flat list and a GeoJSON FeatureCollection so the frontend
    can feed it directly to Leaflet L.heatLayer() or Mapbox addSource().

    Intensity is normalised 0.0–1.0 (busiest camera in window = 1.0).
    """
    cutoff      = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    all_cameras = {c.camera_id: c for c in db.query(TrajectoryCamera).all()}

    count_rows = (
        db.query(Detection.camera_id, func.count(Detection.id).label("cnt"))
          .filter(Detection.timestamp >= cutoff)
          .group_by(Detection.camera_id)
          .all()
    )
    count_map: Dict[str, int] = {r.camera_id: r.cnt for r in count_rows}

    max_count = max(count_map.values(), default=1)

    points: List[HeatmapPoint] = []
    features = []

    for cam_id, cam in sorted(all_cameras.items()):
        cnt       = count_map.get(cam_id, 0)
        intensity = round(cnt / max_count, 4) if max_count > 0 else 0.0
        label     = _density_label(cnt)

        points.append(HeatmapPoint(
            camera_id     = cam_id,
            location_name = cam.location_name,
            latitude      = cam.latitude,
            longitude     = cam.longitude,
            vehicle_count = cnt,
            density_label = label,
            intensity     = intensity,
        ))

        features.append({
            "type"    : "Feature",
            "geometry": {
                "type"       : "Point",
                "coordinates": [cam.longitude, cam.latitude],   # GeoJSON: [lon, lat]
            },
            "properties": {
                "camera_id"    : cam_id,
                "location_name": cam.location_name,
                "vehicle_count": cnt,
                "density_label": label,
                "intensity"    : intensity,
            },
        })

    # Sort by density descending so map renderers draw busiest markers on top
    points.sort(key=lambda p: p.vehicle_count, reverse=True)
    features.sort(key=lambda f: f["properties"]["vehicle_count"], reverse=True)

    geojson = {
        "type"    : "FeatureCollection",
        "features": features,
    }

    return HeatmapResponse(
        window_hours      = window_hours,
        generated_at      = datetime.now(timezone.utc),
        total_cameras     = len(all_cameras),
        max_vehicle_count = max_count,
        points            = points,
        geojson           = geojson,
    )


# =============================================================================
# C4 — Origin-Destination Matrix
# =============================================================================

def get_od_matrix(
    db          : Session,
    window_hours: int = 24,
    top_n       : int = 20,
) -> ODMatrixResponse:
    """
    C4: Origin-Destination pattern detection.

    For every plate seen at ≥2 cameras in the time window:
      origin = camera of the plate's FIRST detection
      dest   = camera of the plate's LAST detection

    Aggregates (origin, dest) pairs, counts distinct plates per pair,
    and computes average travel time and Haversine distance.

    Returns the top_n pairs by vehicle count, plus a GeoJSON FeatureCollection
    of LineString arcs for desire-line map rendering.

    Plates seen at only one camera are excluded — no journey to measure.
    """
    cutoff      = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    cam_lookup  : Dict[str, TrajectoryCamera] = {
        c.camera_id: c for c in db.query(TrajectoryCamera).all()
    }

    # ── Step 1: get first + last detection per plate in window ────────────────
    # SQLite doesn't support FIRST_VALUE/LAST_VALUE directly, so we pull all
    # detections for the window and compute first/last in Python.
    # Cap at 5000 rows to keep response time bounded.
    rows = (
        db.query(
            Detection.plate_number,
            Detection.camera_id,
            Detection.timestamp,
        )
        .filter(Detection.timestamp >= cutoff)
        .order_by(Detection.plate_number, Detection.timestamp.asc())
        .limit(5000)
        .all()
    )

    # Group by plate: {plate → [(camera_id, timestamp), ...]}
    plate_sightings: Dict[str, List[Tuple[str, datetime]]] = defaultdict(list)
    for plate, cam_id, ts in rows:
        plate_sightings[plate].append((cam_id, ts))

    # ── Step 2: extract (origin, dest) pairs ─────────────────────────────────
    # pair → list of (duration_minutes, distance_km)
    OD = Tuple[str, str]
    pair_data: Dict[OD, List[Tuple[float, float]]] = defaultdict(list)

    for plate, sightings in plate_sightings.items():
        if len(sightings) < 2:
            continue   # only one camera — no journey
        origin_cam, origin_ts = sightings[0]
        dest_cam,   dest_ts   = sightings[-1]
        if origin_cam == dest_cam:
            continue   # started and ended at same camera — not a meaningful OD

        duration_min = (dest_ts - origin_ts).total_seconds() / 60.0

        origin_c = cam_lookup.get(origin_cam)
        dest_c   = cam_lookup.get(dest_cam)
        if origin_c and dest_c:
            dist_km = haversine_km(
                origin_c.latitude, origin_c.longitude,
                dest_c.latitude,   dest_c.longitude,
            )
        else:
            dist_km = 0.0

        pair_data[(origin_cam, dest_cam)].append((duration_min, dist_km))

    total_plates_tracked = sum(
        1 for s in plate_sightings.values() if len(s) >= 2
    )

    # ── Step 3: build ODPair objects, sort by count ───────────────────────────
    od_pairs: List[ODPair] = []
    for (orig_cam, dest_cam), measurements in pair_data.items():
        count          = len(measurements)
        avg_duration   = round(sum(d for d, _ in measurements) / count, 2)
        avg_dist       = round(sum(k for _, k in measurements) / count, 3)

        orig_c = cam_lookup.get(orig_cam)
        dest_c = cam_lookup.get(dest_cam)
        if not orig_c or not dest_c:
            continue

        geojson_line = {
            "type"    : "Feature",
            "geometry": {
                "type"       : "LineString",
                "coordinates": [
                    [orig_c.longitude, orig_c.latitude],
                    [dest_c.longitude, dest_c.latitude],
                ],
            },
            "properties": {
                "origin_camera_id" : orig_cam,
                "origin_location"  : orig_c.location_name,
                "dest_camera_id"   : dest_cam,
                "dest_location"    : dest_c.location_name,
                "vehicle_count"    : count,
                "avg_duration_min" : avg_duration,
                "avg_distance_km"  : avg_dist,
            },
        }

        od_pairs.append(ODPair(
            origin_camera_id  = orig_cam,
            origin_location   = orig_c.location_name,
            origin_lat        = orig_c.latitude,
            origin_lon        = orig_c.longitude,
            dest_camera_id    = dest_cam,
            dest_location     = dest_c.location_name,
            dest_lat          = dest_c.latitude,
            dest_lon          = dest_c.longitude,
            vehicle_count     = count,
            avg_duration_min  = avg_duration,
            avg_distance_km   = avg_dist,
            geojson_line      = geojson_line,
        ))

    od_pairs.sort(key=lambda p: p.vehicle_count, reverse=True)
    od_pairs = od_pairs[:top_n]

    geojson_fc = {
        "type"    : "FeatureCollection",
        "features": [p.geojson_line for p in od_pairs],
    }

    return ODMatrixResponse(
        window_hours         = window_hours,
        generated_at         = datetime.now(timezone.utc),
        total_plates_tracked = total_plates_tracked,
        total_od_pairs       = len(od_pairs),
        pairs                = od_pairs,
        geojson              = geojson_fc,
    )


# =============================================================================
# C5 — Congestion Bottleneck Detection
# =============================================================================

def get_bottlenecks(
    db                : Session,
    window_hours      : int = 3,
    sub_window_minutes: int = 30,
    top_n             : int = 10,
) -> BottleneckResponse:
    """
    C5: Sustained congestion bottleneck ranking.

    Method:
      1. Divide [now - window_hours, now] into sub-windows of sub_window_minutes
      2. For each sub-window × camera: count detections → density label
      3. persistence[camera] = fraction of sub-windows that were HIGH or SEVERE
      4. bottleneck_score    = total_vehicle_count × persistence
      5. Rank by bottleneck_score descending

    This identifies cameras that are *persistently* congested rather than
    just currently busy — a camera with 3 vehicles right now ranks lower than
    one that has been SEVERE for the past 2 hours.
    """
    now         = datetime.now(timezone.utc)
    window_start= now - timedelta(hours=window_hours)
    all_cameras = {c.camera_id: c for c in db.query(TrajectoryCamera).all()}

    # Build list of sub-window (start, end) tuples
    sub_windows: List[Tuple[datetime, datetime]] = []
    sw_start = window_start
    while sw_start < now:
        sw_end = min(sw_start + timedelta(minutes=sub_window_minutes), now)
        sub_windows.append((sw_start, sw_end))
        sw_start = sw_end

    n_windows = max(len(sub_windows), 1)

    # For each sub-window, count detections per camera
    # {camera_id → [count_per_sub_window, ...]}
    cam_counts: Dict[str, List[int]] = {c: [0] * n_windows for c in all_cameras}

    for i, (sw_s, sw_e) in enumerate(sub_windows):
        rows = (
            db.query(Detection.camera_id, func.count(Detection.id).label("cnt"))
              .filter(Detection.timestamp >= sw_s, Detection.timestamp < sw_e)
              .group_by(Detection.camera_id)
              .all()
        )
        for r in rows:
            if r.camera_id in cam_counts:
                cam_counts[r.camera_id][i] = r.cnt

    # Compute total count and persistence per camera
    bottleneck_items: List[BottleneckItem] = []

    for cam_id, cam in all_cameras.items():
        counts = cam_counts[cam_id]
        total  = sum(counts)

        # Persistence: fraction of sub-windows that were HIGH or SEVERE
        high_severe = sum(
            1 for c in counts
            if _density_label(c) in ("HIGH", "SEVERE")
        )
        persistence = round(high_severe / n_windows, 4)
        score       = round(total * persistence, 2)

        if persistence == 0.0:
            continue   # never congested — skip

        # Find the first sub-window where congestion started
        congested_since: Optional[str] = None
        for i, c in enumerate(counts):
            if _density_label(c) in ("HIGH", "SEVERE"):
                congested_since = sub_windows[i][0].isoformat()
                break

        avg_speed = _estimate_camera_avg_speed(db, cam_id, window_start)
        cong_level = _congestion_label(avg_speed)

        bottleneck_items.append(BottleneckItem(
            rank             = 0,   # filled below after sort
            camera_id        = cam_id,
            location_name    = cam.location_name,
            road_name        = cam.road_name,
            latitude         = cam.latitude,
            longitude        = cam.longitude,
            vehicle_count    = total,
            avg_speed_kmh    = round(avg_speed, 2),
            congestion_level = cong_level,
            persistence      = persistence,
            bottleneck_score = score,
            congested_since  = congested_since,
        ))

    # Sort and assign ranks
    bottleneck_items.sort(key=lambda b: b.bottleneck_score, reverse=True)
    bottleneck_items = bottleneck_items[:top_n]
    for i, item in enumerate(bottleneck_items):
        item.rank = i + 1

    return BottleneckResponse(
        window_hours        = window_hours,
        sub_window_minutes  = sub_window_minutes,
        generated_at        = now,
        total_cameras       = len(all_cameras),
        bottleneck_count    = len(bottleneck_items),
        bottlenecks         = bottleneck_items,
    )
