"""
Pydantic schemas for ANPR API request / response.
"""

from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class DetectionResult(BaseModel):
    vehicle_type: str                   = Field(..., example="car")
    vehicle_confidence: float           = Field(..., example=0.95)
    plate_number: Optional[str]         = Field(None, example="TS09AB1234")
    plate_confidence: Optional[float]   = Field(None, example=0.88)
    ocr_confidence: Optional[float]     = Field(None, example=0.92)
    vehicle_bbox: List[int]             = Field(..., example=[100, 80, 400, 350])
    plate_bbox: Optional[List[int]]     = Field(None, example=[150, 280, 360, 330])
    raw_ocr_text: Optional[str]         = Field(None, example="TS 09 AB 1234")


class ANPRResponse(BaseModel):
    camera_id: str                      = Field(..., example="CAM_001")
    timestamp: str                      = Field(..., example="2026-08-24T12:30:00")
    image_name: str                     = Field(..., example="traffic.jpg")
    total_vehicles: int                 = Field(..., example=2)
    detections: List[DetectionResult]   = Field(default_factory=list)
    annotated_image_path: Optional[str] = Field(None)


class HealthResponse(BaseModel):
    status: str = Field(..., example="running")
    version: str
