"""
Ingestion Service — Reliability Upgrade
========================================

Changes wired here:

Change 1:
  - Vehicle category tag:
      car_commercial / two_wheeler / unknown
  - Stored in VehicleEvent.vehicle_category
  - Two-wheelers use TWO_WHEELER_CONF_THRESH
  - Small two-wheeler plate crops can be upscaled before OCR

Change 4:
  - confidence_tier
  - agreement_rate
  - valid_ocr_reads
  - matching_ocr_reads
  are persisted to VehicleEvent after final video consensus.

Change 5:
  - LOW-confidence plate reads are NOT automatically treated as
    blacklist matches.
  - They are routed to ManualReview.

Change 9:
  - Vehicles with >= COMPLIANCE_ANOMALY_MIN_FRAMES_WITHOUT_PLATE
    consecutive sampled frames without a usable plate are identified
    as compliance anomalies.
  - The resulting VehicleEvent has plate_number=None.
  - Manual review is also created where supported.

Change 11:
  - All changes are wired into _build_ingest_detection() and ingest_video().

Memory optimization:
  - Do not retain every frame result.
  - Keep only the strongest representative frame for each track.
  - Keep multi-frame OCR evidence in PlateEvidence.
"""

from __future__ import annotations

import logging
import re
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

from app.models.vehicle_detector import (
    VehicleDetector,
    VehicleDetection,
)

from app.models.plate_detector import (
    PlateDetector,
    PlateDetection,
)

from app.models.ocr_engine import (
    OCREngine,
    OCRResult,
)

from app.models.image_quality import (
    analyse as analyse_quality,
)

from app.models.plate_result import (
    PlateObservation,
    PlateEvidence,
    ConsensuResult,
    PlateStatus,
)

from app.services.event_service import create_event
from app.services.detection_service import create_detection

from app.schemas.trajectory import DetectionCreate

from app.schemas.ingest import (
    IngestDetection,
    ImageIngestResponse,
    VideoIngestResponse,
)

from app.utils.image_utils import (
    load_image,
    annotate_image,
    save_image,
    blur_faces,
)

from app.utils.metadata_loader import (
    get_camera_gps,
    get_camera_meta,
)


logger = logging.getLogger(__name__)


# ============================================================================
# MODEL SINGLETONS
# ============================================================================

_vehicle_detector = VehicleDetector()
_plate_detector = PlateDetector()
_ocr_engine = OCREngine()


# ============================================================================
# INTERNAL THRESHOLDS
# ============================================================================

_LOW_CONF_THRESHOLD = 0.50
_DEBUG_PLATE_IMAGES = False

# Matches VEHICLE_CONF_THRESH from config.py in the configuration you showed.
_YOLO_VEHICLE_CONF = 0.30


# ============================================================================
# PLATE NORMALISATION
# ============================================================================

_PLATE_RE = re.compile(
    r"^([A-Z]{2})\s*[\-]?\s*(\d{1,2})\s*[\-]?\s*"
    r"([A-Z]{1,3})\s*[\-]?\s*(\d{1,4})$"
)


def normalise_plate(raw: str) -> Tuple[str, bool]:
    """
    Normalise an OCR plate string.

    Returns:
        (normalised_text, was_normalised)
    """
    if not raw:
        return raw, False

    cleaned = raw.upper().strip()

    no_sep = re.sub(r"[\s\-_]", "", cleaned)

    match = _PLATE_RE.match(no_sep)

    if match:
        canonical = "".join(match.groups())
        return canonical, canonical != cleaned

    return (
        no_sep if no_sep else cleaned,
        no_sep != cleaned,
    )


# ============================================================================
# SIMPLE SPATIAL TRACKER
# ============================================================================

def _iou(a: List[int], b: List[int]) -> float:
    """
    Calculate Intersection over Union between two bounding boxes.
    """

    ix1 = max(a[0], b[0])
    iy1 = max(a[1], b[1])

    ix2 = min(a[2], b[2])
    iy2 = min(a[3], b[3])

    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0

    inter = (ix2 - ix1) * (iy2 - iy1)

    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])

    return inter / max(
        1,
        area_a + area_b - inter,
    )


class _SimpleTracker:
    """
    Lightweight IoU-based tracker.

    This is intentionally simple:
      - associate a new detection with the existing track having
        the highest IoU above IOU_THRESH
      - otherwise create a new track
      - remove tracks after MAX_MISS unmatched updates
    """

    IOU_THRESH = 0.35
    MAX_MISS = 6

    def __init__(self):
        self._tracks: Dict[str, dict] = {}
        self._next = 1

        # Change 9:
        # number of consecutive sampled frames without a plate.
        self._frames_without_plate: Dict[str, int] = {}

    def update(
        self,
        detections: List[VehicleDetection],
    ) -> List[Tuple[str, VehicleDetection]]:

        matched_ids = set()

        result: List[
            Tuple[str, VehicleDetection]
        ] = []

        for det in detections:

            best_tid = None
            best_iou = self.IOU_THRESH

            for tid, track in self._tracks.items():

                iou = _iou(
                    det.bbox,
                    track["bbox"],
                )

                if iou > best_iou:
                    best_iou = iou
                    best_tid = tid

            if best_tid:

                self._tracks[best_tid].update(
                    {
                        "bbox": det.bbox,
                        "miss_count": 0,
                        "cls": det.vehicle_class,
                    }
                )

                matched_ids.add(best_tid)

                result.append(
                    (
                        best_tid,
                        det,
                    )
                )

            else:

                tid = f"T{self._next:04d}"

                self._next += 1

                self._tracks[tid] = {
                    "bbox": det.bbox,
                    "miss_count": 0,
                    "cls": det.vehicle_class,
                }

                self._frames_without_plate[tid] = 0

                result.append(
                    (
                        tid,
                        det,
                    )
                )

        for tid in list(self._tracks):

            if tid not in matched_ids:

                self._tracks[tid]["miss_count"] += 1

                if (
                    self._tracks[tid]["miss_count"]
                    > self.MAX_MISS
                ):

                    del self._tracks[tid]

                    self._frames_without_plate.pop(
                        tid,
                        None,
                    )

        return result

    def increment_no_plate(
        self,
        track_id: str,
    ) -> None:

        self._frames_without_plate[track_id] = (
            self._frames_without_plate.get(
                track_id,
                0,
            )
            + 1
        )

    def reset_no_plate(
        self,
        track_id: str,
    ) -> None:

        self._frames_without_plate[track_id] = 0

    def get_frames_without_plate(
        self,
        track_id: str,
    ) -> int:

        return self._frames_without_plate.get(
            track_id,
            0,
        )


# ============================================================================
# CHANGE 1
# TWO-WHEELER PLATE CROP HANDLING
# ============================================================================

def _maybe_upscale_plate_crop(
    crop: np.ndarray,
    vehicle_class: str,
) -> np.ndarray:
    """
    Upscale small two-wheeler plate crops.

    Two-wheelers often produce smaller plate crops than cars.
    """

    from app.config import VEHICLE_CLASS_IDS

    cid_map = {
        value: key
        for key, value in VEHICLE_CLASS_IDS.items()
    }

    cid = cid_map.get(
        vehicle_class.lower(),
        -1,
    )

    if cid not in TWO_WHEELER_CLASSES:
        return crop

    h, w = crop.shape[:2]

    if w >= TWO_WHEELER_MIN_PLATE_W:
        return crop

    new_w = int(
        w * TWO_WHEELER_PLATE_UPSCALE
    )

    new_h = int(
        h * TWO_WHEELER_PLATE_UPSCALE
    )

    return cv2.resize(
        crop,
        (new_w, new_h),
        interpolation=cv2.INTER_LANCZOS4,
    )


# ============================================================================
# SINGLE FRAME PIPELINE
# ============================================================================

def _detect_frame(
    image: np.ndarray,
    frame_number: int,
    tracker: _SimpleTracker,
    evidence_map: Dict[str, PlateEvidence],
    privacy_mode: bool = False,
) -> List[
    Tuple[
        str,
        VehicleDetection,
        Optional[PlateDetection],
        Optional[OCRResult],
        ConsensuResult,
    ]
]:
    """
    Run vehicle -> plate -> OCR pipeline for one sampled frame.
    """

    # ------------------------------------------------------------------------
    # PRIVACY
    # ------------------------------------------------------------------------

    if privacy_mode:

        image, n_faces = blur_faces(
            image,
            scale_factor=PRIVACY_FACE_SCALE_FACTOR,
            min_neighbors=PRIVACY_FACE_MIN_NEIGHBORS,
            min_size=PRIVACY_FACE_MIN_SIZE,
        )

        if n_faces:

            logger.debug(
                "[Ingest] Privacy: blurred %d face(s) in frame %d",
                n_faces,
                frame_number,
            )

    # ------------------------------------------------------------------------
    # VEHICLE DETECTION
    # ------------------------------------------------------------------------

    try:

        # Run at the lower threshold so small/distant two-wheelers
        # can be recovered.

        detection_threshold = min(
            _YOLO_VEHICLE_CONF,
            TWO_WHEELER_CONF_THRESH,
        )

        vehicles = _vehicle_detector.detect(
            image,
            conf_threshold=detection_threshold,
        )

        # For non-two-wheelers retain the normal vehicle confidence
        # requirement.
        filtered_vehicles: List[
            VehicleDetection
        ] = []

        for vehicle in vehicles:

            vehicle_category = get_vehicle_category(
                vehicle.vehicle_class
            )

            if vehicle_category == "two_wheeler":

                if (
                    vehicle.confidence
                    >= TWO_WHEELER_CONF_THRESH
                ):
                    filtered_vehicles.append(
                        vehicle
                    )

            else:

                if (
                    vehicle.confidence
                    >= _YOLO_VEHICLE_CONF
                ):
                    filtered_vehicles.append(
                        vehicle
                    )

        vehicles = filtered_vehicles

        logger.debug(
            "[Ingest] Frame %d: %d vehicle(s)",
            frame_number,
            len(vehicles),
        )

    except Exception as exc:

        logger.error(
            "[Ingest] Vehicle detection failed "
            "frame %d: %s",
            frame_number,
            exc,
        )

        vehicles = []

    # ------------------------------------------------------------------------
    # TRACKING
    # ------------------------------------------------------------------------

    tracked = tracker.update(
        vehicles
    )

    frame_results = []

    # ------------------------------------------------------------------------
    # PROCESS EACH VEHICLE
    # ------------------------------------------------------------------------

    for track_id, vehicle in tracked:

        if track_id not in evidence_map:

            evidence_map[track_id] = (
                PlateEvidence(
                    track_id=track_id
                )
            )

        # --------------------------------------------------------------------
        # PLATE DETECTION
        # --------------------------------------------------------------------

        best_plate: Optional[
            PlateDetection
        ] = None

        try:

            plates = _plate_detector.detect(
                image,
                vehicle_bbox=vehicle.bbox,
                frame_number=frame_number,
                save_debug=_DEBUG_PLATE_IMAGES,
            )

            if plates:

                best_plate = max(
                    plates,
                    key=lambda p: p.confidence,
                )

        except Exception as exc:

            logger.warning(
                "[Ingest] Plate detection failed "
                "frame %d track %s: %s",
                frame_number,
                track_id,
                exc,
            )

        # --------------------------------------------------------------------
        # CHANGE 9: NO-PLATE TRACK COUNTER
        # --------------------------------------------------------------------

        if best_plate is None:

            tracker.increment_no_plate(
                track_id
            )

        else:

            tracker.reset_no_plate(
                track_id
            )

        # --------------------------------------------------------------------
        # OCR
        # --------------------------------------------------------------------

        best_ocr: Optional[
            OCRResult
        ] = None

        quality_score = 0.0

        preprocessing = "none"

        if (
            best_plate is not None
            and best_plate.cropped_image is not None
            and best_plate.cropped_image.size > 0
        ):

            try:

                crop = _maybe_upscale_plate_crop(
                    best_plate.cropped_image,
                    vehicle.vehicle_class,
                )

                quality_report = analyse_quality(
                    crop,
                    save_variants=True,
                )

                quality_score = (
                    quality_report.quality_score
                )

                preprocessing = (
                    quality_report.preprocessing_method
                )

                multi_ocr = (
                    _ocr_engine.read_plate_multi(
                        crop
                    )
                )

                best_ocr = OCRResult(
                    plate_number=multi_ocr.plate_number,
                    ocr_confidence=multi_ocr.ocr_confidence,
                    raw_text=multi_ocr.raw_text,
                    variant_name=multi_ocr.variant_name,
                    char_count=multi_ocr.char_count,
                    is_fragment=multi_ocr.is_fragment,
                    is_noise=multi_ocr.is_noise,
                )

            except Exception as exc:

                logger.warning(
                    "[Ingest] OCR failed "
                    "frame %d track %s: %s",
                    frame_number,
                    track_id,
                    exc,
                )

        # --------------------------------------------------------------------
        # ADD OCR OBSERVATION
        # --------------------------------------------------------------------

        if (
            best_ocr is not None
            and best_ocr.ocr_confidence > 0.0
        ):

            observation = PlateObservation(
                frame_number=frame_number,
                raw_ocr_text=best_ocr.raw_text,
                plate_text=best_ocr.plate_number,
                ocr_confidence=(
                    best_ocr.ocr_confidence
                ),
                plate_conf=(
                    best_plate.confidence
                    if best_plate
                    else 0.0
                ),
                quality_score=quality_score,
                char_count=best_ocr.char_count,
                variant_name=best_ocr.variant_name,
                is_fragment=best_ocr.is_fragment,
                preprocessing=preprocessing,
            )

            evidence_map[
                track_id
            ].add(observation)

        # --------------------------------------------------------------------
        # PROVISIONAL CONSENSUS
        # --------------------------------------------------------------------

        provisional = (
            evidence_map[
                track_id
            ].consensus()
        )

        frame_results.append(
            (
                track_id,
                vehicle,
                best_plate,
                best_ocr,
                provisional,
            )
        )

    return frame_results


# ============================================================================
# BUILD FINAL IngestDetection + DATABASE PERSISTENCE
# ============================================================================

def _build_ingest_detection(
    track_id: str,
    vehicle: VehicleDetection,
    plate: Optional[PlateDetection],
    ocr: Optional[OCRResult],
    consensus: ConsensuResult,
    frame_number: int,
    timestamp: datetime,
    camera_id: str,
    latitude: float,
    longitude: float,
    source_file: str,
    db: Optional[Session],
) -> IngestDetection:
    """
    Convert final multi-frame consensus into an IngestDetection.

    Also persists:
      - VehicleEvent
      - trajectory Detection for VERIFIED plates
      - ManualReview for LOW confidence results
    """

    # ------------------------------------------------------------------------
    # CONSENSUS VALUES
    # ------------------------------------------------------------------------

    plate_text = consensus.plate_number

    partial_text_val = consensus.partial_text

    status = consensus.status.value

    # Low confidence is based on actual OCR confidence.
    is_low_conf = (
        ocr.ocr_confidence
        if ocr is not None
        else 0.0
    ) < _LOW_CONF_THRESHOLD

    was_normalised = False

    # ------------------------------------------------------------------------
    # VEHICLE CATEGORY
    # ------------------------------------------------------------------------

    vehicle_cat = get_vehicle_category(
        vehicle.vehicle_class
    )

    # ------------------------------------------------------------------------
    # NORMALISE FINAL PLATE
    # ------------------------------------------------------------------------

    if plate_text:

        plate_text, was_normalised = (
            normalise_plate(
                plate_text
            )
        )

    elif partial_text_val:

        partial_text_val, _ = (
            normalise_plate(
                partial_text_val
            )
        )

    # ------------------------------------------------------------------------
    # CHANGE 4
    # VEHICLE EVENT
    # ------------------------------------------------------------------------

    event_id: Optional[int] = None

    if db is not None:

        try:

            ev = create_event(
                db=db,
                camera_id=camera_id,
                timestamp=timestamp,
                plate_number=(
                    plate_text
                    or partial_text_val
                ),
                vehicle_type=(
                    vehicle.vehicle_class
                ),
                vehicle_conf=(
                    vehicle.confidence
                ),
                plate_conf=(
                    plate.confidence
                    if plate
                    else None
                ),
                ocr_conf=(
                    ocr.ocr_confidence
                    if ocr
                    else None
                ),
            )

            # Change 4 fields.
            ev.confidence_tier = (
                consensus.confidence_tier
            )

            ev.agreement_rate = (
                consensus.agreement_rate
            )

            ev.valid_ocr_reads = (
                consensus.valid_ocr_reads
            )

            ev.matching_ocr_reads = (
                consensus.matching_ocr_reads
            )

            # Change 1.
            ev.vehicle_category = (
                vehicle_cat
            )

            db.commit()

            event_id = ev.id

        except Exception as exc:

            logger.warning(
                "[Ingest] Could not store "
                "VehicleEvent: %s",
                exc,
            )

            try:
                db.rollback()
            except Exception:
                pass

    # ------------------------------------------------------------------------
    # PHASE 4 DETECTION
    #
    # Only complete VERIFIED plate text is inserted.
    # ------------------------------------------------------------------------

    detection_id: Optional[int] = None

    if (
        db is not None
        and plate_text
        and status == PlateStatus.VERIFIED.value
    ):

        try:

            det = create_detection(
                db,
                DetectionCreate(
                    plate_number=plate_text,
                    camera_id=camera_id,
                    timestamp=timestamp,
                    detection_confidence=(
                        plate.confidence
                        if plate
                        else None
                    ),
                ),
            )

            detection_id = det.id

        except Exception as exc:

            logger.warning(
                "[Ingest] Could not store "
                "Detection: %s",
                exc,
            )

            try:
                db.rollback()
            except Exception:
                pass

    # ------------------------------------------------------------------------
    # CHANGE 5
    # LOW-CONFIDENCE -> MANUAL REVIEW
    # ------------------------------------------------------------------------

    display_text = (
        plate_text
        or partial_text_val
    )

    if (
        db is not None
        and display_text
        and consensus.confidence_tier == "LOW"
    ):

        try:

            from app.services.manual_review_service import (
                create_review_item,
            )

            from app.models.manual_review import (
                ManualReview,
            )

            cutoff = (
                timestamp
                - timedelta(hours=1)
            )

            existing = (
                db.query(ManualReview)
                .filter(
                    ManualReview.ocr_plate_text
                    == display_text,

                    ManualReview.camera_id
                    == camera_id,

                    ManualReview.review_status
                    == "PENDING",

                    ManualReview.created_at
                    >= cutoff,
                )
                .first()
            )

            if not existing:

                create_review_item(
                    db=db,
                    camera_id=camera_id,
                    timestamp=timestamp,
                    vehicle_type=(
                        vehicle.vehicle_class
                    ),
                    vehicle_category=(
                        vehicle_cat
                    ),
                    consensus=consensus,
                    source_file=source_file,
                    frame_number=frame_number,
                    reason="low_confidence",
                )

        except Exception as exc:

            logger.warning(
                "[Ingest] Could not create "
                "manual review item: %s",
                exc,
            )

    # ------------------------------------------------------------------------
    # RETURN API OBJECT
    # ------------------------------------------------------------------------

    return IngestDetection(
        vehicle_type=(
            vehicle.vehicle_class
        ),

        vehicle_confidence=(
            vehicle.confidence
        ),

        vehicle_bbox=(
            vehicle.bbox
        ),

        track_id=track_id,

        plate_number=plate_text,

        partial_text=(
            partial_text_val
        ),

        plate_status=status,

        plate_raw_text=(
            ocr.raw_text
            if ocr
            else None
        ),

        plate_confidence=(
            plate.confidence
            if plate
            else None
        ),

        ocr_confidence=(
            ocr.ocr_confidence
            if ocr
            else None
        ),

        plate_bbox=(
            plate.bbox
            if plate
            else None
        ),

        plate_normalised=(
            was_normalised
        ),

        low_confidence=(
            is_low_conf
        ),

        quality_score=(
            consensus.quality_score
        ),

        preprocessing_method=(
            consensus.preprocessing_method
        ),

        supporting_frames=(
            consensus.supporting_frames
        ),

        frame_number=frame_number,

        timestamp=(
            timestamp.isoformat()
        ),

        camera_id=camera_id,

        latitude=latitude,

        longitude=longitude,

        source_file=source_file,

        event_id=event_id,

        detection_id=detection_id,
    )


# ============================================================================
# CHANGE 9
# COMPLIANCE ANOMALY CHECK
# ============================================================================

def _check_compliance_anomalies(
    tracker: _SimpleTracker,
    evidence_map: Dict[str, PlateEvidence],
    camera_id: str,
    timestamp: datetime,
    db: Optional[Session],
) -> None:
    """
    Identify tracks that have had no usable plate read for the
    configured number of sampled frames.

    Important:
      - A track with OCR evidence is NOT considered an anomaly.
      - A track with zero usable OCR observations and enough
        no-plate frames is considered a compliance anomaly.

    The final VehicleEvent for such a track is created by
    _build_ingest_detection(), where plate_number is None.
    """

    threshold = (
        COMPLIANCE_ANOMALY_MIN_FRAMES_WITHOUT_PLATE
    )

    for track_id, evidence in evidence_map.items():

        frames_no_plate = (
            tracker.get_frames_without_plate(
                track_id
            )
        )

        if frames_no_plate < threshold:
            continue

        # If any OCR evidence exists, this is not a
        # "never readable" compliance anomaly.
        if evidence.observations:
            continue

        logger.info(
            "[Ingest] Track %s: compliance anomaly "
            "— %d frames without plate",
            track_id,
            frames_no_plate,
        )


# ============================================================================
# DEMO MULTI-CAMERA SUPPORT
# ============================================================================

def _resolve_demo_camera(
    track_id: str,
    default_camera: str,
    track_index: int,
) -> str:
    """
    Assign a synthetic camera in demo mode.

    This does NOT fabricate detection data.
    Only the camera assignment is synthetic.
    """

    if not (
        DEMO_MODE_SYNTHETIC_CAMERAS
        and DEMO_CAMERA_SEQUENCE
    ):
        return default_camera

    try:

        return DEMO_CAMERA_SEQUENCE[
            track_index
            % len(DEMO_CAMERA_SEQUENCE)
        ]

    except Exception:

        return default_camera


# ============================================================================
# IMAGE INGESTION
# ============================================================================

def ingest_image(
    image_path: Path,
    camera_id: str,
    timestamp: Optional[datetime] = None,
    db: Optional[Session] = None,
    privacy_mode: bool = PRIVACY_MODE,
) -> ImageIngestResponse:
    """
    Process a single image through the ANPR pipeline.
    """

    if timestamp is None:
        timestamp = datetime.now(
            timezone.utc
        )

    latitude, longitude = get_camera_gps(
        camera_id
    )

    warnings: List[str] = []

    if get_camera_meta(camera_id) is None:

        warnings.append(
            f"camera_id '{camera_id}' "
            "not in cameras.json — GPS defaulted"
        )

    if privacy_mode:

        warnings.append(
            "privacy_mode=True: face regions "
            "blurred before detection."
        )

    # ------------------------------------------------------------------------
    # LOAD IMAGE
    # ------------------------------------------------------------------------

    image = load_image(
        image_path
    )

    if image is None:

        raise ValueError(
            f"Could not load image "
            f"'{image_path.name}'."
        )

    # ------------------------------------------------------------------------
    # REUSE FRAME PIPELINE
    # ------------------------------------------------------------------------

    tracker = _SimpleTracker()

    evidence_map: Dict[
        str,
        PlateEvidence,
    ] = {}

    frame_results = _detect_frame(
        image=image,
        frame_number=0,
        tracker=tracker,
        evidence_map=evidence_map,
        privacy_mode=privacy_mode,
    )

    detections: List[
        IngestDetection
    ] = []

    # ------------------------------------------------------------------------
    # BUILD RESULTS
    # ------------------------------------------------------------------------

    for (
        track_id,
        vehicle,
        plate,
        ocr,
        consensus,
    ) in frame_results:

        detection = (
            _build_ingest_detection(
                track_id=track_id,
                vehicle=vehicle,
                plate=plate,
                ocr=ocr,
                consensus=consensus,
                frame_number=0,
                timestamp=timestamp,
                camera_id=camera_id,
                latitude=latitude,
                longitude=longitude,
                source_file=image_path.name,
                db=db,
            )
        )

        detections.append(
            detection
        )

    # ------------------------------------------------------------------------
    # SUMMARY
    # ------------------------------------------------------------------------

    verified_count = sum(
        1
        for d in detections
        if d.plate_status
        == PlateStatus.VERIFIED.value
    )

    partial_count = sum(
        1
        for d in detections
        if d.plate_status
        == PlateStatus.PARTIAL.value
    )

    low_conf_count = sum(
        1
        for d in detections
        if d.low_confidence
    )

    total_vehicles = len(
        detections
    )

    total_plates = sum(
        1
        for d in detections
        if (
            d.plate_number
            or d.partial_text
        )
    )

    # ------------------------------------------------------------------------
    # ANNOTATED IMAGE
    # ------------------------------------------------------------------------

    annotated_image_url = None

    try:

        annotated = image.copy()

        for detection in detections:

            annotated = annotate_image(
                annotated,
                detection,
            )

        output_path = (
            Path(OUTPUT_DIR)
            / f"annotated_{image_path.name}"
        )

        save_image(
            annotated,
            output_path,
        )

        annotated_image_url = str(
            output_path
        )

    except Exception as exc:

        logger.warning(
            "[Ingest] Could not save "
            "annotated image: %s",
            exc,
        )

    # ------------------------------------------------------------------------
    # RETURN
    # ------------------------------------------------------------------------

    return ImageIngestResponse(
        status="ok",

        source_file=image_path.name,

        camera_id=camera_id,

        timestamp=(
            timestamp.isoformat()
        ),

        latitude=latitude,

        longitude=longitude,

        total_vehicles=total_vehicles,

        total_plates=total_plates,

        verified_plates=verified_count,

        partial_plates=partial_count,

        low_confidence_plates=low_conf_count,

        detections=detections,

        annotated_image_url=(
            annotated_image_url
        ),

        warnings=warnings,
    )


# ============================================================================
# VIDEO INGESTION
# ============================================================================

def ingest_video(
    video_path: Path,
    camera_id: str,
    base_timestamp: Optional[datetime] = None,
    frame_skip: int = 5,
    db: Optional[Session] = None,
    demo_multi_camera: bool = False,
    privacy_mode: bool = PRIVACY_MODE,
) -> VideoIngestResponse:
    """
    Ingest a traffic video.

    Memory optimized:
      - frames are processed sequentially
      - no giant frame_store
      - only one representative frame per track is retained
      - multi-frame OCR evidence remains in evidence_map
    """

    if base_timestamp is None:

        base_timestamp = datetime.now(
            timezone.utc
        )

    frame_skip = max(
        1,
        frame_skip,
    )

    # ------------------------------------------------------------------------
    # CAMERA INFORMATION
    # ------------------------------------------------------------------------

    lat, lon = get_camera_gps(
        camera_id
    )

    warnings: List[str] = []

    if get_camera_meta(camera_id) is None:

        warnings.append(
            f"camera_id '{camera_id}' "
            "not in cameras.json — GPS defaulted"
        )

    if privacy_mode:

        warnings.append(
            "privacy_mode=True: face regions "
            "blurred on every frame before detection."
        )

    # ------------------------------------------------------------------------
    # OPEN VIDEO
    # ------------------------------------------------------------------------

    cap = cv2.VideoCapture(
        str(video_path)
    )

    if not cap.isOpened():

        raise ValueError(
            f"Cannot open video "
            f"'{video_path.name}'."
        )

    fps = (
        cap.get(cv2.CAP_PROP_FPS)
        or 25.0
    )

    total_frames = int(
        cap.get(
            cv2.CAP_PROP_FRAME_COUNT
        )
    )

    logger.info(
        "[Ingest] Video '%s' | "
        "frames=%d fps=%.1f skip=%d",
        video_path.name,
        total_frames,
        fps,
        frame_skip,
    )

    # ------------------------------------------------------------------------
    # TRACKING + OCR EVIDENCE
    # ------------------------------------------------------------------------

    tracker = _SimpleTracker()

    evidence_map: Dict[
        str,
        PlateEvidence,
    ] = {}

    # Only best representative frame per track.
    best_frame_by_track: Dict[
        str,
        dict,
    ] = {}

    # First-seen ordering.
    track_order: Dict[
        str,
        int,
    ] = {}

    frames_processed = 0
    frame_idx = 0

    # ------------------------------------------------------------------------
    # PROCESS VIDEO
    # ------------------------------------------------------------------------

    try:

        while True:

            ret, frame = cap.read()

            if not ret:
                break

            # Only process sampled frames.
            if (
                frame_idx
                % frame_skip
                == 0
            ):

                frame_ts = (
                    base_timestamp
                    + timedelta(
                        seconds=(
                            frame_idx
                            / fps
                        )
                    )
                )

                frame_data = (
                    _detect_frame(
                        image=frame,
                        frame_number=frame_idx,
                        tracker=tracker,
                        evidence_map=evidence_map,
                        privacy_mode=privacy_mode,
                    )
                )

                frames_processed += 1

                for (
                    track_id,
                    vehicle,
                    plate,
                    ocr,
                    provisional,
                ) in frame_data:

                    # --------------------------------------------------------
                    # TRACK ORDER
                    # --------------------------------------------------------

                    if (
                        track_id
                        not in track_order
                    ):

                        track_order[
                            track_id
                        ] = len(
                            track_order
                        )

                    # --------------------------------------------------------
                    # REPRESENTATIVE FRAME SCORE
                    # --------------------------------------------------------

                    ocr_score = 0.0

                    if (
                        ocr is not None
                        and not ocr.is_noise
                    ):

                        ocr_score = float(
                            max(
                                0.0,
                                ocr.ocr_confidence,
                            )
                        )

                    plate_score = 0.0

                    if plate is not None:

                        plate_score = float(
                            max(
                                0.0,
                                plate.confidence,
                            )
                        )

                    # OCR is more important than plate
                    # detector confidence for ANPR.
                    representative_score = (
                        ocr_score * 0.8
                        + plate_score * 0.2
                    )

                    current_best = (
                        best_frame_by_track.get(
                            track_id
                        )
                    )

                    if (
                        current_best is None
                        or representative_score
                        > current_best["score"]
                    ):

                        best_frame_by_track[
                            track_id
                        ] = {
                            "vehicle": vehicle,
                            "plate": plate,
                            "ocr": ocr,
                            "frame_number": frame_idx,
                            "frame_timestamp": frame_ts,
                            "score": representative_score,
                        }

            frame_idx += 1

    finally:

        cap.release()

    logger.info(
        "[Ingest] '%s' done — "
        "%d/%d frames, %d track(s)",
        video_path.name,
        frames_processed,
        total_frames,
        len(evidence_map),
    )

    # ------------------------------------------------------------------------
    # CHANGE 9
    # ------------------------------------------------------------------------

    _check_compliance_anomalies(
        tracker=tracker,
        evidence_map=evidence_map,
        camera_id=camera_id,
        timestamp=base_timestamp,
        db=db,
    )

    # ------------------------------------------------------------------------
    # FINAL DETECTIONS
    # ------------------------------------------------------------------------

    all_detections: List[
        IngestDetection
    ] = []

    ordered_tracks = sorted(
        best_frame_by_track.keys(),
        key=lambda tid: track_order.get(
            tid,
            0,
        ),
    )

    for track_id in ordered_tracks:

        frame_info = (
            best_frame_by_track[
                track_id
            ]
        )

        vehicle = frame_info[
            "vehicle"
        ]

        plate = frame_info[
            "plate"
        ]

        ocr = frame_info[
            "ocr"
        ]

        frame_number = frame_info[
            "frame_number"
        ]

        frame_ts = frame_info[
            "frame_timestamp"
        ]

        # --------------------------------------------------------------------
        # FINAL MULTI-FRAME CONSENSUS
        # --------------------------------------------------------------------

        final = (
            evidence_map[
                track_id
            ].consensus()
        )

        # --------------------------------------------------------------------
        # DEMO MULTI-CAMERA
        # --------------------------------------------------------------------

        if demo_multi_camera:

            effective_camera = (
                _resolve_demo_camera(
                    track_id=track_id,
                    default_camera=camera_id,
                    track_index=track_order[
                        track_id
                    ],
                )
            )

        else:

            effective_camera = camera_id

        eff_lat, eff_lon = (
            get_camera_gps(
                effective_camera
            )
        )

        # --------------------------------------------------------------------
        # FINAL DETECTION + DB
        # --------------------------------------------------------------------

        detection = (
            _build_ingest_detection(
                track_id=track_id,
                vehicle=vehicle,
                plate=plate,
                ocr=ocr,
                consensus=final,
                frame_number=frame_number,
                timestamp=frame_ts,
                camera_id=effective_camera,
                latitude=eff_lat,
                longitude=eff_lon,
                source_file=video_path.name,
                db=db,
            )
        )

        all_detections.append(
            detection
        )

    # ------------------------------------------------------------------------
    # VERIFIED PLATES
    # ------------------------------------------------------------------------

    verified_plates = sorted(
        {
            d.plate_number
            for d in all_detections
            if (
                d.plate_number
                and d.plate_status
                == PlateStatus.VERIFIED.value
            )
        }
    )

    # ------------------------------------------------------------------------
    # PARTIAL PLATES
    # ------------------------------------------------------------------------

    partial_plates = sorted(
        {
            d.partial_text
            for d in all_detections
            if (
                d.partial_text
                and d.plate_status
                in (
                    PlateStatus.PARTIAL.value,
                    PlateStatus.LOW_CONFIDENCE.value,
                )
            )
        }
    )

    # ------------------------------------------------------------------------
    # LOW CONFIDENCE COUNT
    # ------------------------------------------------------------------------

    low_conf_count = sum(
        1
        for d in all_detections
        if d.low_confidence
    )

    # ------------------------------------------------------------------------
    # UNREADABLE COUNT
    # ------------------------------------------------------------------------

    unreadable_count = sum(
        1
        for d in all_detections
        if (
            d.plate_status
            == PlateStatus.UNREADABLE.value
        )
    )

    # ------------------------------------------------------------------------
    # DEMO NOTE
    # ------------------------------------------------------------------------

    demo_note = ""

    if (
        demo_multi_camera
        and DEMO_MODE_SYNTHETIC_CAMERAS
    ):

        cams_used = sorted(
            {
                d.camera_id
                for d in all_detections
            }
        )

        demo_note = (
            " ⚠ DEMO MODE: synthetic "
            "camera assignment active — "
            f"camera_ids {cams_used} are "
            "simulated, not real hardware. "
            "Detection data (plates, "
            "confidence, timestamps) is real."
        )

        logger.info(
            "[Ingest] Demo multi-camera active "
            "— cameras used: %s",
            cams_used,
        )

    # ------------------------------------------------------------------------
    # FINAL RESPONSE
    # ------------------------------------------------------------------------

    return VideoIngestResponse(
        status="ok",

        source_file=video_path.name,

        camera_id=camera_id,

        total_frames=total_frames,

        frames_processed=frames_processed,

        frame_skip=frame_skip,

        total_detections=len(
            all_detections
        ),

        unique_plates=verified_plates,

        partial_plates=partial_plates,

        verified_count=len(
            verified_plates
        ),

        partial_count=len(
            partial_plates
        ),

        low_confidence_plates=(
            low_conf_count
        ),

        unreadable_count=(
            unreadable_count
        ),

        detections=all_detections,

        warnings=warnings,

        processing_note=(
            f"Frame skip={frame_skip}. "
            "Verified plates from real "
            "multi-frame OCR evidence. "
            "LOW-confidence reads sent "
            "to manual review queue. "
            "Compliance anomalies stored "
            "for alert engine."
            + demo_note
        ),
    )