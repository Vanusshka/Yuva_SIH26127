"""
Pydantic schemas for Phase 9 ingestion endpoints.

POST /process/image
POST /process/video

Phase 9 additions (all new fields have defaults — backward compatible):
  IngestDetection:
    + track_id           per-vehicle stable ID across frames
    + partial_text       honest partial OCR when plate is not VERIFIED
    + plate_status       VERIFIED | PARTIAL | LOW_CONFIDENCE | UNREADABLE
    + quality_score      0.0–1.0 image quality
    + preprocessing_method  which variant was used
    + supporting_frames  frame numbers that contributed to this result

  ImageIngestResponse:
    + verified_plates    count of VERIFIED detections
    + partial_plates     count of PARTIAL detections

  VideoIngestResponse:
    + partial_plates     list of honest partial OCR texts
    + verified_count     count of unique VERIFIED plates
    + partial_count      count of unique PARTIAL plates
    + unreadable_count   count of UNREADABLE detections
"""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


# ── Per-detection result ───────────────────────────────────────────────────────

class IngestDetection(BaseModel):
    """One vehicle / plate detection produced by the Phase 9 pipeline."""

    # Vehicle
    vehicle_type         : str             = Field(...,  example="car")
    vehicle_confidence   : float           = Field(...,  example=0.95)
    vehicle_bbox         : List[int]       = Field(...,  example=[100, 80, 400, 350])
    track_id             : str             = Field("T0000", description="Stable vehicle track ID across frames")

    # Plate — VERIFIED result (complete, evidence-supported)
    plate_number         : Optional[str]   = Field(None, example="TS08AB1234",
                                                    description="Only populated when plate_status=verified")
    # Plate — PARTIAL result (honest fragment, never fabricated)
    partial_text         : Optional[str]   = Field(None, example="TS08A",
                                                    description="Honest partial OCR when not fully verified")
    plate_status         : str             = Field("unreadable",
                                                    description="verified | partial | low_confidence | unreadable")

    # OCR & plate metadata
    plate_raw_text       : Optional[str]   = Field(None, example="ts 08 ab 1234")
    plate_confidence     : Optional[float] = Field(None, example=0.88)
    ocr_confidence       : Optional[float] = Field(None, example=0.92)
    plate_bbox           : Optional[List[int]] = Field(None, example=[150, 280, 360, 330])
    plate_normalised     : bool            = Field(False)
    low_confidence       : bool            = Field(False, description="True if OCR confidence < 0.50")

    # Quality metadata (Phase 9)
    quality_score        : float           = Field(0.0,  description="0.0–1.0 composite plate crop quality")
    preprocessing_method : str             = Field("unknown", description="Preprocessing variant that produced best OCR")
    supporting_frames    : List[int]       = Field(default_factory=list,
                                                    description="Frame numbers that contributed OCR evidence")

    # Provenance
    frame_number         : int             = Field(...,  example=0)
    timestamp            : str             = Field(...,  example="2026-08-24T10:30:00+00:00")
    camera_id            : str             = Field(...,  example="CAM_001")
    latitude             : float           = Field(...,  example=17.4375)
    longitude            : float           = Field(...,  example=78.4483)
    source_file          : str             = Field(...,  example="traffic_video_01.mp4")

    # DB storage
    event_id             : Optional[int]   = Field(None)
    detection_id         : Optional[int]   = Field(None)


# ── Image response ────────────────────────────────────────────────────────────

class ImageIngestResponse(BaseModel):
    """Response from POST /process/image"""

    status               : str             = Field(...,  example="ok")
    source_file          : str             = Field(...,  example="car_001.jpg")
    camera_id            : str             = Field(...,  example="CAM_001")
    timestamp            : str             = Field(...,  example="2026-08-24T10:30:00+00:00")
    latitude             : float           = Field(...,  example=17.4375)
    longitude            : float           = Field(...,  example=78.4483)
    total_vehicles       : int             = Field(...,  example=3)
    total_plates         : int             = Field(...,  example=2)
    verified_plates      : int             = Field(0,    description="Count of VERIFIED plate reads")
    partial_plates       : int             = Field(0,    description="Count of PARTIAL plate reads")
    low_confidence_plates: int             = Field(...,  example=0)
    detections           : List[IngestDetection]
    annotated_image_url  : Optional[str]   = Field(None)
    warnings             : List[str]       = Field(default_factory=list)


# ── Video response ────────────────────────────────────────────────────────────

class VideoIngestResponse(BaseModel):
    """Response from POST /process/video"""

    status               : str             = Field(...,  example="ok")
    source_file          : str             = Field(...,  example="traffic_video_01.mp4")
    camera_id            : str             = Field(...,  example="CAM_001")
    total_frames         : int             = Field(...,  example=300)
    frames_processed     : int             = Field(...,  example=60)
    frame_skip           : int             = Field(...,  example=5)
    total_detections     : int             = Field(...,  example=87)

    # Only VERIFIED plates are counted as "unique plates"
    unique_plates        : List[str]       = Field(...,
                                                    description="VERIFIED plate numbers only — evidence-supported, not fabricated",
                                                    example=["TS08AB1234"])
    # Honest partial reads — displayed separately, not counted as verified unique plates
    partial_plates       : List[str]       = Field(default_factory=list,
                                                    description="Honest partial OCR texts — not complete plates",
                                                    example=["TS08A"])

    verified_count       : int             = Field(0,    description="Number of unique VERIFIED plates")
    partial_count        : int             = Field(0,    description="Number of unique PARTIAL texts")
    low_confidence_plates: int             = Field(...,  example=2)
    unreadable_count     : int             = Field(0,    description="Detections where plate could not be read")
    detections           : List[IngestDetection]
    warnings             : List[str]       = Field(default_factory=list)
    processing_note      : str             = Field(
        default="Frame skip configurable. Only verified plates shown as unique. Partials shown separately."
    )
