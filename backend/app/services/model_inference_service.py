"""
ModelInferenceService — deployment abstraction for AI model calls.

Supports two providers controlled by the MODEL_PROVIDER environment variable:

  MODEL_PROVIDER=local (default)
    Uses .pt model files from backend/models/ via ultralytics YOLO.
    Requires model files to be present on disk.
    Used for local development and self-hosted deployment.

  MODEL_PROVIDER=huggingface
    Calls HuggingFace Inference API endpoints for vehicle and plate detection.
    Model files are NOT required on disk.
    Used for cloud deployment (Render free tier) where storing large model
    files is impractical.
    Requires: HF_VEHICLE_MODEL_URL, HF_PLATE_MODEL_URL, HF_TOKEN env vars.

OCR is always run locally regardless of MODEL_PROVIDER — PaddleOCR is
too specialised to delegate to a generic HF endpoint reliably.

IMPORTANT: The local pipeline is unchanged. This module only wraps
the vehicle and plate detection calls; all other pipeline logic
(tracking, OCR, DB writes, trajectory, analytics) is unaffected.
"""

from __future__ import annotations

import io
import logging
from typing import List, Optional

import cv2
import numpy as np

from app.config import MODEL_PROVIDER, HF_VEHICLE_MODEL_URL, HF_PLATE_MODEL_URL, HF_TOKEN

logger = logging.getLogger(__name__)

# ── Local provider ────────────────────────────────────────────────────────────

def detect_vehicles_local(
    image: np.ndarray,
    conf_threshold: float,
) -> List[dict]:
    """Delegate to the existing VehicleDetector singleton (unchanged)."""
    from app.models.vehicle_detector import VehicleDetector, VehicleDetection
    dets = VehicleDetector().detect(image, conf_threshold=conf_threshold)
    return [
        {"vehicle_class": d.vehicle_class, "confidence": d.confidence, "bbox": d.bbox}
        for d in dets
    ]


def detect_plates_local(
    image: np.ndarray,
    vehicle_bbox: Optional[List[int]],
    frame_number: int,
) -> List[dict]:
    """Delegate to the existing PlateDetector singleton (unchanged)."""
    from app.models.plate_detector import PlateDetector, PlateDetection
    dets = PlateDetector().detect(image, vehicle_bbox=vehicle_bbox, frame_number=frame_number)
    return [
        {"bbox": d.bbox, "confidence": d.confidence, "cropped_image": d.cropped_image, "source": d.source}
        for d in dets
    ]


# ── HuggingFace provider ──────────────────────────────────────────────────────

def _image_to_bytes(image: np.ndarray) -> bytes:
    """Encode a BGR numpy image to JPEG bytes for the HF API."""
    ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise ValueError("Failed to encode image to JPEG")
    return buf.tobytes()


def _call_hf_endpoint(url: str, image: np.ndarray) -> List[dict]:
    """
    Call a HuggingFace Inference Endpoint for object detection.
    Returns list of {label, score, box: {xmin, ymin, xmax, ymax}}.
    """
    import httpx

    headers = {"Content-Type": "image/jpeg"}
    if HF_TOKEN:
        headers["Authorization"] = f"Bearer {HF_TOKEN}"

    img_bytes = _image_to_bytes(image)

    try:
        resp = httpx.post(url, content=img_bytes, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("[ModelInference] HF endpoint call failed (%s): %s", url, exc)
        return []


def detect_vehicles_hf(
    image: np.ndarray,
    conf_threshold: float,
) -> List[dict]:
    """
    Call HF vehicle detection endpoint and convert to the same format
    as detect_vehicles_local().
    """
    from app.config import VEHICLE_CLASS_IDS

    if not HF_VEHICLE_MODEL_URL:
        logger.warning("[ModelInference] HF_VEHICLE_MODEL_URL not set — returning empty detections")
        return []

    raw = _call_hf_endpoint(HF_VEHICLE_MODEL_URL, image)
    results = []
    for det in raw:
        score = float(det.get("score", 0.0))
        if score < conf_threshold:
            continue
        label = det.get("label", "").lower()
        # Map HF label to our vehicle class names
        # HF YOLO models typically return COCO class names
        _label_map = {
            "car": "car", "motorcycle": "motorcycle", "bus": "bus",
            "truck": "truck", "bicycle": "bicycle",
            "auto_rickshaw": "auto_rickshaw",
        }
        vehicle_class = _label_map.get(label)
        if not vehicle_class:
            continue
        box = det.get("box", {})
        x1, y1 = int(box.get("xmin", 0)), int(box.get("ymin", 0))
        x2, y2 = int(box.get("xmax", 0)), int(box.get("ymax", 0))
        results.append({
            "vehicle_class": vehicle_class,
            "confidence": round(score, 4),
            "bbox": [x1, y1, x2, y2],
        })

    return results


def detect_plates_hf(
    image: np.ndarray,
    vehicle_bbox: Optional[List[int]],
    frame_number: int,
) -> List[dict]:
    """
    Call HF plate detection endpoint and return plate regions.
    If vehicle_bbox is given, crop first (same logic as local detector).
    """
    if not HF_PLATE_MODEL_URL:
        logger.warning("[ModelInference] HF_PLATE_MODEL_URL not set — returning empty plates")
        return []

    h, w = image.shape[:2]

    # Use vehicle crop if available (matches local detector behaviour)
    if vehicle_bbox:
        x1, y1, x2, y2 = [max(0, v) for v in vehicle_bbox]
        x2, y2 = min(w, x2), min(h, y2)
        search_region = image[y1:y2, x1:x2] if x2 > x1 and y2 > y1 else image
        offset_x, offset_y = x1, y1
    else:
        search_region = image
        offset_x, offset_y = 0, 0

    if search_region.size == 0:
        return []

    raw = _call_hf_endpoint(HF_PLATE_MODEL_URL, search_region)
    results = []

    for det in raw:
        score = float(det.get("score", 0.0))
        box   = det.get("box", {})
        lx1, ly1 = int(box.get("xmin", 0)), int(box.get("ymin", 0))
        lx2, ly2 = int(box.get("xmax", 0)), int(box.get("ymax", 0))

        # Translate back to full-frame coordinates
        fx1 = max(0, lx1 + offset_x)
        fy1 = max(0, ly1 + offset_y)
        fx2 = min(w,  lx2 + offset_x)
        fy2 = min(h,  ly2 + offset_y)

        # Crop from search region
        crop = search_region[ly1:ly2, lx1:lx2].copy() if lx2 > lx1 and ly2 > ly1 else np.zeros((1, 1, 3), dtype=np.uint8)

        results.append({
            "bbox": [fx1, fy1, fx2, fy2],
            "confidence": round(score, 4),
            "cropped_image": crop,
            "source": "hf",
        })

    return results


# ── Public API — used by ingest_service.py ────────────────────────────────────

def detect_vehicles(
    image: np.ndarray,
    conf_threshold: float,
) -> List[dict]:
    """
    Route vehicle detection to local or HuggingFace provider.
    Returns list of dicts with keys: vehicle_class, confidence, bbox.
    """
    if MODEL_PROVIDER == "huggingface":
        return detect_vehicles_hf(image, conf_threshold)
    return detect_vehicles_local(image, conf_threshold)


def detect_plates(
    image: np.ndarray,
    vehicle_bbox: Optional[List[int]],
    frame_number: int,
) -> List[dict]:
    """
    Route plate detection to local or HuggingFace provider.
    Returns list of dicts with keys: bbox, confidence, cropped_image, source.
    """
    if MODEL_PROVIDER == "huggingface":
        return detect_plates_hf(image, vehicle_bbox, frame_number)
    return detect_plates_local(image, vehicle_bbox, frame_number)
