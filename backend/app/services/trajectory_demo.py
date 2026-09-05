"""
Trajectory Explorer — Synthetic Demo Dataset
=============================================
Self-contained demo data for demonstrating multi-camera vehicle trajectory
reconstruction in UrbanEye AI (SIH26127).

Source: urbaneye-synthetic-trajectory-demo.csv
All 10 vehicles, 6 cameras, Hyderabad — 2026-09-05 morning rush hour.

⚠ DEMO / SAMPLE DATA ONLY
These observations are NOT from real CCTV cameras.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Optional
from dataclasses import dataclass, field, asdict

# ── Camera metadata (shared across vehicles) ──────────────────────────────────
_CAMERAS = {
    "CAM-01": {"location_name": "Ameerpet Junction",   "area": "Central Hyderabad",    "road_name": "Ameerpet–Punjagutta Road",         "latitude": 17.4375, "longitude": 78.4483, "direction": "NORTH_BOUND"},
    "CAM-02": {"location_name": "Punjagutta",           "area": "Central Hyderabad",    "road_name": "Punjagutta–Banjara Hills Road",    "latitude": 17.4289, "longitude": 78.4521, "direction": "SOUTH_BOUND"},
    "CAM-03": {"location_name": "Banjara Hills",        "area": "South-West Hyderabad", "road_name": "Road No. 12, Banjara Hills",       "latitude": 17.4156, "longitude": 78.4488, "direction": "WEST_BOUND"},
    "CAM-04": {"location_name": "Jubilee Hills",        "area": "West Hyderabad",       "road_name": "Jubilee Hills Check Post Road",    "latitude": 17.4319, "longitude": 78.4071, "direction": "WEST_BOUND"},
    "CAM-05": {"location_name": "Madhapur",             "area": "IT Corridor",          "road_name": "Hitech City–Madhapur Road",        "latitude": 17.4483, "longitude": 78.3915, "direction": "NORTH_WEST_BOUND"},
    "CAM-06": {"location_name": "Gachibowli",           "area": "Financial District",   "road_name": "Gachibowli–Nallagandla Road",      "latitude": 17.4401, "longitude": 78.3489, "direction": "WEST_BOUND"},
}

def _obs(idx, cam_id, ts, conf):
    c = _CAMERAS[cam_id]
    return {
        "obs_id"       : idx,
        "camera_id"    : cam_id,
        "location_name": c["location_name"],
        "area"         : c["area"],
        "road_name"    : c["road_name"],
        "latitude"     : c["latitude"],
        "longitude"    : c["longitude"],
        "timestamp"    : f"2026-09-05T{ts}+05:30",
        "confidence"   : conf,
        "direction"    : c["direction"],
    }

# ── Demo dataset — 10 vehicles from CSV ───────────────────────────────────────
DEMO_VEHICLES = [
    {
        "vehicle_id" : "VEH-001",
        "plate_number": "TS09AB1234",
        "vehicle_type": "Car",
        "make_model" : "Sedan",
        "notes"      : "4-camera route: Ameerpet → Punjagutta → Banjara Hills → Jubilee Hills",
        "observations": [
            _obs(1, "CAM-01", "09:02:15", 0.96),
            _obs(2, "CAM-02", "09:07:42", 0.94),
            _obs(3, "CAM-03", "09:14:18", 0.97),
            _obs(4, "CAM-04", "09:21:31", 0.95),
        ],
    },
    {
        "vehicle_id" : "VEH-002",
        "plate_number": "TS08CD5678",
        "vehicle_type": "Car",
        "make_model" : "Hatchback",
        "notes"      : "3-camera route: Ameerpet → Punjagutta → Jubilee Hills",
        "observations": [
            _obs(1, "CAM-01", "09:04:21", 0.91),
            _obs(2, "CAM-02", "09:09:05", 0.93),
            _obs(3, "CAM-04", "09:21:44", 0.90),
        ],
    },
    {
        "vehicle_id" : "VEH-003",
        "plate_number": "AP09EF2468",
        "vehicle_type": "Car",
        "make_model" : "SUV",
        "notes"      : "3-camera route: Ameerpet → Banjara Hills → Madhapur (IT corridor)",
        "observations": [
            _obs(1, "CAM-01", "09:07:12", 0.92),
            _obs(2, "CAM-03", "09:14:36", 0.95),
            _obs(3, "CAM-05", "09:23:10", 0.94),
        ],
    },
    {
        "vehicle_id" : "VEH-004",
        "plate_number": "TS10GH1357",
        "vehicle_type": "Car",
        "make_model" : "Sedan",
        "notes"      : "3-camera route: Punjagutta → Banjara Hills → Madhapur",
        "observations": [
            _obs(1, "CAM-02", "09:11:08", 0.89),
            _obs(2, "CAM-03", "09:17:22", 0.93),
            _obs(3, "CAM-05", "09:28:41", 0.91),
        ],
    },
    {
        "vehicle_id" : "VEH-005",
        "plate_number": "KA05JK7890",
        "vehicle_type": "Car",
        "make_model" : "SUV",
        "notes"      : "3-camera route: Ameerpet → Jubilee Hills → Gachibowli (Financial District)",
        "observations": [
            _obs(1, "CAM-01", "09:15:30", 0.90),
            _obs(2, "CAM-04", "09:23:52", 0.94),
            _obs(3, "CAM-06", "09:34:16", 0.92),
        ],
    },
    {
        "vehicle_id" : "VEH-006",
        "plate_number": "TS11LM4821",
        "vehicle_type": "Motorcycle",
        "make_model" : "Bike",
        "notes"      : "3-camera route: Banjara Hills → Madhapur → Gachibowli",
        "observations": [
            _obs(1, "CAM-03", "09:20:05", 0.96),
            _obs(2, "CAM-05", "09:29:27", 0.95),
            _obs(3, "CAM-06", "09:39:02", 0.93),
        ],
    },
    {
        "vehicle_id" : "VEH-007",
        "plate_number": "TS12NP6314",
        "vehicle_type": "Car",
        "make_model" : "Hatchback",
        "notes"      : "3-camera route: Punjagutta → Jubilee Hills → Gachibowli",
        "observations": [
            _obs(1, "CAM-02", "09:25:44", 0.88),
            _obs(2, "CAM-04", "09:32:18", 0.91),
            _obs(3, "CAM-06", "09:43:55", 0.90),
        ],
    },
    {
        "vehicle_id" : "VEH-008",
        "plate_number": "AP10QR9753",
        "vehicle_type": "Car",
        "make_model" : "Sedan",
        "notes"      : "3-camera route: Ameerpet → Banjara Hills → Madhapur",
        "observations": [
            _obs(1, "CAM-01", "09:29:11", 0.93),
            _obs(2, "CAM-03", "09:36:40", 0.92),
            _obs(3, "CAM-05", "09:45:12", 0.94),
        ],
    },
    {
        "vehicle_id" : "VEH-009",
        "plate_number": "TS13ST2046",
        "vehicle_type": "Car",
        "make_model" : "Sedan",
        "notes"      : "3-camera route: Banjara Hills → Jubilee Hills → Gachibowli",
        "observations": [
            _obs(1, "CAM-03", "09:33:27", 0.91),
            _obs(2, "CAM-04", "09:40:03", 0.89),
            _obs(3, "CAM-06", "09:51:29", 0.92),
        ],
    },
    {
        "vehicle_id" : "VEH-010",
        "plate_number": "TS14UV8162",
        "vehicle_type": "Car",
        "make_model" : "Sedan",
        "notes"      : "3-camera route: Ameerpet → Punjagutta → Madhapur",
        "observations": [
            _obs(1, "CAM-01", "09:37:16", 0.95),
            _obs(2, "CAM-02", "09:42:33", 0.93),
            _obs(3, "CAM-05", "09:52:07", 0.96),
        ],
    },
]


# ── helpers ───────────────────────────────────────────────────────────────────

def get_all_demo_vehicles() -> list:
    """Return summary list of all demo vehicles."""
    result = []
    for v in DEMO_VEHICLES:
        obs = v["observations"]
        result.append({
            "vehicle_id"   : v["vehicle_id"],
            "plate_number" : v["plate_number"],
            "vehicle_type" : v["vehicle_type"],
            "make_model"   : v["make_model"],
            "total_obs"    : len(obs),
            "first_seen"   : obs[0]["timestamp"] if obs else None,
            "last_seen"    : obs[-1]["timestamp"] if obs else None,
            "cameras"      : [o["camera_id"] for o in obs],
            "data_source"  : "DEMO_DATASET",
            "notes"        : v["notes"],
        })
    return result


def get_demo_vehicle(vehicle_id: str) -> dict | None:
    """Return full trajectory for one demo vehicle by vehicle_id or plate_number."""
    key = vehicle_id.strip().upper()
    for v in DEMO_VEHICLES:
        if v["vehicle_id"].upper() == key or v["plate_number"].upper() == key:
            return _build_trajectory(v)
    return None


def _haversine(lat1, lon1, lat2, lon2) -> float:
    """Return distance in km between two lat/lon points."""
    import math
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(d_lon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def _build_trajectory(v: dict) -> dict:
    obs = v["observations"]

    # Compute hop metrics between consecutive observations
    hops = []
    total_dist = 0.0
    for i in range(1, len(obs)):
        prev = obs[i-1]
        curr = obs[i]
        dist = _haversine(prev["latitude"], prev["longitude"],
                          curr["latitude"], curr["longitude"])
        t1 = datetime.fromisoformat(prev["timestamp"])
        t2 = datetime.fromisoformat(curr["timestamp"])
        mins = (t2 - t1).total_seconds() / 60.0
        speed = (dist / mins * 60) if mins > 0 else 0.0
        total_dist += dist
        hops.append({
            "from_camera"   : prev["camera_id"],
            "to_camera"     : curr["camera_id"],
            "from_location" : prev["location_name"],
            "to_location"   : curr["location_name"],
            "distance_km"   : round(dist, 3),
            "duration_min"  : round(mins, 1),
            "speed_kmh"     : round(speed, 1),
        })

    # Total duration
    t_first = datetime.fromisoformat(obs[0]["timestamp"])
    t_last  = datetime.fromisoformat(obs[-1]["timestamp"])
    total_min = (t_last - t_first).total_seconds() / 60.0

    return {
        "vehicle_id"    : v["vehicle_id"],
        "plate_number"  : v["plate_number"],
        "vehicle_type"  : v["vehicle_type"],
        "make_model"    : v["make_model"],
        "data_source"   : "DEMO_DATASET",
        "disclaimer"    : (
            "SYNTHETIC DEMO DATA — Source: urbaneye-synthetic-trajectory-demo.csv. "
            "These observations simulate a real multi-camera ANPR network across Hyderabad "
            "on 2026-09-05 morning rush hour. Not from real CCTV cameras."
        ),
        "observations"  : obs,
        "hops"          : hops,
        "summary"       : {
            "total_observations" : len(obs),
            "total_cameras"      : len(set(o["camera_id"] for o in obs)),
            "total_distance_km"  : round(total_dist, 3),
            "total_duration_min" : round(total_min, 1),
            "first_seen"         : obs[0]["timestamp"],
            "last_seen"          : obs[-1]["timestamp"],
            "first_location"     : obs[0]["location_name"],
            "last_location"      : obs[-1]["location_name"],
            "first_area"         : obs[0]["area"],
            "last_area"          : obs[-1]["area"],
        },
    }
