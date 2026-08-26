"""
Phase 3 – Database & API smoke tests.
Uses an in-memory SQLite database so nothing touches traffic.db.

Run from backend/:
    python -m pytest tests/test_phase3_db.py -v
"""

from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime, timezone

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
    """Create all tables in the in-memory DB before tests run."""
    import app.models.camera        # noqa: F401
    import app.models.vehicle_event # noqa: F401
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "running"
    print("  [PASS] GET /health")


def test_create_camera(client):
    payload = {
        "camera_id": "CAM_TEST_01",
        "name": "Test Camera One",
        "latitude": 17.44,
        "longitude": 78.45,
        "address": "Test Road, Hyderabad",
        "status": "ACTIVE",
    }
    r = client.post("/cameras", json=payload)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["camera_id"] == "CAM_TEST_01"
    assert data["status"] == "ACTIVE"
    print("  [PASS] POST /cameras")


def test_duplicate_camera_rejected(client):
    payload = {
        "camera_id": "CAM_TEST_01",
        "name": "Duplicate",
        "latitude": 0.0,
        "longitude": 0.0,
    }
    r = client.post("/cameras", json=payload)
    assert r.status_code == 409
    print("  [PASS] Duplicate camera returns 409")


def test_list_cameras(client):
    r = client.get("/cameras")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert len(r.json()) >= 1
    print("  [PASS] GET /cameras")


def test_get_camera(client):
    r = client.get("/cameras/CAM_TEST_01")
    assert r.status_code == 200
    assert r.json()["camera_id"] == "CAM_TEST_01"
    print("  [PASS] GET /cameras/{camera_id}")


def test_get_unknown_camera(client):
    r = client.get("/cameras/DOES_NOT_EXIST")
    assert r.status_code == 404
    print("  [PASS] Unknown camera returns 404")


def test_update_camera(client):
    r = client.put("/cameras/CAM_TEST_01", json={"status": "INACTIVE"})
    assert r.status_code == 200
    assert r.json()["status"] == "INACTIVE"
    print("  [PASS] PUT /cameras/{camera_id}")


def test_create_second_camera(client):
    payload = {
        "camera_id": "CAM_TEST_02",
        "name": "Test Camera Two",
        "latitude": 17.50,
        "longitude": 78.50,
        "address": "Second Road, Hyderabad",
        "status": "ACTIVE",
    }
    r = client.post("/cameras", json=payload)
    assert r.status_code == 201
    print("  [PASS] POST /cameras (second camera)")


def test_events_empty(client):
    r = client.get("/events")
    assert r.status_code == 200
    assert r.json() == []
    print("  [PASS] GET /events returns empty list initially")


def test_vehicle_history_not_found(client):
    r = client.get("/vehicles/TS09ZZ9999/history")
    assert r.status_code == 404
    print("  [PASS] Unknown plate history returns 404")


def test_delete_camera(client):
    r = client.delete("/cameras/CAM_TEST_01")
    assert r.status_code == 204
    r2 = client.get("/cameras/CAM_TEST_01")
    assert r2.status_code == 404
    print("  [PASS] DELETE /cameras/{camera_id}")


# ── Manual runner ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Quick run without pytest
    import app.models.camera        # noqa: F401
    import app.models.vehicle_event # noqa: F401
    Base.metadata.create_all(bind=test_engine)

    c = TestClient(app)
    tests = [
        lambda: test_health(c),
        lambda: test_create_camera(c),
        lambda: test_duplicate_camera_rejected(c),
        lambda: test_list_cameras(c),
        lambda: test_get_camera(c),
        lambda: test_get_unknown_camera(c),
        lambda: test_update_camera(c),
        lambda: test_create_second_camera(c),
        lambda: test_events_empty(c),
        lambda: test_vehicle_history_not_found(c),
        lambda: test_delete_camera(c),
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
