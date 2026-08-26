"""
Plate Result Status System — Phase 9
======================================

Classifies each plate read into:
  VERIFIED       — complete, high-confidence, evidence-supported
  PARTIAL        — readable but incomplete or moderate confidence
  LOW_CONFIDENCE — OCR ran but confidence below threshold
  UNREADABLE     — crop too small, blurry, or OCR produced nothing

Multi-frame evidence consensus:
  For each tracked vehicle, observations from multiple frames are
  aggregated. The final plate_number is ONLY set when it is genuinely
  supported by the evidence — never fabricated.

ABSOLUTE RULE: Characters MUST come from real OCR observations.
No autocomplete. No pattern-filling. No guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class PlateStatus(str, Enum):
    VERIFIED       = "verified"        # complete, high-confidence
    PARTIAL        = "partial"         # readable but incomplete/moderate conf
    LOW_CONFIDENCE = "low_confidence"  # OCR ran, confidence below threshold
    UNREADABLE     = "unreadable"      # crop failed / nothing readable


# ── Thresholds ────────────────────────────────────────────────────────────────

# Minimum OCR confidence to qualify as VERIFIED
VERIFIED_CONF_THRESH    = 0.70
# Minimum OCR confidence to qualify as PARTIAL (not LOW_CONFIDENCE)
PARTIAL_CONF_THRESH     = 0.40
# Minimum character count to qualify as VERIFIED
VERIFIED_MIN_CHARS      = 5
# Minimum character count to qualify as PARTIAL
PARTIAL_MIN_CHARS       = 3
# Indian plate full-length patterns (9–10 chars)
_FULL_PLATE_MIN_CHARS   = 8

# Multi-frame consensus: minimum observations needed to trust a result
MIN_OBSERVATIONS_TO_VERIFY = 1   # even 1 strong read can verify

# ── Plate patterns ────────────────────────────────────────────────────────────
_INDIAN_PLATE_RE = re.compile(
    r"^[A-Z]{2}\d{1,2}[A-Z]{1,3}\d{1,4}$"
)


def _matches_plate_pattern(text: str) -> bool:
    """True if text looks like a complete Indian plate."""
    return bool(_INDIAN_PLATE_RE.match(text.strip().upper()))


# ── Single-observation result ─────────────────────────────────────────────────

@dataclass
class PlateObservation:
    """One plate read from one frame."""

    frame_number       : int
    raw_ocr_text       : str
    plate_text         : str          # cleaned
    ocr_confidence     : float
    plate_conf         : float        # detector confidence
    quality_score      : float
    char_count         : int
    variant_name       : str
    is_fragment        : bool
    preprocessing      : str


def classify_observation(obs: PlateObservation) -> PlateStatus:
    """Classify a single observation."""
    if not obs.plate_text or obs.char_count < PARTIAL_MIN_CHARS:
        return PlateStatus.UNREADABLE
    if obs.ocr_confidence < PARTIAL_CONF_THRESH:
        return PlateStatus.LOW_CONFIDENCE
    if obs.char_count < VERIFIED_MIN_CHARS:
        return PlateStatus.PARTIAL
    if obs.ocr_confidence >= VERIFIED_CONF_THRESH and obs.char_count >= VERIFIED_MIN_CHARS:
        return PlateStatus.VERIFIED
    return PlateStatus.PARTIAL


# ── Multi-frame evidence aggregation ─────────────────────────────────────────

@dataclass
class PlateEvidence:
    """
    Accumulated evidence for one tracked vehicle.
    Collects observations across frames; consensus() produces the final result.
    """

    track_id    : str
    observations: List[PlateObservation] = field(default_factory=list)

    def add(self, obs: PlateObservation) -> None:
        self.observations.append(obs)

    def consensus(self) -> "ConsensuResult":
        """
        Produce the evidence-based final plate result.

        Selection priority:
          1. Complete observation (≥ FULL_PLATE_MIN_CHARS, conf ≥ VERIFIED_CONF_THRESH)
             — longest first, then highest confidence
          2. Most-repeated text with ≥ PARTIAL_MIN_CHARS
          3. Longest single observation with ≥ PARTIAL_MIN_CHARS
          4. Any non-empty observation
          5. UNREADABLE

        Characters are NEVER invented, padded, or pattern-completed.
        """
        if not self.observations:
            return ConsensuResult(
                track_id=self.track_id,
                plate_number=None,
                partial_text=None,
                status=PlateStatus.UNREADABLE,
                ocr_confidence=0.0,
                plate_confidence=0.0,
                quality_score=0.0,
                sightings=0,
                supporting_frames=[],
                preprocessing_method="none",
            )

        # ── Filter useful observations ────────────────────────────────────────
        non_empty = [o for o in self.observations if o.plate_text and o.char_count >= PARTIAL_MIN_CHARS]

        if not non_empty:
            return ConsensuResult(
                track_id=self.track_id,
                plate_number=None,
                partial_text=None,
                status=PlateStatus.UNREADABLE,
                ocr_confidence=0.0,
                plate_confidence=max((o.plate_conf for o in self.observations), default=0.0),
                quality_score=max((o.quality_score for o in self.observations), default=0.0),
                sightings=len(self.observations),
                supporting_frames=[o.frame_number for o in self.observations],
                preprocessing_method="n/a",
            )

        # ── Priority 1: complete high-confidence read ─────────────────────────
        complete = [
            o for o in non_empty
            if o.char_count >= _FULL_PLATE_MIN_CHARS
            and o.ocr_confidence >= VERIFIED_CONF_THRESH
        ]
        if complete:
            # prefer longest, then highest confidence
            best = max(complete, key=lambda o: (o.char_count, o.ocr_confidence))
            return _build_result(self.track_id, best, non_empty, PlateStatus.VERIFIED)

        # ── Priority 2: most-repeated text ───────────────────────────────────
        freq: Dict[str, List[PlateObservation]] = {}
        for o in non_empty:
            freq.setdefault(o.plate_text, []).append(o)

        # Find text seen in multiple frames
        repeated = {t: obs for t, obs in freq.items() if len(obs) >= 2}
        if repeated:
            # Pick the repeated text with the highest total char-count × avg conf
            def _rep_score(t: str) -> float:
                obs_list = repeated[t]
                avg_conf = sum(o.ocr_confidence for o in obs_list) / len(obs_list)
                return len(t) * avg_conf
            best_text = max(repeated, key=_rep_score)
            best_obs  = max(repeated[best_text], key=lambda o: o.ocr_confidence)
            status    = (
                PlateStatus.VERIFIED
                if best_obs.char_count >= VERIFIED_MIN_CHARS and best_obs.ocr_confidence >= VERIFIED_CONF_THRESH
                else PlateStatus.PARTIAL
            )
            return _build_result(self.track_id, best_obs, non_empty, status)

        # ── Priority 3: longest single observation ────────────────────────────
        best = max(non_empty, key=lambda o: (o.char_count, o.ocr_confidence))
        status = classify_observation(best)
        return _build_result(self.track_id, best, non_empty, status)


def _build_result(
    track_id   : str,
    best       : PlateObservation,
    all_obs    : List[PlateObservation],
    status     : PlateStatus,
) -> "ConsensuResult":
    avg_conf  = sum(o.ocr_confidence for o in all_obs) / len(all_obs)
    avg_pconf = sum(o.plate_conf     for o in all_obs) / len(all_obs)
    avg_qual  = sum(o.quality_score  for o in all_obs) / len(all_obs)

    return ConsensuResult(
        track_id           = track_id,
        plate_number       = best.plate_text if status == PlateStatus.VERIFIED else None,
        partial_text       = best.plate_text if status != PlateStatus.VERIFIED else None,
        status             = status,
        ocr_confidence     = round(best.ocr_confidence, 4),
        plate_confidence   = round(avg_pconf, 4),
        quality_score      = round(avg_qual, 4),
        sightings          = len(all_obs),
        supporting_frames  = sorted({o.frame_number for o in all_obs}),
        preprocessing_method = best.preprocessing,
    )


@dataclass
class ConsensuResult:
    """Final evidence-based result for one tracked vehicle."""

    track_id           : str
    plate_number       : Optional[str]   # set ONLY when status == VERIFIED
    partial_text       : Optional[str]   # set when status is PARTIAL / LOW_CONFIDENCE
    status             : PlateStatus
    ocr_confidence     : float
    plate_confidence   : float
    quality_score      : float
    sightings          : int
    supporting_frames  : List[int]
    preprocessing_method: str

    @property
    def display_text(self) -> Optional[str]:
        """What to show the user — plate_number if VERIFIED, else partial_text."""
        return self.plate_number or self.partial_text

    def to_dict(self) -> dict:
        return {
            "track_id"            : self.track_id,
            "plate_number"        : self.plate_number,
            "partial_text"        : self.partial_text,
            "plate_status"        : self.status.value,
            "ocr_confidence"      : self.ocr_confidence,
            "plate_confidence"    : self.plate_confidence,
            "quality_score"       : self.quality_score,
            "sightings"           : self.sightings,
            "supporting_frames"   : self.supporting_frames,
            "preprocessing_method": self.preprocessing_method,
        }
