"""
Metadata Loader – Phase 7

Loads and caches camera metadata and the demo blacklist from
data/metadata/*.json.

NOTE: All data loaded here is DEMO / SIMULATED unless the files have
been replaced with real data by an authorised operator.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── paths ─────────────────────────────────────────────────────────────────────
_METADATA_DIR  = Path(__file__).resolve().parents[2] / "data" / "metadata"
_CAMERAS_FILE  = _METADATA_DIR / "cameras.json"
_BLACKLIST_FILE= _METADATA_DIR / "blacklist.json"


# ── camera metadata ───────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def load_cameras() -> List[Dict]:
    """
    Returns a list of camera dicts from cameras.json.
    Cached after first read – restart the process to pick up file changes.
    """
    if not _CAMERAS_FILE.exists():
        logger.warning("[MetadataLoader] cameras.json not found at %s", _CAMERAS_FILE)
        return []
    try:
        with _CAMERAS_FILE.open(encoding="utf-8") as fh:
            data = json.load(fh)
        cameras = data.get("cameras", [])
        logger.info("[MetadataLoader] Loaded %d cameras from cameras.json", len(cameras))
        return cameras
    except Exception as exc:
        logger.error("[MetadataLoader] Failed to load cameras.json: %s", exc)
        return []


@lru_cache(maxsize=1)
def _camera_map() -> Dict[str, Dict]:
    """Returns a dict keyed by camera_id for O(1) lookup."""
    return {c["camera_id"]: c for c in load_cameras()}


def get_camera_meta(camera_id: str) -> Optional[Dict]:
    """
    Return camera metadata dict for the given camera_id, or None if not found.

    Example return value:
    {
      "camera_id": "CAM_001",
      "camera_name": "Ameerpet Junction Camera",
      "latitude": 17.4375,
      "longitude": 78.4483,
      "location": "Ameerpet Junction",
      "road_name": "Ameerpet–Punjagutta Road",
      "direction": "NORTH_BOUND",
      "zone": "Central Hyderabad",
      "status": "ACTIVE"
    }
    """
    return _camera_map().get(camera_id.upper())


def get_camera_gps(camera_id: str) -> tuple[float, float]:
    """
    Return (latitude, longitude) for a camera_id.
    Falls back to (0.0, 0.0) if the camera is not found.
    """
    meta = get_camera_meta(camera_id)
    if meta:
        return meta["latitude"], meta["longitude"]
    logger.warning("[MetadataLoader] GPS not found for camera_id=%s – defaulting to (0,0)", camera_id)
    return 0.0, 0.0


# ── blacklist ─────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def load_blacklist() -> List[Dict]:
    """
    Returns the list of blacklist entries from blacklist.json.
    Cached after first read.

    WARNING: This is DEMO DATA only. Do not use in production law-enforcement contexts.
    """
    if not _BLACKLIST_FILE.exists():
        logger.warning("[MetadataLoader] blacklist.json not found at %s", _BLACKLIST_FILE)
        return []
    try:
        with _BLACKLIST_FILE.open(encoding="utf-8") as fh:
            data = json.load(fh)
        entries = data.get("entries", [])
        logger.info("[MetadataLoader] Loaded %d blacklist entries (DEMO DATA)", len(entries))
        return entries
    except Exception as exc:
        logger.error("[MetadataLoader] Failed to load blacklist.json: %s", exc)
        return []


@lru_cache(maxsize=1)
def _blacklist_map() -> Dict[str, Dict]:
    """Returns a dict keyed by normalised plate_number for O(1) lookup."""
    return {e["plate_number"].upper(): e for e in load_blacklist()}


def is_blacklisted(plate_number: str) -> Optional[Dict]:
    """
    Return the blacklist entry for a plate number, or None if not blacklisted.

    Example return value:
    {
      "plate_number": "TS08AB1234",
      "reason": "Demo Blacklisted Vehicle – Stolen (SIMULATED)",
      "category": "STOLEN",
      "added_date": "2026-08-01",
      "priority": "HIGH"
    }
    """
    if not plate_number:
        return None
    return _blacklist_map().get(plate_number.strip().upper())


def reload_metadata() -> None:
    """
    Clear all LRU caches so updated JSON files are re-read on the next call.
    Call this endpoint if you update cameras.json or blacklist.json at runtime.
    """
    load_cameras.cache_clear()
    _camera_map.cache_clear()
    load_blacklist.cache_clear()
    _blacklist_map.cache_clear()
    logger.info("[MetadataLoader] Metadata caches cleared – will reload on next access.")
