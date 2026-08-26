# SIH26127 — Phase 7 Implementation Notes

**Project:** City-Wide AI Engine for Multi-Camera ANPR Trajectory Tracking and Urban Traffic Analytics  
**Problem Statement:** SIH26127  
**Phase 7:** Dataset Integration & End-to-End Pipeline Verification  

---

## 1. Existing Architecture (Phases 1–6)

```
backend/
├── app/
│   ├── main.py                      ← FastAPI app + ALL routes (inline, no routers)
│   ├── config.py                    ← Paths, thresholds, DB URL, API metadata
│   ├── database.py                  ← SQLAlchemy engine, session, Base, init_db()
│   │
│   ├── models/                      ← ORM models (SQLAlchemy) + ML model wrappers
│   │   ├── camera.py                ← Camera table (Phase 3)
│   │   ├── vehicle_event.py         ← VehicleEvent table (Phase 3)
│   │   ├── trajectory_camera.py     ← TrajectoryCamera table (Phase 4)
│   │   ├── detection.py             ← Detection table (Phase 4)
│   │   ├── vehicle_detector.py      ← YOLOv8n wrapper (Phase 2)
│   │   ├── plate_detector.py        ← YOLO plate / contour fallback (Phase 2)
│   │   └── ocr_engine.py            ← EasyOCR / Tesseract wrapper (Phase 2)
│   │
│   ├── schemas/                     ← Pydantic request/response models
│   │   ├── anpr.py                  ← HealthResponse, ANPRResponse (Phase 2)
│   │   ├── camera.py                ← CameraCreate/Response/Update (Phase 3)
│   │   ├── vehicle_event.py         ← VehicleEvent schemas (Phase 3)
│   │   ├── trajectory.py            ← Trajectory / Detection schemas (Phase 4)
│   │   └── analytics.py             ← Analytics schemas (Phase 5)
│   │
│   ├── services/                    ← Business logic
│   │   ├── anpr_service.py          ← Full ANPR pipeline orchestration (Phase 2-3)
│   │   ├── camera_service.py        ← Camera CRUD (Phase 3)
│   │   ├── event_service.py         ← VehicleEvent CRUD (Phase 3)
│   │   ├── detection_service.py     ← Detection CRUD (Phase 4)
│   │   ├── trajectory_camera_service.py ← TrajectoryCamera CRUD (Phase 4)
│   │   ├── image_service.py         ← Upload save/cleanup (Phase 2)
│   │   └── analytics_service.py     ← Analytics queries (Phase 5)
│   │
│   ├── trajectory/                  ← Trajectory engine
│   │   ├── engine.py                ← reconstruct() – Haversine + anomaly (Phase 4)
│   │   ├── haversine.py             ← Great-circle distance math (Phase 4)
│   │   └── anomaly.py               ← Movement classifier NORMAL/FAST/SUSPICIOUS/IMPOSSIBLE (Phase 4)
│   │
│   └── utils/
│       └── image_utils.py           ← OpenCV annotation helpers (Phase 2)
│
├── data/
│   ├── input/                       ← Uploaded images (Phase 2)
│   ├── output/                      ← Annotated images (Phase 2)
│   └── traffic.db                   ← SQLite database (created on startup)
│
├── models/                          ← Model weight files (.pt)
└── requirements.txt
```

### Database Tables

| Table | Phase | Purpose |
|-------|-------|---------|
| `cameras` | 3 | Registered ANPR cameras with GPS |
| `vehicle_events` | 3 | Every ANPR detection event from `/anpr/detect` |
| `trajectory_cameras` | 4 | Extended camera metadata for trajectory engine |
| `detections` | 4 | Raw plate detections feeding the trajectory engine |

### Detection Pipeline (Pre-Phase 7)

```
POST /anpr/detect  (upload image + camera_id)
  ↓
VehicleDetector.detect()     [YOLOv8n – car/motorcycle/bus/truck]
  ↓
PlateDetector.detect()       [YOLO plate model / OpenCV contour fallback]
  ↓
OCREngine.read_plate()       [EasyOCR → cleaned text]
  ↓
plate-to-vehicle matching    [centroid inside vehicle bbox]
  ↓
create_event()               [→ vehicle_events table]
  ↓
annotate_image()             [save annotated JPEG]
  ↓
ANPRResponseV3               [JSON with event_id per detection]
```

---

## 2. Phase 7 — What Was Added

### 2.1 New Folders

```
data/
├── raw/
│   ├── traffic_images/      ← Drop .jpg/.png traffic photos here
│   ├── traffic_videos/      ← Drop .mp4/.avi traffic videos here
│   └── license_plates/      ← Drop plate crop images here
├── processed/               ← Intermediate outputs (auto-cleaned)
└── metadata/
    ├── cameras.json         ← 15 DEMO camera definitions (Hyderabad)
    └── blacklist.json       ← 5 DEMO blacklisted plates

scripts/
└── demo_pipeline.py         ← End-to-end 7-test demo runner
```

### 2.2 New Source Files

| File | Purpose |
|------|---------|
| `app/utils/metadata_loader.py` | Load/cache cameras.json and blacklist.json |
| `app/schemas/ingest.py` | Pydantic schemas for `/process/image` and `/process/video` |
| `app/schemas/p7_analytics.py` | Schemas for vehicle breakdown and camera stats |
| `app/schemas/p7_alerts.py` | Schema for combined alert feed |
| `app/services/ingest_service.py` | `ingest_image()`, `ingest_video()`, `normalise_plate()` |
| `app/services/p7_analytics_service.py` | `get_vehicle_type_breakdown()`, `get_camera_stats()` |
| `app/services/p7_alert_service.py` | `get_combined_alerts()` — 6 alert types |

### 2.3 Modified Files

| File | Change |
|------|--------|
| `app/main.py` | Version → 0.7.0. Added 9 new Phase 7 routes. Updated description. |
| `.gitignore` | Added rules for raw/processed dataset folders |

### 2.4 New API Endpoints (Phase 7)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/process/image` | Traffic image → full ANPR pipeline |
| `POST` | `/process/video` | Traffic video → sampled frame pipeline |
| `GET` | `/vehicle/{plate}/trajectory` | Demo trajectory (DEMO/SIMULATED label) |
| `GET` | `/analytics/summary` | Dashboard KPI summary |
| `GET` | `/analytics/vehicles` | Vehicle type breakdown + congestion score |
| `GET` | `/analytics/cameras` | Per-camera stats (count, density, congestion) |
| `GET` | `/analytics/hourly` | Hourly traffic distribution |
| `GET` | `/alerts` | Combined alert feed (6 alert types) |
| `POST` | `/metadata/reload` | Reload cameras.json / blacklist.json caches |

---

## 3. Complete Pipeline (Phase 7)

```
Traffic Image / Video
        ↓
POST /process/image  or  POST /process/video
        ↓
ingest_service.py
  → VehicleDetector.detect()        [YOLOv8n – reused from Phase 2]
  → PlateDetector.detect()          [YOLO plate / contour – reused from Phase 2]
  → OCREngine.read_plate()          [EasyOCR – reused from Phase 2]
  → normalise_plate()               [NEW – Phase 7: ts 08 ab → TS08AB1234]
  → get_camera_gps(camera_id)       [NEW – Phase 7: GPS from cameras.json]
        ↓
Detection Storage
  → create_event()                  [Phase-3 vehicle_events table – reused]
  → create_detection()              [Phase-4 detections table – reused]
        ↓
IngestDetection JSON response
  (vehicle_type, confidence, plate_number, plate_normalised,
   low_confidence, frame_number, timestamp, camera_id, lat, lon,
   source_file, event_id, detection_id)
        ↓
Trajectory Reconstruction
GET /vehicle/{plate}/trajectory
  → reconstruct()                   [Phase-4 engine – reused]
  → Haversine distance per hop      [Phase-4 – reused]
  → Anomaly classification          [Phase-4 – reused]
  → "DEMO / SIMULATED TRAJECTORY" label  [Phase 7]
        ↓
Traffic Analytics
GET /analytics/summary              [Phase-5 get_overview() – reused]
GET /analytics/vehicles             [Phase-7 get_vehicle_type_breakdown()]
GET /analytics/cameras              [Phase-7 get_camera_stats()]
GET /analytics/hourly               [Phase-5 get_peak_hours() – reused]
        ↓
Alerts
GET /alerts
  → _blacklist_alerts()             [checks detections vs blacklist.json]
  → _congestion_alerts()            [from Phase-5 traffic density]
  → _trajectory_anomaly_alerts()    [SUSPICIOUS/IMPOSSIBLE from Phase-4]
  → _low_confidence_alerts()        [OCR conf < 0.50]
  → _frequent_sightings_alerts()    [plate seen ≥ 10x/hour]
```

---

## 4. Plate Normalisation

`normalise_plate()` in `app/services/ingest_service.py` handles all common
Indian plate input variations:

| Input | Output | Changed |
|-------|--------|---------|
| `ts 08 ab 1234` | `TS08AB1234` | Yes |
| `TS-08-AB-1234` | `TS08AB1234` | Yes |
| `ts08ab1234` | `TS08AB1234` | Yes |
| `TS08AB1234` | `TS08AB1234` | No |
| `MH 12 XY 5678` | `MH12XY5678` | Yes |

Pattern: `^([A-Z]{2})\s*[-]?\s*(\d{1,2})\s*[-]?\s*([A-Z]{1,3})\s*[-]?\s*(\d{1,4})$`

---

## 5. Congestion Score Formula

```
congestion_score = round(total_detections / (MAX_HOURLY_CAPACITY × window_hours), 2)

where:
  MAX_HOURLY_CAPACITY = 500 vehicles/hour  (configurable in p7_analytics_service.py)
  window_hours        = query parameter (default 24h)

Examples:
  244 detections / (500 × 24h) = 0.02   → very low load
  500 detections / (500 × 1h)  = 1.00   → at capacity
  750 detections / (500 × 1h)  = 1.50   → over capacity (SEVERE)
```

Score range: 0.0 (empty) to 1.0+ (saturated / severe congestion).

---

## 6. Demo Mode

All simulated data is clearly labelled. Three distinct data types exist:

| Data Type | Label | Source |
|-----------|-------|--------|
| Real model inference | (no label) | YOLOv8n + EasyOCR running on actual images |
| Simulated camera metadata | `DEMO / SIMULATED` in JSON `_note` field | `data/metadata/cameras.json` |
| Simulated trajectory data | `"data_mode": "DEMO / SIMULATED TRAJECTORY"` in API response | `seed_trajectory.py` |
| Demo blacklist | `demo_data: true` on every alert | `data/metadata/blacklist.json` |

**Pre-seeded demo plates for trajectory testing:**

| Plate | Route | Expected Status |
|-------|-------|----------------|
| `TS09AB1234` | CAM_001 → 002 → 005 → 014 | NORMAL |
| `MH12XY5678` | CAM_003 → 007 → 015 | FAST |
| `DL01ZZ9999` | CAM_004 → 007 → 008 | SUSPICIOUS / IMPOSSIBLE |

---

## 7. Alert Types

| Alert Type | Severity | Trigger | Demo Data |
|------------|----------|---------|-----------|
| `BLACKLISTED_VEHICLE` | CRITICAL | Plate in blacklist.json seen in last 24h | Yes |
| `CONGESTION` | WARNING / CRITICAL | Camera with HIGH/SEVERE traffic density | No |
| `IMPOSSIBLE_TRAJECTORY` | CRITICAL | Speed > 200 km/h or negative time gap | No |
| `SUSPICIOUS_TRAJECTORY` | WARNING | Speed 120–200 km/h or anomalous hop | No |
| `LOW_CONFIDENCE_ANPR` | INFO | OCR confidence < 0.50 in last 6h | No |
| `FREQUENT_SIGHTINGS` | WARNING | Same plate ≥ 10 times in 1 hour | No |

---

## 8. How to Run

### Prerequisites

```bash
cd backend/
pip install -r requirements.txt
```

### Seed the database

```bash
# Phase 3 cameras (required for /anpr/detect)
python -m app.seed_data

# Phase 4 trajectory cameras + sample detections (required for trajectory/analytics)
python -m app.seed_trajectory
```

### Start the API server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Swagger UI: http://127.0.0.1:8000/docs  
ReDoc:       http://127.0.0.1:8000/redoc

### Run the end-to-end demo pipeline

```bash
# From backend/ directory:
python scripts/demo_pipeline.py

# With options:
python scripts/demo_pipeline.py --no-video              # skip video test
python scripts/demo_pipeline.py --plate MH12XY5678      # different demo plate
python scripts/demo_pipeline.py --image path/to/car.jpg # real image
python scripts/demo_pipeline.py --camera CAM_003        # different camera
```

### Add sample data

Place files in the correct folders:
- Traffic images: `data/raw/traffic_images/*.jpg`
- Traffic videos: `data/raw/traffic_videos/*.mp4`
- Plate crops:    `data/raw/license_plates/*.jpg`

The demo pipeline auto-generates synthetic images/videos if the folders are empty.

---

## 9. API Quick Reference

### Ingestion

```bash
# Upload a traffic image
curl -X POST http://localhost:8000/process/image \
  -F "file=@data/raw/traffic_images/car001.jpg" \
  -F "camera_id=CAM_001"

# Upload a video (every 10th frame)
curl -X POST http://localhost:8000/process/video \
  -F "file=@data/raw/traffic_videos/traffic01.mp4" \
  -F "camera_id=CAM_003" \
  -F "frame_skip=10"
```

### Trajectory

```bash
# Demo trajectory
curl http://localhost:8000/vehicle/TS09AB1234/trajectory

# Full Phase-4 trajectory with Haversine metrics
curl http://localhost:8000/trajectory/TS09AB1234
```

### Analytics

```bash
curl http://localhost:8000/analytics/summary
curl http://localhost:8000/analytics/vehicles?window_hours=24
curl http://localhost:8000/analytics/cameras?window_hours=24
curl http://localhost:8000/analytics/hourly
```

### Alerts

```bash
curl http://localhost:8000/alerts?limit=20
```

---

## 10. Known Limitations

1. **No real CCTV feed** — all multi-camera trajectories use seeded or uploaded demo data.
2. **OCR accuracy** — EasyOCR struggles with low-resolution, blurry, or angled plates. Low-confidence reads are flagged but not discarded.
3. **Plate model** — `license_plate_detector.pt` auto-downloads from GitHub on first run. If download fails, the OpenCV contour fallback is used (lower accuracy).
4. **SQLite concurrency** — fine for development. For production load switch to PostgreSQL by updating `DATABASE_URL` in `config.py`.
5. **CPU-only inference** — torch CPU build. Swap to a CUDA wheel for GPU acceleration.
6. **Video processing speed** — depends on `frame_skip`. A 5-minute HD video at `frame_skip=10` takes ~2–3 minutes on CPU.
7. **Synthetic test images** — the demo pipeline generates minimal car shapes that YOLO may not detect as vehicles (by design — real traffic photos are needed for full accuracy testing).

---

## 11. Recommended Phase 8

1. **Live RTSP/WebSocket feed** — real-time frame ingestion from live cameras.
2. **Multi-camera synchronisation** — align timestamps across cameras for accurate trajectory matching.
3. **Re-identification (ReID)** — correlate vehicles across cameras even when plates are unreadable.
4. **PostgreSQL migration** — production-grade database with connection pooling.
5. **GPU inference** — swap torch CPU wheel for CUDA build; enable `gpu=True` in EasyOCR.
6. **Frontend dashboard** — React UI (already scaffolded in `frontend/`) connecting to Phase 7 APIs.
7. **Alembic migrations** — replace `create_all()` with proper schema versioning.
8. **Authentication** — JWT / API key middleware for all endpoints.
9. **Automated accuracy benchmarks** — ground-truth test set with known plate numbers to measure OCR accuracy objectively.
10. **Deployment** — Docker Compose with nginx reverse proxy, gunicorn workers, and volume mounts for model weights and data.
