"""
License Plate Detector — Phase 9 Improvement
=============================================

Key fixes over Phase 8:
  1. YOLO path now RESPECTS vehicle_bbox — runs on crop first, then full frame
  2. Configurable % padding added to every detected bbox (prevents edge cut-off)
  3. All bounding boxes are safety-clamped to image dimensions
  4. detect() returns coordinates in original full-frame space regardless of path
  5. Optional debug image saving for diagnosis
  6. Both YOLO + contour methods can be compared per-call
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

from app.config import (
    PLATE_MODEL_NAME,
    PLATE_CONF_THRESH,
    MODELS_DIR,
    OUTPUT_DIR,
)

logger = logging.getLogger(__name__)

# ── Padding fraction applied to every detected bbox ─────────────────────────
PLATE_BBOX_PAD_FRAC: float = 0.10


@dataclass
class PlateDetection:
    """One detected license plate region."""

    bbox         : List[int]          # [x1, y1, x2, y2] in full-frame coords
    confidence   : float
    cropped_image: np.ndarray         # BGR crop (padded, clamped)
    source       : str = "yolo"       # "yolo" | "contour"


# ── helpers ───────────────────────────────────────────────────────────────────


def _pad_bbox(
    x1: int, y1: int, x2: int, y2: int,
    img_w: int, img_h: int,
    pad_frac: float = PLATE_BBOX_PAD_FRAC,
) -> Tuple[int, int, int, int]:
    """
    Expand a bounding box by `pad_frac` on each side and clamp to image bounds.
    Prevents characters at the physical edge of the plate from being cut off.
    """
    bw = x2 - x1
    bh = y2 - y1
    px = max(1, int(bw * pad_frac))
    py = max(1, int(bh * pad_frac))
    return (
        max(0, x1 - px),
        max(0, y1 - py),
        min(img_w, x2 + px),
        min(img_h, y2 + py),
    )


def _safe_crop(image: np.ndarray, x1: int, y1: int, x2: int, y2: int) -> np.ndarray:
    """Crop with boundary safety. Returns 1×1 black if degenerate."""
    h, w = image.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    if x2 <= x1 or y2 <= y1:
        return np.zeros((1, 1, 3), dtype=np.uint8)
    return image[y1:y2, x1:x2].copy()


def _save_debug_image(
    frame       : np.ndarray,
    vehicle_bbox: Optional[List[int]],
    plate_bbox  : Optional[List[int]],
    plate_crop  : Optional[np.ndarray],
    frame_number: int,
    prefix      : str = "dbg",
) -> None:
    """
    Save a composite debug image showing:
      LEFT  — full frame with vehicle (green) + plate (cyan) boxes
      RIGHT — the plate crop
    Saved to OUTPUT_DIR/debug_plates/
    """
    try:
        dbg_dir = OUTPUT_DIR / "debug_plates"
        dbg_dir.mkdir(parents=True, exist_ok=True)

        vis = frame.copy()
        if vehicle_bbox:
            vx1, vy1, vx2, vy2 = vehicle_bbox
            cv2.rectangle(vis, (vx1, vy1), (vx2, vy2), (0, 255, 0), 2)
            cv2.putText(vis, "vehicle", (vx1, vy1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        if plate_bbox:
            px1, py1, px2, py2 = plate_bbox
            cv2.rectangle(vis, (px1, py1), (px2, py2), (255, 200, 0), 2)
            cv2.putText(vis, "plate", (px1, py1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 200, 0), 1)

        parts = [vis]
        if plate_crop is not None and plate_crop.size > 0:
            h = max(64, plate_crop.shape[0])
            w = max(1, int(plate_crop.shape[1] * h / max(1, plate_crop.shape[0])))
            resized = cv2.resize(plate_crop, (w, h), interpolation=cv2.INTER_CUBIC)
            # pad to same height as vis
            pad_h = max(0, vis.shape[0] - h)
            resized = cv2.copyMakeBorder(resized, 0, pad_h, 0, 0,
                                          cv2.BORDER_CONSTANT, value=(40, 40, 40))
            parts.append(resized)

        composite = np.hstack(parts) if len(parts) > 1 else vis
        fname = dbg_dir / f"{prefix}_f{frame_number:06d}_{uuid.uuid4().hex[:6]}.jpg"
        cv2.imwrite(str(fname), composite)
    except Exception as exc:
        logger.debug("[PlateDetector] Debug save failed: %s", exc)


# ── Contour-based fallback ────────────────────────────────────────────────────

def _contour_detect(
    search_region : np.ndarray,
    offset_x      : int,
    offset_y      : int,
    full_frame_w  : int,
    full_frame_h  : int,
) -> List[PlateDetection]:
    """
    Morphology + contour search on `search_region`.
    Translates local coords to full-frame coords via offset_x / offset_y.
    """
    if search_region is None or search_region.size == 0:
        return []
    rh, rw = search_region.shape[:2]
    if rh < 16 or rw < 32:
        return []

    gray   = cv2.cvtColor(search_region, cv2.COLOR_BGR2GRAY)
    blur   = cv2.GaussianBlur(gray, (5, 5), 0)
    edges  = cv2.Canny(blur, 30, 120)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 2))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)

    cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    results: List[PlateDetection] = []

    for cnt in cnts:
        lx, ly, lw, lh = cv2.boundingRect(cnt)
        area  = lw * lh
        ratio = lw / max(lh, 1)

        # Strict size + aspect filters
        if area < 600 or area > (rh * rw * 0.18):
            continue
        if lw < 36 or lh < 10:
            continue
        if not (2.2 <= ratio <= 7.0):
            continue

        # Translate to full-frame, add padding, clamp
        fx1, fy1, fx2, fy2 = _pad_bbox(
            lx + offset_x, ly + offset_y,
            lx + offset_x + lw, ly + offset_y + lh,
            full_frame_w, full_frame_h,
        )
        crop = _safe_crop(search_region,
                          fx1 - offset_x, fy1 - offset_y,
                          fx2 - offset_x, fy2 - offset_y)
        results.append(PlateDetection(
            bbox=[fx1, fy1, fx2, fy2],
            confidence=0.42,
            cropped_image=crop,
            source="contour",
        ))

    results.sort(key=lambda d: (d.bbox[2]-d.bbox[0])*(d.bbox[3]-d.bbox[1]), reverse=True)
    return results[:2]


# ── Main detector ─────────────────────────────────────────────────────────────

class PlateDetector:
    """
    License plate detector.

    Tier 1 — YOLO plate model (if loaded):
      - Runs on vehicle crop if vehicle_bbox provided (more focused)
      - Falls back to full frame if crop yields nothing
      - Bboxes translated back to full-frame space with padding applied

    Tier 2 — Enhanced contour fallback:
      - Searches vehicle crop first with offset correction
      - Falls back to full frame if crop yields nothing
    """

    _instance: "PlateDetector | None" = None

    def __new__(cls):
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._model    = None
            inst._use_yolo = False
            inst._loaded   = False
            cls._instance  = inst
        return cls._instance

    # ── model loading ─────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True

        model_path = MODELS_DIR / PLATE_MODEL_NAME
        if not model_path.exists():
            logger.error(
                "[PlateDetector] Model file not found: %s — falling back to contour detector",
                model_path,
            )

        if model_path.exists() and model_path.stat().st_size > 100_000:
            try:
                from ultralytics import YOLO
                self._model    = YOLO(str(model_path))
                self._use_yolo = True
                logger.info("[PlateDetector] YOLO plate model loaded (%s, %.1f MB)",
                            PLATE_MODEL_NAME, model_path.stat().st_size / 1_048_576)
            except Exception as exc:
                logger.warning("[PlateDetector] YOLO load failed (%s); using contour fallback", exc)
                self._use_yolo = False
        else:
            logger.warning("[PlateDetector] No YOLO model — using enhanced contour fallback")
            self._use_yolo = False

    # ── YOLO helpers ──────────────────────────────────────────────────────────

    def _yolo_on_region(
        self,
        image     : np.ndarray,
        offset_x  : int,
        offset_y  : int,
        full_w    : int,
        full_h    : int,
        conf_thr  : float,
    ) -> List[PlateDetection]:
        """Run YOLO on `image` and translate bbox back to full-frame coords."""
        try:
            res = self._model(image, conf=conf_thr, verbose=False)[0]
        except Exception as exc:
            logger.warning("[PlateDetector] YOLO inference failed: %s", exc)
            return []

        dets: List[PlateDetection] = []
        for box in res.boxes:
            lx1, ly1, lx2, ly2 = map(int, box.xyxy[0].tolist())
            conf = round(float(box.conf[0]), 4)

            # Translate local → full-frame, then pad, then clamp
            fx1, fy1, fx2, fy2 = _pad_bbox(
                lx1 + offset_x, ly1 + offset_y,
                lx2 + offset_x, ly2 + offset_y,
                full_w, full_h,
            )
            # Crop from the search region using local (un-offset) coords
            lx1p = max(0, lx1 - max(1, int((lx2 - lx1) * PLATE_BBOX_PAD_FRAC)))
            ly1p = max(0, ly1 - max(1, int((ly2 - ly1) * PLATE_BBOX_PAD_FRAC)))
            lx2p = min(image.shape[1], lx2 + max(1, int((lx2 - lx1) * PLATE_BBOX_PAD_FRAC)))
            ly2p = min(image.shape[0], ly2 + max(1, int((ly2 - ly1) * PLATE_BBOX_PAD_FRAC)))
            crop = _safe_crop(image, lx1p, ly1p, lx2p, ly2p)

            dets.append(PlateDetection(
                bbox=[fx1, fy1, fx2, fy2],
                confidence=conf,
                cropped_image=crop,
                source="yolo",
            ))

        # Sort by confidence descending
        dets.sort(key=lambda d: d.confidence, reverse=True)
        return dets

    # ── public API ────────────────────────────────────────────────────────────

    def detect(
        self,
        image        : np.ndarray,
        conf_threshold: float = PLATE_CONF_THRESH,
        vehicle_bbox : Optional[List[int]] = None,
        frame_number : int = 0,
        save_debug   : bool = False,
    ) -> List[PlateDetection]:
        """
        Detect license plates in `image` (full BGR frame).

        Strategy
        --------
        If vehicle_bbox is given:
          1. Run detector on vehicle crop first (focused, faster)
          2. If nothing found, run on full frame
        If vehicle_bbox is None:
          Run on full frame only

        All returned bboxes are in full-frame coordinate space.
        Bboxes always include padding and are clamped to image bounds.

        Parameters
        ----------
        image          BGR full frame
        conf_threshold minimum detection confidence
        vehicle_bbox   [x1,y1,x2,y2] optional vehicle region
        frame_number   used for debug image naming
        save_debug     if True, write diagnostic images to OUTPUT_DIR/debug_plates/
        """
        self._load()

        fh, fw = image.shape[:2]
        found : List[PlateDetection] = []

        # ── Tier 1: YOLO ─────────────────────────────────────────────────────
        if self._use_yolo and self._model is not None:
            if vehicle_bbox is not None:
                vx1, vy1, vx2, vy2 = vehicle_bbox
                vx1 = max(0, vx1); vy1 = max(0, vy1)
                vx2 = min(fw, vx2); vy2 = min(fh, vy2)
                if vx2 > vx1 and vy2 > vy1:
                    crop_region = image[vy1:vy2, vx1:vx2]
                    found = self._yolo_on_region(
                        crop_region, vx1, vy1, fw, fh, conf_threshold
                    )
                    logger.debug("[PlateDetector] YOLO on crop: %d plates (frame %d)",
                                 len(found), frame_number)

            if not found:
                found = self._yolo_on_region(image, 0, 0, fw, fh, conf_threshold)
                if found and vehicle_bbox:
                    # Filter to plates whose centroid is inside vehicle bbox
                    vx1, vy1, vx2, vy2 = vehicle_bbox
                    inside = []
                    for d in found:
                        cx = (d.bbox[0] + d.bbox[2]) // 2
                        cy = (d.bbox[1] + d.bbox[3]) // 2
                        if vx1 <= cx <= vx2 and vy1 <= cy <= vy2:
                            inside.append(d)
                    found = inside if inside else found
                logger.debug("[PlateDetector] YOLO on full frame: %d plates (frame %d)",
                             len(found), frame_number)

        # ── Tier 2: Contour fallback ──────────────────────────────────────────
        if not found:
            if vehicle_bbox is not None:
                vx1, vy1, vx2, vy2 = vehicle_bbox
                vx1 = max(0, vx1); vy1 = max(0, vy1)
                vx2 = min(fw, vx2); vy2 = min(fh, vy2)
                if vx2 > vx1 and vy2 > vy1:
                    crop_region = image[vy1:vy2, vx1:vx2]
                    found = _contour_detect(crop_region, vx1, vy1, fw, fh)
                    logger.debug("[PlateDetector] Contour on crop: %d plates (frame %d)",
                                 len(found), frame_number)

            if not found:
                found = _contour_detect(image, 0, 0, fw, fh)
                logger.debug("[PlateDetector] Contour on full frame: %d plates (frame %d)",
                             len(found), frame_number)

        # ── Optional debug images ─────────────────────────────────────────────
        if save_debug and found:
            _save_debug_image(
                frame        = image,
                vehicle_bbox = vehicle_bbox,
                plate_bbox   = found[0].bbox,
                plate_crop   = found[0].cropped_image,
                frame_number = frame_number,
            )

        return found
