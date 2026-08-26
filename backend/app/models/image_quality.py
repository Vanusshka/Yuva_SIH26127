"""
Image Quality Analysis & Adaptive Preprocessing — Phase 9
==========================================================

Analyses a plate crop for brightness, contrast, sharpness, and blur,
then selects the preprocessing strategy most likely to help OCR.

ABSOLUTE RULE: Enhancement may improve contrast/sharpness for OCR to read
EXISTING characters more clearly. It MUST NOT be used to invent, hallucinate,
or guess missing characters. If a plate remains unreadable after enhancement,
it must be reported as UNREADABLE — not fabricated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple, Optional
import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ── Thresholds (all tunable) ──────────────────────────────────────────────────

# Minimum crop dimensions — anything smaller is too small to read
MIN_PLATE_W = 60    # pixels
MIN_PLATE_H = 15    # pixels

# Sharpness (Laplacian variance): below this = blurry
SHARPNESS_BLUR_THRESH   = 50.0
# Sharpness above this = good quality
SHARPNESS_OK_THRESH     = 150.0

# Brightness (mean pixel value 0–255)
BRIGHTNESS_DARK_THRESH  = 60.0   # below = dark / low-light
BRIGHTNESS_BRIGHT_THRESH = 210.0  # above = overexposed

# Minimum plate crop area (pixels²)
MIN_AREA = MIN_PLATE_W * MIN_PLATE_H

# Target height for resizing (keeps aspect ratio)
OCR_TARGET_H = 64


@dataclass
class QualityReport:
    """Quality metrics and preprocessing recommendation for a plate crop."""

    width             : int
    height            : int
    brightness        : float     # mean pixel value 0–255
    contrast          : float     # std dev of pixel values
    sharpness         : float     # Laplacian variance (higher = sharper)
    is_too_small      : bool
    is_blurry         : bool
    is_dark           : bool
    is_overexposed    : bool
    quality_score     : float     # 0.0–1.0 composite
    preprocessing_method: str     # human-readable label
    # Preprocessed variants (BGR arrays, may be empty list if too small)
    variants          : List[Tuple[str, np.ndarray]] = field(default_factory=list)


def analyse(image: np.ndarray, save_variants: bool = True) -> QualityReport:
    """
    Analyse a plate crop and generate all preprocessing variants.

    Parameters
    ----------
    image         BGR plate crop
    save_variants if True, populate QualityReport.variants for multi-OCR

    Returns
    -------
    QualityReport
    """
    if image is None or image.size == 0:
        return _empty_report()

    h, w = image.shape[:2]

    # ── Basic metrics ─────────────────────────────────────────────────────────
    gray        = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()
    brightness  = float(np.mean(gray))
    contrast    = float(np.std(gray))
    sharpness   = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    is_too_small  = (w < MIN_PLATE_W or h < MIN_PLATE_H)
    is_blurry     = sharpness < SHARPNESS_BLUR_THRESH
    is_dark       = brightness < BRIGHTNESS_DARK_THRESH
    is_overexposed= brightness > BRIGHTNESS_BRIGHT_THRESH

    # ── Composite quality score (0–1) ─────────────────────────────────────────
    sharpness_score   = min(1.0, sharpness / 500.0)
    brightness_score  = 1.0 - abs(brightness - 128.0) / 128.0
    contrast_score    = min(1.0, contrast / 64.0)
    size_score        = min(1.0, (w * h) / (MIN_PLATE_W * MIN_PLATE_H * 4))
    quality_score     = round(
        0.40 * sharpness_score +
        0.25 * brightness_score +
        0.20 * contrast_score +
        0.15 * size_score,
        3,
    )

    # ── Preprocessing label ───────────────────────────────────────────────────
    if is_too_small:
        method = "upscale_only"
    elif is_dark:
        method = "gamma_clahe"
    elif is_blurry:
        method = "sharpen_clahe"
    elif is_overexposed:
        method = "reduce_bright_clahe"
    else:
        method = "standard_clahe"

    # ── Generate variants ─────────────────────────────────────────────────────
    variants: List[Tuple[str, np.ndarray]] = []
    if save_variants and not is_too_small:
        variants = _build_variants(image, gray, is_dark, is_blurry, is_overexposed)

    return QualityReport(
        width               = w,
        height              = h,
        brightness          = round(brightness, 2),
        contrast            = round(contrast, 2),
        sharpness           = round(sharpness, 2),
        is_too_small        = is_too_small,
        is_blurry           = is_blurry,
        is_dark             = is_dark,
        is_overexposed      = is_overexposed,
        quality_score       = quality_score,
        preprocessing_method= method,
        variants            = variants,
    )


def _empty_report() -> QualityReport:
    return QualityReport(
        width=0, height=0, brightness=0.0, contrast=0.0, sharpness=0.0,
        is_too_small=True, is_blurry=True, is_dark=False, is_overexposed=False,
        quality_score=0.0, preprocessing_method="empty", variants=[],
    )


def _resize_to_height(image: np.ndarray, target_h: int = OCR_TARGET_H) -> np.ndarray:
    """Resize preserving aspect ratio to target_h pixels tall."""
    h, w = image.shape[:2]
    if h == 0:
        return image
    scale = target_h / h
    new_w = max(1, int(w * scale))
    return cv2.resize(image, (new_w, target_h), interpolation=cv2.INTER_CUBIC)


def _to_bgr(gray: np.ndarray) -> np.ndarray:
    """Convert single-channel to 3-channel BGR."""
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def _upscale_small(image: np.ndarray) -> np.ndarray:
    """
    Upscale small plates with INTER_LANCZOS4 to improve OCR readability.
    Minimum width after upscale: 180 px.
    """
    h, w = image.shape[:2]
    if w >= 180:
        return _resize_to_height(image)
    scale = max(2.0, 180 / max(w, 1))
    new_w = int(w * scale)
    new_h = int(h * scale)
    return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)


def _clahe_enhance(gray: np.ndarray, clip: float = 2.0) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(4, 4))
    return clahe.apply(gray)


def _gamma_correct(gray: np.ndarray, gamma: float = 0.5) -> np.ndarray:
    """Gamma < 1 brightens; gamma > 1 darkens."""
    lut = np.array([((i / 255.0) ** gamma) * 255 for i in range(256)], dtype=np.uint8)
    return cv2.LUT(gray, lut)


def _otsu_binary(gray: np.ndarray) -> np.ndarray:
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def _adaptive_threshold(gray: np.ndarray) -> np.ndarray:
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 8
    )


def _sharpen(gray: np.ndarray) -> np.ndarray:
    """Controlled unsharp mask — does NOT invent texture, just accentuates edges."""
    blurred = cv2.GaussianBlur(gray, (0, 0), 2.0)
    sharpened = cv2.addWeighted(gray, 1.5, blurred, -0.5, 0)
    return np.clip(sharpened, 0, 255).astype(np.uint8)


def _denoise(image: np.ndarray) -> np.ndarray:
    """Light non-local means denoising — reduces noise without blurring edges."""
    return cv2.fastNlMeansDenoisingColored(image, None, 6, 6, 7, 21)


def _build_variants(
    image       : np.ndarray,
    gray        : np.ndarray,
    is_dark     : bool,
    is_blurry   : bool,
    is_overexposed: bool,
) -> List[Tuple[str, np.ndarray]]:
    """
    Build 3–5 preprocessing variants for multi-OCR voting.

    Each variant is a (name, BGR_image) tuple.
    OCR runs on each; the highest-confidence result wins.
    """
    variants: List[Tuple[str, np.ndarray]] = []

    # 1. Standard: resize + CLAHE + Otsu binary
    g1 = _clahe_enhance(gray, clip=2.0)
    b1 = _otsu_binary(g1)
    r1 = _resize_to_height(_to_bgr(b1))
    variants.append(("standard_clahe_otsu", r1))

    # 2. Adaptive threshold (better for uneven lighting)
    g2 = _clahe_enhance(gray, clip=3.0)
    b2 = _adaptive_threshold(g2)
    r2 = _resize_to_height(_to_bgr(b2))
    variants.append(("adaptive_thresh", r2))

    # 3. Low-light / dark frames
    if is_dark:
        g3 = _gamma_correct(gray, gamma=0.45)
        g3 = _clahe_enhance(g3, clip=3.0)
        b3 = _otsu_binary(g3)
        r3 = _resize_to_height(_to_bgr(b3))
        variants.append(("gamma_clahe_otsu", r3))

    # 4. Blur: sharpen first, then enhance
    if is_blurry:
        g4 = _sharpen(gray)
        g4 = _clahe_enhance(g4, clip=2.5)
        b4 = _otsu_binary(g4)
        r4 = _resize_to_height(_to_bgr(b4))
        variants.append(("sharpen_clahe_otsu", r4))

    # 5. Overexposed: reduce brightness, then enhance
    if is_overexposed:
        g5 = _gamma_correct(gray, gamma=1.8)
        g5 = _clahe_enhance(g5, clip=2.0)
        b5 = _otsu_binary(g5)
        r5 = _resize_to_height(_to_bgr(b5))
        variants.append(("darken_clahe_otsu", r5))

    # 6. Colour original (resized) — EasyOCR sometimes reads colour better
    r6 = _resize_to_height(image)
    variants.append(("colour_resized", r6))

    return variants


def select_best_crop(
    crops_with_quality: List[Tuple[np.ndarray, QualityReport]],
) -> Optional[Tuple[np.ndarray, QualityReport]]:
    """
    Given multiple plate crops from different frames, return the one with the
    highest quality_score. Used by the multi-frame tracker.
    """
    if not crops_with_quality:
        return None
    return max(crops_with_quality, key=lambda x: x[1].quality_score)
