"""
Seed demo alerts by inserting realistic vehicle_events and detections
that will trigger the alert engine:

1. BLACKLISTED_VEHICLE  - insert events for plates on the blacklist
2. FREQUENT_SIGHTINGS   - insert 12 events for one plate in the last hour  
3. SUSPICIOUS_TRAJECTORY - insert detections with fast inter-camera movement
4. COMPLIANCE_ANOMALY   - insert vehicle_events with no plate (None)

Run from backend/:
    .\\venv313\\Scripts\\python.exe scripts/seed_alerts.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import init_db, SessionLocal
from app.models.vehicle_event import VehicleEvent
from app.models.detection import Detection
import app.models.camera               # noqa
import app.models.trajectory_camera    # noqa
import app.models.manual_review        # noqa
from datetime import datetime, timezone, timedelta

init_db()
db = SessionLocal()

NOW = datetime.now(timezone.utc)

# ── Helper ────────────────────────────────────────────────────────────────────

def make_event(plate, cam, minutes_ago, vtype="car", tier="HIGH", conf=0.92):
    return VehicleEvent(
        plate_number       = plate,
        camera_id          = cam,
        timestamp          = NOW - timedelta(minutes=minutes_ago),
        vehicle_type       = vtype,
        vehicle_confidence = 0.88,
        plate_confidence   = 0.91,
        ocr_confidence     = conf,
        confidence_tier    = tier,
        valid_ocr_reads    = 3,
        matching_ocr_reads = 3,
        agreement_rate     = 1.0,
        vehicle_category   = "car_commercial",
        created_at         = NOW,
    )

def make_detection(plate, cam, minutes_ago, conf=0.92):
    return Detection(
        plate_number          = plate,
        camera_id             = cam,
        timestamp             = NOW - timedelta(minutes=minutes_ago),
        detection_confidence  = conf,
        created_at            = NOW,
    )

# ── 1. Blacklisted vehicle alerts ─────────────────────────────────────────────
# Use plates that are in data/metadata/blacklist.json
from app.utils.metadata_loader import load_blacklist
blacklist_entries = load_blacklist()
blacklist = [e['plate_number'] for e in blacklist_entries]
print(f"Blacklist has {len(blacklist)} entries: {blacklist[:5]}")

if blacklist:
    for i, plate in enumerate(blacklist[:3]):
        db.add(make_event(plate, "CAM_001", 10 + i*5, tier="HIGH", conf=0.91))
        db.add(make_detection(plate, "CAM_001", 10 + i*5))
        print(f"  Added blacklist event: {plate}")
else:
    # No blacklist — add some suspicious plates manually
    for plate in ["TS09ZZ9999", "AP99XX0001", "KA01AB0000"]:
        db.add(make_event(plate, "CAM_002", 15, tier="HIGH", conf=0.93))

# ── 2. Frequent sightings (same plate seen 12 times in 1 hour) ────────────────
freq_plate = "TS08CD5678"
print(f"  Adding 12 frequent sightings for {freq_plate}")
for i in range(12):
    cam = f"CAM_00{(i % 5) + 1}"
    db.add(make_event(freq_plate, cam, i * 4, tier="HIGH", conf=0.89))
    db.add(make_detection(freq_plate, cam, i * 4))

# ── 3. Suspicious trajectory (fast movement between distant cameras) ──────────
# CAM_001 (Ameerpet 17.4375,78.4483) → CAM_006 (Gachibowli 17.4401,78.3489)
# Distance ~8km, 2 minutes apart → ~240 km/h → IMPOSSIBLE
fast_plate = "DL01ZZ9999"
print(f"  Adding impossible trajectory for {fast_plate}")
db.add(make_event(fast_plate, "CAM_001", 5,  tier="HIGH", conf=0.95))
db.add(make_event(fast_plate, "CAM_006", 3,  tier="HIGH", conf=0.94))
db.add(make_detection(fast_plate, "CAM_001", 5))
db.add(make_detection(fast_plate, "CAM_006", 3))

# Another suspicious plate — fast but not impossible
susp_plate = "MH12XY5678"
print(f"  Adding suspicious trajectory for {susp_plate}")
db.add(make_event(susp_plate, "CAM_001", 20, tier="HIGH", conf=0.90))
db.add(make_event(susp_plate, "CAM_003", 15, tier="HIGH", conf=0.88))
db.add(make_detection(susp_plate, "CAM_001", 20))
db.add(make_detection(susp_plate, "CAM_003", 15))

# ── 4. Compliance anomaly (vehicle detected but plate unreadable) ─────────────
print("  Adding compliance anomaly events")
for cam in ["CAM_002", "CAM_004", "CAM_005"]:
    db.add(VehicleEvent(
        plate_number       = None,
        camera_id          = cam,
        timestamp          = NOW - timedelta(minutes=30),
        vehicle_type       = "bus",
        vehicle_confidence = 0.85,
        plate_confidence   = None,
        ocr_confidence     = None,
        confidence_tier    = "LOW",
        valid_ocr_reads    = 0,
        matching_ocr_reads = 0,
        agreement_rate     = 0.0,
        vehicle_category   = "car_commercial",
        created_at         = NOW,
    ))

db.commit()
db.close()

print("\nDone. Verifying alerts now...")

# Verify alerts are generated
db2 = SessionLocal()
from app.services.p7_alert_service import get_combined_alerts
alerts = get_combined_alerts(db2, limit=50)
print(f"Total alerts generated: {alerts.total_alerts}")
for a in alerts.alerts:
    print(f"  [{a.severity:8s}] {a.alert_type:30s} | plate={a.plate_number} | {a.location}")
db2.close()
