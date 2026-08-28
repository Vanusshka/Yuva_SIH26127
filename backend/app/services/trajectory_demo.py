"""
Trajectory Explorer — Built-in Demo Dataset
=============================================
Self-contained demo data for demonstrating multi-camera vehicle trajectory
reconstruction in UrbanEye AI (SIH26127).

⚠ DEMO / SAMPLE DATA ONLY
These observations are NOT from real CCTV cameras.
They are constructed to demonstrate the Trajectory Explorer feature.

All coordinates are real Hyderabad locations matching the existing camera
network in cameras.json.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Optional
from dataclasses import dataclass, field, asdict

# ── Demo dataset ──────────────────────────────────────────────────────────────

DEMO_VEHICLES = [
    {
        "vehicle_id"    : "VH-DEMO-001",
        "plate_number"  : "TS09AB1234",
        "vehicle_type"  : "Car",
        "make_model"    : "Honda City (Silver)",
        "notes"         : "Demo vehicle — 5-camera intercity route",
        "observations"  : [
            {
                "obs_id"         : 1,
                "camera_id"      : "CAM_001",
                "location_name"  : "Ameerpet Junction",
                "area"           : "Central Hyderabad",
                "road_name"      : "Ameerpet–Punjagutta Road",
                "latitude"       : 17.4375,
                "longitude"      : 78.4483,
                "timestamp"      : "2026-08-28T08:00:00+05:30",
                "confidence"     : 0.94,
                "direction"      : "NORTH_BOUND",
            },
            {
                "obs_id"         : 2,
                "camera_id"      : "CAM_002",
                "location_name"  : "Begumpet Junction",
                "area"           : "Central Hyderabad",
                "road_name"      : "Begumpet–Secunderabad Road",
                "latitude"       : 17.4432,
                "longitude"      : 78.4556,
                "timestamp"      : "2026-08-28T08:09:00+05:30",
                "confidence"     : 0.91,
                "direction"      : "NORTH_EAST_BOUND",
            },
            {
                "obs_id"         : 3,
                "camera_id"      : "CAM_005",
                "location_name"  : "Secunderabad Railway Station",
                "area"           : "North Hyderabad",
                "road_name"      : "Station Road",
                "latitude"       : 17.4399,
                "longitude"      : 78.4983,
                "timestamp"      : "2026-08-28T08:22:00+05:30",
                "confidence"     : 0.88,
                "direction"      : "EAST_BOUND",
            },
            {
                "obs_id"         : 4,
                "camera_id"      : "CAM_013",
                "location_name"  : "Uppal X Roads",
                "area"           : "East Hyderabad",
                "road_name"      : "Uppal–Nagole Corridor",
                "latitude"       : 17.4052,
                "longitude"      : 78.5592,
                "timestamp"      : "2026-08-28T08:41:00+05:30",
                "confidence"     : 0.85,
                "direction"      : "EAST_BOUND",
            },
            {
                "obs_id"         : 5,
                "camera_id"      : "CAM_008",
                "location_name"  : "LB Nagar Junction",
                "area"           : "South-East Hyderabad",
                "road_name"      : "LB Nagar–Nagole Road",
                "latitude"       : 17.3494,
                "longitude"      : 78.5520,
                "timestamp"      : "2026-08-28T08:58:00+05:30",
                "confidence"     : 0.82,
                "direction"      : "SOUTH_EAST_BOUND",
            },
        ],
    },
    {
        "vehicle_id"    : "VH-DEMO-002",
        "plate_number"  : "MH12XY5678",
        "vehicle_type"  : "Motorcycle",
        "make_model"    : "Royal Enfield Classic 350 (Black)",
        "notes"         : "Demo vehicle — west Hyderabad route, 3 cameras",
        "observations"  : [
            {
                "obs_id"         : 1,
                "camera_id"      : "CAM_011",
                "location_name"  : "Gachibowli Stadium Gate",
                "area"           : "West Hyderabad",
                "road_name"      : "Gachibowli–Financial District Road",
                "latitude"       : 17.4239,
                "longitude"      : 78.3516,
                "timestamp"      : "2026-08-28T09:15:00+05:30",
                "confidence"     : 0.89,
                "direction"      : "NORTH_WEST_BOUND",
            },
            {
                "obs_id"         : 2,
                "camera_id"      : "CAM_003",
                "location_name"  : "Hitech City Entry Gate",
                "area"           : "West Hyderabad",
                "road_name"      : "HITEC City Road",
                "latitude"       : 17.4504,
                "longitude"      : 78.3806,
                "timestamp"      : "2026-08-28T09:28:00+05:30",
                "confidence"     : 0.86,
                "direction"      : "NORTH_BOUND",
            },
            {
                "obs_id"         : 3,
                "camera_id"      : "CAM_007",
                "location_name"  : "Kukatpally Bus Stop",
                "area"           : "North-West Hyderabad",
                "road_name"      : "NH-65 Kukatpally",
                "latitude"       : 17.4849,
                "longitude"      : 78.4138,
                "timestamp"      : "2026-08-28T09:44:00+05:30",
                "confidence"     : 0.79,
                "direction"      : "NORTH_BOUND",
            },
        ],
    },
    {
        "vehicle_id"    : "VH-DEMO-003",
        "plate_number"  : "DL01ZZ9999",
        "vehicle_type"  : "Bus",
        "make_model"    : "Tata Marcopolo (Blue)",
        "notes"         : "Demo vehicle — south Hyderabad route (anomalous speed detected)",
        "observations"  : [
            {
                "obs_id"         : 1,
                "camera_id"      : "CAM_004",
                "location_name"  : "Charminar Intersection",
                "area"           : "Old City",
                "road_name"      : "Charminar Road",
                "latitude"       : 17.3616,
                "longitude"      : 78.4747,
                "timestamp"      : "2026-08-28T10:00:00+05:30",
                "confidence"     : 0.93,
                "direction"      : "SOUTH_BOUND",
            },
            {
                "obs_id"         : 2,
                "camera_id"      : "CAM_009",
                "location_name"  : "Mehdipatnam Signal",
                "area"           : "South-West Hyderabad",
                "road_name"      : "Mehdipatnam–Tolichowki Road",
                "latitude"       : 17.3929,
                "longitude"      : 78.4370,
                "timestamp"      : "2026-08-28T10:14:00+05:30",
                "confidence"     : 0.90,
                "direction"      : "NORTH_BOUND",
            },
            {
                "obs_id"         : 3,
                "camera_id"      : "CAM_012",
                "location_name"  : "Tolichowki Toll Plaza",
                "area"           : "South-West Hyderabad",
                "road_name"      : "Outer Ring Road South",
                "latitude"       : 17.3963,
                "longitude"      : 78.4125,
                "timestamp"      : "2026-08-28T10:22:00+05:30",
                "confidence"     : 0.87,
                "direction"      : "WEST_BOUND",
            },
            {
                "obs_id"         : 4,
                "camera_id"      : "CAM_015",
                "location_name"  : "Kondapur Signal",
                "area"           : "West Hyderabad",
                "road_name"      : "Kondapur–Gachibowli Road",
                "latitude"       : 17.4600,
                "longitude"      : 78.3620,
                "timestamp"      : "2026-08-28T10:36:00+05:30",
                "confidence"     : 0.83,
                "direction"      : "NORTH_WEST_BOUND",
            },
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
            "DEMO / SAMPLE DATA — These observations are NOT from real CCTV cameras. "
            "They are built-in sample data to demonstrate the Trajectory Explorer feature."
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
