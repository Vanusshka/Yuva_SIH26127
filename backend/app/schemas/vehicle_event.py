"""
Pydantic schemas for VehicleEvent API endpoints.
"""

from __future__ import annotations
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ── Single event ──────────────────────────────────────────────────────────────

class VehicleEventResponse(BaseModel):
    id                 : int
    plate_number       : Optional[str]
    camera_id          : str
    timestamp          : datetime
    vehicle_type       : Optional[str]
    vehicle_confidence : Optional[float]
    plate_confidence   : Optional[float]
    ocr_confidence     : Optional[float]
    image_path         : Optional[str]
    created_at         : datetime

    model_config = {"from_attributes": True}


# ── Vehicle history ───────────────────────────────────────────────────────────

class VehicleHistoryEvent(BaseModel):
    event_id    : int
    camera_id   : str
    camera_name : str
    latitude    : float
    longitude   : float
    address     : Optional[str]
    timestamp   : datetime
    vehicle_type: Optional[str]

    model_config = {"from_attributes": True}


class VehicleHistoryResponse(BaseModel):
    plate_number      : str
    total_detections  : int
    events            : List[VehicleHistoryEvent]


# ── Extended ANPR response (Phase 3) ─────────────────────────────────────────

class DetectionResultWithEvent(BaseModel):
    """ANPR detection result enriched with the saved database event_id."""
    event_id           : Optional[int]   = Field(None, example=1)
    vehicle_type       : str             = Field(...,  example="car")
    vehicle_confidence : float           = Field(...,  example=0.95)
    plate_number       : Optional[str]   = Field(None, example="TS09AB1234")
    plate_confidence   : Optional[float] = Field(None, example=0.91)
    ocr_confidence     : Optional[float] = Field(None, example=0.92)
    vehicle_bbox       : List[int]       = Field(...,  example=[100, 80, 400, 350])
    plate_bbox         : Optional[List[int]] = Field(None, example=[150, 280, 360, 330])
    raw_ocr_text       : Optional[str]   = Field(None, example="TS 09 AB 1234")


class ANPRResponseV3(BaseModel):
    """Phase 3 ANPR response – includes database event IDs."""
    camera_id              : str
    timestamp              : str
    image_name             : str
    total_vehicles         : int
    detections             : List[DetectionResultWithEvent]
    annotated_image_path   : Optional[str] = None
