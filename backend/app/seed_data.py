"""
Seed the database with 5 sample Hyderabad ANPR cameras.

Run from backend/ directory:
    python -m app.seed_data
"""

from __future__ import annotations
import sys
from pathlib import Path

# Allow running as a script from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import init_db, SessionLocal
from app.models.camera import Camera, CameraStatus
from sqlalchemy.exc import IntegrityError

SAMPLE_CAMERAS = [
    {
        "camera_id" : "CAM_001",
        "name"      : "Ameerpet Junction Camera",
        "latitude"  : 17.4375,
        "longitude" : 78.4483,
        "address"   : "Ameerpet Junction, Hyderabad",
        "status"    : CameraStatus.ACTIVE,
    },
    {
        "camera_id" : "CAM_002",
        "name"      : "Begumpet Junction Camera",
        "latitude"  : 17.4432,
        "longitude" : 78.4556,
        "address"   : "Begumpet Junction, Hyderabad",
        "status"    : CameraStatus.ACTIVE,
    },
    {
        "camera_id" : "CAM_003",
        "name"      : "Hitech City Entry Camera",
        "latitude"  : 17.4504,
        "longitude" : 78.3806,
        "address"   : "Hitech City Road, Madhapur, Hyderabad",
        "status"    : CameraStatus.ACTIVE,
    },
    {
        "camera_id" : "CAM_004",
        "name"      : "Charminar Intersection Camera",
        "latitude"  : 17.3616,
        "longitude" : 78.4747,
        "address"   : "Charminar Intersection, Old City, Hyderabad",
        "status"    : CameraStatus.ACTIVE,
    },
    {
        "camera_id" : "CAM_005",
        "name"      : "Secunderabad Railway Station Camera",
        "latitude"  : 17.4399,
        "longitude" : 78.4983,
        "address"   : "Secunderabad Railway Station, Secunderabad",
        "status"    : CameraStatus.ACTIVE,
    },
]


def seed():
    init_db()
    db = SessionLocal()
    inserted = skipped = 0
    try:
        for cam_data in SAMPLE_CAMERAS:
            existing = db.query(Camera).filter(
                Camera.camera_id == cam_data["camera_id"]
            ).first()
            if existing:
                print(f"  [SKIP]   {cam_data['camera_id']} already exists.")
                skipped += 1
                continue
            cam = Camera(**cam_data)
            db.add(cam)
            try:
                db.commit()
                print(f"  [INSERT] {cam_data['camera_id']} – {cam_data['name']}")
                inserted += 1
            except IntegrityError:
                db.rollback()
                print(f"  [SKIP]   {cam_data['camera_id']} (race condition).")
                skipped += 1
    finally:
        db.close()

    print(f"\nDone. Inserted: {inserted}  Skipped: {skipped}")


if __name__ == "__main__":
    seed()
