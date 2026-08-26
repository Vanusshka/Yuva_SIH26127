"""
Phase 4 – Trajectory Reconstruction Tests.

Covers:
  - Haversine calculation
  - Anomaly classification
  - Trajectory camera CRUD
  - Detection storage
  - Full trajectory reconstruction API
  - All movement status cases (NORMAL, FAST, SUSPICIOUS, IMPOSSIBLE)

Run from backend/:
    python -m pytest tests/test_phase4_trajectory.py -v
"""

from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app

# ── In-memory test DB ─────────────────────────────────────────────────────────
TEST_DB_URL = "sqlite:///:memory:"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    import app.models.camera
    import app.models.vehicle_event
    import app.models.trajectory_camera
    import app.models.detection
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


# ── Unit: Haversine ───────────────────────────────────────────────────────────

def test_haversine_same_point():
    from app.trajectory.haversine import haversine_km
    assert haversine_km(17.4375, 78.4483, 17.4375, 78.4483) == pytest.approx(0.0, abs=1e-6)
    print("  [PASS] haversine same point = 0")


def test_haversine_known_distance():
    from app.trajectory.haversine import haversine_km
    # Ameerpet → Begumpet: ~0.95 km
    dist = haversine_km(17.4375, 78.4483, 17.4432, 78.4556)
    assert 0.5 < dist < 1.5, f"Expected ~0.95 km, got {dist:.3f}"
    print(f"  [PASS] haversine Ameerpet→Begumpet = {dist:.3f} km")


def test_time_diff():
    from app.trajectory.haversine import time_diff_minutes
    t1 = datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 8, 24, 10, 30, tzinfo=timezone.utc)
    assert time_diff_minutes(t1, t2) == pytest.approx(30.0)
    print("  [PASS] time_diff_minutes = 30.0")


def test_average_speed():
    from app.trajectory.haversine import average_speed_kmh
    assert average_speed_kmh(30.0, 30.0) == pytest.approx(60.0)
    assert average_speed_kmh(10.0, 0.0) == pytest.approx(0.0)  # zero time
    print("  [PASS] average_speed_kmh correct")


# ── Unit: Anomaly classifier ──────────────────────────────────────────────────

def test_classify_normal():
    from app.trajectory.anomaly import classify_hop, MovementStatus
    s = classify_hop(5.0, 10.0, 30.0, False)
    assert s == MovementStatus.NORMAL
    print("  [PASS] classify_hop NORMAL")


def test_classify_fast():
    from app.trajectory.anomaly import classify_hop, MovementStatus
    s = classify_hop(10.0, 6.0, 100.0, False)
    assert s == MovementStatus.FAST
    print("  [PASS] classify_hop FAST")


def test_classify_suspicious_speed():
    from app.trajectory.anomaly import classify_hop, MovementStatus
    s = classify_hop(20.0, 8.0, 150.0, False)
    assert s == MovementStatus.SUSPICIOUS
    print("  [PASS] classify_hop SUSPICIOUS (speed)")


def test_classify_impossible_speed():
    from app.trajectory.anomaly import classify_hop, MovementStatus
    s = classify_hop(50.0, 5.0, 600.0, False)
    assert s == MovementStatus.IMPOSSIBLE
    print("  [PASS] classify_hop IMPOSSIBLE (speed)")


def test_classify_negative_time():
    from app.trajectory.anomaly import classify_hop, MovementStatus
    s = classify_hop(5.0, -5.0, 0.0, False)
    assert s == MovementStatus.IMPOSSIBLE
    print("  [PASS] classify_hop IMPOSSIBLE (negative time)")


def test_classify_duplicate():
    from app.trajectory.anomaly import classify_hop, MovementStatus
    # Same camera, 10 seconds apart → SUSPICIOUS
    s = classify_hop(0.0, 10/60, 0.0, True)
    assert s == MovementStatus.SUSPICIOUS
    print("  [PASS] classify_hop SUSPICIOUS (duplicate)")


def test_worst_status():
    from app.trajectory.anomaly import worst_status, MovementStatus
    statuses = [MovementStatus.NORMAL, MovementStatus.FAST, MovementStatus.SUSPICIOUS]
    assert worst_status(statuses) == MovementStatus.SUSPICIOUS
    assert worst_status([]) == MovementStatus.NORMAL
    print("  [PASS] worst_status correct")


# ── API: Trajectory cameras ───────────────────────────────────────────────────

def test_create_trajectory_camera(client):
    r = client.post("/trajectory/cameras", json={
        "camera_id"    : "TRAJ_CAM_01",
        "location_name": "Test Junction",
        "road_name"    : "Test Road",
        "direction"    : "NORTH_BOUND",
        "latitude"     : 17.4375,
        "longitude"    : 78.4483,
    })
    assert r.status_code == 201, r.text
    assert r.json()["camera_id"] == "TRAJ_CAM_01"
    print("  [PASS] POST /trajectory/cameras")


def test_create_second_trajectory_camera(client):
    r = client.post("/trajectory/cameras", json={
        "camera_id"    : "TRAJ_CAM_02",
        "location_name": "Second Junction",
        "latitude"     : 17.4432,
        "longitude"    : 78.4556,
    })
    assert r.status_code == 201
    print("  [PASS] POST /trajectory/cameras (second)")


def test_duplicate_trajectory_camera_rejected(client):
    r = client.post("/trajectory/cameras", json={
        "camera_id"    : "TRAJ_CAM_01",
        "location_name": "Duplicate",
        "latitude"     : 0.0,
        "longitude"    : 0.0,
    })
    assert r.status_code == 409
    print("  [PASS] Duplicate trajectory camera returns 409")


def test_list_trajectory_cameras(client):
    r = client.get("/trajectory/cameras")
    assert r.status_code == 200
    assert len(r.json()) >= 2
    print("  [PASS] GET /trajectory/cameras")


# ── API: Detections ───────────────────────────────────────────────────────────

_BASE_TS = "2026-08-24T10:00:00Z"

def test_store_detection_cam1(client):
    r = client.post("/detections", json={
        "plate_number"        : "TS99TEST01",
        "camera_id"           : "TRAJ_CAM_01",
        "timestamp"           : "2026-08-24T10:00:00Z",
        "detection_confidence": 0.95,
    })
    assert r.status_code == 201, r.text
    assert r.json()["plate_number"] == "TS99TEST01"
    print("  [PASS] POST /detections (cam 1)")


def test_store_detection_cam2(client):
    r = client.post("/detections", json={
        "plate_number"        : "TS99TEST01",
        "camera_id"           : "TRAJ_CAM_02",
        "timestamp"           : "2026-08-24T10:10:00Z",
        "detection_confidence": 0.92,
    })
    assert r.status_code == 201
    print("  [PASS] POST /detections (cam 2)")


def test_unknown_camera_detection_rejected(client):
    r = client.post("/detections", json={
        "plate_number": "TS99TEST01",
        "camera_id"   : "DOES_NOT_EXIST",
        "timestamp"   : "2026-08-24T10:00:00Z",
    })
    assert r.status_code == 404
    print("  [PASS] Detection with unknown camera returns 404")


def test_list_detections(client):
    r = client.get("/detections?plate_number=TS99TEST01")
    assert r.status_code == 200
    assert len(r.json()) == 2
    print("  [PASS] GET /detections?plate_number=TS99TEST01")


# ── API: Trajectory reconstruction ───────────────────────────────────────────

def test_trajectory_normal(client):
    r = client.get("/trajectory/TS99TEST01")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["plate_number"] == "TS99TEST01"
    assert len(body["trajectory"]) == 2
    assert len(body["hops"])       == 1
    assert body["statistics"]["total_detections"] == 2
    assert body["statistics"]["total_hops"]       == 1
    assert body["statistics"]["average_speed_kmh"] >= 0
    assert body["status"] in ("NORMAL", "FAST", "SUSPICIOUS", "IMPOSSIBLE")
    print(f"  [PASS] GET /trajectory/TS99TEST01 → status={body['status']}")


def test_trajectory_not_found(client):
    r = client.get("/trajectory/NOTEXIST9999")
    assert r.status_code == 404
    print("  [PASS] Trajectory for unknown plate returns 404")


def test_trajectory_impossible(client):
    """
    Store two detections 1 minute apart at locations ~14 km apart.
    Speed = 840 km/h → IMPOSSIBLE.
    """
    # Create cameras far apart
    client.post("/trajectory/cameras", json={
        "camera_id": "TRAJ_FAR_A",
        "location_name": "Far North",
        "latitude": 17.55, "longitude": 78.45,
    })
    client.post("/trajectory/cameras", json={
        "camera_id": "TRAJ_FAR_B",
        "location_name": "Far South",
        "latitude": 17.30, "longitude": 78.45,
    })
    client.post("/detections", json={
        "plate_number": "XX00IMPOSSIBLE",
        "camera_id": "TRAJ_FAR_A",
        "timestamp": "2026-08-24T09:00:00Z",
        "detection_confidence": 0.90,
    })
    client.post("/detections", json={
        "plate_number": "XX00IMPOSSIBLE",
        "camera_id": "TRAJ_FAR_B",
        "timestamp": "2026-08-24T09:01:00Z",
        "detection_confidence": 0.90,
    })
    r = client.get("/trajectory/XX00IMPOSSIBLE")
    assert r.status_code == 200
    assert r.json()["status"] == "IMPOSSIBLE"
    print(f"  [PASS] IMPOSSIBLE trajectory correctly classified")


# ── Runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import app.models.camera
    import app.models.vehicle_event
    import app.models.trajectory_camera
    import app.models.detection
    Base.metadata.create_all(bind=test_engine)

    c = TestClient(app)
    tests = [
        test_haversine_same_point,
        test_haversine_known_distance,
        test_time_diff,
        test_average_speed,
        test_classify_normal,
        test_classify_fast,
        test_classify_suspicious_speed,
        test_classify_impossible_speed,
        test_classify_negative_time,
        test_classify_duplicate,
        test_worst_status,
        lambda: test_create_trajectory_camera(c),
        lambda: test_create_second_trajectory_camera(c),
        lambda: test_duplicate_trajectory_camera_rejected(c),
        lambda: test_list_trajectory_cameras(c),
        lambda: test_store_detection_cam1(c),
        lambda: test_store_detection_cam2(c),
        lambda: test_unknown_camera_detection_rejected(c),
        lambda: test_list_detections(c),
        lambda: test_trajectory_normal(c),
        lambda: test_trajectory_not_found(c),
        lambda: test_trajectory_impossible(c),
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {e}")
            failed += 1
    print(f"\nResults: {passed} passed, {failed} failed")
