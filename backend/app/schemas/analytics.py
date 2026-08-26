"""
Pydantic schemas for Phase 5 Analytics API endpoints.
"""

from __future__ import annotations
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


# ── Overview ──────────────────────────────────────────────────────────────────

class OverviewResponse(BaseModel):
    total_active_cameras    : int   = Field(..., example=15)
    total_detections        : int   = Field(..., example=1240)
    suspicious_vehicle_count: int   = Field(..., example=3)
    congested_locations_count: int  = Field(..., example=4)
    total_unique_plates     : int   = Field(..., example=312)


# ── Traffic density ───────────────────────────────────────────────────────────

class TrafficDensityItem(BaseModel):
    camera_id      : str
    location_name  : str
    latitude       : float
    longitude      : float
    vehicle_count  : int
    traffic_density: str   # LOW | MEDIUM | HIGH | SEVERE


class TrafficDensityResponse(BaseModel):
    window_hours   : int
    items          : List[TrafficDensityItem]


# ── Congestion ────────────────────────────────────────────────────────────────

class CongestionItem(BaseModel):
    camera_id          : str
    location_name      : str
    latitude           : float
    longitude          : float
    vehicle_count      : int
    avg_speed_kmh      : float
    congestion_level   : str   # LOW | MEDIUM | HIGH | SEVERE
    road_name          : Optional[str]


class CongestionResponse(BaseModel):
    items: List[CongestionItem]


# ── Peak hours ────────────────────────────────────────────────────────────────

class PeakHourItem(BaseModel):
    hour         : int    # 0-23
    vehicle_count: int


class PeakHoursResponse(BaseModel):
    hours: List[PeakHourItem]


# ── Alerts ────────────────────────────────────────────────────────────────────

class AlertItem(BaseModel):
    alert_type  : str    # CONGESTION | SUSPICIOUS | IMPOSSIBLE
    severity    : str    # INFO | WARNING | CRITICAL
    camera_id   : Optional[str]
    plate_number: Optional[str]
    message     : str
    timestamp   : datetime


class AlertsResponse(BaseModel):
    alerts: List[AlertItem]
