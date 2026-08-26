"""
Fuzzy plate matching and camera travel-time feasibility — Changes 7+8.

Change 7 — Fuzzy matching:
  The existing trajectory engine uses exact plate string comparison only.
  This module adds a controlled Levenshtein-distance check so that
  near-identical OCR variations (e.g. TS09AB1234 vs TS09A81234) can be
  considered possible matches for trajectory linking.

  Conservative rules:
    - Edit distance <= TRAJECTORY_FUZZY_MAX_EDIT_DISTANCE (default 1)
    - Fuzzy match ALONE does not confirm a trajectory
    - Fuzzy candidates are flagged as POSSIBLE_MATCH, not CONFIRMED

Change 8 — Travel-time feasibility:
  Before accepting a hop between two cameras, verify that the observed
  travel time is physically plausible given the geographic distance.

  Reject if:
    time_minutes < distance_km * TRAJECTORY_MIN_MINUTES_PER_KM

  Example: 5 km distance, 0.4 min/km minimum → 2 minutes required.
  If the detection timestamps only differ by 1 minute, the hop is IMPOSSIBLE.

All thresholds are in config.py and documented there.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from app.config import (
    TRAJECTORY_FUZZY_MAX_EDIT_DISTANCE,
    TRAJECTORY_MIN_MINUTES_PER_KM,
)

logger = logging.getLogger(__name__)


# ── Levenshtein distance (pure Python, no external library) ───────────────────

def levenshtein(s1: str, s2: str) -> int:
    """
    Compute the Levenshtein edit distance between two strings.

    Pure Python — no external library required.
    Uses the standard dynamic-programming O(n*m) algorithm.
    """
    if s1 == s2:
        return 0
    if not s1:
        return len(s2)
    if not s2:
        return len(s1)

    n, m = len(s1), len(s2)
    # Use a 1D rolling array to save memory
    prev = list(range(m + 1))
    for i, c1 in enumerate(s1, 1):
        curr = [i] + [0] * m
        for j, c2 in enumerate(s2, 1):
            cost = 0 if c1 == c2 else 1
            curr[j] = min(
                curr[j - 1] + 1,       # insert
                prev[j] + 1,           # delete
                prev[j - 1] + cost,    # replace
            )
        prev = curr
    return prev[m]


# ── Fuzzy plate comparison ─────────────────────────────────────────────────────

def plates_possibly_match(plate_a: str, plate_b: str) -> Tuple[bool, int]:
    """
    Return (is_possible_match, edit_distance).

    Rules:
      - Exact match always returns (True, 0)
      - edit_distance <= TRAJECTORY_FUZZY_MAX_EDIT_DISTANCE → (True, dist)
      - Otherwise → (False, dist)

    This does NOT confirm a trajectory — it only flags the pair for
    further validation (travel-time, camera adjacency, confidence tier).
    """
    a = plate_a.strip().upper()
    b = plate_b.strip().upper()
    dist = levenshtein(a, b)
    max_dist = TRAJECTORY_FUZZY_MAX_EDIT_DISTANCE
    return (dist <= max_dist, dist)


# ── Travel-time feasibility check (Change 8) ─────────────────────────────────

def is_travel_time_feasible(
    distance_km    : float,
    time_minutes   : float,
) -> bool:
    """
    Return True if a vehicle COULD have travelled `distance_km` in `time_minutes`.

    Uses TRAJECTORY_MIN_MINUTES_PER_KM from config.py as the hard lower bound.
    Default: 0.4 min/km (equivalent to ~150 km/h, which is beyond any city limit
    but leaves a safety margin for highway footage).

    Returns False (infeasible) when:
      time_minutes < distance_km * TRAJECTORY_MIN_MINUTES_PER_KM

    A negative time_minutes is always infeasible.
    Zero distance (same camera) is always feasible.
    """
    if time_minutes < 0:
        return False
    if distance_km <= 0:
        return True   # same camera / zero distance — feasible
    min_time = distance_km * TRAJECTORY_MIN_MINUTES_PER_KM
    return time_minutes >= min_time


def min_feasible_time_minutes(distance_km: float) -> float:
    """Return the minimum travel time (minutes) for a given distance."""
    return distance_km * TRAJECTORY_MIN_MINUTES_PER_KM


# ── Build a fuzzy-matched detection list for trajectory engine ────────────────

def find_fuzzy_plate_candidates(
    target_plate : str,
    candidate_plates: List[str],
) -> List[Tuple[str, int]]:
    """
    Given a target plate and a list of candidate plates from the DB,
    return all candidates that are within the fuzzy edit distance.

    Returns list of (plate, edit_distance) sorted by edit_distance ASC.
    """
    results: List[Tuple[str, int]] = []
    for cand in candidate_plates:
        is_match, dist = plates_possibly_match(target_plate, cand)
        if is_match:
            results.append((cand, dist))
    results.sort(key=lambda x: x[1])
    return results
