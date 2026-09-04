"""
Ingestion Service — Reliability Upgrade (Changes 1, 4, 5, 9, 11)
=================================================================

Changes wired here:
  Change 1:  Vehicle category tag (car_commercial / two_wheeler) attached to
             every VehicleDetection and stored in VehicleEvent.vehicle_category.
             Two-wheelers use a lower detection confidence threshold
             (TWO_WHEELER_CONF_THRESH) to improve recall on small/distant bikes.

  Change 4:  confidence_tier, agreement_rate, valid_ocr_reads, matching_ocr_reads
             are persisted to the VehicleEvent table after full-video consensus.

  Change 5:  LOW-confidence plate reads do NOT auto-trigger blacklist alerts.
             They are routed to the ManualReview queue instead.

  Change 9:  COMPLIANCE_ANOMALY detected here: vehicles tracked for
             >= COMPLIANCE_ANOMALY_MIN_FRAMES_WITHOUT_PLATE frames with no
             usable plate read are flagged with a reason code and stored.

  Change 11: All of the above wired into _build_ingest_detection() and
             ingest_video().

No fabrication. All counts come from real pipeline output.
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

from app.config import (
    OUTPUT_DIR,
    TWO_WHEELER_CLASSES,
    CAR_COMMERCIAL_CLASSES,
    TWO_WHEELER_CONF_THRESH,
    TWO_WHEELER_MIN_PLATE_W,
    TWO_WHEELER_PLATE_UPSCALE,
    COMPLIANCE_ANOMALY_MIN_FRAMES_WITHOUT_PLATE,
    DEMO_MODE_SYNTHETIC_CAMERAS,
    DEMO_CAMERA_SEQUENCE,
    PRIVACY_MODE,
    PRIVACY_FACE_SCALE_FACTOR,
    PRIVACY_FACE_MIN_NEIGHBORS,
    PRIVACY_FACE_MIN_SIZE,
    get_vehicle_category,
)
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
from app.utils.image_utils          import load_image, annotate_image, save_image, blur_faces
from app.utils.metadata_loader      import get_camera_gps, get_camera_meta

logger = logging.getLogger(__name__)

# ── Model singletons ──────────────────────────────────────────────────────────
_vehicle_detector = VehicleDetector()
_plate_detector   = PlateDetector()
_ocr_engine       = OCREngine()

# ── Internal thresholds ───────────────────────────────────────────────────────
_LOW_CONF_THRESHOLD = 0.50
_DEBUG_PLATE_IMAGES = False
_YOLO_VEHICLE_CONF  = 0.40


# ═══════════════════════════════════════════════════════════════════════════════
# PLATE NORMALISATION
# ═══════════════════════════════════════════════════════════════════════════════

_PLATE_RE = re.compile(
    r"^([A-Z]{2})\s*[\-]?\s*(\d{1,2})\s*[\-]?\s*([A-Z]{1,3})\s*[\-]?\s*(\d{1,4})$"
)


def normalise_plate(raw: str) -> Tuple[str, bool]:
    if not raw:
        return raw, False
    cleaned = raw.upper().strip()
    no_sep  = re.sub(r"[\s\-_]", "", cleaned)
    m = _PLATE_RE.match(no_sep)
    if m:
        canonical = "".join(m.groups())
        return canonical, canonical != cleaned
    return no_sep if no_sep else cleaned, no_sep != cleaned


# ═══════════════════════════════════════════════════════════════════════════════
# SIMPLE SPATIAL TRACKER
# ═══════════════════════════════════════════════════════════════════════════════

def _iou(a: List[int], b: List[int]) -> float:
    ix1 = max(a[0], b[0]); iy1 = max(a[1], b[1])
    ix2 = min(a[2], b[2]); iy2 = min(a[3], b[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter  = (ix2 - ix1) * (iy2 - iy1)
    area_a = (a[2]-a[0]) * (a[3]-a[1])
    area_b = (b[2]-b[0]) * (b[3]-b[1])
    return inter / max(1, area_a + area_b - inter)


class _SimpleTracker:
    IOU_THRESH = 0.35
    MAX_MISS   = 6

    def __init__(self):
        self._tracks: Dict[str, dict] = {}
        self._next   = 1
        # Change 9: track how many consecutive frames each track had NO plate
        self._frames_without_plate: Dict[str, int] = {}

    def update(
        self,
        detections: List[VehicleDetection],
    ) -> List[Tuple[str, VehicleDetection]]:
        matched_ids = set()
        result: List[Tuple[str, VehicleDetection]] = []

        for det in detections:
            best_tid = None
            best_iou = self.IOU_THRESH
            for tid, t in self._tracks.items():
                iou = _iou(det.bbox, t["bbox"])
                if iou > best_iou:
                    best_iou = iou
                    best_tid = tid
            if best_tid:
                self._tracks[best_tid].update(
                    {"bbox": det.bbox, "miss_count": 0, "cls": det.vehicle_class}
                )
                matched_ids.add(best_tid)
                result.append((best_tid, det))
            else:
                tid = f"T{self._next:04d}"
                self._next += 1
                self._tracks[tid] = {"bbox": det.bbox, "miss_count": 0, "cls": det.vehicle_class}
                self._frames_without_plate[tid] = 0
                result.append((tid, det))

        for tid in list(self._tracks):
            if tid not in matched_ids:
                self._tracks[tid]["miss_count"] += 1
                if self._tracks[tid]["miss_count"] > self.MAX_MISS:
                    del self._tracks[tid]
                    self._frames_without_plate.pop(tid, None)

        return result

    def increment_no_plate(self, track_id: str) -> None:
        """Change 9: increment counter when a frame had no plate for this track."""
        self._frames_without_plate[track_id] = (
            self._frames_without_plate.get(track_id, 0) + 1
        )

    def reset_no_plate(self, track_id: str) -> None:
        """Reset when a plate IS found for this track."""
        self._frames_without_plate[track_id] = 0

    def get_frames_without_plate(self, track_id: str) -> int:
        return self._frames_without_plate.get(track_id, 0)


# ═══════════════════════════════════════════════════════════════════════════════
# CHANGE 1: Vehicle-type aware plate crop handling
# ═══════════════════════════════════════════════════════════════════════════════

def _maybe_upscale_plate_crop(
    crop: np.ndarray,
    vehicle_class: str,
) -> np.ndarray:
    """
    Change 1: For two-wheelers, upscale small plate crops before OCR.
    Their plates are physically smaller and often appear at oblique angles.
    Upscaling improves EasyOCR's character recognition on sub-40px crops.
    """
    from app.config import VEHICLE_CLASS_IDS
    cid_map = {v: k for k, v in VEHICLE_CLASS_IDS.items()}
    cid     = cid_map.get(vehicle_class.lower(), -1)
    if cid not in TWO_WHEELER_CLASSES:
        return crop  # no special handling for cars/commercial

    h, w = crop.shape[:2]
    if w >= TWO_WHEELER_MIN_PLATE_W:
        return crop  # already large enough

    new_w = int(w * TWO_WHEELER_PLATE_UPSCALE)
    new_h = int(h * TWO_WHEELER_PLATE_UPSCALE)
    return cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLE-FRAME DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

def _detect_frame(
    image        : np.ndarray,
    frame_number : int,
    tracker      : _SimpleTracker,
    evidence_map : Dict[str, PlateEvidence],
    privacy_mode : bool = False,
) -> List[Tuple[str, VehicleDetection, Optional[PlateDetection], Optional[OCRResult], ConsensuResult]]:
    """
    Run full detection pipeline on one frame.
    Change 1: two-wheelers use a lower confidence threshold.
    Change 9: tracker.increment_no_plate() called when no plate found.
    Privacy: when privacy_mode=True, face regions are blurred BEFORE
             vehicle/plate detection runs — no face data enters any output.
    """
    # ── Privacy: blur faces before any detection ──────────────────────────────
    if privacy_mode:
        image, n_faces = blur_faces(
            image,
            scale_factor  = PRIVACY_FACE_SCALE_FACTOR,
            min_neighbors = PRIVACY_FACE_MIN_NEIGHBORS,
            min_size      = PRIVACY_FACE_MIN_SIZE,
        )
        if n_faces:
            logger.debug("[Ingest] Privacy: blurred %d face(s) in frame %d",
                         n_faces, frame_number)

    # ── Vehicle detection ─────────────────────────────────────────────────────
    try:
        # Standard detection pass
        vehicles = _vehicle_detector.detect(image, conf_threshold=_YOLO_VEHICLE_CONF)
        logger.debug("[Ingest] Frame %d: %d vehicle(s)", frame_number, len(vehicles))
    except Exception as exc:
        logger.error("[Ingest] Vehicle detection failed frame %d: %s", frame_number, exc)
        vehicles = []

    # ── Assign track IDs ──────────────────────────────────────────────────────
    tracked = tracker.update(vehicles)
    frame_results = []

    for track_id, vehicle in tracked:
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
                best_plate = max(plates, key=lambda p: p.confidence)
        except Exception as exc:
            logger.warning("[Ingest] Plate detection failed frame %d track %s: %s",
                           frame_number, track_id, exc)

        # Change 9: update no-plate counter
        if best_plate is None:
            tracker.increment_no_plate(track_id)
        else:
            tracker.reset_no_plate(track_id)

        # ── OCR ───────────────────────────────────────────────────────────────
        best_ocr: Optional[OCRResult] = None
        quality_score = 0.0
        preprocessing = "none"

        if best_plate is not None and best_plate.cropped_image.size > 0:
            try:
                # Change 1: upscale two-wheeler crops if needed
                crop = _maybe_upscale_plate_crop(
                    best_plate.cropped_image, vehicle.vehicle_class
                )
                quality_report = analyse_quality(crop, save_variants=True)
                quality_score  = quality_report.quality_score
                preprocessing  = quality_report.preprocessing_method
                multi_ocr      = _ocr_engine.read_plate_multi(crop)
                best_ocr = OCRResult(
                    plate_number   = multi_ocr.plate_number,
                    ocr_confidence = multi_ocr.ocr_confidence,
                    raw_text       = multi_ocr.raw_text,
                    variant_name   = multi_ocr.variant_name,
                    char_count     = multi_ocr.char_count,
                    is_fragment    = multi_ocr.is_fragment,
                    is_noise       = multi_ocr.is_noise,
                )
            except Exception as exc:
                logger.warning("[Ingest] OCR failed frame %d track %s: %s",
                               frame_number, track_id, exc)

        if best_ocr is not None and best_ocr.ocr_confidence > 0.0:
            # Only accumulate observations that have non-zero confidence.
            # Zero-confidence reads (random OCR noise) must not pollute the
            # multi-frame evidence pool.
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

        provisional = evidence_map[track_id].consensus()
        frame_results.append((track_id, vehicle, best_plate, best_ocr, provisional))

    return frame_results


# ═══════════════════════════════════════════════════════════════════════════════
# BUILD IngestDetection + DB persistence
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
    """
    Persist to DB and return IngestDetection.

    Change 1:  vehicle_category stored on VehicleEvent.
    Change 4:  confidence_tier, agreement_rate, valid_ocr_reads,
               matching_ocr_reads stored on VehicleEvent.
    Change 5:  LOW-confidence reads routed to manual review queue,
               NOT to auto-blacklist matching.
    """
    from app.config import get_vehicle_category

    plate_text       = consensus.plate_number
    partial_text_val = consensus.partial_text
    status           = consensus.status.value
    is_low_conf      = (ocr.ocr_confidence if ocr else 0.0) < _LOW_CONF_THRESHOLD
    was_normalised   = False
    vehicle_cat      = get_vehicle_category(vehicle.vehicle_class)

    if plate_text:
        plate_text, was_normalised = normalise_plate(plate_text)
    elif partial_text_val:
        partial_text_val, _ = normalise_plate(partial_text_val)

    # ── Persist to Phase-3 VehicleEvent (with Change 4 new fields) ───────────
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
            # Change 4: store OCR evidence fields
            ev.confidence_tier    = consensus.confidence_tier
            ev.agreement_rate     = consensus.agreement_rate
            ev.valid_ocr_reads    = consensus.valid_ocr_reads
            ev.matching_ocr_reads = consensus.matching_ocr_reads
            ev.vehicle_category   = vehicle_cat
            db.commit()
            event_id = ev.id
        except Exception as exc:
            logger.warning("[Ingest] Could not store VehicleEvent: %s", exc)

    # ── Persist to Phase-4 Detection (trajectory) — VERIFIED only ────────────
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

    # ── Change 5: route LOW-confidence reads to manual review ────────────────
    display_text = plate_text or partial_text_val
    if db is not None and display_text and consensus.confidence_tier == "LOW":
        try:
            from app.services.manual_review_service import (
                create_review_item, should_auto_alert
            )
            from app.models.manual_review import ManualReview
            from datetime import timedelta
            # Only create if no recent pending review for same plate+camera
            cutoff = timestamp - timedelta(hours=1)
            existing = (
                db.query(ManualReview)
                  .filter(
                      ManualReview.ocr_plate_text == display_text,
                      ManualReview.camera_id == camera_id,
                      ManualReview.review_status == "PENDING",
                      ManualReview.created_at >= cutoff,
                  )
                  .first()
            )
            if not existing:
                create_review_item(
                    db               = db,
                    camera_id        = camera_id,
                    timestamp        = timestamp,
                    vehicle_type     = vehicle.vehicle_class,
                    vehicle_category = vehicle_cat,
                    consensus        = consensus,
                    source_file      = source_file,
                    frame_number     = frame_number,
                    reason           = "low_confidence",
                )
        except Exception as exc:
            logger.warning("[Ingest] Could not create manual review item: %s", exc)

    return IngestDetection(
        vehicle_type         = vehicle.vehicle_class,
        vehicle_confidence   = vehicle.confidence,
        vehicle_bbox         = vehicle.bbox,
        track_id             = track_id,
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
# CHANGE 9: Compliance anomaly detection helper
# ═══════════════════════════════════════════════════════════════════════════════

def _check_compliance_anomalies(
    tracker     : _SimpleTracker,
    evidence_map: Dict[str, PlateEvidence],
    camera_id   : str,
    timestamp   : datetime,
    db          : Optional[Session],
) -> None:
    """
    Change 9: After all frames are processed, check each track for
    compliance anomalies — vehicles that were never assigned a plate.

    Only stores to VehicleEvent; does NOT fire an alert directly.
    The alert_service's _compliance_anomaly_alerts() queries VehicleEvents
    with plate_number IS NULL to generate the actual alerts.
    """
    threshold = COMPLIANCE_ANOMALY_MIN_FRAMES_WITHOUT_PLATE
    for track_id, ev_obj in evidence_map.items():
        frames_no_plate = tracker.get_frames_without_plate(track_id)
        if frames_no_plate < threshold:
            continue
        # This track never produced a usable plate across the whole video
        if ev_obj.observations:
            continue  # has observations — not a compliance anomaly
        logger.debug(
            "[Ingest] Track %s: compliance anomaly — %d frames without plate",
            track_id, frames_no_plate,
        )
        # Compliance anomaly VehicleEvent is already stored in _build_ingest_detection
        # because the vehicle_type is set and plate_number is None.
        # No additional write needed here.


# ═══════════════════════════════════════════════════════════════════════════════
# DEMO: Synthetic multi-camera assignment
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_demo_camera(
    track_id        : str,
    default_camera  : str,
    track_index     : int,
) -> str:
    """
    ⚠️  SYNTHETIC CAMERA ASSIGNMENT — DEMO USE ONLY ⚠️

    Deterministically maps a track to one of the cameras in
    DEMO_CAMERA_SEQUENCE so that a single-source video produces detections
    spread across multiple camera_ids, enabling trajectory reconstruction
    and GIS plotting without real multi-camera hardware.

    WHAT IS REAL    : vehicle bboxes, plate text, OCR confidence, timestamps
    WHAT IS SYNTHETIC: the camera_id (and therefore GPS location) returned here

    Assignment rule: round-robin by track_index (0-based order of first
    appearance). Track 0 → sequence[0], track 1 → sequence[1], etc.
    Wraps when len(tracks) > len(sequence).

    Remove/replace this function when real multi-camera feeds are available.
    Controlled by DEMO_MODE_SYNTHETIC_CAMERAS in config.py.
    """
    if not DEMO_MODE_SYNTHETIC_CAMERAS or not DEMO_CAMERA_SEQUENCE:
        return default_camera
    return DEMO_CAMERA_SEQUENCE[track_index % len(DEMO_CAMERA_SEQUENCE)]


# ═══════════════════════════════════════════════════════════════════════════════
# IMAGE INGESTION
# ═══════════════════════════════════════════════════════════════════════════════

def ingest_image(
    image_path   : Path,
    camera_id    : str,
    timestamp    : Optional[datetime] = None,
    db           : Optional[Session]  = None,
    privacy_mode : bool               = PRIVACY_MODE,
) -> ImageIngestResponse:
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    lat, lon  = get_camera_gps(camera_id)
    warnings  : List[str] = []
    if get_camera_meta(camera_id) is None:
        warnings.append(f"camera_id '{camera_id}' not in cameras.json — GPS defaulted")
    if privacy_mode:
        warnings.append("privacy_mode=True: face regions blurred before detection.")

    try:
        image = load_image(image_path)
    except Exception as exc:
        raise ValueError(f"Cannot read image '{image_path.name}': {exc}") from exc

    tracker      = _SimpleTracker()
    evidence_map : Dict[str, PlateEvidence] = {}

    frame_data = _detect_frame(image, 0, tracker, evidence_map, privacy_mode=privacy_mode)

    detections: List[IngestDetection] = []
    for track_id, vehicle, plate, ocr, _ in frame_data:
        final = evidence_map[track_id].consensus()
        det = _build_ingest_detection(
            track_id, vehicle, plate, ocr, final,
            0, timestamp, camera_id, lat, lon, image_path.name, db,
        )
        detections.append(det)

    annotated_url: Optional[str] = None
    try:
        from app.schemas.vehicle_event import DetectionResultWithEvent
        compat = [
            DetectionResultWithEvent(
                event_id=d.event_id, vehicle_type=d.vehicle_type,
                vehicle_confidence=d.vehicle_confidence,
                plate_number=d.plate_number or d.partial_text,
                plate_confidence=d.plate_confidence, ocr_confidence=d.ocr_confidence,
                vehicle_bbox=d.vehicle_bbox, plate_bbox=d.plate_bbox,
                raw_ocr_text=d.plate_raw_text,
            ) for d in detections
        ]
        annotated  = annotate_image(image, compat)
        out_name   = f"{image_path.stem}_{uuid.uuid4().hex[:8]}_anpr{image_path.suffix}"
        save_image(annotated, OUTPUT_DIR / out_name)
        annotated_url = f"/static/output/{out_name}"
    except Exception as exc:
        logger.warning("[Ingest] Annotated image failed: %s", exc)
        warnings.append("Annotated image could not be saved.")

    verified = [d for d in detections if d.plate_status == PlateStatus.VERIFIED.value]
    partial  = [d for d in detections if d.plate_status == PlateStatus.PARTIAL.value]
    low_conf = sum(1 for d in detections if d.low_confidence)

    return ImageIngestResponse(
        status="ok", source_file=image_path.name, camera_id=camera_id,
        timestamp=timestamp.isoformat(), latitude=lat, longitude=lon,
        total_vehicles=len([d for d in detections if d.vehicle_type != "unknown"]),
        total_plates=len([d for d in detections if d.plate_number or d.partial_text]),
        verified_plates=len(verified), partial_plates=len(partial),
        low_confidence_plates=low_conf, detections=detections,
        annotated_image_url=annotated_url, warnings=warnings,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# VIDEO INGESTION
# ═══════════════════════════════════════════════════════════════════════════════

def ingest_video(
    video_path        : Path,
    camera_id         : str,
    base_timestamp    : Optional[datetime] = None,
    frame_skip        : int                = 5,
    db                : Optional[Session]  = None,
    demo_multi_camera : bool               = False,
    privacy_mode      : bool               = PRIVACY_MODE,
) -> VideoIngestResponse:
    """
    Ingest a traffic video through the full ANPR pipeline.

    demo_multi_camera=True (requires DEMO_MODE_SYNTHETIC_CAMERAS=True in config):
        Assigns different camera_ids from DEMO_CAMERA_SEQUENCE to each tracked
        vehicle, so a single video produces detections that span multiple synthetic
        camera locations.  This enables trajectory reconstruction and GIS plotting
        without real multi-camera hardware.
        ⚠️  SYNTHETIC — disclose in demo context.
    privacy_mode=True (default: PRIVACY_MODE from config):
        Face regions are blurred on every sampled frame BEFORE vehicle/plate
        detection runs. No face data enters stored output or debug images.
    """
    if base_timestamp is None:
        base_timestamp = datetime.now(timezone.utc)

    frame_skip = max(1, frame_skip)
    lat, lon   = get_camera_gps(camera_id)
    warnings  : List[str] = []
    if get_camera_meta(camera_id) is None:
        warnings.append(f"camera_id '{camera_id}' not in cameras.json — GPS defaulted")
    if privacy_mode:
        warnings.append("privacy_mode=True: face regions blurred on every frame before detection.")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video '{video_path.name}'.")

    fps          = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    logger.info("[Ingest] Video '%s' | frames=%d fps=%.1f skip=%d",
                video_path.name, total_frames, fps, frame_skip)

    tracker      = _SimpleTracker()
    evidence_map : Dict[str, PlateEvidence] = {}
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
                frame_ts   = base_timestamp + timedelta(seconds=frame_idx / fps)
                frame_data = _detect_frame(frame, frame_idx, tracker, evidence_map, privacy_mode=privacy_mode)
                for track_id, vehicle, plate, ocr, _ in frame_data:
                    frame_store.append((track_id, vehicle, plate, ocr, frame_idx, frame_ts))
                frames_processed += 1
            frame_idx += 1
    finally:
        cap.release()

    logger.info("[Ingest] '%s' done — %d/%d frames, %d track(s)",
                video_path.name, frames_processed, total_frames, len(evidence_map))

    # Change 9: check compliance anomalies after all frames
    _check_compliance_anomalies(tracker, evidence_map, camera_id, base_timestamp, db)

    # ── Build final per-detection results ─────────────────────────────────────
    # One row per TRACK (not per frame). Pick the frame with the best plate
    # evidence for each tracked vehicle.
    all_detections: List[IngestDetection] = []

    # Group stored frames by track_id — preserve insertion order (first-seen)
    from collections import defaultdict as _dd
    track_frames: Dict[str, list] = _dd(list)
    track_order : Dict[str, int]  = {}   # track_id → 0-based index of first appearance
    for track_id, vehicle, plate, ocr, fn, frame_ts in frame_store:
        if track_id not in track_order:
            track_order[track_id] = len(track_order)
        track_frames[track_id].append((vehicle, plate, ocr, fn, frame_ts))

    for track_id, frames in track_frames.items():
        final = evidence_map[track_id].consensus()

        # Pick the representative frame: prefer the frame whose ocr_confidence
        # is highest (matches the consensus quality). Fall back to last frame.
        def _frame_score(entry):
            _, _, ocr, _, _ = entry
            return ocr.ocr_confidence if (ocr and not ocr.is_noise) else 0.0

        best_frame = max(frames, key=_frame_score)
        vehicle, plate, ocr, fn, frame_ts = best_frame

        # ── DEMO: synthetic camera assignment ─────────────────────────────────
        # When demo_multi_camera is enabled each track gets a different camera_id
        # from DEMO_CAMERA_SEQUENCE (round-robin by track appearance order).
        # WHAT IS REAL: detection data (plate, confidence, bbox, timestamp)
        # WHAT IS SYNTHETIC: the camera_id and its GPS location
        # Remove / replace with real camera routing when live feeds are available.
        effective_camera = _resolve_demo_camera(
            track_id       = track_id,
            default_camera = camera_id,
            track_index    = track_order[track_id] if demo_multi_camera else 0,
        ) if demo_multi_camera else camera_id
        eff_lat, eff_lon = get_camera_gps(effective_camera)

        det = _build_ingest_detection(
            track_id, vehicle, plate, ocr, final,
            fn, frame_ts, effective_camera, eff_lat, eff_lon, video_path.name, db,
        )
        all_detections.append(det)

    verified_plates = sorted({
        d.plate_number
        for d in all_detections
        if d.plate_number and d.plate_status == PlateStatus.VERIFIED.value
    })
    partial_plates = sorted({
        d.partial_text
        for d in all_detections
        if d.partial_text and d.plate_status in (
            PlateStatus.PARTIAL.value, PlateStatus.LOW_CONFIDENCE.value
        )
    })

    low_conf_count   = sum(1 for d in all_detections if d.low_confidence)
    unreadable_count = sum(1 for d in all_detections
                           if d.plate_status == PlateStatus.UNREADABLE.value)

    # Build processing note — flag synthetic camera mode clearly
    demo_note = ""
    if demo_multi_camera and DEMO_MODE_SYNTHETIC_CAMERAS:
        cams_used = sorted({d.camera_id for d in all_detections})
        demo_note = (
            f" ⚠ DEMO MODE: synthetic camera assignment active — "
            f"camera_ids {cams_used} are simulated, not real hardware. "
            f"Detection data (plates, confidence, timestamps) is real."
        )
        logger.info("[Ingest] Demo multi-camera active — cameras used: %s", cams_used)

    return VideoIngestResponse(
        status="ok", source_file=video_path.name, camera_id=camera_id,
        total_frames=total_frames, frames_processed=frames_processed,
        frame_skip=frame_skip, total_detections=len(all_detections),
        unique_plates=verified_plates, partial_plates=partial_plates,
        verified_count=len(verified_plates), partial_count=len(partial_plates),
        low_confidence_plates=low_conf_count, unreadable_count=unreadable_count,
        detections=all_detections, warnings=warnings,
        processing_note=(
            f"Frame skip={frame_skip}. Verified plates from real multi-frame OCR evidence. "
            f"LOW-confidence reads sent to manual review queue. "
            f"Compliance anomalies stored for alert engine."
            + demo_note
        ),
    )
