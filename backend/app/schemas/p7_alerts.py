"""
Pydantic schemas for Phase 7 combined alert feed.

GET /alerts
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class CombinedAlertItem(BaseModel):
    alert_type   : str            = Field(
        ...,
        example="BLACKLISTED_VEHICLE",
        description=(
            "BLACKLISTED_VEHICLE | CONGESTION | SUSPICIOUS_TRAJECTORY | "
            "IMPOSSIBLE_TRAJECTORY | LOW_CONFIDENCE_ANPR | FREQUENT_SIGHTINGS"
        ),
    )
    severity     : str            = Field(..., example="CRITICAL",
                                          description="INFO | WARNING | CRITICAL")
    camera_id    : Optional[str]  = Field(None, example="CAM_001")
    plate_number : Optional[str]  = Field(None, example="TS08AB1234")
    message      : str            = Field(..., example="[DEMO] Blacklisted plate TS08AB1234 detected at CAM_001")
    timestamp    : datetime       = Field(..., example="2026-08-24T10:30:00+00:00")
    demo_data    : bool           = Field(
        default=False,
        description="True when this alert is based on DEMO/SIMULATED data (e.g. demo blacklist).",
    )
    metadata     : Optional[dict] = Field(
        default=None,
        description="Additional context (blacklist category, speed, etc.)",
    )


class CombinedAlertsResponse(BaseModel):
    """Response for GET /alerts"""
    total_alerts      : int                   = Field(..., example=5)
    critical_count    : int                   = Field(..., example=2)
    warning_count     : int                   = Field(..., example=2)
    info_count        : int                   = Field(..., example=1)
    demo_disclaimer   : str                   = Field(
        default=(
            "Alerts marked demo_data=true are based on SIMULATED data created for "
            "SIH26127 development purposes. They do NOT represent real law-enforcement "
            "records or real surveillance data."
        )
    )
    alerts            : List[CombinedAlertItem]
