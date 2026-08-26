"""
Anomaly / movement-status classifier – Phase 4.

Rules applied to each consecutive camera pair in a trajectory:

  IMPOSSIBLE   speed > SPEED_IMPOSSIBLE_KMPH
               OR time difference is negative (timestamp went backwards)
  SUSPICIOUS   speed > SPEED_SUSPICIOUS_KMPH
               OR same camera seen twice within DUPLICATE_WINDOW_SECS
               OR distance between two *different* cameras < MIN_INTER_CAMERA_KM
                  (suggests GPS/metadata error)
  FAST         speed > SPEED_FAST_KMPH
  NORMAL       everything else

Overall trajectory status = worst status across all hops.
"""

from __future__ import annotations
from enum import Enum

from app.config import (
    SPEED_FAST_KMPH,
    SPEED_SUSPICIOUS_KMPH,
    SPEED_IMPOSSIBLE_KMPH,
    DUPLICATE_WINDOW_SECS,
    MIN_INTER_CAMERA_KM,
)


class MovementStatus(str, Enum):
    NORMAL     = "NORMAL"
    FAST       = "FAST"
    SUSPICIOUS = "SUSPICIOUS"
    IMPOSSIBLE = "IMPOSSIBLE"


# Severity order (higher index = worse)
_SEVERITY = [
    MovementStatus.NORMAL,
    MovementStatus.FAST,
    MovementStatus.SUSPICIOUS,
    MovementStatus.IMPOSSIBLE,
]


def classify_hop(
    distance_km     : float,
    time_minutes    : float,
    speed_kmh       : float,
    same_camera     : bool,
) -> MovementStatus:
    """
    Classify a single camera-to-camera hop.

    Parameters
    ----------
    distance_km  : Haversine distance between the two cameras
    time_minutes : elapsed time between detections (can be negative)
    speed_kmh    : calculated average speed
    same_camera  : True when consecutive detections are on the same camera
    """
    # Negative time is always impossible
    if time_minutes < 0:
        return MovementStatus.IMPOSSIBLE

    # Physically impossible speed
    if speed_kmh > SPEED_IMPOSSIBLE_KMPH:
        return MovementStatus.IMPOSSIBLE

    # Same camera within the duplicate window
    if same_camera and abs(time_minutes * 60) <= DUPLICATE_WINDOW_SECS:
        return MovementStatus.SUSPICIOUS

    # Different cameras but suspiciously close together (likely metadata error)
    if not same_camera and distance_km < MIN_INTER_CAMERA_KM:
        return MovementStatus.SUSPICIOUS

    if speed_kmh > SPEED_SUSPICIOUS_KMPH:
        return MovementStatus.SUSPICIOUS

    if speed_kmh > SPEED_FAST_KMPH:
        return MovementStatus.FAST

    return MovementStatus.NORMAL


def worst_status(statuses: list[MovementStatus]) -> MovementStatus:
    """Return the most severe status from a list."""
    if not statuses:
        return MovementStatus.NORMAL
    return max(statuses, key=lambda s: _SEVERITY.index(s))
