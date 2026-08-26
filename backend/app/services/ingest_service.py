"""
Ingestion Service — Phase 9 (Complete Rewrite)
===============================================

Pipeline per frame
------------------
  frame → VehicleDetector (YOLOv8n)
        → per vehicle:
            PlateDetector (YOLO crop-first → full-frame fallback, with padding)
            ImageQuality  (brightness / sharpness / blur scoring)
            OCREngine     (multi-variant preprocessing, best result)
            PlateObservation → accumulated in per-track PlateEvidence
  After all frames processed:
        → PlateEvidence.consensus() → ConsensuResult per track
        → IngestDetection list with plate_status field

No fabrication:
  - Fragments < MIN_CHARS_NOISE characters are discarded
  - Only VERIFIED results populate plate_number
  - PARTIAL results populate partial_text
  - UNREADABLE results have both fields as None
"""

from __future__ import annotations

import logging
import re
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from sqlalchemy.orm import Session

from app.config import OUTPUT_DIR
from app.models.vehicle_detector import VehicleDetector, VehicleDetection
from app.models.plate_detector   import PlateDetector,   PlateDetection
from app.models.ocr_engine       import OCREngine,        OCRResult
from app.models.image_quality    import analyse           as analyse_quality
from app.models.plate_result     import (
    PlateObservation, PlateEvidence, ConsensuResult,
    PlateStatus, classify_observation,
)
from app.services.event_service     import create_event
from app.services.detection_service import create_detection
from app.schemas.trajectory         import DetectionCreate
from app.schemas.ingest             import IngestDetection, ImageIngestResponse, VideoIngestResponse
from app.utils.image_utils          import load_image, annotate_image, save_image
from app.utils.metadata_loader      import get_camera_gps, get_camera_meta

logger = logging.getLogger(__name__)

# ── Model singletons (loaded once per worker process) ─────────────────────────
_vehicle_detector = VehicleDetector()
_plate_detector   = PlateDetector()
_ocr_engine       = OCREngine()

# ── Thresholds ────────────────────────────────────────────────────────────────
_LOW_CONF_THRESHOLD    = 0.50    # below this → low_confidence flag in detection
_DEBUG_PLATE_IMAGES    = False   # set True for diagnostic images in OUTPUT_DIR/debug_plates/
_YOLO_VEHICLE_CONF     = 0.40   # minimum vehicle detection confidence


# ═══════════════════════════════════════════════════════════════════════════════
# PLATE NORMALISATION
# ═══════════════════════════════════════════════════════════════════════════════

_PLATE_RE = re.compile(
    r"^([A-Z]{2})\s*[\-]?\s*(\d{1,2})\s*[\-]?\s*([A-Z]{1,3})\s*[\-]?\s*(\d{1,4})$"
)


def normalise_plate(raw: str) -> Tuple[str, bool]:
    """
    Normalise to canonical uppercase no-separator form.
    Returns (canonical, was_changed).
    NEVER adds or guesses missing characters.
    """
    if not raw:
        return raw, False
    cleaned = raw.upper().strip()
    no_sep  = re.sub(r"[\s\-_]", "", cleaned)
    m = _PLATE_RE.match(no_sep)
    if m:
        canonical   = "".join(m.groups())
        was_changed = canonical != cleaned
        return canonical, was_changed
    return no_sep if no_sep else cleaned, no_sep != cleaned


# ═══════════════════════════════════════════════════════════════════════════════
# SIMPLE SPATIAL TRACKER
# Assigns a stable track_id to each vehicle bbox across frames using IoU.
# No external library dependency.
# ═══════════════════════════════════════════════════════════════════════════════

def _iou(a: List[int], b: List[int]) -> float:
    """Intersection over Union of two [x1,y1,x2,y2] boxes."""
    ix1 = max(a[0], b[0]); iy1 = max(a[1], b[1])
    ix2 = min(a[2], b[2]); iy2 = min(a[3], b[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    area_a = (a[2]-a[0]) * (a[3]-a[1])
    area_b = (b[2]-b[0]) * (b[3]-b[1])
    return inter / max(1, area_a + area_b - inter)


class _SimpleTracker:
    """
    Assigns stable track IDs to vehicle bounding boxes across consecutive frames.
    Uses IoU matching; IOU_THRESH controls how close boxes must be to match.
    """

    IOU_THRESH   = 0.35
    MAX_MISS     = 6     # frames a track can be missing before deletion

    def __init__(self):
        self._tracks: Dict[str, dict] = {}   # track_id → {bbox, miss_count, class}
        self._next   = 1

    def update(
        self,
        detections: List[VehicleDetection],
    ) -> List[Tuple[str, VehicleDetection]]:
        """
        Match new detections to existing tracks.
        Returns list of (track_id, VehicleDetection).
        """
        matched_track_ids = set()
        result: List[Tuple[str, VehicleDetection]] = []

        # Match existing tracks to new detections
        for det in detections:
            best_tid  = None
            best_iou  = self.IOU_THRESH
            for tid, t in self._tracks.items():
                iou = _iou(det.bbox, t["bbox"])
                if iou > best_iou:
                    best_iou = iou
                    best_tid = tid
            if best_tid:
                self._tracks[best_tid]["bbox"]       = det.bbox
                self._tracks[best_tid]["miss_count"] = 0
                self._tracks[best_tid]["cls"]        = det.vehicle_class
                matched_track_ids.add(best_tid)
                result.append((best_tid, det))
            else:
                # New track
                tid = f"T{self._next:04d}"
                self._next += 1
                self._tracks[tid] = {"bbox": det.bbox, "miss_count": 0, "cls": det.vehicle_class}
                result.append((tid, det))

        # Increment miss count for unmatched tracks; prune stale ones
        for tid in list(self._tracks):
            if tid not in matched_track_ids:
                self._tracks[tid]["miss_count"] += 1
                if self._tracks[tid]["miss_count"] > self.MAX_MISS:
                    del self._tracks[tid]

        return result


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLE-FRAME DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

def _detect_frame(
    image        : np.ndarray,
    frame_number : int,
    tracker      : _SimpleTracker,
    evidence_map : Dict[str, PlateEvidence],
) -> List[Tuple[str, VehicleDetection, Optional[PlateDetection], Optional[OCRResult], ConsensuResult]]:
    """
    Run full detection pipeline on one frame.

    Returns a list of (track_id, vehicle, plate, ocr, single_frame_consensus)
    for each detected vehicle. The single_frame_consensus is a PROVISIONAL result
    for this frame only; the final result will be computed after all frames.
    """
    # ── Vehicle detection ─────────────────────────────────────────────────────
    try:
        vehicles = _vehicle_detector.detect(image, conf_threshold=_YOLO_VEHICLE_CONF)
        logger.debug("[Ingest] Frame %d: %d vehicle(s)", frame_number, len(vehicles))
    except Exception as exc:
        logger.error("[Ingest] Vehicle detection failed frame %d: %s", frame_number, exc)
        vehicles = []

    # ── Assign track IDs ──────────────────────────────────────────────────────
    tracked = tracker.update(vehicles)

    frame_results = []

    for track_id, vehicle in tracked:
        # Ensure evidence bucket exists
        if track_id not in evidence_map:
            evidence_map[track_id] = PlateEvidence(track_id=track_id)

        # ── Plate detection ───────────────────────────────────────────────────
        best_plate: Optional[PlateDetection] = None
        try:
            plates = _plate_detector.detect(
                image,
                vehicle_bbox = vehicle.bbox,
                frame_number = frame_number,
                save_debug   = _DEBUG_PLATE_IMAGES,
            )
            if plates:
                # Pick plate with highest YOLO confidence
                best_plate = max(plates, key=lambda p: p.confidence)
                logger.debug("[Ingest] Frame %d track %s: plate conf=%.3f bbox=%s",
                             frame_number, track_id, best_plate.confidence, best_plate.bbox)
        except Exception as exc:
            logger.warning("[Ingest] Plate detection failed frame %d track %s: %s",
                           frame_number, track_id, exc)

        # ── Image quality + OCR ───────────────────────────────────────────────
        best_ocr: Optional[OCRResult] = None
        quality_score = 0.0
        preprocessing = "none"

        if best_plate is not None and best_plate.cropped_image.size > 0:
            try:
                quality_report  = analyse_quality(best_plate.cropped_image, save_variants=True)
                quality_score   = quality_report.quality_score
                preprocessing   = quality_report.preprocessing_method
                multi_ocr       = _ocr_engine.read_plate_multi(best_plate.cropped_image)
                best_ocr        = OCRResult(
                    plate_number   = multi_ocr.plate_number,
                    ocr_confidence = multi_ocr.ocr_confidence,
                    raw_text       = multi_ocr.raw_text,
                    variant_name   = multi_ocr.variant_name,
                    char_count     = multi_ocr.char_count,
                    is_fragment    = multi_ocr.is_fragment,
                    is_noise       = multi_ocr.is_noise,
                )
                logger.debug("[Ingest] Frame %d track %s: OCR='%s' conf=%.3f chars=%d",
                             frame_number, track_id,
                             best_ocr.plate_number, best_ocr.ocr_confidence, best_ocr.char_count)
            except Exception as exc:
                logger.warning("[Ingest] OCR failed frame %d track %s: %s",
                               frame_number, track_id, exc)

        # ── Record observation ────────────────────────────────────────────────
        if best_ocr is not None:
            obs = PlateObservation(
                frame_number   = frame_number,
                raw_ocr_text   = best_ocr.raw_text,
                plate_text     = best_ocr.plate_number,
                ocr_confidence = best_ocr.ocr_confidence,
                plate_conf     = best_plate.confidence if best_plate else 0.0,
                quality_score  = quality_score,
                char_count     = best_ocr.char_count,
                variant_name   = best_ocr.variant_name,
                is_fragment    = best_ocr.is_fragment,
                preprocessing  = preprocessing,
            )
            evidence_map[track_id].add(obs)

        # Provisional single-frame consensus (for per-frame DB storage)
        provisional = evidence_map[track_id].consensus()
        frame_results.append((track_id, vehicle, best_plate, best_ocr, provisional))

    return frame_results


# ═══════════════════════════════════════════════════════════════════════════════
# BUILD IngestDetection FROM FINAL CONSENSUS
# ═══════════════════════════════════════════════════════════════════════════════

def _build_ingest_detection(
    track_id     : str,
    vehicle      : VehicleDetection,
    plate        : Optional[PlateDetection],
    ocr          : Optional[OCRResult],
    consensus    : ConsensuResult,
    frame_number : int,
    timestamp    : datetime,
    camera_id    : str,
    latitude     : float,
    longitude    : float,
    source_file  : str,
    db           : Optional[Session],
) -> IngestDetection:
    """Persist to DB and return IngestDetection."""

    # Use consensus for what to store and display
    plate_text       = consensus.plate_number          # VERIFIED only
    partial_text_val = consensus.partial_text
    status           = consensus.status.value
    is_low_conf      = (ocr.ocr_confidence if ocr else 0.0) < _LOW_CONF_THRESHOLD
    was_normalised   = False

    # Normalise (no fabrication — only strips separators from existing text)
    if plate_text:
        plate_text, was_normalised = normalise_plate(plate_text)
    elif partial_text_val:
        partial_text_val, _ = normalise_plate(partial_text_val)

    # ── Persist to Phase-3 VehicleEvent ───────────────────────────────────────
    event_id: Optional[int] = None
    if db is not None:
        try:
            ev = create_event(
                db           = db,
                camera_id    = camera_id,
                timestamp    = timestamp,
                plate_number = plate_text or partial_text_val,
                vehicle_type = vehicle.vehicle_class,
                vehicle_conf = vehicle.confidence,
                plate_conf   = plate.confidence   if plate else None,
                ocr_conf     = ocr.ocr_confidence if ocr   else None,
            )
            event_id = ev.id
        except Exception as exc:
            logger.warning("[Ingest] Could not store VehicleEvent: %s", exc)

    # ── Persist to Phase-4 Detection (trajectory engine) — VERIFIED only ─────
    detection_id: Optional[int] = None
    if db is not None and plate_text:
        try:
            det = create_detection(
                db,
                DetectionCreate(
                    plate_number         = plate_text,
                    camera_id            = camera_id,
                    timestamp            = timestamp,
                    detection_confidence = plate.confidence if plate else None,
                ),
            )
            detection_id = det.id
        except Exception as exc:
            logger.warning("[Ingest] Could not store Detection: %s", exc)

    return IngestDetection(
        vehicle_type         = vehicle.vehicle_class,
        vehicle_confidence   = vehicle.confidence,
        vehicle_bbox         = vehicle.bbox,
        track_id             = track_id,
        # plate_number: only VERIFIED; partial shown in partial_text field
        plate_number         = plate_text,
        partial_text         = partial_text_val,
        plate_status         = status,
        plate_raw_text       = ocr.raw_text        if ocr   else None,
        plate_confidence     = plate.confidence    if plate else None,
        ocr_confidence       = ocr.ocr_confidence  if ocr   else None,
        plate_bbox           = plate.bbox          if plate else None,
        plate_normalised     = was_normalised,
        low_confidence       = is_low_conf,
        quality_score        = consensus.quality_score,
        preprocessing_method = consensus.preprocessing_method,
        supporting_frames    = consensus.supporting_frames,
        frame_number         = frame_number,
        timestamp            = timestamp.isoformat(),
        camera_id            = camera_id,
        latitude             = latitude,
        longitude            = longitude,
        source_file          = source_file,
        event_id             = event_id,
        detection_id         = detection_id,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# IMAGE INGESTION
# ═══════════════════════════════════════════════════════════════════════════════

def ingest_image(
    image_path : Path,
    camera_id  : str,
    timestamp  : Optional[datetime] = None,
    db         : Optional[Session]  = None,
) -> ImageIngestResponse:
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    lat, lon  = get_camera_gps(camera_id)
    warnings  : List[str] = []
    cam_meta  = get_camera_meta(camera_id)
    if cam_meta is None:
        warnings.append(
            f"camera_id '{camera_id}' not found in cameras.json — GPS defaulted to (0,0)"
        )

    try:
        image = load_image(image_path)
    except Exception as exc:
        raise ValueError(f"Cannot read image '{image_path.name}': {exc}") from exc

    tracker      = _SimpleTracker()
    evidence_map : Dict[str, PlateEvidence] = {}

    frame_data = _detect_frame(image, 0, tracker, evidence_map)

    detections: List[IngestDetection] = []
    for track_id, vehicle, plate, ocr, _ in frame_data:
        final = evidence_map[track_id].consensus()
        det = _build_ingest_detection(
            track_id, vehicle, plate, ocr, final,
            0, timestamp, camera_id, lat, lon, image_path.name, db,
        )
        detections.append(det)

    # Annotated image
    annotated_url: Optional[str] = None
    try:
        from app.schemas.vehicle_event import DetectionResultWithEvent
        compat = [
            DetectionResultWithEvent(
                event_id           = d.event_id,
                vehicle_type       = d.vehicle_type,
                vehicle_confidence = d.vehicle_confidence,
                plate_number       = d.plate_number or d.partial_text,
                plate_confidence   = d.plate_confidence,
                ocr_confidence     = d.ocr_confidence,
                vehicle_bbox       = d.vehicle_bbox,
                plate_bbox         = d.plate_bbox,
                raw_ocr_text       = d.plate_raw_text,
            )
            for d in detections
        ]
        annotated  = annotate_image(image, compat)
        out_name   = f"{image_path.stem}_{uuid.uuid4().hex[:8]}_anpr{image_path.suffix}"
        out_path   = OUTPUT_DIR / out_name
        save_image(annotated, out_path)
        annotated_url = f"/static/output/{out_name}"
    except Exception as exc:
        logger.warning("[Ingest] Could not save annotated image: %s", exc)
        warnings.append("Annotated image could not be saved.")

    verified = [d for d in detections if d.plate_status == PlateStatus.VERIFIED.value]
    partial  = [d for d in detections if d.plate_status == PlateStatus.PARTIAL.value]
    low_conf = sum(1 for d in detections if d.low_confidence)

    return ImageIngestResponse(
        status                = "ok",
        source_file           = image_path.name,
        camera_id             = camera_id,
        timestamp             = timestamp.isoformat(),
        latitude              = lat,
        longitude             = lon,
        total_vehicles        = len([d for d in detections if d.vehicle_type != "unknown"]),
        total_plates          = len([d for d in detections if d.plate_number or d.partial_text]),
        verified_plates       = len(verified),
        partial_plates        = len(partial),
        low_confidence_plates = low_conf,
        detections            = detections,
        annotated_image_url   = annotated_url,
        warnings              = warnings,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# VIDEO INGESTION
# ═══════════════════════════════════════════════════════════════════════════════

def ingest_video(
    video_path    : Path,
    camera_id     : str,
    base_timestamp: Optional[datetime] = None,
    frame_skip    : int                = 5,
    db            : Optional[Session]  = None,
) -> VideoIngestResponse:
    """
    Process a traffic video.

    Frame skip default changed from 10 → 5 for better plate coverage.
    Set frame_skip=2 or 3 for more complete reads (slower).
    Set frame_skip=10+ for a quick scan.
    """
    if base_timestamp is None:
        base_timestamp = datetime.now(timezone.utc)

    frame_skip = max(1, frame_skip)
    lat, lon   = get_camera_gps(camera_id)
    warnings  : List[str] = []

    cam_meta = get_camera_meta(camera_id)
    if cam_meta is None:
        warnings.append(f"camera_id '{camera_id}' not in cameras.json — GPS defaulted")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video '{video_path.name}'.")

    fps          = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    logger.info("[Ingest] Video '%s' | frames=%d fps=%.1f skip=%d",
                video_path.name, total_frames, fps, frame_skip)

    tracker      = _SimpleTracker()
    evidence_map : Dict[str, PlateEvidence] = {}
    # Store per-frame data for DB persistence after consensus
    frame_store  : List[Tuple[str, VehicleDetection, Optional[PlateDetection],
                               Optional[OCRResult], int, datetime]] = []

    frames_processed = 0
    frame_idx        = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % frame_skip == 0:
                frame_ts = base_timestamp + timedelta(seconds=frame_idx / fps)
                frame_data = _detect_frame(frame, frame_idx, tracker, evidence_map)
                for track_id, vehicle, plate, ocr, _ in frame_data:
                    frame_store.append((track_id, vehicle, plate, ocr, frame_idx, frame_ts))
                frames_processed += 1
            frame_idx += 1
    finally:
        cap.release()

    logger.info("[Ingest] '%s' done — %d/%d frames, %d track(s)",
                video_path.name, frames_processed, total_frames, len(evidence_map))

    # ── Build final per-detection results using full-video consensus ──────────
    all_detections: List[IngestDetection] = []

    # Deduplicate: one detection per (track_id × frame_number)
    seen_key = set()
    for track_id, vehicle, plate, ocr, fn, frame_ts in frame_store:
        key = (track_id, fn)
        if key in seen_key:
            continue
        seen_key.add(key)

        final = evidence_map[track_id].consensus()
        det   = _build_ingest_detection(
            track_id, vehicle, plate, ocr, final,
            fn, frame_ts, camera_id, lat, lon, video_path.name, db,
        )
        all_detections.append(det)

    # ── Summary stats ─────────────────────────────────────────────────────────
    # Unique VERIFIED plates (not fragments)
    verified_plates = sorted({
        d.plate_number
        for d in all_detections
        if d.plate_number and d.plate_status == PlateStatus.VERIFIED.value
    })

    # Unique partial texts (honest — not counted as verified unique plates)
    partial_plates = sorted({
        d.partial_text
        for d in all_detections
        if d.partial_text and d.plate_status in (
            PlateStatus.PARTIAL.value, PlateStatus.LOW_CONFIDENCE.value
        )
    })

    low_conf_count  = sum(1 for d in all_detections if d.low_confidence)
    unreadable_count= sum(1 for d in all_detections if d.plate_status == PlateStatus.UNREADABLE.value)

    return VideoIngestResponse(
        status               = "ok",
        source_file          = video_path.name,
        camera_id            = camera_id,
        total_frames         = total_frames,
        frames_processed     = frames_processed,
        frame_skip           = frame_skip,
        total_detections     = len(all_detections),
        # unique_plates: VERIFIED ONLY — matches frontend KPI "Unique plates"
        unique_plates        = verified_plates,
        partial_plates       = partial_plates,
        verified_count       = len(verified_plates),
        partial_count        = len(partial_plates),
        low_confidence_plates= low_conf_count,
        unreadable_count     = unreadable_count,
        detections           = all_detections,
        warnings             = warnings,
        processing_note      = (
            f"Frame skip={frame_skip}. "
            f"Verified plates contain characters confirmed by real OCR evidence. "
            f"Partial results shown honestly — no fabrication."
        ),
    )
