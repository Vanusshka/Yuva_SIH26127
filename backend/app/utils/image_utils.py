"""
Shared image utility helpers used across the pipeline.
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np


# ── colour palette (BGR) per vehicle class ────────────────────────────────────
_VEHICLE_COLOURS = {
    "car":        (0, 255, 0),
    "motorcycle": (255, 0, 255),
    "bus":        (0, 165, 255),
    "truck":      (0, 0, 255),
}
_PLATE_COLOUR   = (0, 255, 255)   # cyan
_DEFAULT_COLOUR = (200, 200, 200)


def load_image(path: str | Path) -> np.ndarray:
    """Load an image from disk; raises FileNotFoundError if missing."""
    img = cv2.imread(str(path))
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {path}")
    return img


def save_image(image: np.ndarray, path: str | Path) -> None:
    """Save a BGR numpy array to disk, creating parent dirs as needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), image)


def draw_vehicle_box(
    frame: np.ndarray,
    bbox: List[int],
    label: str,
    colour: Optional[Tuple[int, int, int]] = None,
) -> None:
    """Draw a filled-label bounding box on *frame* in-place."""
    x1, y1, x2, y2 = bbox
    col = colour or _VEHICLE_COLOURS.get(label.lower(), _DEFAULT_COLOUR)

    cv2.rectangle(frame, (x1, y1), (x2, y2), col, 2)

    (tw, th), bl = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    cv2.rectangle(frame, (x1, y1 - th - bl - 4), (x1 + tw + 2, y1), col, -1)
    cv2.putText(frame, label, (x1 + 1, y1 - bl - 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1, cv2.LINE_AA)


def draw_plate_box(
    frame: np.ndarray,
    bbox: List[int],
    plate_text: str,
    conf: float,
) -> None:
    """Draw a plate bounding box and text overlay in-place."""
    x1, y1, x2, y2 = bbox
    cv2.rectangle(frame, (x1, y1), (x2, y2), _PLATE_COLOUR, 2)

    label = f"{plate_text} ({conf:.0%})" if plate_text else "plate"
    (tw, th), bl = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.50, 1)
    # draw label below the plate box
    by = y2 + th + bl + 4
    cv2.rectangle(frame, (x1, y2), (x1 + tw + 2, by), _PLATE_COLOUR, -1)
    cv2.putText(frame, label, (x1 + 1, by - bl - 1),
                cv2.FONT_HERSHEY_SIMPLEX, 0.50, (0, 0, 0), 1, cv2.LINE_AA)


def annotate_image(frame: np.ndarray, detections: list) -> np.ndarray:
    """
    Draw all vehicle + plate annotations on a copy of *frame*.

    Parameters
    ----------
    frame      : BGR image
    detections : list of DetectionResult-compatible dicts or objects

    Returns
    -------
    Annotated BGR image
    """
    annotated = frame.copy()

    for det in detections:
        # Support both dict and object access
        vtype   = det["vehicle_type"]   if isinstance(det, dict) else det.vehicle_type
        vconf   = det["vehicle_confidence"] if isinstance(det, dict) else det.vehicle_confidence
        vbbox   = det["vehicle_bbox"]   if isinstance(det, dict) else det.vehicle_bbox
        pbbox   = det["plate_bbox"]     if isinstance(det, dict) else det.plate_bbox
        pnum    = det["plate_number"]   if isinstance(det, dict) else det.plate_number
        oconf   = det["ocr_confidence"] if isinstance(det, dict) else det.ocr_confidence

        vlabel = f"{vtype} {vconf:.0%}"
        draw_vehicle_box(annotated, vbbox, vlabel)

        if pbbox:
            draw_plate_box(annotated, pbbox, pnum or "", oconf or 0.0)

    return annotated


# ── Privacy / redaction ───────────────────────────────────────────────────────

import threading

_face_cascade_lock = threading.Lock()
_face_cascade: Optional[cv2.CascadeClassifier] = None


def _get_face_cascade() -> cv2.CascadeClassifier:
    """
    Lazy-load the Haar cascade classifier (thread-safe singleton).
    Ships with OpenCV — no download required.
    """
    global _face_cascade
    if _face_cascade is None:
        with _face_cascade_lock:
            if _face_cascade is None:
                _face_cascade = cv2.CascadeClassifier(
                    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                )
    return _face_cascade


def blur_faces(
    frame          : np.ndarray,
    scale_factor   : float               = 1.1,
    min_neighbors  : int                 = 4,
    min_size       : Tuple[int, int]     = (30, 30),
    blur_strength  : int                 = 31,   # must be odd
) -> Tuple[np.ndarray, int]:
    """
    Detect faces in *frame* using OpenCV Haar cascade and apply Gaussian blur
    to each detected face region.

    Privacy guarantee:
      - Face regions are blurred BEFORE any plate detection or OCR runs.
      - Only face regions are blurred; plate regions are left untouched so
        ANPR accuracy is not affected.
      - The original frame is never written to disk — this function returns
        a blurred copy.

    Parameters
    ----------
    frame         : BGR numpy array (full video frame)
    scale_factor  : Haar cascade parameter — 1.05 (sensitive) to 1.3 (fast)
    min_neighbors : Haar cascade min neighbours before accepting a detection
    min_size      : Minimum face size in pixels to detect
    blur_strength : Gaussian kernel size (must be odd; higher = stronger blur)

    Returns
    -------
    (blurred_frame, n_faces_blurred)
    """
    if frame is None or frame.size == 0:
        return frame, 0

    cascade = _get_face_cascade()
    gray    = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces   = cascade.detectMultiScale(
        gray,
        scaleFactor  = scale_factor,
        minNeighbors = min_neighbors,
        minSize      = min_size,
    )

    if len(faces) == 0:
        return frame.copy(), 0

    result = frame.copy()
    # Ensure blur_strength is odd
    k = blur_strength | 1
    for (fx, fy, fw, fh) in faces:
        # Add 15 % padding around the detected face region
        pad_x = max(1, int(fw * 0.15))
        pad_y = max(1, int(fh * 0.15))
        x1 = max(0, fx - pad_x)
        y1 = max(0, fy - pad_y)
        x2 = min(result.shape[1], fx + fw + pad_x)
        y2 = min(result.shape[0], fy + fh + pad_y)
        result[y1:y2, x1:x2] = cv2.GaussianBlur(result[y1:y2, x1:x2], (k, k), 0)

    return result, len(faces)


def redact_frame(
    frame: np.ndarray,
    plate_bboxes: Optional[List[List[int]]] = None,
) -> np.ndarray:
    """
    Full-frame redaction: blur ALL regions EXCEPT the known license plate
    bounding boxes.  Use this for report images / exported crops.

    Parameters
    ----------
    frame        : original BGR frame
    plate_bboxes : list of [x1,y1,x2,y2] plate regions to PRESERVE (not blurred)

    Returns
    -------
    Redacted frame where everything except plate regions is heavily blurred.
    """
    if frame is None or frame.size == 0:
        return frame

    blurred = cv2.GaussianBlur(frame, (51, 51), 0)
    result  = blurred.copy()

    # Paste original (sharp) plate regions back over the blurred background
    for bbox in (plate_bboxes or []):
        x1, y1, x2, y2 = bbox
        h, w = frame.shape[:2]
        x1 = max(0, x1); y1 = max(0, y1)
        x2 = min(w, x2); y2 = min(h, y2)
        if x2 > x1 and y2 > y1:
            result[y1:y2, x1:x2] = frame[y1:y2, x1:x2]

    return result
