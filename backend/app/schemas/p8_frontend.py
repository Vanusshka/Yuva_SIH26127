"""
Phase 8 – Frontend-Ready Schemas
=================================

Clean, flat JSON structures designed for the UrbanEye AI React frontend.
These are separate from the internal Phase 2-7 schemas so existing endpoints
are completely unaffected.

All schemas follow the exact response shapes requested in the Phase 8 spec.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════════════
# VEHICLE SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

class VehicleRecord(BaseModel):
    """
    Frontend-ready vehicle summary card.

    Returned by:
      GET /vehicles           (in a list)
      GET /vehicles/{plate}   (single item)
    """
    plate_number   : str            = Field(...,  example="TS09AB1234")
    vehicle_type   : str            = Field(...,  example="car",
                                             description="car | motorcycle | bus | truck | unknown")
    confidence     : float          = Field(...,  example=0.94,
                                             description="Highest detection confidence seen for this plate")
    first_seen     : Optional[datetime] = Field(None, example="2026-08-24T08:00:00+00:00")
    last_seen      : Optional[datetime] = Field(None, example="2026-08-24T08:30:00+00:00")
    camera_count   : int            = Field(...,  example=4,
                                             description="Number of distinct cameras that detected this plate")
    total_sightings: int            = Field(...,  example=4,
                                             description="Total detection events across all cameras")
    status         : str            = Field(...,  example="active",
                                             description="active | suspicious | impossible | unknown")
    last_camera_id : Optional[str]  = Field(None, example="CAM_014")
    last_location  : Optional[str]  = Field(None, example="Paradise Circle")
    is_blacklisted : bool           = Field(False,description="True when plate appears in the demo blacklist")
    blacklist_reason: Optional[str] = Field(None, example="Demo Blacklisted Vehicle – Stolen (SIMULATED)")


class VehicleListResponse(BaseModel):
    """Response for GET /vehicles"""
    total          : int                    = Field(..., example=12)
    vehicles       : List[VehicleRecord]
    generated_at   : datetime               = Field(default_factory=datetime.utcnow)


# ═══════════════════════════════════════════════════════════════════════════════
# TRAJECTORY SCHEMAS (frontend-ready)
# ═══════════════════════════════════════════════════════════════════════════════

class TrajectoryStop(BaseModel):
    """One camera sighting in a trajectory."""
    camera_id      : str            = Field(..., example="CAM_001")
    location       : str            = Field(..., example="Ameerpet Junction")
    road_name      : Optional[str]  = Field(None, example="Ameerpet–Punjagutta Road")
    direction      : Optional[str]  = Field(None, example="NORTH_BOUND")
    latitude       : float          = Field(..., example=17.4375)
    longitude      : float          = Field(..., example=78.4483)
    timestamp      : datetime       = Field(..., example="2026-08-24T08:00:00+00:00")
    confidence     : Optional[float]= Field(None, example=0.96)


class TrajectoryHop(BaseModel):
    """Metrics for travel between two consecutive cameras."""
    from_camera    : str            = Field(..., example="CAM_001")
    to_camera      : str            = Field(..., example="CAM_002")
    distance_km    : float          = Field(..., example=1.23)
    duration_min   : float          = Field(..., example=8.0)
    speed_kmh      : float          = Field(..., example=9.2)
    anomaly        : str            = Field(..., example="NORMAL",
                                            description="NORMAL | FAST | SUSPICIOUS | IMPOSSIBLE")


class FrontendTrajectoryResponse(BaseModel):
    """
    Response for GET /trajectory/{plate}   (Phase 8 frontend-ready version)

    The existing /trajectory/{plate_number} (Phase 4) is preserved unchanged.
    The Phase 7 /vehicle/{plate}/trajectory is a dict alias.
    This schema provides the exact fields the React frontend needs.
    """
    plate_number         : str            = Field(...,  example="TS09AB1234")
    total_observations   : int            = Field(...,  example=4)
    total_distance_km    : float          = Field(...,  example=5.23)
    travel_duration_min  : float          = Field(...,  example=30.0)
    average_speed_kmh    : float          = Field(...,  example=10.46)
    anomaly_score        : float          = Field(...,  example=0.0,
                                                  description="0.0 = NORMAL, 0.33 = FAST, 0.67 = SUSPICIOUS, 1.0 = IMPOSSIBLE")
    overall_status       : str            = Field(...,  example="NORMAL",
                                                  description="NORMAL | FAST | SUSPICIOUS | IMPOSSIBLE")
    first_seen           : Optional[datetime] = Field(None)
    last_seen            : Optional[datetime] = Field(None)
    cameras_visited      : List[str]      = Field(...,  example=["CAM_001","CAM_002","CAM_005","CAM_014"])
    stops                : List[TrajectoryStop]
    hops                 : List[TrajectoryHop]
    data_mode            : str            = Field(
        default="DEMO / SIMULATED TRAJECTORY",
        description="Always present. Real data will say 'LIVE' once a live feed is connected.",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ANALYTICS SCHEMAS (frontend-ready unified dashboard)
# ═══════════════════════════════════════════════════════════════════════════════

class VehicleCategoryItem(BaseModel):
    """One row of the vehicle type distribution."""
    category   : str   = Field(..., example="car")
    count      : int   = Field(..., example=142)
    percentage : float = Field(..., example=58.2)


class CongestionZone(BaseModel):
    """One congested camera location."""
    camera_id        : str           = Field(..., example="CAM_001")
    location         : str           = Field(..., example="Ameerpet Junction")
    latitude         : float         = Field(..., example=17.4375)
    longitude        : float         = Field(..., example=78.4483)
    vehicle_count    : int           = Field(..., example=12)
    avg_speed_kmh    : float         = Field(..., example=18.5)
    congestion_level : str           = Field(..., example="HIGH")


class TrafficTrendPoint(BaseModel):
    """One hourly data point for the traffic trend chart."""
    hour          : int = Field(..., example=8,  description="Hour 0–23")
    vehicle_count : int = Field(..., example=47)


class UnifiedAnalyticsResponse(BaseModel):
    """
    Response for GET /analytics

    Merges all Phase 5 & 7 analytics into a single frontend-friendly payload.
    The frontend only needs one request to populate the full dashboard.
    """
    # KPI cards
    total_vehicles        : int                      = Field(..., example=244)
    total_unique_plates   : int                      = Field(..., example=12)
    total_cameras         : int                      = Field(..., example=15)
    active_alerts         : int                      = Field(..., example=3)
    suspicious_vehicles   : int                      = Field(..., example=1)

    # Vehicle distribution (pie chart)
    vehicle_distribution  : List[VehicleCategoryItem]

    # Traffic density (map overlay)
    traffic_density_label : str                      = Field(..., example="MEDIUM")
    average_speed_kmh     : float                    = Field(..., example=28.4)
    congestion_score      : float                    = Field(..., example=0.49)

    # Congestion zones (map markers)
    congestion_zones      : List[CongestionZone]

    # Traffic trends (line chart, last 24h hourly)
    traffic_trends        : List[TrafficTrendPoint]

    # Most active camera
    most_active_camera    : Optional[str]            = Field(None, example="CAM_001")
    most_active_location  : Optional[str]            = Field(None, example="Ameerpet Junction")

    generated_at          : datetime                 = Field(default_factory=datetime.utcnow)
    window_hours          : int                      = Field(default=24)


# ═══════════════════════════════════════════════════════════════════════════════
# ALERT SCHEMAS (frontend-ready with alert_id)
# ═══════════════════════════════════════════════════════════════════════════════

class FrontendAlertItem(BaseModel):
    """
    Single alert enriched with a stable alert_id for React list keys.

    Returned by GET /alerts (Phase 8 version)
    """
    alert_id     : str            = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Stable UUID for React list key. Re-generated each poll cycle.",
    )
    alert_type   : str            = Field(..., example="BLACKLISTED_VEHICLE",
                                          description=(
                                              "BLACKLISTED_VEHICLE | CONGESTION | "
                                              "IMPOSSIBLE_TRAJECTORY | SUSPICIOUS_TRAJECTORY | "
                                              "LOW_CONFIDENCE_ANPR | FREQUENT_SIGHTINGS"
                                          ))
    severity     : str            = Field(..., example="CRITICAL",
                                          description="INFO | WARNING | CRITICAL")
    plate_number : Optional[str]  = Field(None, example="TS08AB1234")
    location     : Optional[str]  = Field(None, example="Ameerpet Junction")
    camera_id    : Optional[str]  = Field(None, example="CAM_001")
    timestamp    : datetime       = Field(..., example="2026-08-24T10:30:00+00:00")
    message      : str            = Field(..., example="[DEMO] Blacklisted plate TS08AB1234 detected at CAM_001")
    status       : str            = Field(default="open",
                                          description="open | acknowledged | resolved")
    demo_data    : bool           = Field(False,
                                          description="True when based on DEMO/SIMULATED data")


class FrontendAlertsResponse(BaseModel):
    """Response for GET /alerts (Phase 8)"""
    total_alerts   : int                      = Field(..., example=5)
    critical_count : int                      = Field(..., example=2)
    warning_count  : int                      = Field(..., example=2)
    info_count     : int                      = Field(..., example=1)
    alerts         : List[FrontendAlertItem]
    demo_disclaimer: str                      = Field(
        default=(
            "Alerts marked demo_data=true are based on SIMULATED data created for "
            "SIH26127 development purposes. They do NOT represent real law-enforcement "
            "records or real surveillance data."
        )
    )
    generated_at   : datetime                 = Field(default_factory=datetime.utcnow)


# ═══════════════════════════════════════════════════════════════════════════════
# PROCESS ENDPOINT SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════════

class ProcessResponse(BaseModel):
    """
    Unified response for POST /process (Phase 8 frontend shorthand).

    Wraps the existing ImageIngestResponse with an additional
    frontend_summary block so the React UI can show a quick result card
    without parsing the full detections array.
    """
    status              : str             = Field(..., example="ok")
    pipeline_version    : str             = Field(default="8.0")
    source_file         : str             = Field(..., example="car001.jpg")
    camera_id           : str             = Field(..., example="CAM_001")
    timestamp           : str             = Field(..., example="2026-08-24T10:30:00+00:00")
    latitude            : float           = Field(..., example=17.4375)
    longitude           : float           = Field(..., example=78.4483)
    total_vehicles      : int             = Field(..., example=2)
    total_plates        : int             = Field(..., example=2)
    low_confidence_count: int             = Field(..., example=0)
    plates_detected     : List[str]       = Field(..., example=["TS08AB1234", "MH12XY5678"])
    annotated_image_url : Optional[str]   = Field(None, example="/static/output/car001_annotated.jpg")
    warnings            : List[str]       = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# HEALTH (Phase 8 extended)
# ═══════════════════════════════════════════════════════════════════════════════

class Phase8HealthResponse(BaseModel):
    """Extended health response for Phase 8."""
    status          : str            = Field(..., example="running")
    version         : str            = Field(..., example="0.8.0")
    api_phase       : str            = Field(default="Phase 8 – Backend Integration & API Readiness")
    database        : str            = Field(..., example="connected")
    total_cameras   : int            = Field(..., example=15)
    total_detections: int            = Field(..., example=10)
    uptime_note     : str            = Field(
        default="Use GET /analytics for full dashboard data."
    )
