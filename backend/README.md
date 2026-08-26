# SIH26127 — City-Wide AI Engine for Multi-Camera ANPR Trajectory Tracking and Urban Traffic Analytics

**Smart India Hackathon 2026 | Problem Statement SIH26127**

> **DEMO MODE NOTICE**  
> Camera metadata, blacklist entries, and multi-camera trajectory data in this repository are
> **SIMULATED** and created solely for development and demonstration purposes.  
> They do not represent real CCTV infrastructure, real law-enforcement records, or real surveillance data.

---

## Problem Statement Coverage

| SIH26127 Requirement | Implementation |
|----------------------|----------------|
| Multi-camera ANPR | `POST /process/image`, `POST /process/video` → vehicle + plate detection + OCR across any camera |
| Plate normalisation | `normalise_plate()` in `ingest_service.py` |
| Trajectory tracking | `GET /vehicle/{plate}/trajectory`, `GET /trajectory/{plate}` with Haversine metrics |
| Urban traffic analytics | `/analytics/summary`, `/analytics/vehicles`, `/analytics/cameras`, `/analytics/hourly` |
| Congestion detection | Traffic density + congestion score per camera |
| Alert engine | `GET /alerts` — 6 alert types including blacklist and anomaly detection |
| City-wide camera network | 15 simulated Hyderabad cameras in `data/metadata/cameras.json` |

---

## Architecture

```
                    ┌─────────────────────────────────┐
                    │         FastAPI Backend          │
                    │  app/main.py  (31 endpoints)     │
                    └─────────┬───────────────┬────────┘
                              │               │
               ┌──────────────▼──┐     ┌──────▼──────────────┐
               │  AI/ML Pipeline │     │   Database Layer     │
               │                 │     │                      │
               │ YOLOv8n         │     │ SQLite (dev)         │
               │ (vehicle detect)│     │ PostgreSQL (prod)    │
               │                 │     │                      │
               │ YOLO Plate Model│     │ Tables:              │
               │ (+ contour fallb│     │  cameras             │
               │                 │     │  vehicle_events      │
               │ EasyOCR         │     │  trajectory_cameras  │
               │ (plate OCR)     │     │  detections          │
               └──────────────┬──┘     └──────┬──────────────┘
                              │               │
               ┌──────────────▼───────────────▼──────────────┐
               │               Analytics & Alerts            │
               │                                             │
               │  Trajectory Engine (Haversine + anomaly)    │
               │  Traffic Density / Congestion Score         │
               │  Alert Feed (blacklist + trajectory + OCR)  │
               └─────────────────────────────────────────────┘
```

---

## Installation

### Requirements

- Python 3.10+
- pip

### Setup

```bash
# 1. Clone / navigate to backend
cd backend/

# 2. Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/macOS

# 3. Install dependencies
pip install -r requirements.txt

# 4. Seed the database
python -m app.seed_data        # Phase-3 ANPR cameras (required for /anpr/detect)
python -m app.seed_trajectory  # Phase-4 trajectory cameras + sample detections

# 5. Start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Swagger UI

Open **http://127.0.0.1:8000/docs** in your browser after starting the server.

---

## Dataset Folder Structure

```
backend/data/
├── raw/
│   ├── traffic_images/        ← Place .jpg / .png traffic photos here
│   ├── traffic_videos/        ← Place .mp4 / .avi traffic videos here
│   └── license_plates/        ← Place plate crop images here
├── processed/                 ← Auto-generated intermediate outputs
├── input/                     ← Uploaded files (auto-managed)
├── output/                    ← Annotated output images
└── metadata/
    ├── cameras.json           ← [DEMO] 15 Hyderabad camera definitions
    └── blacklist.json         ← [DEMO] 5 simulated blacklisted plates
```

### How to add sample images and videos

1. Place any `.jpg` / `.png` traffic photograph in `data/raw/traffic_images/`
2. Place any `.mp4` / `.avi` traffic video in `data/raw/traffic_videos/`
3. Use the API or demo pipeline — files are not auto-processed on startup

**You do not need large datasets.** Even a single traffic photograph works for testing.

### Where to find free sample images

- [Google Open Images](https://storage.googleapis.com/openimages/web/index.html) — search "car", "traffic"
- [Unsplash](https://unsplash.com/s/photos/traffic) — free high-res traffic photos
- [COCO Dataset](https://cocodataset.org/) — vehicle images with annotations

---

## How to Run the Backend

```bash
cd backend/
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The server:
- Creates the SQLite database automatically on first run
- Auto-downloads `yolov8n.pt` on first detection request
- Attempts to download `license_plate_detector.pt` on first plate detection (falls back to OpenCV contours if download fails)
- Serves Swagger UI at `/docs` and ReDoc at `/redoc`

---

## How to Run the Demo Pipeline

```bash
cd backend/
python scripts/demo_pipeline.py
```

The script runs 7 end-to-end tests without needing a running server:

| Test | What It Verifies |
|------|-----------------|
| TEST 1 | Image → Vehicle Detection (YOLOv8n) |
| TEST 2 | Image → ANPR (plate detect + OCR + normalisation) |
| TEST 3 | Video → Frame sampling → Detection |
| TEST 4 | Detection → Database storage (Phase-3 + Phase-4 tables) |
| TEST 5 | Plate search → Trajectory reconstruction |
| TEST 6 | Stored detections → Traffic analytics |
| TEST 7 | Blacklisted plate → Alert fired |

If no real images/videos are present the script generates synthetic test files automatically.

**Options:**

```bash
python scripts/demo_pipeline.py --no-video               # skip video test (faster)
python scripts/demo_pipeline.py --image car.jpg          # use a specific image
python scripts/demo_pipeline.py --plate MH12XY5678       # use a different demo plate
python scripts/demo_pipeline.py --camera CAM_003         # use a different camera
python scripts/demo_pipeline.py --frame-skip 15          # sample every 15th frame
```

---

## API Reference

### System

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness probe |
| `POST` | `/metadata/reload` | Reload cameras.json / blacklist.json |

### ANPR (Phase 2–3)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/anpr/detect` | Upload image → ANPR → DB event |
| `GET` | `/anpr/output/{filename}` | Download annotated image |

### Cameras (Phase 3)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/cameras` | Register a camera |
| `GET` | `/cameras` | List all cameras |
| `GET` | `/cameras/{camera_id}` | Get one camera |
| `PUT` | `/cameras/{camera_id}` | Update camera |
| `DELETE` | `/cameras/{camera_id}` | Delete camera |

### Events & Vehicles (Phase 3)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/events` | Query events (plate / camera / time filters) |
| `GET` | `/events/{event_id}` | Get one event |
| `GET` | `/vehicles/{plate}/history` | Chronological detection history |

### Trajectory (Phase 4)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/trajectory/cameras` | Register a trajectory camera |
| `GET` | `/trajectory/cameras` | List all trajectory cameras |
| `GET` | `/trajectory/cameras/{camera_id}` | Get one trajectory camera |
| `POST` | `/detections` | Store an ANPR detection |
| `GET` | `/detections` | Query detections |
| `GET` | `/trajectory/{plate}` | Reconstruct trajectory (Phase-4 full response) |

### Analytics (Phase 5)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/analytics/overview` | Dashboard KPIs |
| `GET` | `/analytics/traffic-density` | Vehicle count + density per camera |
| `GET` | `/analytics/congestion` | Avg speed + congestion level per camera |
| `GET` | `/analytics/peak-hours` | 24-hour traffic distribution |
| `GET` | `/analytics/alerts` | Phase-5 congestion + anomaly alerts |

### Ingestion — Phase 7

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/process/image` | Traffic image → full pipeline → structured JSON |
| `POST` | `/process/video` | Traffic video → sampled frames → structured JSON |

### Vehicle & Analytics — Phase 7

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/vehicle/{plate}/trajectory` | Demo trajectory (DEMO/SIMULATED label) |
| `GET` | `/analytics/summary` | Dashboard KPI summary |
| `GET` | `/analytics/vehicles` | Vehicle type breakdown + congestion score |
| `GET` | `/analytics/cameras` | Per-camera stats |
| `GET` | `/analytics/hourly` | Hourly traffic distribution |
| `GET` | `/alerts` | Combined alert feed (6 alert types) |

---

## API Examples

### Process a traffic image

```bash
curl -X POST http://localhost:8000/process/image \
  -F "file=@data/raw/traffic_images/car001.jpg" \
  -F "camera_id=CAM_001"
```

```json
{
  "status": "ok",
  "source_file": "car001.jpg",
  "camera_id": "CAM_001",
  "timestamp": "2026-08-24T10:30:00+00:00",
  "latitude": 17.4375,
  "longitude": 78.4483,
  "total_vehicles": 2,
  "total_plates": 2,
  "low_confidence_plates": 0,
  "detections": [
    {
      "vehicle_type": "car",
      "vehicle_confidence": 0.94,
      "plate_number": "TS08AB1234",
      "plate_raw_text": "ts 08 ab 1234",
      "ocr_confidence": 0.87,
      "plate_normalised": true,
      "low_confidence": false,
      "frame_number": 0,
      "camera_id": "CAM_001",
      "event_id": 1,
      "detection_id": 11
    }
  ]
}
```

### Get demo trajectory

```bash
curl http://localhost:8000/vehicle/TS09AB1234/trajectory
```

```json
{
  "data_mode": "DEMO / SIMULATED TRAJECTORY",
  "disclaimer": "This trajectory is reconstructed from seeded or uploaded demo data...",
  "plate": "TS09AB1234",
  "total_observations": 4,
  "status": "MovementStatus.NORMAL",
  "statistics": {
    "total_detections": 4,
    "total_hops": 3,
    "total_distance_km": 5.23,
    "total_duration_minutes": 30.0,
    "average_speed_kmh": 10.46,
    "cameras_visited": ["CAM_001", "CAM_002", "CAM_005", "CAM_014"]
  },
  "trajectory": [...]
}
```

### Get analytics summary

```bash
curl http://localhost:8000/analytics/summary
```

```json
{
  "total_active_cameras": 15,
  "total_detections": 244,
  "suspicious_vehicle_count": 1,
  "congested_locations_count": 0,
  "total_unique_plates": 3
}
```

### Get alerts

```bash
curl "http://localhost:8000/alerts?limit=10"
```

```json
{
  "total_alerts": 3,
  "critical_count": 1,
  "warning_count": 1,
  "info_count": 1,
  "demo_disclaimer": "Alerts marked demo_data=true are based on SIMULATED data...",
  "alerts": [
    {
      "alert_type": "BLACKLISTED_VEHICLE",
      "severity": "CRITICAL",
      "camera_id": "CAM_001",
      "plate_number": "TS08AB1234",
      "message": "[DEMO] Blacklisted plate TS08AB1234 detected at CAM_001...",
      "demo_data": true
    }
  ]
}
```

---

## Demo Mode Explanation

This project uses three distinct types of data:

| Type | How to identify | Source |
|------|----------------|--------|
| **Real model inference** | No special label | YOLOv8n / EasyOCR running on actual uploaded images |
| **Simulated camera metadata** | `"_note": "DEMO / SIMULATED DATA"` in JSON file | `data/metadata/cameras.json` |
| **Simulated trajectory data** | `"data_mode": "DEMO / SIMULATED TRAJECTORY"` in API response | `app/seed_trajectory.py` |
| **Demo blacklist** | `"demo_data": true` on every alert | `data/metadata/blacklist.json` |

The demo blacklist contains 5 fictional plate numbers created only for testing the alert pipeline. **They are not real law-enforcement records and must never be treated as such.**

---

## Known Limitations

1. **OCR accuracy** — EasyOCR performance degrades on low-resolution, blurry, angled, or night-time plates. Low-confidence reads are flagged with `"low_confidence": true`.
2. **Plate detector** — the `license_plate_detector.pt` model auto-downloads on first run. If this fails, an OpenCV contour heuristic is used (lower accuracy on unusual plate styles).
3. **No live camera feed** — trajectory data is reconstructed from uploaded images/videos and seed data only. There is no real-time RTSP/WebSocket ingestion in Phase 7.
4. **SQLite** — suitable for development and demo. Switch to PostgreSQL for production by updating `DATABASE_URL` in `app/config.py`.
5. **CPU inference** — the torch build is CPU-only. GPU inference requires swapping to a CUDA-enabled torch wheel.
6. **Video processing time** — scales linearly with `total_frames / frame_skip`. Large 1080p videos at `frame_skip=1` can take many minutes on CPU.

---

## Phase Summary

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 | Project scaffolding | ✓ Complete |
| Phase 2 | Vehicle + plate detection + OCR | ✓ Complete |
| Phase 3 | Database + camera event management | ✓ Complete |
| Phase 4 | Trajectory reconstruction engine | ✓ Complete |
| Phase 5 | Traffic analytics API | ✓ Complete |
| Phase 6 | (Architecture consolidation) | ✓ Complete |
| **Phase 7** | **Dataset integration + end-to-end pipeline** | **✓ Complete** |
| Phase 8 | Live feed + ReID + production deployment | Recommended next |

---

## Project Structure

```
Yuva_SIH26127/
├── backend/
│   ├── app/
│   │   ├── main.py              ← FastAPI app (38 endpoints, all phases)
│   │   ├── config.py            ← Configuration
│   │   ├── database.py          ← SQLAlchemy setup
│   │   ├── models/              ← ORM models + ML wrappers
│   │   ├── schemas/             ← Pydantic schemas
│   │   ├── services/            ← Business logic
│   │   ├── trajectory/          ← Haversine + anomaly engine
│   │   └── utils/               ← Image utils + metadata loader
│   ├── data/
│   │   ├── raw/                 ← Sample traffic images/videos (not committed)
│   │   ├── metadata/            ← cameras.json, blacklist.json
│   │   └── traffic.db           ← SQLite (not committed)
│   ├── models/                  ← Model weights (not committed)
│   ├── scripts/
│   │   └── demo_pipeline.py     ← End-to-end demo runner
│   ├── tests/                   ← pytest test suite
│   ├── requirements.txt
│   └── README.md
└── frontend/                    ← React dashboard (separate)
```

---

## Phase 8 Testing

**Phase 8 — Backend Integration & API Readiness**  
API version: `0.8.0` | 38 total endpoints | Frontend-ready for UrbanEye AI React dashboard

### Prerequisites

```bash
cd backend/

# 1. Create and activate virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/macOS

# 2. Install all dependencies
pip install -r requirements.txt

# 3. Seed the database (required before testing)
python -m app.seed_data        # Phase-3 ANPR cameras
python -m app.seed_trajectory  # Phase-4 trajectory cameras + sample detections

# 4. Start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Swagger UI: **http://127.0.0.1:8000/docs**  
ReDoc:       **http://127.0.0.1:8000/redoc**

---

### Run the automated test suite

```bash
# From backend/ directory (server does NOT need to be running)
pytest tests/test_phase8_integration.py -v

# Run all phases together
pytest tests/ -v

# Run a single class
pytest tests/test_phase8_integration.py::TestVehicles -v
pytest tests/test_phase8_integration.py::TestAlerts -v
pytest tests/test_phase8_integration.py::TestAnalytics -v
```

---

### Run the end-to-end demo pipeline

```bash
# Full 7-test demo (generates synthetic data automatically)
python scripts/demo_pipeline.py

# With options
python scripts/demo_pipeline.py --no-video
python scripts/demo_pipeline.py --plate MH12XY5678
python scripts/demo_pipeline.py --image data/raw/traffic_images/car001.jpg
```

---

### Manual curl testing — every Phase 8 endpoint

All commands assume the server is running at `http://localhost:8000`.

#### System

```bash
# Health check (Phase 8 — includes DB stats)
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "running",
  "version": "0.8.0",
  "api_phase": "Phase 8 – Backend Integration & API Readiness",
  "database": "connected",
  "total_cameras": 15,
  "total_detections": 10
}
```

```bash
# Reload metadata caches (after editing cameras.json / blacklist.json)
curl -X POST http://localhost:8000/metadata/reload
```

---

#### POST /process — Upload image (Phase 8 unified shorthand)

```bash
curl -X POST http://localhost:8000/process \
  -F "file=@data/raw/traffic_images/car001.jpg" \
  -F "camera_id=CAM_001"
```

Expected response:
```json
{
  "status": "ok",
  "pipeline_version": "8.0",
  "source_file": "car001.jpg",
  "camera_id": "CAM_001",
  "timestamp": "2026-08-24T10:30:00+00:00",
  "latitude": 17.4375,
  "longitude": 78.4483,
  "total_vehicles": 2,
  "total_plates": 2,
  "low_confidence_count": 0,
  "plates_detected": ["TS08AB1234", "MH12XY5678"],
  "annotated_image_url": "/static/output/car001_annotated.jpg",
  "warnings": []
}
```

With optional timestamp:
```bash
curl -X POST http://localhost:8000/process \
  -F "file=@data/raw/traffic_images/car001.jpg" \
  -F "camera_id=CAM_003" \
  -F "timestamp=2026-08-24T10:30:00"
```

---

#### POST /process/image — Phase 7 detailed ingestion (full detections array)

```bash
curl -X POST http://localhost:8000/process/image \
  -F "file=@data/raw/traffic_images/car001.jpg" \
  -F "camera_id=CAM_001"
```

#### POST /process/video — Video ingestion

```bash
curl -X POST http://localhost:8000/process/video \
  -F "file=@data/raw/traffic_videos/traffic01.mp4" \
  -F "camera_id=CAM_003" \
  -F "frame_skip=10"
```

---

#### GET /vehicles — Paginated vehicle list (Phase 8)

```bash
# All vehicles
curl http://localhost:8000/vehicles

# With pagination
curl "http://localhost:8000/vehicles?limit=10&offset=0"

# Filter by status
curl "http://localhost:8000/vehicles?status_filter=suspicious"
curl "http://localhost:8000/vehicles?status_filter=active"
curl "http://localhost:8000/vehicles?status_filter=impossible"
```

Expected response:
```json
{
  "total": 3,
  "vehicles": [
    {
      "plate_number": "TS09AB1234",
      "vehicle_type": "car",
      "confidence": 0.95,
      "first_seen": "2026-08-24T08:00:00+00:00",
      "last_seen": "2026-08-24T08:30:00+00:00",
      "camera_count": 4,
      "total_sightings": 4,
      "status": "active",
      "last_camera_id": "CAM_014",
      "last_location": "Paradise Circle",
      "is_blacklisted": false,
      "blacklist_reason": null
    }
  ],
  "generated_at": "2026-08-24T10:00:00+00:00"
}
```

---

#### GET /vehicles/{plate} — Single vehicle detail (Phase 8)

```bash
# Normal vehicle
curl http://localhost:8000/vehicles/TS09AB1234

# Suspicious/blacklisted vehicle
curl http://localhost:8000/vehicles/DL01ZZ9999

# Case-insensitive
curl http://localhost:8000/vehicles/ts09ab1234

# 404 example
curl http://localhost:8000/vehicles/XX99ZZ0000
```

404 error response format (Phase 8 global handler):
```json
{
  "error": "No detections found for plate 'XX99ZZ0000'.",
  "status": 404,
  "path": "/vehicles/XX99ZZ0000"
}
```

---

#### GET /api/trajectory/{plate} — Frontend trajectory (Phase 8)

```bash
# Normal route
curl http://localhost:8000/api/trajectory/TS09AB1234

# Fast movement
curl http://localhost:8000/api/trajectory/MH12XY5678

# Suspicious/impossible
curl http://localhost:8000/api/trajectory/DL01ZZ9999
```

Expected response shape:
```json
{
  "plate_number": "TS09AB1234",
  "total_observations": 4,
  "total_distance_km": 5.23,
  "travel_duration_min": 30.0,
  "average_speed_kmh": 10.46,
  "anomaly_score": 0.0,
  "overall_status": "NORMAL",
  "first_seen": "2026-08-24T08:00:00+00:00",
  "last_seen": "2026-08-24T08:30:00+00:00",
  "cameras_visited": ["CAM_001", "CAM_002", "CAM_005", "CAM_014"],
  "stops": [
    {
      "camera_id": "CAM_001",
      "location": "Ameerpet Junction",
      "road_name": "Ameerpet–Punjagutta Road",
      "direction": "NORTH_BOUND",
      "latitude": 17.4375,
      "longitude": 78.4483,
      "timestamp": "2026-08-24T08:00:00+00:00",
      "confidence": 0.96
    }
  ],
  "hops": [
    {
      "from_camera": "CAM_001",
      "to_camera": "CAM_002",
      "distance_km": 0.87,
      "duration_min": 8.0,
      "speed_kmh": 6.5,
      "anomaly": "NORMAL"
    }
  ],
  "data_mode": "DEMO / SIMULATED TRAJECTORY"
}
```

Anomaly score guide:
| Score | Status |
|-------|--------|
| `0.0` | NORMAL |
| `0.33` | FAST |
| `0.67` | SUSPICIOUS |
| `1.0` | IMPOSSIBLE |

---

#### GET /analytics — Unified dashboard payload (Phase 8)

```bash
# Default 24-hour window
curl http://localhost:8000/analytics

# Custom window
curl "http://localhost:8000/analytics?window_hours=1"
curl "http://localhost:8000/analytics?window_hours=168"
```

Expected response shape:
```json
{
  "total_vehicles": 244,
  "total_unique_plates": 12,
  "total_cameras": 15,
  "active_alerts": 3,
  "suspicious_vehicles": 1,
  "vehicle_distribution": [
    {"category": "car",         "count": 142, "percentage": 58.2},
    {"category": "motorcycle",  "count": 67,  "percentage": 27.5},
    {"category": "bus",         "count": 24,  "percentage": 9.8},
    {"category": "truck",       "count": 11,  "percentage": 4.5}
  ],
  "traffic_density_label": "MEDIUM",
  "average_speed_kmh": 28.4,
  "congestion_score": 0.02,
  "congestion_zones": [
    {
      "camera_id": "CAM_001",
      "location": "Ameerpet Junction",
      "latitude": 17.4375,
      "longitude": 78.4483,
      "vehicle_count": 12,
      "avg_speed_kmh": 18.5,
      "congestion_level": "HIGH"
    }
  ],
  "traffic_trends": [
    {"hour": 0,  "vehicle_count": 0},
    {"hour": 8,  "vehicle_count": 7},
    {"hour": 17, "vehicle_count": 3}
  ],
  "most_active_camera": "CAM_001",
  "most_active_location": "Ameerpet Junction",
  "generated_at": "2026-08-24T10:00:00+00:00",
  "window_hours": 24
}
```

---

#### GET /alerts — Combined alert feed (Phase 8)

```bash
# Default (50 alerts max)
curl http://localhost:8000/alerts

# Limit results
curl "http://localhost:8000/alerts?limit=5"
```

Expected response shape:
```json
{
  "total_alerts": 3,
  "critical_count": 1,
  "warning_count": 1,
  "info_count": 1,
  "alerts": [
    {
      "alert_id": "a1b2c3d4-...",
      "alert_type": "BLACKLISTED_VEHICLE",
      "severity": "CRITICAL",
      "plate_number": "TS08AB1234",
      "location": "Ameerpet Junction",
      "camera_id": "CAM_001",
      "timestamp": "2026-08-24T10:30:00+00:00",
      "message": "[DEMO] Blacklisted plate TS08AB1234 detected at CAM_001...",
      "status": "open",
      "demo_data": true
    }
  ],
  "demo_disclaimer": "Alerts marked demo_data=true are based on SIMULATED data...",
  "generated_at": "2026-08-24T10:00:00+00:00"
}
```

Alert types reference:
| `alert_type` | `severity` | Trigger |
|---|---|---|
| `BLACKLISTED_VEHICLE` | CRITICAL | Plate in demo blacklist seen in last 24h |
| `CONGESTION` | WARNING / CRITICAL | Camera with HIGH/SEVERE traffic density |
| `IMPOSSIBLE_TRAJECTORY` | CRITICAL | Speed > 200 km/h or negative time gap |
| `SUSPICIOUS_TRAJECTORY` | WARNING | Speed 120–200 km/h or anomalous hop |
| `LOW_CONFIDENCE_ANPR` | INFO | OCR confidence < 0.50 |
| `FREQUENT_SIGHTINGS` | WARNING | Same plate ≥ 10 times in 1 hour |

---

#### GET /api/cameras — Camera map data (Phase 8)

```bash
curl http://localhost:8000/api/cameras
```

Expected response:
```json
[
  {
    "camera_id": "CAM_001",
    "location_name": "Ameerpet Junction",
    "road_name": "Ameerpet–Punjagutta Road",
    "direction": "NORTH_BOUND",
    "latitude": 17.4375,
    "longitude": 78.4483,
    "detections_last_hour": 0
  }
]
```

---

#### Preserved Phase 2–7 endpoints (backward compatibility)

All existing endpoints continue to work unchanged:

```bash
# Phase 3 — ANPR
curl -X POST http://localhost:8000/anpr/detect \
  -F "file=@data/raw/traffic_images/car001.jpg" \
  -F "camera_id=CAM_001"

# Phase 3 — Camera CRUD
curl http://localhost:8000/cameras
curl http://localhost:8000/cameras/CAM_001

# Phase 3 — Events
curl "http://localhost:8000/events?plate_number=TS09AB1234"
curl "http://localhost:8000/events?camera_id=CAM_001&limit=10"

# Phase 3 — Vehicle history
curl http://localhost:8000/vehicles/TS09AB1234/history

# Phase 4 — Trajectory (full Haversine response)
curl http://localhost:8000/trajectory/TS09AB1234
curl http://localhost:8000/trajectory/cameras
curl "http://localhost:8000/detections?plate_number=TS09AB1234"

# Phase 5 — Analytics
curl http://localhost:8000/analytics/overview
curl "http://localhost:8000/analytics/traffic-density?window_hours=1"
curl "http://localhost:8000/analytics/congestion?window_hours=1"
curl http://localhost:8000/analytics/peak-hours

# Phase 7 — Extended
curl http://localhost:8000/analytics/summary
curl http://localhost:8000/analytics/vehicles
curl http://localhost:8000/analytics/cameras
curl http://localhost:8000/analytics/hourly
curl http://localhost:8000/vehicle/TS09AB1234/trajectory
```

---

### CORS configuration

The backend accepts cross-origin requests from these origins out of the box:

| Origin | Purpose |
|--------|---------|
| `http://localhost:3000` | React (CRA) dev server |
| `http://localhost:5173` | Vite dev server |
| `http://localhost:5174` | Vite alternative port |
| `http://localhost:8080` | Vue / webpack dev server |
| `https://urbaneye-ai.vercel.app` | Emergent Vercel deployment |
| `https://urbaneye-ai.netlify.app` | Emergent Netlify deployment |
| `https://*.vercel.app` | All Vercel preview deployments (regex) |

To add your Emergent deployment URL, edit `_ALLOWED_ORIGINS` in `app/main.py`.

---

### API response shapes — quick reference

| Endpoint | Key fields |
|----------|-----------|
| `GET /health` | `status`, `version`, `database`, `total_cameras`, `total_detections` |
| `POST /process` | `plates_detected[]`, `total_vehicles`, `annotated_image_url` |
| `GET /vehicles` | `total`, `vehicles[]{plate_number, vehicle_type, confidence, status, is_blacklisted}` |
| `GET /vehicles/{plate}` | `plate_number`, `vehicle_type`, `confidence`, `first_seen`, `last_seen`, `camera_count`, `status` |
| `GET /api/trajectory/{plate}` | `stops[]`, `hops[]`, `anomaly_score`, `overall_status`, `data_mode` |
| `GET /analytics` | `total_vehicles`, `vehicle_distribution[]`, `congestion_zones[]`, `traffic_trends[]` |
| `GET /alerts` | `alerts[]{alert_id, alert_type, severity, location, status}` |
| `GET /api/cameras` | `[]{camera_id, location_name, latitude, longitude, detections_last_hour}` |

Error responses always follow:
```json
{"error": "...", "status": 404, "path": "/vehicles/XX99ZZ0000"}
```

---

### Phase 8 — What changed from Phase 7

| Area | Phase 7 | Phase 8 |
|------|---------|---------|
| API version | `0.7.0` | `0.8.0` |
| Health endpoint | Simple `{status, version}` | Extended with DB stats |
| CORS | `allow_origins=["*"]` | Explicit origins + Vercel regex |
| Error responses | FastAPI default (varies) | Uniform `{error, status, path}` |
| Logging | None | Structured `%(asctime)s \| %(levelname)s \| %(name)s` |
| Vehicle list | Not available | `GET /vehicles` with pagination + status filter |
| Vehicle detail | Not available | `GET /vehicles/{plate}` with blacklist flag |
| Trajectory | Phase-4 internal schema | `GET /api/trajectory/{plate}` with `anomaly_score` + `stops[]` |
| Analytics | 5 separate endpoints | `GET /analytics` unified dashboard payload |
| Alerts | No `alert_id`, no `location` | `alert_id` UUID + `location` + `status` field |
| Cameras (map) | Phase-3 CRUD only | `GET /api/cameras` with `detections_last_hour` |
| Tests | Phases 3–4 only | Phase 8 integration: 50+ tests across all 38 routes |
