"""
Pydantic schemas for Camera API endpoints.
"""

from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ── Request ───────────────────────────────────────────────────────────────────

class CameraCreate(BaseModel):
    camera_id : str   = Field(..., min_length=1, max_length=50,  example="CAM_001")
    name      : str   = Field(..., min_length=1, max_length=200, example="Ameerpet Junction Camera")
    latitude  : float = Field(..., ge=-90.0,  le=90.0,           example=17.4375)
    longitude : float = Field(..., ge=-180.0, le=180.0,          example=78.4483)
    address   : Optional[str] = Field(None, max_length=500,      example="Ameerpet Junction, Hyderabad")
    status    : Literal["ACTIVE", "INACTIVE"] = Field("ACTIVE",  example="ACTIVE")

    @field_validator("camera_id")
    @classmethod
    def _no_spaces(cls, v: str) -> str:
        if " " in v:
            raise ValueError("camera_id must not contain spaces")
        return v.upper()


class CameraUpdate(BaseModel):
    name      : Optional[str]  = Field(None, max_length=200)
    latitude  : Optional[float]= Field(None, ge=-90.0,  le=90.0)
    longitude : Optional[float]= Field(None, ge=-180.0, le=180.0)
    address   : Optional[str]  = Field(None, max_length=500)
    status    : Optional[Literal["ACTIVE", "INACTIVE"]] = None


# ── Response ──────────────────────────────────────────────────────────────────

class CameraResponse(BaseModel):
    id         : int
    camera_id  : str
    name       : str
    latitude   : float
    longitude  : float
    address    : Optional[str]
    status     : str
    created_at : datetime

    model_config = {"from_attributes": True}
