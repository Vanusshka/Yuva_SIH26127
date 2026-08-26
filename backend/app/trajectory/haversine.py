"""
Haversine distance and speed helpers.

No external dependencies – pure Python math.
"""

from __future__ import annotations
import math
from datetime import datetime


_EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Return the great-circle distance in kilometres between two GPS points.

    Parameters
    ----------
    lat1, lon1 : coordinates of point A (degrees)
    lat2, lon2 : coordinates of point B (degrees)
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return _EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def time_diff_minutes(t1: datetime, t2: datetime) -> float:
    """
    Return the signed time difference in minutes (t2 - t1).
    Positive means t2 is later than t1.
    """
    delta = (t2 - t1).total_seconds()
    return delta / 60.0


def average_speed_kmh(distance_km: float, time_minutes: float) -> float:
    """
    Return average speed in km/h.
    Returns 0.0 if time_minutes is zero or negative (prevents division by zero).
    """
    if time_minutes <= 0:
        return 0.0
    return distance_km / (time_minutes / 60.0)
