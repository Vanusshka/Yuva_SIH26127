"""
Phase 8 Integration Tests
==========================

Tests every Phase 8 endpoint using FastAPI's TestClient with an in-memory
SQLite database.  No running server required.

Run from the backend/ directory:
    pytest tests/test_phase8_integration.py -v

Coverage:
  GET  /health                    → Phase8HealthResponse
  POST /process                   → ProcessResponse
  GET  /vehicles                  → VehicleListResponse
  GET  /vehicles/{plate}          → VehicleRecord  (200 + 404)
  GET  /api/trajectory/{plate}    → FrontendTrajectoryResponse  (200 + 404)
  GET  /analytics                 → UnifiedAnalyticsResponse
  GET  /alerts                    → FrontendAlertsResponse
  GET  /api/cameras               → list[dict]
  GET  /cameras                   → List[CameraResponse]  (Phase 3, not broken)
  GET  /trajectory/{plate}        → TrajectoryResponse    (Phase 4, not broken)
  GET  /analytics/overview        → OverviewResponse      (Phase 5, not broken)
  GET  /analytics/summary         → OverviewResponse      (Phase 7, not broken)
  POST /metadata/reload           → {status: ok}
  CORS preflight                  → 200 with correct headers
"""

from __future__ import annotations

import io
import sys
import types
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

# ── path setup ────────────────────────────────────────────────────────────────
_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

# ── stub heavy ML deps before any app import ──────────────────────────────────
def _stub_ml():
    ul = types.ModuleType("ultralytics")
    class _YOLO:
        def __init__(self, *a, **kw): pass
        def __call__(self, *a, **kw):
            class _R:
                class boxes:
                    # empty – no vehicles detected on synthetic images
                    def __iter__(self): return iter([])
                boxes = boxes()
            return [_R()]
    ul.YOLO = _YOLO
    sys.modules.setdefault("ultralytics", ul)

    eo = types.ModuleType("easyocr")
    class _Reader:
        def __init__(self, *a, **kw): pass
        def readtext(self, *a, **kw): return []
    eo.Reader = _Reader
    sys.modules.setdefault("easyocr", eo)

    for mod in ["torch", "torchvision", "torchvision.transforms"]:
        sys.modules.setdefault(mod, types.ModuleType(mod))

_stub_ml()

# ── now safe to import app ────────────────────────────────────────────────────
import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.camera import Camera, CameraStatus
from app.models.trajectory_camera import TrajectoryCamera
from app.models.detection import Detection
from app.models.vehicle_event import VehicleEvent


# ═══════════════════════════════════════════════════════════════════════════════
# DB FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="module")
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()

    _BASE = datetime(2026, 8, 24, 8, 0, 0, tzinfo=timezone.utc)

    # ── Phase-3 cameras ───────────────────────────────────────────────────────
    for i in range(1, 6):
        session.add(Camera(
            camera_id = f"CAM_00{i}",
            name      = f"Test Camera {i}",
            latitude  = 17.4375 + i * 0.01,
            longitude = 78.4483 + i * 0.01,
            address   = f"Test Address {i}",
            status    = CameraStatus.ACTIVE,
        ))
    session.commit()

    # ── Phase-4 trajectory cameras ────────────────────────────────────────────
    traj_cams = [
        dict(camera_id="CAM_001", location_name="Ameerpet Junction",
             road_name="Ameerpet–Punjagutta Road", direction="NORTH_BOUND",
             latitude=17.4375, longitude=78.4483),
        dict(camera_id="CAM_002", location_name="Begumpet Junction",
             road_name="Begumpet Road", direction="NORTH_EAST_BOUND",
             latitude=17.4432, longitude=78.4556),
        dict(camera_id="CAM_003", location_name="Hitech City",
             road_name="HITEC City Road", direction="WEST_BOUND",
             latitude=17.4504, longitude=78.3806),
        dict(camera_id="CAM_004", location_name="Charminar",
             road_name="Charminar Road", direction="SOUTH_BOUND",
             latitude=17.3616, longitude=78.4747),
        dict(camera_id="CAM_005", location_name="Secunderabad Station",
             road_name="Station Road", direction="EAST_BOUND",
             latitude=17.4399, longitude=78.4983),
    ]
    for c in traj_cams:
        session.add(TrajectoryCamera(**c))
    session.commit()

    # ── Phase-4 detections ────────────────────────────────────────────────────
    dets = [
        # TS09AB1234 – normal route 4 hops
        dict(plate_number="TS09AB1234", camera_id="CAM_001",
             timestamp=_BASE,                          detection_confidence=0.96),
        dict(plate_number="TS09AB1234", camera_id="CAM_002",
             timestamp=_BASE + timedelta(minutes=8),   detection_confidence=0.94),
        dict(plate_number="TS09AB1234", camera_id="CAM_005",
             timestamp=_BASE + timedelta(minutes=20),  detection_confidence=0.91),
        # MH12XY5678 – fast (in blacklist)
        dict(plate_number="MH12XY5678", camera_id="CAM_003",
             timestamp=_BASE + timedelta(minutes=5),   detection_confidence=0.88),
        dict(plate_number="MH12XY5678", camera_id="CAM_004",
             timestamp=_BASE + timedelta(minutes=9),   detection_confidence=0.85),
        # DL01ZZ9999 – suspicious (in blacklist)
        dict(plate_number="DL01ZZ9999", camera_id="CAM_001",
             timestamp=_BASE,                          detection_confidence=0.79),
        dict(plate_number="DL01ZZ9999", camera_id="CAM_005",
             timestamp=_BASE + timedelta(minutes=1),   detection_confidence=0.80),
    ]
    for d in dets:
        session.add(Detection(**d))
    session.commit()

    # ── Phase-3 vehicle events ────────────────────────────────────────────────
    evts = [
        dict(plate_number="TS09AB1234", camera_id="CAM_001",
             timestamp=_BASE, vehicle_type="car", vehicle_confidence=0.95,
             plate_confidence=0.88, ocr_confidence=0.92),
        dict(plate_number="MH12XY5678", camera_id="CAM_003",
             timestamp=_BASE + timedelta(minutes=5), vehicle_type="motorcycle",
             vehicle_confidence=0.87, plate_confidence=0.80, ocr_confidence=0.82),
        dict(plate_number="DL01ZZ9999", camera_id="CAM_001",
             timestamp=_BASE, vehicle_type="car", vehicle_confidence=0.79,
             plate_confidence=0.75, ocr_confidence=0.45),   # low confidence
    ]
    for e in evts:
        session.add(VehicleEvent(**e))
    session.commit()

    yield session
    session.close()


@pytest.fixture(scope="module")
def client(db_session):
    """TestClient with DB dependency override."""
    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER
# ═══════════════════════════════════════════════════════════════════════════════

def _assert_ok(resp, expected_status=200):
    assert resp.status_code == expected_status, (
        f"Expected {expected_status}, got {resp.status_code}: {resp.text[:300]}"
    )
    return resp.json()


# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════

class TestHealth:
    def test_health_returns_running(self, client):
        data = _assert_ok(client.get("/health"))
        assert data["status"] == "running"

    def test_health_version_is_0_8(self, client):
        data = _assert_ok(client.get("/health"))
        assert data["version"] == "0.8.0"

    def test_health_has_db_field(self, client):
        data = _assert_ok(client.get("/health"))
        assert "database" in data
        assert data["database"] == "connected"

    def test_health_has_camera_count(self, client):
        data = _assert_ok(client.get("/health"))
        assert "total_cameras" in data
        assert data["total_cameras"] >= 5

    def test_health_has_detection_count(self, client):
        data = _assert_ok(client.get("/health"))
        assert "total_detections" in data
        assert data["total_detections"] >= 7

    def test_metadata_reload(self, client):
        data = _assert_ok(client.post("/metadata/reload"))
        assert data["status"] == "ok"


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 8 – VEHICLES
# ═══════════════════════════════════════════════════════════════════════════════

class TestVehicles:
    def test_list_vehicles_returns_200(self, client):
        data = _assert_ok(client.get("/vehicles"))
        assert "vehicles" in data
        assert "total" in data

    def test_list_vehicles_has_correct_fields(self, client):
        data = _assert_ok(client.get("/vehicles"))
        assert len(data["vehicles"]) > 0
        v = data["vehicles"][0]
        required = {
            "plate_number", "vehicle_type", "confidence",
            "first_seen", "last_seen", "camera_count",
            "total_sightings", "status", "is_blacklisted",
        }
        assert required.issubset(v.keys()), f"Missing fields: {required - v.keys()}"

    def test_list_vehicles_contains_seeded_plates(self, client):
        data = _assert_ok(client.get("/vehicles"))
        plates = {v["plate_number"] for v in data["vehicles"]}
        assert "TS09AB1234" in plates
        assert "MH12XY5678" in plates
        assert "DL01ZZ9999" in plates

    def test_list_vehicles_blacklist_flag(self, client):
        data = _assert_ok(client.get("/vehicles"))
        by_plate = {v["plate_number"]: v for v in data["vehicles"]}
        # MH12XY5678 and DL01ZZ9999 are in the demo blacklist
        if "MH12XY5678" in by_plate:
            assert by_plate["MH12XY5678"]["is_blacklisted"] is True

    def test_list_vehicles_pagination(self, client):
        data = _assert_ok(client.get("/vehicles?limit=1&offset=0"))
        assert len(data["vehicles"]) == 1

    def test_get_vehicle_detail_200(self, client):
        data = _assert_ok(client.get("/vehicles/TS09AB1234"))
        assert data["plate_number"] == "TS09AB1234"
        assert data["vehicle_type"] == "car"
        assert data["camera_count"] >= 2

    def test_get_vehicle_detail_case_insensitive(self, client):
        data = _assert_ok(client.get("/vehicles/ts09ab1234"))
        assert data["plate_number"] == "TS09AB1234"

    def test_get_vehicle_detail_404(self, client):
        resp = client.get("/vehicles/XX99ZZ0000")
        assert resp.status_code == 404
        body = resp.json()
        assert "error" in body        # Phase 8 global handler format

    def test_get_vehicle_detail_has_all_required_fields(self, client):
        data = _assert_ok(client.get("/vehicles/TS09AB1234"))
        required = {
            "plate_number", "vehicle_type", "confidence",
            "first_seen", "last_seen", "camera_count",
            "total_sightings", "status",
        }
        assert required.issubset(data.keys())

    def test_vehicle_status_values_are_valid(self, client):
        data = _assert_ok(client.get("/vehicles"))
        valid = {"active", "suspicious", "impossible", "unknown"}
        for v in data["vehicles"]:
            assert v["status"] in valid, f"Invalid status {v['status']!r}"


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 8 – TRAJECTORY
# ═══════════════════════════════════════════════════════════════════════════════

class TestTrajectory:
    def test_trajectory_200(self, client):
        data = _assert_ok(client.get("/api/trajectory/TS09AB1234"))
        assert data["plate_number"] == "TS09AB1234"

    def test_trajectory_has_required_fields(self, client):
        data = _assert_ok(client.get("/api/trajectory/TS09AB1234"))
        required = {
            "plate_number", "total_observations", "total_distance_km",
            "travel_duration_min", "average_speed_kmh",
            "anomaly_score", "overall_status",
            "first_seen", "last_seen", "cameras_visited",
            "stops", "hops", "data_mode",
        }
        assert required.issubset(data.keys())

    def test_trajectory_stops_have_gps(self, client):
        data = _assert_ok(client.get("/api/trajectory/TS09AB1234"))
        assert len(data["stops"]) >= 3
        for stop in data["stops"]:
            assert "latitude" in stop and "longitude" in stop
            assert "camera_id" in stop and "location" in stop
            assert "timestamp" in stop

    def test_trajectory_hops_have_metrics(self, client):
        data = _assert_ok(client.get("/api/trajectory/TS09AB1234"))
        assert len(data["hops"]) >= 2
        for hop in data["hops"]:
            assert "from_camera" in hop
            assert "to_camera" in hop
            assert "distance_km" in hop
            assert "duration_min" in hop
            assert "speed_kmh" in hop
            assert "anomaly" in hop

    def test_trajectory_anomaly_score_range(self, client):
        data = _assert_ok(client.get("/api/trajectory/TS09AB1234"))
        assert 0.0 <= data["anomaly_score"] <= 1.0

    def test_trajectory_status_is_valid(self, client):
        data = _assert_ok(client.get("/api/trajectory/TS09AB1234"))
        assert data["overall_status"] in {"NORMAL", "FAST", "SUSPICIOUS", "IMPOSSIBLE"}

    def test_trajectory_data_mode_label(self, client):
        data = _assert_ok(client.get("/api/trajectory/TS09AB1234"))
        assert "DEMO" in data["data_mode"] or "SIMULATED" in data["data_mode"]

    def test_trajectory_404_unknown_plate(self, client):
        resp = client.get("/api/trajectory/XX99ZZ0000")
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_trajectory_suspicious_plate(self, client):
        data = _assert_ok(client.get("/api/trajectory/DL01ZZ9999"))
        # DL01ZZ9999 jumps CAM_001→CAM_005 in 1 min — suspicious/impossible
        assert data["overall_status"] in {"SUSPICIOUS", "IMPOSSIBLE", "FAST"}
        assert data["anomaly_score"] > 0.0

    # Phase 4 endpoint must still work unchanged
    def test_phase4_trajectory_not_broken(self, client):
        data = _assert_ok(client.get("/trajectory/TS09AB1234"))
        assert "plate_number" in data
        assert "trajectory" in data
        assert "statistics" in data


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 8 – ANALYTICS
# ═══════════════════════════════════════════════════════════════════════════════

class TestAnalytics:
    def test_analytics_unified_200(self, client):
        data = _assert_ok(client.get("/analytics"))
        assert "total_vehicles" in data

    def test_analytics_unified_kpi_fields(self, client):
        data = _assert_ok(client.get("/analytics"))
        required = {
            "total_vehicles", "total_unique_plates", "total_cameras",
            "active_alerts", "suspicious_vehicles",
            "vehicle_distribution", "traffic_density_label",
            "average_speed_kmh", "congestion_score",
            "congestion_zones", "traffic_trends",
            "generated_at", "window_hours",
        }
        assert required.issubset(data.keys())

    def test_analytics_vehicle_distribution_structure(self, client):
        data = _assert_ok(client.get("/analytics"))
        for item in data["vehicle_distribution"]:
            assert "category" in item
            assert "count" in item
            assert "percentage" in item

    def test_analytics_traffic_trends_has_24_hours(self, client):
        data = _assert_ok(client.get("/analytics"))
        assert len(data["traffic_trends"]) == 24
        for pt in data["traffic_trends"]:
            assert 0 <= pt["hour"] <= 23

    def test_analytics_window_hours_param(self, client):
        data = _assert_ok(client.get("/analytics?window_hours=1"))
        assert data["window_hours"] == 1

    def test_analytics_counts_match_seeded_data(self, client):
        data = _assert_ok(client.get("/analytics"))
        assert data["total_vehicles"] >= 7      # 7 detections seeded
        assert data["total_unique_plates"] >= 3 # 3 plates seeded

    def test_analytics_density_label_is_valid(self, client):
        data = _assert_ok(client.get("/analytics"))
        assert data["traffic_density_label"] in {"LOW", "MEDIUM", "HIGH", "SEVERE"}

    def test_analytics_congestion_score_non_negative(self, client):
        data = _assert_ok(client.get("/analytics"))
        assert data["congestion_score"] >= 0.0

    # Phase 5 + Phase 7 endpoints must still work
    def test_phase5_overview_not_broken(self, client):
        data = _assert_ok(client.get("/analytics/overview"))
        assert "total_detections" in data

    def test_phase7_summary_not_broken(self, client):
        data = _assert_ok(client.get("/analytics/summary"))
        assert "total_detections" in data

    def test_phase5_traffic_density_not_broken(self, client):
        data = _assert_ok(client.get("/analytics/traffic-density"))
        assert "items" in data

    def test_phase5_congestion_not_broken(self, client):
        data = _assert_ok(client.get("/analytics/congestion"))
        assert "items" in data

    def test_phase5_peak_hours_not_broken(self, client):
        data = _assert_ok(client.get("/analytics/peak-hours"))
        assert "hours" in data
        assert len(data["hours"]) == 24


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 8 – ALERTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestAlerts:
    def test_alerts_200(self, client):
        data = _assert_ok(client.get("/alerts"))
        assert "alerts" in data

    def test_alerts_has_required_top_level_fields(self, client):
        data = _assert_ok(client.get("/alerts"))
        required = {
            "total_alerts", "critical_count", "warning_count",
            "info_count", "alerts", "demo_disclaimer", "generated_at",
        }
        assert required.issubset(data.keys())

    def test_alert_items_have_alert_id(self, client):
        data = _assert_ok(client.get("/alerts"))
        for alert in data["alerts"]:
            assert "alert_id" in alert, "alert_id missing from alert item"
            assert len(alert["alert_id"]) == 36  # UUID format

    def test_alert_items_have_required_fields(self, client):
        data = _assert_ok(client.get("/alerts"))
        required_fields = {
            "alert_id", "alert_type", "severity",
            "timestamp", "message", "status", "demo_data",
        }
        for alert in data["alerts"]:
            assert required_fields.issubset(alert.keys()), (
                f"Missing fields in alert: {required_fields - alert.keys()}"
            )

    def test_alert_severity_values_are_valid(self, client):
        data = _assert_ok(client.get("/alerts"))
        valid = {"INFO", "WARNING", "CRITICAL"}
        for alert in data["alerts"]:
            assert alert["severity"] in valid

    def test_alert_status_field_defaults_to_open(self, client):
        data = _assert_ok(client.get("/alerts"))
        for alert in data["alerts"]:
            assert alert["status"] == "open"

    def test_alert_counts_are_consistent(self, client):
        data = _assert_ok(client.get("/alerts"))
        computed = (
            data["critical_count"] + data["warning_count"] + data["info_count"]
        )
        assert computed == data["total_alerts"]

    def test_alerts_limit_param(self, client):
        data = _assert_ok(client.get("/alerts?limit=2"))
        assert data["total_alerts"] <= 2

    def test_blacklisted_plates_generate_alerts(self, client):
        # DL01ZZ9999 and MH12XY5678 are in blacklist.json and were seeded
        data = _assert_ok(client.get("/alerts"))
        bl_alerts = [
            a for a in data["alerts"]
            if a["alert_type"] == "BLACKLISTED_VEHICLE"
        ]
        # At least one blacklist alert should fire for our seeded plates
        plates_alerted = {a.get("plate_number") for a in bl_alerts}
        blacklisted_seeded = {"MH12XY5678", "DL01ZZ9999"}
        assert bool(plates_alerted & blacklisted_seeded), (
            "Expected at least one blacklist alert for seeded plates, got: "
            + str(plates_alerted)
        )

    def test_blacklist_alerts_marked_demo(self, client):
        data = _assert_ok(client.get("/alerts"))
        for alert in data["alerts"]:
            if alert["alert_type"] == "BLACKLISTED_VEHICLE":
                assert alert["demo_data"] is True, (
                    "Blacklist alert must have demo_data=True"
                )


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 8 – CAMERAS
# ═══════════════════════════════════════════════════════════════════════════════

class TestCameras:
    def test_api_cameras_200(self, client):
        data = _assert_ok(client.get("/api/cameras"))
        assert isinstance(data, list)

    def test_api_cameras_has_metadata_fields(self, client):
        data = _assert_ok(client.get("/api/cameras"))
        assert len(data) > 0
        cam = data[0]
        required = {
            "camera_id", "location_name", "latitude",
            "longitude", "detections_last_hour",
        }
        assert required.issubset(cam.keys())

    def test_api_cameras_gps_coordinates_are_floats(self, client):
        data = _assert_ok(client.get("/api/cameras"))
        for cam in data:
            assert isinstance(cam["latitude"],  float)
            assert isinstance(cam["longitude"], float)

    # Phase 3 camera endpoint must still work
    def test_phase3_cameras_not_broken(self, client):
        data = _assert_ok(client.get("/cameras"))
        assert isinstance(data, list)
        assert len(data) >= 5

    def test_phase3_trajectory_cameras_not_broken(self, client):
        data = _assert_ok(client.get("/trajectory/cameras"))
        assert isinstance(data, list)
        assert len(data) >= 5


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 8 – POST /process
# ═══════════════════════════════════════════════════════════════════════════════

class TestProcessEndpoint:
    def _make_image_bytes(self) -> bytes:
        """Generate a minimal valid JPEG in memory using numpy + cv2."""
        try:
            import cv2
            img = np.zeros((480, 640, 3), dtype=np.uint8)
            img[100:380, 80:560] = (70, 70, 70)  # car body
            _, buf = cv2.imencode(".jpg", img)
            return buf.tobytes()
        except Exception:
            # Fallback: minimal 1x1 white JPEG (valid JPEG bytes)
            return (
                b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01"
                b"\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07"
                b"\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14"
                b"\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444"
                b"\x1f'9=82<.342\x1edL\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t\t"
                b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4"
                b"\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00"
                b"\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
                b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xf5\xff\xd9"
            )

    def test_process_image_200(self, client):
        img_bytes = self._make_image_bytes()
        resp = client.post(
            "/process",
            files  = {"file": ("test_car.jpg", io.BytesIO(img_bytes), "image/jpeg")},
            data   = {"camera_id": "CAM_001"},
        )
        data = _assert_ok(resp)
        assert data["status"] == "ok"

    def test_process_image_has_frontend_summary_fields(self, client):
        img_bytes = self._make_image_bytes()
        resp = client.post(
            "/process",
            files  = {"file": ("test.jpg", io.BytesIO(img_bytes), "image/jpeg")},
            data   = {"camera_id": "CAM_001"},
        )
        data = _assert_ok(resp)
        required = {
            "status", "source_file", "camera_id", "timestamp",
            "latitude", "longitude",
            "total_vehicles", "total_plates",
            "low_confidence_count", "plates_detected", "warnings",
        }
        assert required.issubset(data.keys())

    def test_process_image_plates_detected_is_list(self, client):
        img_bytes = self._make_image_bytes()
        resp = client.post(
            "/process",
            files = {"file": ("test.jpg", io.BytesIO(img_bytes), "image/jpeg")},
            data  = {"camera_id": "CAM_001"},
        )
        data = _assert_ok(resp)
        assert isinstance(data["plates_detected"], list)

    def test_process_image_gps_populated(self, client):
        img_bytes = self._make_image_bytes()
        resp = client.post(
            "/process",
            files = {"file": ("test.jpg", io.BytesIO(img_bytes), "image/jpeg")},
            data  = {"camera_id": "CAM_001"},
        )
        data = _assert_ok(resp)
        # CAM_001 is in cameras.json — GPS should be real coordinates
        assert data["latitude"]  != 0.0 or data["longitude"] != 0.0

    def test_process_invalid_timestamp_422(self, client):
        img_bytes = self._make_image_bytes()
        resp = client.post(
            "/process",
            files = {"file": ("test.jpg", io.BytesIO(img_bytes), "image/jpeg")},
            data  = {"camera_id": "CAM_001", "timestamp": "not-a-date"},
        )
        assert resp.status_code == 422

    def test_process_image_missing_file_422(self, client):
        resp = client.post("/process", data={"camera_id": "CAM_001"})
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# CORS
# ═══════════════════════════════════════════════════════════════════════════════

class TestCORS:
    def test_cors_preflight_react_dev(self, client):
        resp = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        # FastAPI/Starlette returns 200 for OPTIONS when CORS matches
        assert resp.status_code in (200, 204)

    def test_cors_allow_origin_header_present(self, client):
        resp = client.get(
            "/health",
            headers={"Origin": "http://localhost:3000"},
        )
        assert "access-control-allow-origin" in resp.headers

    def test_cors_vite_port_allowed(self, client):
        resp = client.get(
            "/health",
            headers={"Origin": "http://localhost:5173"},
        )
        # Should not be blocked
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# BACKWARD-COMPATIBILITY – ALL PHASE 2-7 ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestBackwardCompatibility:
    """Ensures all existing Phase 2-7 endpoints still return 200."""

    def test_get_events_empty(self, client):
        data = _assert_ok(client.get("/events"))
        assert isinstance(data, list)

    def test_get_detections_list(self, client):
        data = _assert_ok(client.get("/detections"))
        assert isinstance(data, list)
        assert len(data) >= 7

    def test_get_trajectory_cameras(self, client):
        data = _assert_ok(client.get("/trajectory/cameras"))
        assert len(data) >= 5

    def test_get_analytics_vehicles_p7(self, client):
        data = _assert_ok(client.get("/analytics/vehicles"))
        assert "breakdown" in data

    def test_get_analytics_cameras_p7(self, client):
        data = _assert_ok(client.get("/analytics/cameras"))
        assert "cameras" in data

    def test_get_analytics_hourly_p7(self, client):
        data = _assert_ok(client.get("/analytics/hourly"))
        assert "hours" in data

    def test_vehicle_history_p3(self, client):
        data = _assert_ok(client.get("/vehicles/TS09AB1234/history"))
        assert data["plate_number"] == "TS09AB1234"
        assert data["total_detections"] >= 3

    def test_phase7_vehicle_trajectory_alias(self, client):
        data = _assert_ok(client.get("/vehicle/TS09AB1234/trajectory"))
        assert "plate" in data
        assert "data_mode" in data

    def test_error_response_format(self, client):
        """Global error handler returns {error, status, path}."""
        resp = client.get("/vehicles/XX99ZZ0000")
        assert resp.status_code == 404
        body = resp.json()
        assert "error" in body
        assert "status" in body
        assert body["status"] == 404
