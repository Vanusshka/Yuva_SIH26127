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
