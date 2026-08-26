"""
Pydantic schemas for Phase 7 extended analytics endpoints.

GET /analytics/vehicles
GET /analytics/cameras
"""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


# ── Vehicle type breakdown ────────────────────────────────────────────────────

class VehicleTypeCount(BaseModel):
    vehicle_type : str  = Field(..., example="car")
    count        : int  = Field(..., example=142)
    percentage   : float= Field(..., example=58.2)


class VehicleBreakdownResponse(BaseModel):
    """Response for GET /analytics/vehicles"""
    window_hours       : int              = Field(..., example=24)
    total_detections   : int              = Field(..., example=244)
    breakdown          : List[VehicleTypeCount]
    most_common_type   : Optional[str]    = Field(None, example="car")
    congestion_score   : float            = Field(
        ...,
        example=0.49,
        description=(
            "Normalised congestion score 0.0–1.0+. "
            "Formula: (total_detections / (500 * window_hours)) rounded to 2dp. "
            "500 vehicles/hour is the configurable baseline capacity."
        ),
    )
    formula_note       : str              = Field(
        default=(
            "congestion_score = round(total_detections / (MAX_HOURLY_CAPACITY * window_hours), 2) "
            "where MAX_HOURLY_CAPACITY = 500 vehicles/hour"
        )
    )


# ── Per-camera statistics ─────────────────────────────────────────────────────

class CameraStatItem(BaseModel):
    camera_id      : str           = Field(..., example="CAM_001")
    location_name  : str           = Field(..., example="Ameerpet Junction")
    road_name      : Optional[str] = Field(None, example="Ameerpet–Punjagutta Road")
    latitude       : float         = Field(..., example=17.4375)
    longitude      : float         = Field(..., example=78.4483)
    vehicle_count  : int           = Field(..., example=47)
    unique_plates  : int           = Field(..., example=41)
    traffic_density: str           = Field(..., example="MEDIUM")
    congestion_level: str          = Field(..., example="LOW")


class CameraStatsResponse(BaseModel):
    """Response for GET /analytics/cameras"""
    window_hours       : int                = Field(..., example=24)
    total_cameras      : int                = Field(..., example=15)
    most_active_camera : Optional[str]      = Field(None, example="CAM_001")
    cameras            : List[CameraStatItem]
