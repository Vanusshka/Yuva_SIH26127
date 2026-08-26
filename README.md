# SIH26127 – City-Wide AI Engine for Multi-Camera ANPR Trajectory Tracking and Urban Traffic Analytics

---

## Phase 1 – Vehicle Detection ✅
See [`SIH_ANPR/README.md`](SIH_ANPR/README.md)

---

## Phase 2 – Minimum Viable ANPR Detection Pipeline ✅
Single-image pipeline: Vehicle Detection → Plate Detection → OCR → FastAPI

---

## Phase 3 – Database + Camera Event Management ✅

### Architecture

```
Camera / Image
      ↓
 ANPR Pipeline  (YOLOv8 + Plate Detector + EasyOCR)
      ↓
 Plate Number + Confidence Scores
      ↓
 Camera ID + Timestamp
      ↓
 Camera Location Lookup  (cameras table)
      ↓
 VehicleEvent persisted  (vehicle_events table)
      ↓
 Structured JSON Response  (with event_id)
```

---

### Database Schema

**cameras**

| Column     | Type     | Notes                        |
|------------|----------|------------------------------|
| id         | INTEGER  | Primary key, auto-increment  |
| camera_id  | TEXT(50) | Unique, indexed              |
| name       | TEXT     | Human-readable location name |
| latitude   | REAL     | GPS latitude                 |
| longitude  | REAL     | GPS longitude                |
| address    | TEXT     | Street address               |
| status     | ENUM     | ACTIVE / INACTIVE            |
| created_at | DATETIME | UTC, auto-set on insert      |

**vehicle_events**

| Column             | Type     | Notes                              |
|--------------------|----------|------------------------------------|
| id                 | INTEGER  | Primary key, auto-increment        |
| plate_number       | TEXT(20) | OCR result, indexed                |
| camera_id          | TEXT(50) | FK → cameras.camera_id             |
| timestamp          | DATETIME | When detection occurred (UTC)      |
| vehicle_type       | TEXT     | car / bus / truck / motorcycle     |
| vehicle_confidence | REAL     | YOLO confidence score              |
| plate_confidence   | REAL     | Plate detector confidence          |
| ocr_confidence     | REAL     | OCR confidence                     |
| image_path         | TEXT     | Path to annotated output image     |
| created_at         | DATETIME | When DB record was created (UTC)   |

**Relationship:** One `Camera` → Many `VehicleEvents`

---

### Project Structure

```
backend/
├── app/
│   ├── main.py              ← FastAPI routes (all phases)
│   ├── config.py            ← paths, model names, DB URL
│   ├── database.py          ← SQLAlchemy engine, session, Base, init_db
│   ├── seed_data.py         ← 5 sample Hyderabad cameras
│   ├── models/
│   │   ├── camera.py        ← Camera ORM model
│   │   ├── vehicle_event.py ← VehicleEvent ORM model
│   │   ├── vehicle_detector.py
│   │   ├── plate_detector.py
│   │   └── ocr_engine.py
│   ├── services/
│   │   ├── anpr_service.py  ← pipeline + DB event creation
│   │   ├── camera_service.py← camera CRUD
│   │   ├── event_service.py ← event CRUD + history
│   │   └── image_service.py
│   ├── schemas/
│   │   ├── anpr.py
│   │   ├── camera.py
│   │   └── vehicle_event.py
│   └── utils/
│       └── image_utils.py
├── data/
│   ├── input/
│   ├── output/
│   └── traffic.db           ← SQLite database (auto-created)
├── models/                  ← downloaded .pt weights
├── tests/
│   ├── test_pipeline.py     ← Phase 2 AI tests
│   └── test_phase3_db.py    ← Phase 3 API/DB tests
├── requirements.txt
└── .gitignore
```

---

### Setup – Windows PowerShell

```powershell
# From repo root
cd backend

# Activate virtual environment (create if needed)
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install all dependencies
pip install -r requirements.txt
```

---

### Seed Sample Cameras

```powershell
# From backend/ with venv activated
python -m app.seed_data
```

Expected output:
```
  [INSERT] CAM_001 – Ameerpet Junction Camera
  [INSERT] CAM_002 – Begumpet Junction Camera
  [INSERT] CAM_003 – Hitech City Entry Camera
  [INSERT] CAM_004 – Charminar Intersection Camera
  [INSERT] CAM_005 – Secunderabad Railway Station Camera

Done. Inserted: 5  Skipped: 0
```

---

### Start the Server

```powershell
# From backend/ with venv activated
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Server → `http://localhost:8000`  
Swagger → `http://localhost:8000/docs`

---

### API Endpoints

| Method   | Path                              | Description                          |
|----------|-----------------------------------|--------------------------------------|
| GET      | `/health`                         | Liveness probe                       |
| POST     | `/anpr/detect`                    | Upload image → pipeline → DB event   |
| GET      | `/anpr/output/{filename}`         | Download annotated image             |
| POST     | `/cameras`                        | Register a camera                    |
| GET      | `/cameras`                        | List all cameras                     |
| GET      | `/cameras/{camera_id}`            | Get one camera                       |
| PUT      | `/cameras/{camera_id}`            | Update camera                        |
| DELETE   | `/cameras/{camera_id}`            | Delete camera + all events           |
| GET      | `/events`                         | Query events (filters available)     |
| GET      | `/events/{event_id}`              | Get one event                        |
| GET      | `/vehicles/{plate_number}/history`| Chronological sightings of a plate   |

---

### Swagger Testing Procedure

1. Open `http://localhost:8000/docs`

2. **GET /health** → Execute → expect `{"status": "running"}`

3. **POST /cameras** → Try it out → paste:
   ```json
   {
     "camera_id": "CAM_001",
     "name": "Ameerpet Junction Camera",
     "latitude": 17.4375,
     "longitude": 78.4483,
     "address": "Ameerpet Junction, Hyderabad",
     "status": "ACTIVE"
   }
   ```
   *(Skip if you already ran seed_data)*

4. **POST /anpr/detect**
   - Upload a vehicle image
   - Set `camera_id` = `CAM_001`
   - Execute → note `event_id` in each detection

5. **POST /anpr/detect** again
   - Upload the same image
   - Set `camera_id` = `CAM_002`
   - Execute → new event IDs, different camera

6. **GET /events?plate_number=TS09AB1234**
   → Both events returned in order

7. **GET /vehicles/TS09AB1234/history**
   → Both cameras with GPS coordinates, timestamps

---

### Example API Responses

**POST /anpr/detect**
```json
{
  "camera_id": "CAM_001",
  "timestamp": "2026-08-24T10:30:00+00:00",
  "image_name": "traffic.jpg",
  "total_vehicles": 1,
  "detections": [
    {
      "event_id": 1,
      "vehicle_type": "car",
      "vehicle_confidence": 0.95,
      "plate_number": "TS09AB1234",
      "plate_confidence": 0.88,
      "ocr_confidence": 0.92,
      "vehicle_bbox": [100, 80, 400, 350],
      "plate_bbox": [150, 280, 360, 330]
    }
  ],
  "annotated_image_path": "backend/data/output/traffic_abc123_annotated.jpg"
}
```

**GET /vehicles/TS09AB1234/history**
```json
{
  "plate_number": "TS09AB1234",
  "total_detections": 2,
  "events": [
    {
      "event_id": 1,
      "camera_id": "CAM_001",
      "camera_name": "Ameerpet Junction Camera",
      "latitude": 17.4375,
      "longitude": 78.4483,
      "address": "Ameerpet Junction, Hyderabad",
      "timestamp": "2026-08-24T10:30:00+00:00",
      "vehicle_type": "car"
    },
    {
      "event_id": 2,
      "camera_id": "CAM_002",
      "camera_name": "Begumpet Junction Camera",
      "latitude": 17.4432,
      "longitude": 78.4556,
      "address": "Begumpet Junction, Hyderabad",
      "timestamp": "2026-08-24T10:40:00+00:00",
      "vehicle_type": "car"
    }
  ]
}
```

---

### Run Tests

```powershell
# Phase 3 DB/API tests (no AI models needed – uses in-memory SQLite)
python -m pytest tests/test_phase3_db.py -v

# Phase 2 AI pipeline tests
python -m pytest tests/test_pipeline.py -v

# All tests
python -m pytest tests/ -v
```

---

### Known Limitations (Phase 3)

- SQLite is single-writer; for production use the PostgreSQL URL in `config.py`
- No deduplication across accidental API retries (each call creates a new event by design)
- No authentication/API key on endpoints yet
- Video/streaming not yet supported
- Trajectory reconstruction deferred to Phase 4

---

### Phase Roadmap

- [x] **Phase 1** – Vehicle detection with YOLOv8
- [x] **Phase 2** – License plate detection + OCR + FastAPI
- [x] **Phase 3** – Database + Camera event management
- [ ] Phase 4 – Multi-camera trajectory reconstruction
- [ ] Phase 5 – Urban traffic analytics dashboard
- [ ] Phase 6 – Real-time streaming pipeline


---

## Phase 4 – Vehicle Trajectory Reconstruction Engine ✅

### Architecture

```
ANPR Detection  (POST /detections)
      ↓
  SQLite  →  detections table
      ↓
  Trajectory Engine
      ├── Sort by timestamp
      ├── Join camera GPS coordinates
      ├── Haversine distance per hop
      ├── Time difference per hop
      ├── Average speed per hop
      ├── Anomaly classification per hop
      └── Aggregate statistics
      ↓
  TrajectoryResponse  (GET /trajectory/{plate})
```

---

### New Files (Phase 4)

| File | Purpose |
|------|---------|
| `app/models/trajectory_camera.py` | Extended camera ORM (road_name, direction) |
| `app/models/detection.py` | Raw ANPR detection ORM |
| `app/trajectory/haversine.py` | Haversine distance + speed helpers |
| `app/trajectory/anomaly.py` | Movement status classifier (NORMAL/FAST/SUSPICIOUS/IMPOSSIBLE) |
| `app/trajectory/engine.py` | Full reconstruction orchestrator |
| `app/schemas/trajectory.py` | Pydantic schemas for all trajectory types |
| `app/services/trajectory_camera_service.py` | Camera CRUD |
| `app/services/detection_service.py` | Detection CRUD |
| `app/seed_trajectory.py` | 15 cameras + 10 sample detections |
| `tests/test_phase4_trajectory.py` | 22 automated tests |

---

### Setup and Run

```powershell
cd backend
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Seed 15 cameras + sample detections
python -m app.seed_trajectory

# Start server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

### Phase 4 API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/trajectory/cameras` | Register trajectory camera |
| `GET`  | `/trajectory/cameras` | List all 15 cameras with GPS |
| `GET`  | `/trajectory/cameras/{id}` | Get one camera |
| `POST` | `/detections` | Store ANPR detection |
| `GET`  | `/detections` | Query detections (filter by plate/camera) |
| `GET`  | `/detections/{id}` | Get one detection |
| `GET`  | `/trajectory/{plate_number}` | Full trajectory reconstruction |

---

### Anomaly Classification Rules

| Status | Condition |
|--------|-----------|
| `NORMAL` | Speed ≤ 80 km/h, no anomalies |
| `FAST` | Speed 80–120 km/h |
| `SUSPICIOUS` | Speed 120–200 km/h, same camera within 30s, or distance < 50m between different cameras |
| `IMPOSSIBLE` | Speed > 200 km/h or negative time gap between detections |

Overall trajectory status = worst status across all hops.

---

### Swagger Testing Procedure (Phase 4)

1. Start server: `uvicorn app.main:app --reload --port 8000`
2. Run seed: `python -m app.seed_trajectory`
3. Open `http://localhost:8000/docs`

4. **GET /trajectory/cameras** → verify 15 cameras listed

5. **POST /detections** → store a detection:
   ```json
   {
     "plate_number": "TS09AB1234",
     "camera_id": "CAM_001",
     "timestamp": "2026-08-24T10:30:00Z",
     "detection_confidence": 0.94
   }
   ```

6. **GET /trajectory/TS09AB1234** → full trajectory JSON

7. **GET /trajectory/MH12XY5678** → seeded fast-movement plate (FAST status)

8. **GET /trajectory/DL01ZZ9999** → seeded suspicious plate (SUSPICIOUS/IMPOSSIBLE)

---

### Example Trajectory Response

```json
{
  "plate_number": "TS09AB1234",
  "trajectory": [
    {
      "detection_id": 1,
      "camera_id": "CAM_001",
      "location_name": "Ameerpet Junction",
      "road_name": "Ameerpet–Punjagutta Road",
      "direction": "NORTH_BOUND",
      "latitude": 17.4375,
      "longitude": 78.4483,
      "timestamp": "2026-08-24T08:00:00+00:00",
      "detection_confidence": 0.96
    },
    {
      "detection_id": 2,
      "camera_id": "CAM_002",
      "location_name": "Begumpet Junction",
      "road_name": "Begumpet–Secunderabad Road",
      "direction": "NORTH_EAST_BOUND",
      "latitude": 17.4432,
      "longitude": 78.4556,
      "timestamp": "2026-08-24T08:08:00+00:00",
      "detection_confidence": 0.94
    }
  ],
  "hops": [
    {
      "from_camera_id": "CAM_001",
      "to_camera_id": "CAM_002",
      "from_timestamp": "2026-08-24T08:00:00+00:00",
      "to_timestamp": "2026-08-24T08:08:00+00:00",
      "distance_km": 0.9254,
      "time_difference_minutes": 8.0,
      "average_speed_kmh": 6.94,
      "status": "NORMAL"
    }
  ],
  "statistics": {
    "total_detections": 4,
    "total_hops": 3,
    "total_distance_km": 8.4231,
    "total_duration_minutes": 30.0,
    "average_speed_kmh": 16.85,
    "first_seen": "2026-08-24T08:00:00+00:00",
    "last_seen": "2026-08-24T08:30:00+00:00",
    "cameras_visited": ["CAM_001", "CAM_002", "CAM_005", "CAM_014"]
  },
  "status": "NORMAL"
}
```

---

### Run All Tests

```powershell
# Phase 4 tests (no AI models – uses in-memory SQLite)
python -m pytest tests/test_phase4_trajectory.py -v

# All phases
python -m pytest tests/ -v
```

---

### Phase Roadmap

- [x] **Phase 1** – Vehicle detection with YOLOv8
- [x] **Phase 2** – License plate detection + OCR + FastAPI
- [x] **Phase 3** – Database + Camera event management
- [x] **Phase 4** – Trajectory reconstruction engine
- [ ] Phase 5 – Urban traffic analytics dashboard (frontend)
- [ ] Phase 6 – Real-time video streaming pipeline
- [ ] Phase 7 – Multi-city deployment + PostgreSQL migration

---

## Phase 8 — Backend Integration & API Readiness ✅

Full FastAPI backend with 38 endpoints across Phases 2–8. See [`backend/README.md`](backend/README.md).

---

## UrbanEye AI Frontend Integration ✅

**Frontend:** `urban-eye-ai/` — Next.js 16 + React 19 + TypeScript  
**Integration guide:** [`urban-eye-ai/INTEGRATION.md`](urban-eye-ai/INTEGRATION.md)

### Quick Start

**Terminal 1 — Backend:**
```bash
cd backend
venv\Scripts\activate
python -m app.seed_data
python -m app.seed_trajectory
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 — Frontend:**
```bash
cd urban-eye-ai
pnpm install
pnpm dev
```

Open **http://localhost:3000** — the sidebar shows a live API status indicator.

### Frontend → Backend API Mapping

| Dashboard Page | Backend API | Status |
|---------------|------------|--------|
| Overview | `GET /analytics` | ✅ Live |
| Vehicle Search | `GET /vehicles/{plate}` + `GET /api/trajectory/{plate}` | ✅ Live |
| Traffic Analytics | `GET /analytics` | ✅ Live |
| Alerts | `GET /alerts` | ✅ Live |
| Blacklist Monitoring | `GET /alerts` (filtered) | ✅ Live |
| System Health | `GET /health` | ✅ Live |
| Camera Network | `GET /api/cameras` (count + metadata) | 🔶 Partial (feed thumbnails = Phase 9) |
| City Map | GPS from `GET /api/cameras` | 🔲 Placeholder (needs mapping library) |

### Environment Configuration

`urban-eye-ai/.env.local`:
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_DEMO_MODE=false
```

### Project Folder Structure

| Folder | Purpose |
|--------|---------|
| `backend/` | FastAPI server (Phases 2–8) — the real AI backend |
| `urban-eye-ai/` | React/Next.js dashboard frontend |
| `SIH_ANPR/` | Phase 1 offline CLI video processor (not a server) |
| `frontend/` | Legacy frontend scaffold (superseded by `urban-eye-ai/`) |

### Updated Phase Roadmap

- [x] **Phase 1** – Vehicle detection with YOLOv8 (`SIH_ANPR/`)
- [x] **Phase 2** – License plate detection + OCR + FastAPI
- [x] **Phase 3** – Database + Camera event management
- [x] **Phase 4** – Trajectory reconstruction engine
- [x] **Phase 5** – Traffic analytics API
- [x] **Phase 6** – Analytics + alert consolidation
- [x] **Phase 7** – Dataset integration + end-to-end pipeline
- [x] **Phase 8** – Backend integration & API readiness
- [x] **Frontend** – UrbanEye AI dashboard connected to backend
- [ ] Phase 9 – Live RTSP camera feed + interactive map (Leaflet/Mapbox)
- [ ] Phase 10 – PostgreSQL migration + production deployment
