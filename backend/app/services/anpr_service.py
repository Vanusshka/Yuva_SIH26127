"""
ANPR Service – orchestrates the full pipeline:
  image → vehicle detection → plate detection → OCR → DB event → structured result

Phase 3 change: accepts an optional SQLAlchemy Session.
When a session is provided, every valid plate detection is persisted as a VehicleEvent.
"""

from __future__ import annotations
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import numpy as np
from sqlalchemy.orm import Session

from app.config import OUTPUT_DIR
from app.models.vehicle_detector import VehicleDetector, VehicleDetection
from app.models.plate_detector import PlateDetector, PlateDetection
from app.models.ocr_engine import OCREngine, OCRResult
from app.schemas.anpr import ANPRResponse, DetectionResult
from app.schemas.vehicle_event import ANPRResponseV3, DetectionResultWithEvent
from app.utils.image_utils import load_image, save_image, annotate_image


# Module-level singletons (loaded once per worker process)
_vehicle_detector = VehicleDetector()
_plate_detector   = PlateDetector()
_ocr_engine       = OCREngine()


# ── internal helpers ──────────────────────────────────────────────────────────

def _plate_inside_vehicle(plate_bbox: List[int], vehicle_bbox: List[int]) -> bool:
    """Return True if the plate centroid falls inside the vehicle bounding box."""
    cx = (plate_bbox[0] + plate_bbox[2]) // 2
    cy = (plate_bbox[1] + plate_bbox[3]) // 2
    return (vehicle_bbox[0] <= cx <= vehicle_bbox[2] and
            vehicle_bbox[1] <= cy <= vehicle_bbox[3])


# ── public API ────────────────────────────────────────────────────────────────

def process_image(
    image_path     : str | Path,
    camera_id      : str = "CAM_001",
    save_annotated : bool = True,
    db             : Optional[Session] = None,
) -> ANPRResponseV3:
    """
    Full ANPR pipeline for a single image.

    Parameters
    ----------
    image_path     : path to input image
    camera_id      : camera identifier (validated by caller before passing here)
    save_annotated : write annotated image to OUTPUT_DIR
    db             : SQLAlchemy session; if supplied, events are persisted

    Returns
    -------
    ANPRResponseV3  – Phase 3 response with event_id on each detection
    """
    from app.services.event_service import create_event   # local import avoids circular

    image_path = Path(image_path)
    image      = load_image(image_path)
    timestamp  = datetime.now(timezone.utc)

    # ── 1. Vehicle detection ──────────────────────────────────────────────────
    vehicles: List[VehicleDetection] = _vehicle_detector.detect(image)

    # ── 2. Plate detection on full image ──────────────────────────────────────
    plates: List[PlateDetection] = _plate_detector.detect(image)

    # ── 3. OCR on every plate crop ────────────────────────────────────────────
    plate_ocr: List[tuple[PlateDetection, OCRResult]] = []
    for plate in plates:
        ocr = _ocr_engine.read_plate(plate.cropped_image)
        plate_ocr.append((plate, ocr))

    # ── 4. Match plates → vehicles ────────────────────────────────────────────
    detections: List[DetectionResultWithEvent] = []
    used_plates: set[int] = set()

    for vehicle in vehicles:
        best_plate : Optional[PlateDetection] = None
        best_ocr   : Optional[OCRResult]      = None
        best_score  = -1.0
        best_idx    = -1

        for idx, (plate, ocr) in enumerate(plate_ocr):
            if idx in used_plates:
                continue
            if _plate_inside_vehicle(plate.bbox, vehicle.bbox):
                score = plate.confidence + (ocr.ocr_confidence or 0.0)
                if score > best_score:
                    best_score = score
                    best_plate = plate
                    best_ocr   = ocr
                    best_idx   = idx

        if best_plate and best_idx >= 0:
            used_plates.add(best_idx)

        # ── 5. Persist event ──────────────────────────────────────────────────
        event_id: Optional[int] = None
        if db is not None:
            ev = create_event(
                db           = db,
                camera_id    = camera_id,
                timestamp    = timestamp,
                plate_number = best_ocr.plate_number  if best_ocr   else None,
                vehicle_type = vehicle.vehicle_class,
                vehicle_conf = vehicle.confidence,
                plate_conf   = best_plate.confidence  if best_plate else None,
                ocr_conf     = best_ocr.ocr_confidence if best_ocr  else None,
                image_path   = None,  # filled in after annotated image is saved
            )
            event_id = ev.id

        detections.append(
            DetectionResultWithEvent(
                event_id           = event_id,
                vehicle_type       = vehicle.vehicle_class,
                vehicle_confidence = vehicle.confidence,
                plate_number       = best_ocr.plate_number    if best_ocr   else None,
                plate_confidence   = best_plate.confidence    if best_plate else None,
                ocr_confidence     = best_ocr.ocr_confidence  if best_ocr   else None,
                vehicle_bbox       = vehicle.bbox,
                plate_bbox         = best_plate.bbox          if best_plate else None,
                raw_ocr_text       = best_ocr.raw_text        if best_ocr   else None,
            )
        )

    # ── Orphan plates (not matched to any vehicle) ────────────────────────────
    for idx, (plate, ocr) in enumerate(plate_ocr):
        if idx not in used_plates:
            event_id = None
            if db is not None:
                ev = create_event(
                    db           = db,
                    camera_id    = camera_id,
                    timestamp    = timestamp,
                    plate_number = ocr.plate_number or None,
                    vehicle_type = "unknown",
                    vehicle_conf = 0.0,
                    plate_conf   = plate.confidence,
                    ocr_conf     = ocr.ocr_confidence or None,
                    image_path   = None,
                )
                event_id = ev.id

            detections.append(
                DetectionResultWithEvent(
                    event_id           = event_id,
                    vehicle_type       = "unknown",
                    vehicle_confidence = 0.0,
                    plate_number       = ocr.plate_number  or None,
                    plate_confidence   = plate.confidence,
                    ocr_confidence     = ocr.ocr_confidence or None,
                    vehicle_bbox       = [0, 0, 0, 0],
                    plate_bbox         = plate.bbox,
                    raw_ocr_text       = ocr.raw_text      or None,
                )
            )

    # ── 6. Annotated output image ─────────────────────────────────────────────
    annotated_path: Optional[str] = None
    if save_annotated:
        annotated = annotate_image(image, detections)
        out_name  = f"{image_path.stem}_{uuid.uuid4().hex[:8]}_annotated{image_path.suffix}"
        out_path  = OUTPUT_DIR / out_name
        save_image(annotated, out_path)
        annotated_path = str(out_path)

        # Back-fill image_path on events that were just created
        if db is not None:
            from app.models.vehicle_event import VehicleEvent
            for det in detections:
                if det.event_id is not None:
                    ev_row = db.query(VehicleEvent).filter(
                        VehicleEvent.id == det.event_id
                    ).first()
                    if ev_row:
                        ev_row.image_path = annotated_path
            db.commit()

    return ANPRResponseV3(
        camera_id            = camera_id,
        timestamp            = timestamp.isoformat(),
        image_name           = image_path.name,
        total_vehicles       = len(vehicles),
        detections           = detections,
        annotated_image_path = annotated_path,
    )
