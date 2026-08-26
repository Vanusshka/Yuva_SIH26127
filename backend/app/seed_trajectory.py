"""
Seed 15 simulated Hyderabad ANPR cameras for Phase 4 trajectory testing.
Also seeds sample detections for 3 test plates so trajectory APIs work out
of the box without needing a real camera feed.

Run from backend/ directory:
    python -m app.seed_trajectory
"""

from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import init_db, SessionLocal
from app.models.trajectory_camera import TrajectoryCamera
from app.models.detection import Detection
from sqlalchemy.exc import IntegrityError

# ── 15 Simulated cameras ──────────────────────────────────────────────────────
CAMERAS = [
    {
        "camera_id"    : "CAM_001",
        "location_name": "Ameerpet Junction",
        "road_name"    : "Ameerpet–Punjagutta Road",
        "direction"    : "NORTH_BOUND",
        "latitude"     : 17.4375,
        "longitude"    : 78.4483,
    },
    {
        "camera_id"    : "CAM_002",
        "location_name": "Begumpet Junction",
        "road_name"    : "Begumpet–Secunderabad Road",
        "direction"    : "NORTH_EAST_BOUND",
        "latitude"     : 17.4432,
        "longitude"    : 78.4556,
    },
    {
        "camera_id"    : "CAM_003",
        "location_name": "Hitech City Entry Gate",
        "road_name"    : "HITEC City Road",
        "direction"    : "WEST_BOUND",
        "latitude"     : 17.4504,
        "longitude"    : 78.3806,
    },
    {
        "camera_id"    : "CAM_004",
        "location_name": "Charminar Intersection",
        "road_name"    : "Charminar Road",
        "direction"    : "SOUTH_BOUND",
        "latitude"     : 17.3616,
        "longitude"    : 78.4747,
    },
    {
        "camera_id"    : "CAM_005",
        "location_name": "Secunderabad Railway Station",
        "road_name"    : "Station Road",
        "direction"    : "EAST_BOUND",
        "latitude"     : 17.4399,
        "longitude"    : 78.4983,
    },
    {
        "camera_id"    : "CAM_006",
        "location_name": "Madhapur Flyover",
        "road_name"    : "Madhapur–Kondapur Road",
        "direction"    : "NORTH_WEST_BOUND",
        "latitude"     : 17.4489,
        "longitude"    : 78.3908,
    },
    {
        "camera_id"    : "CAM_007",
        "location_name": "Kukatpally Bus Stop",
        "road_name"    : "NH-65 Kukatpally",
        "direction"    : "NORTH_BOUND",
        "latitude"     : 17.4849,
        "longitude"    : 78.4138,
    },
    {
        "camera_id"    : "CAM_008",
        "location_name": "LB Nagar Junction",
        "road_name"    : "LB Nagar–Nagole Road",
        "direction"    : "EAST_BOUND",
        "latitude"     : 17.3494,
        "longitude"    : 78.5520,
    },
    {
        "camera_id"    : "CAM_009",
        "location_name": "Mehdipatnam Signal",
        "road_name"    : "Mehdipatnam–Tolichowki Road",
        "direction"    : "SOUTH_WEST_BOUND",
        "latitude"     : 17.3929,
        "longitude"    : 78.4370,
    },
    {
        "camera_id"    : "CAM_010",
        "location_name": "Dilsukhnagar Underpass",
        "road_name"    : "Dilsukhnagar Main Road",
        "direction"    : "SOUTH_EAST_BOUND",
        "latitude"     : 17.3688,
        "longitude"    : 78.5260,
    },
    {
        "camera_id"    : "CAM_011",
        "location_name": "Gachibowli Stadium Gate",
        "road_name"    : "Gachibowli–Financial District Road",
        "direction"    : "SOUTH_WEST_BOUND",
        "latitude"     : 17.4239,
        "longitude"    : 78.3516,
    },
    {
        "camera_id"    : "CAM_012",
        "location_name": "Tolichowki Toll Plaza",
        "road_name"    : "Outer Ring Road South",
        "direction"    : "WEST_BOUND",
        "latitude"     : 17.3963,
        "longitude"    : 78.4125,
    },
    {
        "camera_id"    : "CAM_013",
        "location_name": "Uppal X Roads",
        "road_name"    : "Uppal–Nagole Corridor",
        "direction"    : "EAST_BOUND",
        "latitude"     : 17.4052,
        "longitude"    : 78.5592,
    },
    {
        "camera_id"    : "CAM_014",
        "location_name": "Paradise Circle",
        "road_name"    : "MG Road–Paradise Road",
        "direction"    : "NORTH_BOUND",
        "latitude"     : 17.4480,
        "longitude"    : 78.4980,
    },
    {
        "camera_id"    : "CAM_015",
        "location_name": "Kondapur Signal",
        "road_name"    : "Kondapur–Gachibowli Road",
        "direction"    : "SOUTH_BOUND",
        "latitude"     : 17.4600,
        "longitude"    : 78.3620,
    },
]

# ── Sample detections for 3 test plates ───────────────────────────────────────
# Plate TS09AB1234 – normal city commute through 5 cameras
# Plate MH12XY5678 – fast movement (will be classified FAST)
# Plate DL01ZZ9999 – suspicious jump (will be classified SUSPICIOUS/IMPOSSIBLE)

_BASE = datetime(2026, 8, 24, 8, 0, 0, tzinfo=timezone.utc)

SAMPLE_DETECTIONS = [
    # ── TS09AB1234 – normal route: CAM_001 → CAM_002 → CAM_005 → CAM_014
    {"plate_number": "TS09AB1234", "camera_id": "CAM_001",
     "timestamp": _BASE,                         "detection_confidence": 0.96},
    {"plate_number": "TS09AB1234", "camera_id": "CAM_002",
     "timestamp": _BASE + timedelta(minutes=8),  "detection_confidence": 0.94},
    {"plate_number": "TS09AB1234", "camera_id": "CAM_005",
     "timestamp": _BASE + timedelta(minutes=20), "detection_confidence": 0.91},
    {"plate_number": "TS09AB1234", "camera_id": "CAM_014",
     "timestamp": _BASE + timedelta(minutes=30), "detection_confidence": 0.93},

    # ── MH12XY5678 – fast movement: CAM_003 → CAM_007 → CAM_015 (short gaps)
    {"plate_number": "MH12XY5678", "camera_id": "CAM_003",
     "timestamp": _BASE + timedelta(minutes=5),  "detection_confidence": 0.88},
    {"plate_number": "MH12XY5678", "camera_id": "CAM_007",
     "timestamp": _BASE + timedelta(minutes=9),  "detection_confidence": 0.85},
    {"plate_number": "MH12XY5678", "camera_id": "CAM_015",
     "timestamp": _BASE + timedelta(minutes=12), "detection_confidence": 0.87},

    # ── DL01ZZ9999 – suspicious: appears at CAM_004 (south) then instantly CAM_007 (north)
    {"plate_number": "DL01ZZ9999", "camera_id": "CAM_004",
     "timestamp": _BASE + timedelta(minutes=0),  "detection_confidence": 0.79},
    {"plate_number": "DL01ZZ9999", "camera_id": "CAM_007",
     "timestamp": _BASE + timedelta(minutes=1),  "detection_confidence": 0.80},
    {"plate_number": "DL01ZZ9999", "camera_id": "CAM_008",
     "timestamp": _BASE + timedelta(minutes=2),  "detection_confidence": 0.76},
]


def seed():
    init_db()
    db = SessionLocal()

    cam_inserted = cam_skipped = 0
    det_inserted = 0

    try:
        # ── Cameras ───────────────────────────────────────────────────────────
        print("Seeding trajectory cameras...")
        for c in CAMERAS:
            existing = db.query(TrajectoryCamera).filter(
                TrajectoryCamera.camera_id == c["camera_id"]
            ).first()
            if existing:
                print(f"  [SKIP]   {c['camera_id']} already exists.")
                cam_skipped += 1
                continue
            db.add(TrajectoryCamera(**c))
            try:
                db.commit()
                print(f"  [INSERT] {c['camera_id']} – {c['location_name']}")
                cam_inserted += 1
            except IntegrityError:
                db.rollback()
                cam_skipped += 1

        # ── Detections ────────────────────────────────────────────────────────
        print("\nSeeding sample detections...")
        for d in SAMPLE_DETECTIONS:
            det = Detection(**d)
            db.add(det)
            db.commit()
            print(f"  [INSERT] {d['plate_number']} @ {d['camera_id']} "
                  f"at {d['timestamp'].strftime('%H:%M')}")
            det_inserted += 1

    finally:
        db.close()

    print(f"\nDone.")
    print(f"  Cameras  – inserted: {cam_inserted}  skipped: {cam_skipped}")
    print(f"  Detections inserted: {det_inserted}")


if __name__ == "__main__":
    seed()
