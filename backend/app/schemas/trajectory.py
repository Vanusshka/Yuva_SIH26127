"""
Pydantic schemas for Phase 4 trajectory endpoints.
"""

from __future__ import annotations
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.trajectory.anomaly import MovementStatus


# ── Camera ────────────────────────────────────────────────────────────────────

class TrajectoryCameraCreate(BaseModel):
    camera_id     : str            = Field(..., example="CAM_001")
    location_name : str            = Field(..., example="Ameerpet Junction")
    road_name     : Optional[str]  = Field(None, example="Ameerpet–Begumpet Road")
    direction     : Optional[str]  = Field(None, example="NORTH_BOUND")
    latitude      : float          = Field(..., ge=-90.0,  le=90.0,  example=17.4375)
    longitude     : float          = Field(..., ge=-180.0, le=180.0, example=78.4483)


class TrajectoryCameraResponse(BaseModel):
    id            : int
    camera_id     : str
    location_name : str
    road_name     : Optional[str]
    direction     : Optional[str]
    latitude      : float
    longitude     : float
    created_at    : datetime

    model_config = {"from_attributes": True}


# ── Detection ─────────────────────────────────────────────────────────────────

class DetectionCreate(BaseModel):
    plate_number         : str      = Field(..., example="TS09AB1234")
    camera_id            : str      = Field(..., example="CAM_001")
    timestamp            : datetime = Field(..., example="2026-08-24T10:30:00Z")
    detection_confidence : Optional[float] = Field(None, ge=0.0, le=1.0, example=0.94)


class DetectionResponse(BaseModel):
    id                   : int
    plate_number         : str
    camera_id            : str
    timestamp            : datetime
    detection_confidence : Optional[float]
    created_at           : datetime

    model_config = {"from_attributes": True}


# ── Trajectory ────────────────────────────────────────────────────────────────

class TrajectoryPoint(BaseModel):
    """One camera sighting in the trajectory."""
    detection_id         : int
    camera_id            : str
    location_name        : str
    road_name            : Optional[str]
    direction            : Optional[str]
    latitude             : float
    longitude            : float
    timestamp            : datetime
    detection_confidence : Optional[float]


class HopMetrics(BaseModel):
    """Spatial and temporal metrics between two consecutive detections."""
    from_camera_id          : str
    to_camera_id            : str
    from_timestamp          : datetime
    to_timestamp            : datetime
    distance_km             : float
    time_difference_minutes : float
    average_speed_kmh       : float
    status                  : MovementStatus


class TrajectoryStatistics(BaseModel):
    """Aggregated statistics for the full trajectory."""
    total_detections        : int
    total_hops              : int
    total_distance_km       : float
    total_duration_minutes  : float
    average_speed_kmh       : float
    first_seen              : Optional[datetime]
    last_seen               : Optional[datetime]
    cameras_visited         : List[str]


class TrajectoryResponse(BaseModel):
    """Full trajectory reconstruction response."""
    plate_number : str
    trajectory   : List[TrajectoryPoint]
    hops         : List[HopMetrics]
    statistics   : TrajectoryStatistics
    status       : MovementStatus
