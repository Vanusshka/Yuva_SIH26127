"""
Pydantic schemas for advanced analytics endpoints:
  C3 — Traffic heatmap (GeoJSON point-density for map overlay)
  C4 — Origin-Destination matrix (camera-pair flow counts)
  C5 — Congestion bottleneck ranking (worst segments with persistence)
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# C3 — Traffic Heatmap
# ─────────────────────────────────────────────────────────────────────────────

class HeatmapPoint(BaseModel):
    """One camera's density contribution for the heatmap layer."""
    camera_id     : str   = Field(..., example="CAM_001")
    location_name : str   = Field(..., example="Ameerpet Junction")
    latitude      : float = Field(..., example=17.4375)
    longitude     : float = Field(..., example=78.4483)
    vehicle_count : int   = Field(..., example=42)
    density_label : str   = Field(..., example="HIGH",
                                   description="LOW | MEDIUM | HIGH | SEVERE")
    # Normalised 0.0–1.0 weight for map heatmap rendering
    # (vehicle_count / max_count_in_window)
    intensity     : float = Field(..., example=0.73,
                                   description="0.0–1.0, max across all cameras = 1.0")


class HeatmapGeoJSONFeature(BaseModel):
    """One GeoJSON Point Feature for a camera."""
    type       : str         = Field(default="Feature")
    geometry   : Dict[str, Any] = Field(
        ...,
        example={"type": "Point", "coordinates": [78.4483, 17.4375]},
    )
    properties : Dict[str, Any] = Field(
        ...,
        example={
            "camera_id"    : "CAM_001",
            "location_name": "Ameerpet Junction",
            "vehicle_count": 42,
            "density_label": "HIGH",
            "intensity"    : 0.73,
        },
    )


class HeatmapResponse(BaseModel):
    """
    Response for GET /analytics/heatmap

    Returns both a flat list (for simple charting) and a GeoJSON FeatureCollection
    (for Leaflet / Mapbox heatmap layer — feed directly to L.heatLayer or
    mapboxgl addSource type='geojson').

    intensity values are normalised 0.0–1.0 relative to the busiest camera
    in the requested time window. Use these as the weight/radius inputs for
    your heatmap renderer.
    """
    window_hours      : int                      = Field(..., example=1)
    generated_at      : datetime                 = Field(
        default_factory=datetime.utcnow
    )
    total_cameras     : int                      = Field(..., example=15)
    max_vehicle_count : int                      = Field(
        ..., example=42,
        description="Highest vehicle count across all cameras — denominator for intensity"
    )
    # Flat list for table/chart rendering
    points            : List[HeatmapPoint]
    # GeoJSON FeatureCollection for map layer rendering
    geojson           : Dict[str, Any]           = Field(
        ...,
        description=(
            "GeoJSON FeatureCollection. Feed to Leaflet L.heatLayer() or "
            "Mapbox addSource(type='geojson') directly."
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# C4 — Origin-Destination Matrix
# ─────────────────────────────────────────────────────────────────────────────

class ODPair(BaseModel):
    """
    A single origin→destination camera pair with flow count.

    origin   = first camera a plate was seen at (within the time window)
    dest     = last camera that same plate was seen at
    count    = number of distinct plates that made this journey
    avg_duration_min = average time between first and last sighting
    avg_distance_km  = Haversine distance between origin and dest cameras
    """
    origin_camera_id   : str           = Field(..., example="CAM_001")
    origin_location    : str           = Field(..., example="Ameerpet Junction")
    origin_lat         : float         = Field(..., example=17.4375)
    origin_lon         : float         = Field(..., example=78.4483)
    dest_camera_id     : str           = Field(..., example="CAM_005")
    dest_location      : str           = Field(..., example="Secunderabad Railway Station")
    dest_lat           : float         = Field(..., example=17.4399)
    dest_lon           : float         = Field(..., example=78.4983)
    vehicle_count      : int           = Field(..., example=7,
                                               description="Distinct plates on this OD pair")
    avg_duration_min   : float         = Field(..., example=18.4)
    avg_distance_km    : float         = Field(..., example=5.6)
    # GeoJSON LineString for map arc rendering
    geojson_line       : Dict[str, Any] = Field(
        ...,
        example={
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[78.4483, 17.4375], [78.4983, 17.4399]],
            },
            "properties": {"vehicle_count": 7, "avg_duration_min": 18.4},
        },
    )


class ODMatrixResponse(BaseModel):
    """
    Response for GET /analytics/od-matrix

    Returns the top N origin-destination pairs by flow volume.
    Each pair is a (first_camera → last_camera) tuple derived from the real
    Detection table — plates that appeared at only one camera are excluded
    (no journey to measure).

    The geojson_line in each ODPair can be fed to a Leaflet or Mapbox
    LineString layer to draw desire-line arcs on the city map.
    """
    window_hours        : int           = Field(..., example=24)
    generated_at        : datetime      = Field(default_factory=datetime.utcnow)
    total_plates_tracked: int           = Field(
        ..., example=48,
        description="Distinct plates that appeared at >= 2 cameras in window"
    )
    total_od_pairs      : int           = Field(..., example=12)
    pairs               : List[ODPair]
    # GeoJSON FeatureCollection of all OD arcs for one-shot map rendering
    geojson             : Dict[str, Any] = Field(
        ...,
        description="GeoJSON FeatureCollection of LineString arcs. One feature per OD pair.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# C5 — Congestion Bottleneck Detection
# ─────────────────────────────────────────────────────────────────────────────

class BottleneckItem(BaseModel):
    """
    One congestion bottleneck location — a camera that has been HIGH or SEVERE
    for a sustained period, ranked by severity × persistence.

    bottleneck_score = vehicle_count × persistence_weight
    where persistence_weight is the fraction of sub-windows in the look-back
    period that were HIGH or SEVERE.
    """
    rank               : int           = Field(..., example=1)
    camera_id          : str           = Field(..., example="CAM_001")
    location_name      : str           = Field(..., example="Ameerpet Junction")
    road_name          : Optional[str] = Field(None,  example="Ameerpet–Punjagutta Road")
    latitude           : float         = Field(..., example=17.4375)
    longitude          : float         = Field(..., example=78.4483)
    vehicle_count      : int           = Field(
        ..., example=42,
        description="Total vehicles in the full look-back window"
    )
    avg_speed_kmh      : float         = Field(..., example=14.5)
    congestion_level   : str           = Field(..., example="SEVERE",
                                               description="LOW | MEDIUM | HIGH | SEVERE")
    # Fraction of sub-windows (0.0–1.0) where this camera was HIGH/SEVERE
    persistence        : float         = Field(
        ..., example=0.83,
        description="0.0–1.0 — fraction of sub-windows in look-back that were HIGH/SEVERE"
    )
    # Combined severity score for ranking: vehicle_count * persistence
    bottleneck_score   : float         = Field(..., example=34.9)
    # How long this camera has been congested (consecutive sub-windows)
    congested_since    : Optional[str] = Field(
        None, example="2026-09-04T14:00:00+00:00",
        description="ISO timestamp of the first sub-window where congestion was detected"
    )


class BottleneckResponse(BaseModel):
    """
    Response for GET /analytics/bottlenecks

    Identifies the worst sustained congestion points in the camera network
    by combining current vehicle density with temporal persistence.

    A camera that briefly spikes HIGH scores lower than one that has been
    HIGH for several consecutive sub-windows — this catches genuine structural
    bottlenecks rather than momentary peaks.

    Method:
      1. Divide window_hours into sub-windows of sub_window_minutes each
      2. For each sub-window + camera: label HIGH/SEVERE if vehicle_count ≥ threshold
      3. persistence = fraction of sub-windows where camera was HIGH/SEVERE
      4. bottleneck_score = vehicle_count_total × persistence
      5. Rank by bottleneck_score descending, return top N
    """
    window_hours       : int                  = Field(..., example=3)
    sub_window_minutes : int                  = Field(..., example=30)
    generated_at       : datetime             = Field(default_factory=datetime.utcnow)
    total_cameras      : int                  = Field(..., example=15)
    bottleneck_count   : int                  = Field(
        ..., example=3,
        description="Number of cameras with persistence > 0 (i.e. congested at least once)"
    )
    bottlenecks        : List[BottleneckItem]
