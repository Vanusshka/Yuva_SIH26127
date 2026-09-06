"""
Sync trajectory_cameras table to match the 6 cameras in cameras.json.
Run once: python _sync_cameras.py
"""
import sys; sys.path.insert(0, '.')
from app.database import init_db, SessionLocal
from app.models.trajectory_camera import TrajectoryCamera

CAMERAS_6 = [
    dict(camera_id="CAM_001", location_name="Ameerpet Junction",  road_name="Ameerpet-Punjagutta Road",       direction="NORTH_BOUND",       latitude=17.4375, longitude=78.4483),
    dict(camera_id="CAM_002", location_name="Punjagutta",          road_name="Punjagutta-Banjara Hills Road",  direction="SOUTH_BOUND",       latitude=17.4289, longitude=78.4521),
    dict(camera_id="CAM_003", location_name="Banjara Hills",       road_name="Road No. 12, Banjara Hills",     direction="WEST_BOUND",        latitude=17.4156, longitude=78.4488),
    dict(camera_id="CAM_004", location_name="Jubilee Hills",       road_name="Jubilee Hills Check Post Road",  direction="WEST_BOUND",        latitude=17.4319, longitude=78.4071),
    dict(camera_id="CAM_005", location_name="Madhapur",            road_name="Hitech City-Madhapur Road",      direction="NORTH_WEST_BOUND",  latitude=17.4483, longitude=78.3915),
    dict(camera_id="CAM_006", location_name="Gachibowli",          road_name="Gachibowli-Nallagandla Road",    direction="WEST_BOUND",        latitude=17.4401, longitude=78.3489),
]

init_db()
db = SessionLocal()

# Remove cameras not in our 6
keep = {c["camera_id"] for c in CAMERAS_6}
all_cams = db.query(TrajectoryCamera).all()
for cam in all_cams:
    if cam.camera_id not in keep:
        db.delete(cam)
        print(f"Removed: {cam.camera_id}")

# Upsert the 6 cameras
for c in CAMERAS_6:
    existing = db.query(TrajectoryCamera).filter(TrajectoryCamera.camera_id == c["camera_id"]).first()
    if existing:
        existing.location_name = c["location_name"]
        existing.road_name     = c["road_name"]
        existing.direction     = c["direction"]
        existing.latitude      = c["latitude"]
        existing.longitude     = c["longitude"]
        print(f"Updated: {c['camera_id']} - {c['location_name']}")
    else:
        db.add(TrajectoryCamera(**c))
        print(f"Added:   {c['camera_id']} - {c['location_name']}")

db.commit()
result = db.query(TrajectoryCamera).all()
print(f"\nTotal trajectory cameras: {len(result)}")
for r in result:
    print(f"  {r.camera_id}: {r.location_name} ({r.latitude}, {r.longitude})")
db.close()
print("Done.")
