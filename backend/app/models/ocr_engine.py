"""
OCR Engine — Phase 9 Improvement
==================================

Key changes from Phase 7/8:
  1. Multi-variant OCR: runs each preprocessing variant and picks the best result
  2. read_plate_multi() returns ALL variant results for caller to inspect
  3. No fabrication — empty / too-short results returned honestly
  4. Minimum character count filter: fragments < 3 chars are NOT treated as plates
  5. Both letters AND numbers are always recognised (no digit-only restriction)
  6. Text cleaning: only remove chars that are genuinely noise, never guess missing

ABSOLUTE RULE: If OCR produces no text, or text shorter than MIN_CHARS,
return plate_number="" with ocr_confidence=0.0.
NEVER autocomplete, hallucinate, or pad a short string to look like a full plate.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import cv2
import numpy as np

from app.config import OCR_ENGINE, OCR_LANGUAGES

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# A plate read shorter than this is treated as a fragment, not a plate.
# Indian plates have 9–10 chars; we accept >= 5 as "partial", < 3 as noise.
MIN_CHARS_NOISE   = 3    # fewer than this → noise / unreadable
MIN_CHARS_PARTIAL = 5    # 3–4 chars → fragment; ≥5 → possible partial plate

# Confidence below which we label a read as "low_confidence"
OCR_LOW_CONF = 0.50


@dataclass
class OCRResult:
    """Result from a single OCR run."""

    plate_number  : str    # cleaned, uppercased; empty if unreadable
    ocr_confidence: float  # 0.0–1.0
    raw_text      : str    # raw string from OCR engine (before cleaning)
    variant_name  : str = "unknown"   # which preprocessing was used
    char_count    : int = 0           # number of alphanumeric chars
    is_fragment   : bool = False      # True if < MIN_CHARS_PARTIAL
    is_noise      : bool = False      # True if < MIN_CHARS_NOISE


@dataclass
class MultiOCRResult:
    """
    Aggregated result from running OCR on multiple preprocessing variants.
    The best single result is exposed at the top level for backward compatibility.
    """

    plate_number  : str             # best cleaned plate text (empty if unreadable)
    ocr_confidence: float
    raw_text      : str
    variant_name  : str
    char_count    : int
    is_fragment   : bool
    is_noise      : bool
    all_results   : List[OCRResult] = field(default_factory=list)


# ── Text cleaning (real cleaning only — no fabrication) ───────────────────────

_NOISE_CHARS_RE = re.compile(r"[^A-Z0-9]")

def _clean(raw: str) -> str:
    """
    Uppercase + strip everything that is NOT a letter or digit.
    Does NOT guess missing characters.
    Does NOT pad short strings.
    """
    return _NOISE_CHARS_RE.sub("", raw.upper()).strip()


def _score_result(r: OCRResult) -> float:
    """
    Composite score to pick the best variant.
    Longer, higher-confidence results with more chars score better.
    Short fragments score low regardless of confidence.
    """
    if r.is_noise:
        return 0.0
    length_bonus = min(1.0, r.char_count / 10.0)   # 10 chars = full Indian plate
    conf_weight  = r.ocr_confidence
    return 0.6 * conf_weight + 0.4 * length_bonus


# ── EasyOCR singleton ─────────────────────────────────────────────────────────

class _EasyOCREngine:
    _reader = None

    @classmethod
    def _get_reader(cls):
        if cls._reader is None:
            import easyocr
            logger.info("[OCR] Initialising EasyOCR reader...")
            cls._reader = easyocr.Reader(
                OCR_LANGUAGES,
                gpu=False,
                verbose=False,
                # Recognise full alphanumeric set — both letters AND digits
                # (EasyOCR default already does this with 'en')
            )
            logger.info("[OCR] EasyOCR ready.")
        return cls._reader

    @classmethod
    def read_image(cls, image: np.ndarray) -> Tuple[str, float]:
        """
        Run EasyOCR on `image`.
        Returns (raw_text, confidence).
        Returns ("", 0.0) on failure — never raises.
        """
        try:
            reader  = cls._get_reader()
            results = reader.readtext(image, detail=1, paragraph=False)
            if not results:
                return "", 0.0
            # Concatenate all text segments (handles multi-segment plates)
            # Weight confidence by text length
            total_len  = sum(len(r[1]) for r in results)
            weighted_conf = (
                sum(r[2] * len(r[1]) for r in results) / max(1, total_len)
            )
            combined_text = " ".join(r[1] for r in results)
            return combined_text, float(weighted_conf)
        except Exception as exc:
            logger.warning("[OCR] EasyOCR read failed: %s", exc)
            return "", 0.0


# ── Core OCR function ─────────────────────────────────────────────────────────

def _run_ocr(image: np.ndarray, variant_name: str = "unknown") -> OCRResult:
    """
    Run OCR on a single preprocessed image.
    Returns an OCRResult with honest metadata — never fabricates.
    """
    if image is None or image.size == 0:
        return OCRResult(
            plate_number="", ocr_confidence=0.0, raw_text="",
            variant_name=variant_name, char_count=0,
            is_fragment=False, is_noise=True,
        )

    if OCR_ENGINE == "easyocr":
        raw_text, conf = _EasyOCREngine.read_image(image)
    else:
        raw_text, conf = _run_tesseract(image)

    cleaned    = _clean(raw_text)
    char_count = len(cleaned)
    is_noise   = char_count < MIN_CHARS_NOISE
    is_fragment= MIN_CHARS_NOISE <= char_count < MIN_CHARS_PARTIAL

    # If too short, zero out confidence so callers don't treat it as a plate
    if is_noise:
        cleaned = ""
        conf    = 0.0

    return OCRResult(
        plate_number   = cleaned,
        ocr_confidence = round(conf, 4),
        raw_text       = raw_text,
        variant_name   = variant_name,
        char_count     = char_count,
        is_fragment    = is_fragment,
        is_noise       = is_noise,
    )


def _run_tesseract(image: np.ndarray) -> Tuple[str, float]:
    try:
        import pytesseract
        cfg = (
            r"--oem 3 --psm 7 "
            r"-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        )
        raw  = pytesseract.image_to_string(image, config=cfg).strip()
        data = pytesseract.image_to_data(
            image, config=cfg, output_type=pytesseract.Output.DICT
        )
        confs = [c for c in data["conf"] if c != -1]
        conf  = float(sum(confs) / len(confs) / 100) if confs else 0.0
        return raw, conf
    except Exception as exc:
        logger.warning("[OCR] Tesseract failed: %s", exc)
        return "", 0.0


# ── Public API ────────────────────────────────────────────────────────────────

class OCREngine:
    """
    OCR facade for license plate text extraction.

    read_plate()       — backward-compatible single-result API
    read_plate_multi() — multi-variant API returning all evidence
    """

    def read_plate(self, image: np.ndarray) -> OCRResult:
        """
        Single-variant OCR using standard CLAHE + Otsu preprocessing.
        Preserved for backward compatibility with existing callers.
        """
        if image is None or image.size == 0:
            return OCRResult(plate_number="", ocr_confidence=0.0, raw_text="",
                             variant_name="empty", char_count=0, is_noise=True)

        from app.models.image_quality import analyse
        report = analyse(image, save_variants=True)

        if report.is_too_small or not report.variants:
            # Too small to read — report honestly
            return OCRResult(plate_number="", ocr_confidence=0.0, raw_text="",
                             variant_name="too_small", char_count=0,
                             is_fragment=False, is_noise=True)

        # Run on all variants, pick best
        multi = self.read_plate_multi(image)
        return OCRResult(
            plate_number   = multi.plate_number,
            ocr_confidence = multi.ocr_confidence,
            raw_text       = multi.raw_text,
            variant_name   = multi.variant_name,
            char_count     = multi.char_count,
            is_fragment    = multi.is_fragment,
            is_noise       = multi.is_noise,
        )

    def read_plate_multi(self, image: np.ndarray) -> MultiOCRResult:
        """
        Multi-variant OCR: run every preprocessing variant and return the best.

        The 'best' is chosen by _score_result() which weights:
          - OCR confidence (60 %)
          - Character count (40 %) — longer = more likely complete plate

        NEVER fabricates characters. Short results (< MIN_CHARS_NOISE) are
        discarded. Results are returned as-is from the OCR engine.
        """
        if image is None or image.size == 0:
            return MultiOCRResult(plate_number="", ocr_confidence=0.0, raw_text="",
                                  variant_name="empty", char_count=0,
                                  is_fragment=False, is_noise=True)

        from app.models.image_quality import analyse
        report = analyse(image, save_variants=True)

        if report.is_too_small:
            return MultiOCRResult(plate_number="", ocr_confidence=0.0, raw_text="",
                                  variant_name="too_small", char_count=0,
                                  is_fragment=False, is_noise=True)

        all_results: List[OCRResult] = []
        for vname, vimg in report.variants:
            result = _run_ocr(vimg, variant_name=vname)
            all_results.append(result)
            logger.debug("[OCR] Variant '%s': '%s' conf=%.3f chars=%d",
                         vname, result.plate_number, result.ocr_confidence,
                         result.char_count)

        # Filter out noise-level results
        useful = [r for r in all_results if not r.is_noise]

        if not useful:
            return MultiOCRResult(
                plate_number="", ocr_confidence=0.0, raw_text="",
                variant_name="all_noise", char_count=0,
                is_fragment=False, is_noise=True,
                all_results=all_results,
            )

        # Pick highest-scoring result
        best = max(useful, key=_score_result)

        return MultiOCRResult(
            plate_number   = best.plate_number,
            ocr_confidence = best.ocr_confidence,
            raw_text       = best.raw_text,
            variant_name   = best.variant_name,
            char_count     = best.char_count,
            is_fragment    = best.is_fragment,
            is_noise       = best.is_noise,
            all_results    = all_results,
        )
