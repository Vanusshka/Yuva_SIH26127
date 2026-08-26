"""
SIH26127 ANPR Backend – FastAPI entry point.
Phase 3: Database + Camera Event Management
Phase 4: Vehicle Trajectory Reconstruction Engine
Phase 5: Analytics API
Phase 7: Dataset Ingestion, Plate Normalisation, Demo Trajectory, Extended Alerts

Routes
------
System
  GET  /health
  POST /metadata/reload  – reload cameras.json / blacklist.json caches

ANPR  (Phase 2–3)
  POST /anpr/detect           – upload image → ANPR pipeline → DB event
  GET  /anpr/output/{file}    – serve annotated image

Cameras  (Phase 3)
  POST   /cameras             – register a camera
  GET    /cameras             – list all cameras
  GET    /cameras/{camera_id} – get one camera
  PUT    /cameras/{camera_id} – update camera
  DELETE /cameras/{camera_id} – delete camera

Events  (Phase 3)
  GET /events                 – query events (filters: plate, camera, time, limit)
  GET /events/{event_id}      – get one event

Vehicles  (Phase 3)
  GET /vehicles/{plate_number}/history – chronological sightings

Trajectory Cameras  (Phase 4)
  POST /trajectory/cameras    – register a trajectory camera
  GET  /trajectory/cameras    – list all trajectory cameras

Detections  (Phase 4)
  POST /detections            – store an ANPR detection
  GET  /detections            – query detections

Trajectory  (Phase 4)
  GET /trajectory/{plate_number} – reconstruct full trajectory with metrics

Analytics  (Phase 5)
  GET /analytics/overview
  GET /analytics/traffic-density
  GET /analytics/congestion
  GET /analytics/peak-hours
  GET /analytics/alerts

Ingestion  (Phase 7 – NEW)
  POST /process/image  – upload image → full pipeline → structured JSON
  POST /process/video  – upload video → sampled frame pipeline → structured JSON

Vehicle (Phase 7 – extended)
  GET /vehicle/{plate}/trajectory  – demo trajectory (alias of /trajectory/{plate})

Analytics extended (Phase 7)
  GET /analytics/summary   – alias of /analytics/overview
  GET /analytics/vehicles  – vehicle type breakdown
  GET /analytics/cameras   – per-camera stats
  GET /analytics/hourly    – alias of /analytics/peak-hours

Alerts extended (Phase 7)
  GET /alerts  – combined alert feed (blacklist + congestion + anomaly)
"""

from __future__ import annotations
import logging
import traceback
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.config import API_TITLE, OUTPUT_DIR
from app.database import get_db, init_db
from app.schemas.anpr import HealthResponse

# ── Logging setup (Phase 8) ───────────────────────────────────────────────────
logging.basicConfig(
    level  = logging.INFO,
    format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt= "%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("sih26127")
from app.schemas.camera import CameraCreate, CameraResponse, CameraUpdate
from app.schemas.vehicle_event import (
    ANPRResponseV3,
    VehicleEventResponse,
    VehicleHistoryResponse,
)
from app.schemas.trajectory import (
    TrajectoryCameraCreate,
    TrajectoryCameraResponse,
    DetectionCreate,
    DetectionResponse,
    TrajectoryResponse,
)
from app.services.anpr_service import process_image
from app.services.camera_service import (
    create_camera,
    delete_camera,
    get_all_cameras,
    get_camera_or_404,
    update_camera,
)
from app.services.event_service import (
    get_event_by_id,
    get_events,
    get_vehicle_history,
)
from app.services.image_service import cleanup, save_upload, save_video_upload
from app.services.trajectory_camera_service import (
    create_trajectory_camera,
    get_all_trajectory_cameras,
    get_trajectory_camera_or_404,
)
from app.services.detection_service import (
    create_detection,
    get_detections,
    get_detection_or_404,
)
from app.trajectory.engine import reconstruct
from app.services.analytics_service import (
    get_overview,
    get_traffic_density,
    get_congestion,
    get_peak_hours,
    get_alerts,
)
from app.schemas.analytics import (
    OverviewResponse,
    TrafficDensityResponse,
    CongestionResponse,
    PeakHoursResponse,
    AlertsResponse,
)

# ── Phase 7 ───────────────────────────────────────────────────────────────────
from app.services.ingest_service import ingest_image, ingest_video
from app.services.p7_analytics_service import (
    get_vehicle_type_breakdown,
    get_camera_stats,
)
from app.services.p7_alert_service import get_combined_alerts
from app.schemas.ingest import ImageIngestResponse, VideoIngestResponse
from app.schemas.p7_analytics import VehicleBreakdownResponse, CameraStatsResponse
from app.schemas.p7_alerts import CombinedAlertsResponse
from app.services.image_service import cleanup as _cleanup_upload
from app.utils.metadata_loader import reload_metadata

# ── Phase 8 ───────────────────────────────────────────────────────────────────
from app.services.pipeline_service import (
    get_health,
    get_vehicle_list,
    get_vehicle_detail,
    get_frontend_trajectory,
    get_unified_analytics,
    get_frontend_alerts,
)
from app.schemas.p8_frontend import (
    Phase8HealthResponse,
    VehicleRecord,
    VehicleListResponse,
    FrontendTrajectoryResponse,
    UnifiedAnalyticsResponse,
    FrontendAlertsResponse,
    ProcessResponse,
)

_API_VERSION = "0.8.0"

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title       = API_TITLE,
    version     = _API_VERSION,
    description = (
        "## SIH26127 — UrbanEye AI Backend\n\n"
        "**Phase 8 – Backend Integration & API Readiness**\n\n"
        "City-Wide AI Engine for Multi-Camera ANPR Trajectory Tracking "
        "and Urban Traffic Analytics\n\n"
        "All Phases 2–7 endpoints remain fully functional.\n\n"
        "### Phase 8 Frontend-Ready Endpoints\n"
        "| Method | Path | Description |\n"
        "|--------|------|-----------|\n"
        "| `GET`  | `/health` | Extended health + DB stats |\n"
        "| `POST` | `/process` | Upload image → pipeline → summary card |\n"
        "| `GET`  | `/vehicles` | Paginated vehicle list with status |\n"
        "| `GET`  | `/vehicles/{plate}` | Single vehicle detail card |\n"
        "| `GET`  | `/trajectory/{plate}` | Frontend trajectory with anomaly score |\n"
        "| `GET`  | `/analytics` | Unified dashboard payload |\n"
        "| `GET`  | `/alerts` | Alert feed with alert_id + location |\n"
        "| `GET`  | `/cameras` | Camera list (existing, Phase 3) |\n\n"
        "**Swagger UI:** `/docs`  |  **ReDoc:** `/redoc`\n\n"
        "> **Demo Mode:** Trajectory and blacklist data is SIMULATED. "
        "See `data_mode` and `demo_data` fields in responses."
    ),
    docs_url    = "/docs",
    redoc_url   = "/redoc",
)

# ── CORS (Phase 8 – explicit origins for UrbanEye AI Emergent frontend) ───────
_ALLOWED_ORIGINS = [
    "http://localhost:3000",        # React dev server (CRA / Vite default)
    "http://localhost:5173",        # Vite alternative port
    "http://localhost:5174",        # Vite alternative port
    "http://localhost:8080",        # Vue / webpack-dev-server
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "https://urbaneye-ai.vercel.app",        # Emergent Vercel deployment (update as needed)
    "https://urbaneye-ai.netlify.app",       # Emergent Netlify deployment (update as needed)
    # Add the actual Emergent URL here once known
]

app.add_middleware(
    CORSMiddleware,
    allow_origins     = _ALLOWED_ORIGINS,
    allow_origin_regex= r"https://.*\.vercel\.app",   # all Vercel preview deploys
    allow_credentials = True,
    allow_methods     = ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers     = ["*"],
    expose_headers    = ["X-Request-ID"],
)

# Static output images
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static/output", StaticFiles(directory=str(OUTPUT_DIR)), name="output")


# ── Global exception handlers (Phase 8) ──────────────────────────────────────

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.warning("HTTP %d on %s %s — %s",
                   exc.status_code, request.method, request.url.path, exc.detail)
    return JSONResponse(
        status_code = exc.status_code,
        content     = {
            "error"   : exc.detail,
            "status"  : exc.status_code,
            "path"    : str(request.url.path),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    logger.error("Unhandled exception on %s %s:\n%s",
                 request.method, request.url.path, tb)
    return JSONResponse(
        status_code = 500,
        content     = {
            "error"  : "Internal server error. Check server logs.",
            "status" : 500,
            "path"   : str(request.url.path),
        },
    )


# Initialise DB tables on startup
@app.on_event("startup")
def _startup():
    init_db()
    logger.info("SIH26127 backend v%s started — DB initialised.", _API_VERSION)


# ── System ─────────────────────────────────────────────────────────────────────

@app.get(
    "/health",
    response_model = Phase8HealthResponse,
    tags           = ["System"],
    summary        = "Liveness probe + DB stats",
)
def health(db: Session = Depends(get_db)):
    """
    Extended health check.

    Returns:
    - Server status
    - API version
    - Database connection status
    - Total cameras registered
    - Total detections stored

    Use this as a pre-flight check before making other API calls.
    """
    return get_health(db, version=_API_VERSION)


# ── ANPR ──────────────────────────────────────────────────────────────────────

@app.post(
    "/anpr/detect",
    response_model=ANPRResponseV3,
    tags=["ANPR"],
    summary="Upload a vehicle image → run ANPR pipeline → store event in DB",
)
async def detect(
    file      : UploadFile = File(..., description="Vehicle image (JPEG/PNG/BMP/WebP)"),
    camera_id : str        = Form(default="CAM_001", description="Registered camera_id"),
    db        : Session    = Depends(get_db),
):
    """
    **Full pipeline:**
    1. Validate `camera_id` exists in the database
    2. Save uploaded image
    3. Detect vehicles (YOLOv8)
    4. Detect license plates
    5. Run OCR
    6. Persist a `VehicleEvent` row for every detection
    7. Return structured JSON with `event_id` on each detection

    The annotated image URL: `GET /static/output/<filename>`
    """
    # Validate camera exists before running (potentially slow) AI pipeline
    get_camera_or_404(db, camera_id)

    saved_path = await save_upload(file)
    try:
        result = process_image(
            image_path     = saved_path,
            camera_id      = camera_id,
            save_annotated = True,
            db             = db,
        )
    except Exception as exc:
        cleanup(saved_path)
        raise HTTPException(status_code=500, detail=f"Pipeline error: {exc}") from exc

    return result


@app.get(
    "/anpr/output/{filename}",
    tags=["ANPR"],
    summary="Download an annotated output image",
)
def get_output_image(filename: str):
    target = OUTPUT_DIR / filename
    if not target.exists():
        raise HTTPException(status_code=404, detail="Annotated image not found.")
    return FileResponse(str(target), media_type="image/jpeg")


# ── Cameras ───────────────────────────────────────────────────────────────────

@app.post(
    "/cameras",
    response_model=CameraResponse,
    status_code=201,
    tags=["Cameras"],
    summary="Register a new ANPR camera",
)
def add_camera(data: CameraCreate, db: Session = Depends(get_db)):
    """
    Register a camera with its GPS coordinates and address.

    Example:
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
    """
    return create_camera(db, data)


@app.get(
    "/cameras",
    response_model=List[CameraResponse],
    tags=["Cameras"],
    summary="List all registered cameras",
)
def list_cameras(db: Session = Depends(get_db)):
    return get_all_cameras(db)


@app.get(
    "/cameras/{camera_id}",
    response_model=CameraResponse,
    tags=["Cameras"],
    summary="Get a single camera by camera_id",
)
def get_camera(camera_id: str, db: Session = Depends(get_db)):
    return get_camera_or_404(db, camera_id)


@app.put(
    "/cameras/{camera_id}",
    response_model=CameraResponse,
    tags=["Cameras"],
    summary="Update camera fields",
)
def update_camera_route(
    camera_id : str,
    data      : CameraUpdate,
    db        : Session = Depends(get_db),
):
    return update_camera(db, camera_id, data)


@app.delete(
    "/cameras/{camera_id}",
    status_code=204,
    tags=["Cameras"],
    summary="Delete a camera (and all its events)",
)
def delete_camera_route(camera_id: str, db: Session = Depends(get_db)):
    delete_camera(db, camera_id)


# ── Events ────────────────────────────────────────────────────────────────────

@app.get(
    "/events",
    response_model=List[VehicleEventResponse],
    tags=["Events"],
    summary="Query detection events with optional filters",
)
def list_events(
    plate_number : Optional[str]      = Query(None, description="Filter by plate number"),
    camera_id    : Optional[str]      = Query(None, description="Filter by camera_id"),
    start_time   : Optional[datetime] = Query(None, description="ISO-8601 start timestamp"),
    end_time     : Optional[datetime] = Query(None, description="ISO-8601 end timestamp"),
    limit        : int                = Query(100, ge=1, le=500, description="Max results"),
    db           : Session            = Depends(get_db),
):
    """
    Examples:
    - `GET /events?plate_number=TS09AB1234` – all sightings of a plate
    - `GET /events?camera_id=CAM_001&limit=50` – last 50 events from one camera
    - `GET /events?start_time=2026-08-24T00:00:00Z&end_time=2026-08-24T23:59:59Z`
    """
    return get_events(
        db           = db,
        plate_number = plate_number,
        camera_id    = camera_id,
        start_time   = start_time,
        end_time     = end_time,
        limit        = limit,
    )


@app.get(
    "/events/{event_id}",
    response_model=VehicleEventResponse,
    tags=["Events"],
    summary="Get a single detection event by ID",
)
def get_event(event_id: int, db: Session = Depends(get_db)):
    return get_event_by_id(db, event_id)


# ── Vehicles ──────────────────────────────────────────────────────────────────

@app.get(
    "/vehicles/{plate_number}/history",
    response_model=VehicleHistoryResponse,
    tags=["Vehicles"],
    summary="Chronological detection history of a vehicle",
)
def vehicle_history(plate_number: str, db: Session = Depends(get_db)):
    """
    Returns every recorded sighting of the given plate number across all cameras,
    ordered by timestamp ascending, with camera GPS coordinates.

    **Note:** Trajectory reconstruction is Phase 4 – this endpoint returns
    raw detection history only.
    """
    history = get_vehicle_history(db, plate_number)
    if history.total_detections == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No detections found for plate '{plate_number.upper()}'.",
        )
    return history


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 4 – Trajectory Reconstruction Engine
# ═══════════════════════════════════════════════════════════════════════════════

# ── Trajectory Cameras ────────────────────────────────────────────────────────

@app.post(
    "/trajectory/cameras",
    response_model=TrajectoryCameraResponse,
    status_code=201,
    tags=["Trajectory – Cameras"],
    summary="Register a trajectory-tracking camera",
)
def add_trajectory_camera(data: TrajectoryCameraCreate, db: Session = Depends(get_db)):
    """
    Register a camera with extended trajectory metadata
    (road_name, direction, location_name).

    Example:
    ```json
    {
      "camera_id": "CAM_001",
      "location_name": "Ameerpet Junction",
      "road_name": "Ameerpet–Punjagutta Road",
      "direction": "NORTH_BOUND",
      "latitude": 17.4375,
      "longitude": 78.4483
    }
    ```
    """
    return create_trajectory_camera(db, data)


@app.get(
    "/trajectory/cameras",
    response_model=List[TrajectoryCameraResponse],
    tags=["Trajectory – Cameras"],
    summary="List all trajectory cameras with GPS coordinates",
)
def list_trajectory_cameras(db: Session = Depends(get_db)):
    """
    Returns all 15 trajectory cameras with location, road, direction
    and GPS coordinates. Use this to visualise the camera network.
    """
    return get_all_trajectory_cameras(db)


@app.get(
    "/trajectory/cameras/{camera_id}",
    response_model=TrajectoryCameraResponse,
    tags=["Trajectory – Cameras"],
    summary="Get a single trajectory camera",
)
def get_traj_camera(camera_id: str, db: Session = Depends(get_db)):
    return get_trajectory_camera_or_404(db, camera_id)


# ── Detections ────────────────────────────────────────────────────────────────

@app.post(
    "/detections",
    response_model=DetectionResponse,
    status_code=201,
    tags=["Trajectory – Detections"],
    summary="Store a new ANPR detection",
)
def store_detection(data: DetectionCreate, db: Session = Depends(get_db)):
    """
    Store one ANPR plate detection from a camera.
    The camera must already be registered via `POST /trajectory/cameras`.

    Example:
    ```json
    {
      "plate_number": "TS09AB1234",
      "camera_id": "CAM_001",
      "timestamp": "2026-08-24T10:30:00Z",
      "detection_confidence": 0.94
    }
    ```
    """
    # Validate camera exists
    get_trajectory_camera_or_404(db, data.camera_id)
    return create_detection(db, data)


@app.get(
    "/detections",
    response_model=List[DetectionResponse],
    tags=["Trajectory – Detections"],
    summary="Query stored detections",
)
def list_detections(
    plate_number : Optional[str] = Query(None, description="Filter by plate number"),
    camera_id    : Optional[str] = Query(None, description="Filter by camera_id"),
    limit        : int           = Query(200,  ge=1, le=1000),
    db           : Session       = Depends(get_db),
):
    """
    Returns detections ordered by timestamp ascending.
    Use `plate_number` filter to see all sightings of a vehicle.
    """
    return get_detections(db, plate_number=plate_number, camera_id=camera_id, limit=limit)


@app.get(
    "/detections/{detection_id}",
    response_model=DetectionResponse,
    tags=["Trajectory – Detections"],
    summary="Get a single detection by ID",
)
def get_one_detection(detection_id: int, db: Session = Depends(get_db)):
    return get_detection_or_404(db, detection_id)


# ── Trajectory ────────────────────────────────────────────────────────────────

@app.get(
    "/trajectory/{plate_number}",
    response_model=TrajectoryResponse,
    tags=["Trajectory – Reconstruction"],
    summary="Reconstruct full vehicle trajectory with spatial analytics",
)
def get_trajectory(plate_number: str, db: Session = Depends(get_db)):
    """
    **Full trajectory reconstruction pipeline:**

    1. Retrieve all detections for `plate_number`, sorted by timestamp
    2. Enrich each point with camera GPS coordinates
    3. For every consecutive camera pair:
       - Calculate geographic distance (Haversine formula)
       - Calculate time difference
       - Calculate average speed
       - Classify movement status
    4. Return aggregated statistics and overall anomaly status

    **Status values:**
    | Status | Condition |
    |--------|-----------|
    | `NORMAL` | Speed ≤ 80 km/h, no anomalies |
    | `FAST` | Speed 80–120 km/h |
    | `SUSPICIOUS` | Speed 120–200 km/h, duplicate detection, or impossible distance |
    | `IMPOSSIBLE` | Speed > 200 km/h or negative time gap |
    """
    return reconstruct(db, plate_number)


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 5 – Analytics API
# ═══════════════════════════════════════════════════════════════════════════════

@app.get(
    "/analytics/overview",
    response_model=OverviewResponse,
    tags=["Analytics"],
    summary="Dashboard overview – cameras, detections, alerts",
)
def analytics_overview(db: Session = Depends(get_db)):
    """Returns high-level KPIs for the main dashboard cards."""
    return get_overview(db)


@app.get(
    "/analytics/traffic-density",
    response_model=TrafficDensityResponse,
    tags=["Analytics"],
    summary="Vehicle count and traffic density per camera",
)
def analytics_traffic_density(
    window_hours: int = Query(1, ge=1, le=24, description="Time window in hours"),
    db: Session = Depends(get_db),
):
    """
    Returns vehicle counts and density classification (LOW/MEDIUM/HIGH/SEVERE)
    for every camera over the specified time window.
    """
    return get_traffic_density(db, window_hours=window_hours)


@app.get(
    "/analytics/congestion",
    response_model=CongestionResponse,
    tags=["Analytics"],
    summary="Congestion level per camera based on vehicle count and speed",
)
def analytics_congestion(
    window_hours: int = Query(1, ge=1, le=24),
    db: Session = Depends(get_db),
):
    """
    Classifies congestion at each camera as LOW/MEDIUM/HIGH/SEVERE
    using vehicle count and estimated average vehicle speed.
    """
    return get_congestion(db, window_hours=window_hours)


@app.get(
    "/analytics/peak-hours",
    response_model=PeakHoursResponse,
    tags=["Analytics"],
    summary="Vehicle traffic aggregated by hour of day (0–23)",
)
def analytics_peak_hours(db: Session = Depends(get_db)):
    """Returns 24 data points, one per hour, for bar chart rendering."""
    return get_peak_hours(db)


@app.get(
    "/analytics/alerts",
    response_model=AlertsResponse,
    tags=["Analytics"],
    summary="Active traffic and movement alerts",
)
def analytics_alerts(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """
    Returns CRITICAL and WARNING alerts:
    - High congestion at cameras
    - Suspicious vehicle movement
    - Impossible trajectory detections
    """
    return get_alerts(db, limit=limit)


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 7 – Dataset Ingestion, Extended Analytics, Combined Alerts
# ═══════════════════════════════════════════════════════════════════════════════

# ── Metadata management ───────────────────────────────────────────────────────

@app.post(
    "/metadata/reload",
    tags=["System"],
    summary="Reload cameras.json and blacklist.json caches",
)
def reload_metadata_caches():
    """
    Clears the in-memory LRU caches for camera metadata and the blacklist so
    updated JSON files are picked up on the next request.
    Call this after manually editing `data/metadata/cameras.json` or
    `data/metadata/blacklist.json`.
    """
    reload_metadata()
    return {"status": "ok", "message": "Metadata caches cleared. Files will be re-read on next request."}


# ── Image ingestion ───────────────────────────────────────────────────────────

@app.post(
    "/process/image",
    response_model=ImageIngestResponse,
    tags=["Ingestion – Phase 7"],
    summary="Upload a traffic image → full ANPR pipeline → structured JSON",
)
async def process_image_p7(
    file       : UploadFile    = File(...,  description="Traffic image (JPEG/PNG/BMP/WebP)"),
    camera_id  : str           = Form(default="CAM_001", description="Camera ID (from cameras.json)"),
    timestamp  : Optional[str] = Form(default=None,      description="ISO-8601 timestamp (defaults to UTC now)"),
    db         : Session       = Depends(get_db),
):
    """
    **Phase 7 ingestion pipeline for a single image:**

    1. Accept any traffic/vehicle image
    2. Detect vehicles (YOLOv8n – car, motorcycle, bus, truck)
    3. Detect license plates (YOLO plate model / OpenCV contour fallback)
    4. Run OCR (EasyOCR)
    5. **Normalise plate text** (e.g. `ts 08 ab 1234` → `TS08AB1234`)
    6. Look up GPS coordinates from `data/metadata/cameras.json`
    7. Persist to Phase-3 `vehicle_events` table
    8. Persist to Phase-4 `detections` table (feeds trajectory engine)
    9. Return structured JSON with full provenance

    **Low-confidence detections** (OCR confidence < 0.50) are flagged with
    `"low_confidence": true`. Do not treat them as definitive plate reads.

    Place sample images in `data/raw/traffic_images/` and upload from there.
    """
    ts: Optional[datetime] = None
    if timestamp:
        try:
            ts = datetime.fromisoformat(timestamp)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid timestamp format: '{timestamp}'. Use ISO-8601 (e.g. 2026-08-24T10:30:00).",
            )

    saved_path = await save_upload(file)
    try:
        result = ingest_image(
            image_path = saved_path,
            camera_id  = camera_id,
            timestamp  = ts,
            db         = db,
        )
    except ValueError as exc:
        _cleanup_upload(saved_path)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        _cleanup_upload(saved_path)
        raise HTTPException(status_code=500, detail=f"Ingestion pipeline error: {exc}") from exc

    return result


# ── Video ingestion ───────────────────────────────────────────────────────────

@app.post(
    "/process/video",
    response_model=VideoIngestResponse,
    tags=["Ingestion – Phase 7"],
    summary="Upload a traffic video → sampled frame ANPR pipeline → structured JSON",
)
async def process_video_p7(
    file        : UploadFile    = File(...,  description="Traffic video (MP4/AVI/MOV/MKV)"),
    camera_id   : str           = Form(default="CAM_001", description="Camera ID"),
    timestamp   : Optional[str] = Form(default=None,      description="ISO-8601 timestamp of first frame"),
    frame_skip  : int           = Form(default=5,          description="Process every N-th frame (default 5). Lower=more detections, slower. Set to 2-3 for best ANPR results."),
    db          : Session       = Depends(get_db),
):
    """
    **Phase 7 video ingestion pipeline:**

    1. Accept a traffic video file
    2. Extract frames at the configured sampling rate (`frame_skip`)
    3. Run the full ANPR pipeline on each sampled frame
    4. Persist all detections to the database
    5. Return a summary with unique plates detected

    **Frame sampling** (default every 10th frame) reduces processing time
    significantly. For a 30-fps video this processes 3 frames/second of footage.

    **Recommended sample videos:** Place `.mp4` files in `data/raw/traffic_videos/`.

    **Note:** Processing time scales linearly with `total_frames / frame_skip`
    and with image complexity. Large HD videos may take several minutes on CPU.
    """
    ts: Optional[datetime] = None
    if timestamp:
        try:
            ts = datetime.fromisoformat(timestamp)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid timestamp format: '{timestamp}'. Use ISO-8601.",
            )

    if frame_skip < 1 or frame_skip > 300:
        raise HTTPException(status_code=422, detail="frame_skip must be between 1 and 300.")

    saved_path = await save_video_upload(file)
    try:
        result = ingest_video(
            video_path    = saved_path,
            camera_id     = camera_id,
            base_timestamp= ts,
            frame_skip    = frame_skip,
            db            = db,
        )
    except ValueError as exc:
        _cleanup_upload(saved_path)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        _cleanup_upload(saved_path)
        raise HTTPException(status_code=500, detail=f"Video ingestion error: {exc}") from exc

    return result


# ── Vehicle trajectory (Phase 7 alias with demo label) ───────────────────────

@app.get(
    "/vehicle/{plate}/trajectory",
    response_model=dict,
    tags=["Vehicles – Phase 7"],
    summary="Demo multi-camera trajectory for a plate number",
)
def vehicle_trajectory_demo(plate: str, db: Session = Depends(get_db)):
    """
    **Demo trajectory reconstruction** for a given plate number.

    Queries the Phase-4 `detections` table, sorts by timestamp, and returns
    a structured trajectory with Haversine metrics and anomaly classification.

    **IMPORTANT – DEMO / SIMULATED TRAJECTORY**
    The data returned here is based on either:
    - Real detections from the `/process/image` or `/process/video` endpoints
    - Seeded demo data from `seed_trajectory.py`

    It is **not** sourced from a live CCTV feed. The label
    `"data_mode": "DEMO / SIMULATED TRAJECTORY"` is always present in the
    response to make this clear.

    **Pre-seeded demo plates:**
    | Plate | Route | Status |
    |-------|-------|--------|
    | `TS09AB1234` | CAM_001 → 002 → 005 → 014 | NORMAL |
    | `MH12XY5678` | CAM_003 → 007 → 015 | FAST |
    | `DL01ZZ9999` | CAM_004 → 007 → 008 | SUSPICIOUS / IMPOSSIBLE |
    """
    traj = reconstruct(db, plate)
    return {
        "data_mode"         : "DEMO / SIMULATED TRAJECTORY",
        "disclaimer"        : (
            "This trajectory is reconstructed from seeded or uploaded demo data. "
            "It does NOT represent real CCTV surveillance data."
        ),
        "plate"             : traj.plate_number,
        "total_observations": traj.statistics.total_detections,
        "status"            : traj.status,
        "statistics"        : traj.statistics.model_dump(),
        "trajectory"        : [p.model_dump() for p in traj.trajectory],
        "hops"              : [h.model_dump() for h in traj.hops],
    }


# ── Extended analytics (Phase 7) ─────────────────────────────────────────────

@app.get(
    "/analytics/summary",
    response_model=OverviewResponse,
    tags=["Analytics – Phase 7"],
    summary="Dashboard KPI summary (alias of /analytics/overview)",
)
def analytics_summary(db: Session = Depends(get_db)):
    """
    Returns dashboard KPI cards:
    - Total active cameras
    - Total detections
    - Unique plates
    - Suspicious vehicle count
    - Congested locations count

    This is an alias of `GET /analytics/overview` added for the Phase 7
    frontend API contract.
    """
    return get_overview(db)


@app.get(
    "/analytics/vehicles",
    response_model=VehicleBreakdownResponse,
    tags=["Analytics – Phase 7"],
    summary="Vehicle type breakdown – count per type",
)
def analytics_vehicles(
    window_hours: int = Query(24, ge=1, le=168, description="Look-back window in hours (default 24h)"),
    db: Session = Depends(get_db),
):
    """
    Returns the count of each vehicle type (car / motorcycle / bus / truck /
    unknown) detected within the specified time window.

    Uses the Phase-3 `vehicle_events` table so it reflects all detections
    from both the `/anpr/detect` (Phase 2-3) and `/process/image` (Phase 7)
    endpoints.

    **Congestion score formula:**

    ```
    congestion_score = round(
        (total_detections / max_hourly_capacity) * window_factor, 2
    )
    where:
      max_hourly_capacity = 500 vehicles/hour (configurable baseline)
      window_factor       = min(window_hours, 1)   # normalised to 1-hour window
    ```

    Score range: 0.0 (empty) → 1.0+ (saturated).
    """
    return get_vehicle_type_breakdown(db, window_hours=window_hours)


@app.get(
    "/analytics/cameras",
    response_model=CameraStatsResponse,
    tags=["Analytics – Phase 7"],
    summary="Per-camera statistics – detections, most active, congestion",
)
def analytics_cameras(
    window_hours: int = Query(24, ge=1, le=168, description="Look-back window in hours"),
    db: Session = Depends(get_db),
):
    """
    Returns per-camera statistics including:
    - Vehicle count in time window
    - Most active camera
    - Congestion level
    - GPS coordinates

    Combines Phase-4 `trajectory_cameras` + `detections` tables.
    """
    return get_camera_stats(db, window_hours=window_hours)


@app.get(
    "/analytics/hourly",
    response_model=PeakHoursResponse,
    tags=["Analytics – Phase 7"],
    summary="Hourly traffic distribution (alias of /analytics/peak-hours)",
)
def analytics_hourly(db: Session = Depends(get_db)):
    """
    Returns 24 hourly traffic buckets (0–23h) showing vehicle count per hour.
    Useful for visualising peak and off-peak periods.

    This is an alias of `GET /analytics/peak-hours`.
    """
    return get_peak_hours(db)


# ── Combined alert feed (Phase 7 → upgraded to Phase 8 schema) ───────────────

@app.get(
    "/alerts",
    response_model = FrontendAlertsResponse,
    tags           = ["Alerts – Phase 8"],
    summary        = "Combined alert feed – blacklist + congestion + anomaly (Phase 8)",
)
def get_all_alerts(
    limit: int = Query(50, ge=1, le=200, description="Maximum number of alerts to return"),
    db: Session = Depends(get_db),
):
    """
    **Phase 8 combined alert feed** (upgraded from Phase 7):

    Each alert now includes:
    - `alert_id`   – stable UUID for React list keys
    - `location`   – human-readable location name from TrajectoryCamera table
    - `status`     – open | acknowledged | resolved
    - `demo_data`  – True when based on SIMULATED blacklist data

    | Alert Type | Source | Severity |
    |------------|--------|----------|
    | `BLACKLISTED_VEHICLE` | `data/metadata/blacklist.json` (DEMO) | CRITICAL |
    | `CONGESTION` | Phase-5 traffic density analysis | WARNING / CRITICAL |
    | `SUSPICIOUS_TRAJECTORY` | Phase-4 trajectory anomaly classifier | WARNING |
    | `IMPOSSIBLE_TRAJECTORY` | Phase-4 trajectory anomaly classifier | CRITICAL |
    | `LOW_CONFIDENCE_ANPR` | Phase-7 OCR confidence threshold | INFO |
    | `FREQUENT_SIGHTINGS` | Plate seen ≥ 10 times in 1 hour | WARNING |

    **DEMO DATA DISCLAIMER:**
    Blacklist entries are fictitious and created for SIH26127 demonstration
    purposes only. They do not represent real law-enforcement records.
    """
    return get_frontend_alerts(db, limit=limit)


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 8 – Frontend-Ready Integration Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

# ── POST /process  (Phase 8 frontend shorthand) ───────────────────────────────

@app.post(
    "/process",
    response_model = ProcessResponse,
    tags           = ["Ingestion – Phase 8"],
    summary        = "Upload traffic image → full ANPR pipeline → frontend summary card",
)
async def process_p8(
    file      : UploadFile    = File(..., description="Traffic image (JPEG/PNG/BMP/WebP)"),
    camera_id : str           = Form(default="CAM_001", description="Camera ID"),
    timestamp : Optional[str] = Form(default=None, description="ISO-8601 timestamp (defaults to UTC now)"),
    db        : Session       = Depends(get_db),
):
    """
    **Phase 8 unified process endpoint.**

    Runs the full Phase 7 ingestion pipeline and returns a clean summary card
    suitable for the React frontend — no need to parse the full `detections` array.

    Response includes:
    - `plates_detected` – list of normalised plate strings
    - `total_vehicles`, `total_plates`, `low_confidence_count`
    - `annotated_image_url` – ready to render in `<img src=...>`
    - `warnings` – any camera metadata misses or pipeline warnings

    For the raw per-detection array use `POST /process/image` (Phase 7).
    """
    ts: Optional[datetime] = None
    if timestamp:
        try:
            ts = datetime.fromisoformat(timestamp)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid timestamp '{timestamp}'. Use ISO-8601.",
            )

    saved_path = await save_upload(file)
    try:
        result = ingest_image(
            image_path = saved_path,
            camera_id  = camera_id,
            timestamp  = ts,
            db         = db,
        )
    except ValueError as exc:
        _cleanup_upload(saved_path)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        _cleanup_upload(saved_path)
        logger.error("[POST /process] Pipeline error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline error: {exc}") from exc

    plates = sorted({
        d.plate_number
        for d in result.detections
        if d.plate_number
    })

    return ProcessResponse(
        status               = result.status,
        source_file          = result.source_file,
        camera_id            = result.camera_id,
        timestamp            = result.timestamp,
        latitude             = result.latitude,
        longitude            = result.longitude,
        total_vehicles       = result.total_vehicles,
        total_plates         = result.total_plates,
        low_confidence_count = result.low_confidence_plates,
        plates_detected      = plates,
        annotated_image_url  = result.annotated_image_url,
        warnings             = result.warnings,
    )


# ── GET /vehicles  (Phase 8) ──────────────────────────────────────────────────

@app.get(
    "/vehicles",
    response_model = VehicleListResponse,
    tags           = ["Vehicles – Phase 8"],
    summary        = "Paginated list of all tracked vehicles with status",
)
def list_vehicles_p8(
    limit         : int           = Query(100, ge=1, le=500,  description="Page size"),
    offset        : int           = Query(0,   ge=0,           description="Page offset"),
    status_filter : Optional[str] = Query(None, description="Filter by status: active | suspicious | impossible | unknown"),
    db            : Session       = Depends(get_db),
):
    """
    **Phase 8 vehicle list** — designed for the React vehicles table/grid.

    Each item in `vehicles` contains:

    | Field | Description |
    |-------|-------------|
    | `plate_number` | Normalised plate string |
    | `vehicle_type` | Most common detected type |
    | `confidence` | Highest detection confidence |
    | `first_seen` / `last_seen` | ISO-8601 timestamps |
    | `camera_count` | Distinct cameras that saw this plate |
    | `total_sightings` | Total detection events |
    | `status` | `active` / `suspicious` / `impossible` / `unknown` |
    | `last_camera_id` | Most recent camera ID |
    | `last_location` | Most recent camera location name |
    | `is_blacklisted` | True when in demo blacklist |

    Use `?status_filter=suspicious` to show only anomalous vehicles.
    """
    logger.info("GET /vehicles limit=%d offset=%d filter=%s", limit, offset, status_filter)
    return get_vehicle_list(db, limit=limit, offset=offset, status_filter=status_filter)


# ── GET /vehicles/{plate}  (Phase 8) ─────────────────────────────────────────

@app.get(
    "/vehicles/{plate}",
    response_model = VehicleRecord,
    tags           = ["Vehicles – Phase 8"],
    summary        = "Single vehicle detail card",
)
def get_vehicle_p8(plate: str, db: Session = Depends(get_db)):
    """
    **Phase 8 vehicle detail card.**

    Returns the same fields as the vehicle list but for a single plate.
    Use this to populate a vehicle detail modal in the frontend.

    The `status` field reflects the most recent trajectory classification:
    - `active`      — seen recently, normal movement
    - `suspicious`  — movement speed 120–200 km/h or anomalous jump
    - `impossible`  — speed > 200 km/h or negative timestamp gap
    - `unknown`     — only one detection, cannot classify

    **Pre-seeded demo plates:** `TS09AB1234`, `MH12XY5678`, `DL01ZZ9999`
    """
    logger.info("GET /vehicles/%s", plate)
    return get_vehicle_detail(db, plate)


# ── GET /trajectory/{plate}  (Phase 8 — overrides Phase 4 path) ──────────────
#
# NOTE: The Phase 4 endpoint /trajectory/{plate_number} is kept as-is.
# This Phase 8 endpoint uses a different path prefix so both coexist.

@app.get(
    "/api/trajectory/{plate}",
    response_model = FrontendTrajectoryResponse,
    tags           = ["Trajectory – Phase 8"],
    summary        = "Frontend-ready trajectory with anomaly score",
)
def get_trajectory_p8(plate: str, db: Session = Depends(get_db)):
    """
    **Phase 8 trajectory endpoint** for the UrbanEye AI frontend.

    Returns a clean trajectory shape with:
    - `stops` — ordered list of camera sightings with GPS coords
    - `hops` — metrics between consecutive cameras (distance, speed, anomaly)
    - `anomaly_score` — 0.0 (NORMAL) → 1.0 (IMPOSSIBLE) for heat-map colouring
    - `overall_status` — plain string (NORMAL / FAST / SUSPICIOUS / IMPOSSIBLE)
    - `data_mode` — always `"DEMO / SIMULATED TRAJECTORY"` until live feed

    The existing `GET /trajectory/{plate_number}` (Phase 4) is unchanged.

    **Pre-seeded demo plates:** `TS09AB1234`, `MH12XY5678`, `DL01ZZ9999`
    """
    logger.info("GET /api/trajectory/%s", plate)
    return get_frontend_trajectory(db, plate)


# ── GET /analytics  (Phase 8 unified dashboard) ───────────────────────────────

@app.get(
    "/analytics",
    response_model = UnifiedAnalyticsResponse,
    tags           = ["Analytics – Phase 8"],
    summary        = "Unified dashboard payload – KPIs + distribution + trends + zones",
)
def analytics_unified(
    window_hours: int = Query(24, ge=1, le=168, description="Look-back window in hours (default 24h)"),
    db: Session = Depends(get_db),
):
    """
    **Phase 8 unified analytics endpoint** — one request to populate the full dashboard.

    Returns:
    - **KPI cards**: `total_vehicles`, `total_unique_plates`, `total_cameras`,
      `active_alerts`, `suspicious_vehicles`
    - **Vehicle distribution**: pie-chart data with `category`, `count`, `percentage`
    - **Traffic density**: overall label (LOW/MEDIUM/HIGH/SEVERE), `average_speed_kmh`,
      `congestion_score`
    - **Congestion zones**: HIGH/SEVERE cameras with GPS for map markers
    - **Traffic trends**: 24-point hourly chart for line graph
    - **Most active camera**: for dashboard highlight card

    **Congestion score formula:**
    ```
    congestion_score = total_detections / (500 × window_hours)
    ```
    Score > 1.0 means demand exceeds the 500 vehicles/hour baseline.
    """
    logger.info("GET /analytics window_hours=%d", window_hours)
    return get_unified_analytics(db, window_hours=window_hours)


# ── GET /cameras  (Phase 8 alias — trajectory cameras with full metadata) ─────

@app.get(
    "/api/cameras",
    response_model = List[dict],
    tags           = ["Cameras – Phase 8"],
    summary        = "All cameras with full metadata (GPS + zone + status) for map rendering",
)
def list_cameras_p8(db: Session = Depends(get_db)):
    """
    **Phase 8 camera list** — combines Phase-3 ANPR cameras with Phase-4
    trajectory camera metadata for map rendering.

    Returns all trajectory cameras from `data/metadata/cameras.json`
    enriched with live detection counts.

    For camera CRUD use the Phase-3 `GET /cameras` endpoint.
    """
    from app.models.trajectory_camera import TrajectoryCamera
    from sqlalchemy import func
    from app.models.detection import Detection as Det
    from datetime import timedelta, timezone

    cameras = db.query(TrajectoryCamera).order_by(TrajectoryCamera.camera_id).all()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    count_rows = (
        db.query(Det.camera_id, func.count(Det.id).label("cnt"))
          .filter(Det.timestamp >= cutoff)
          .group_by(Det.camera_id)
          .all()
    )
    count_map = {r.camera_id: r.cnt for r in count_rows}

    result = []
    for cam in cameras:
        result.append({
            "camera_id"     : cam.camera_id,
            "location_name" : cam.location_name,
            "road_name"     : cam.road_name,
            "direction"     : cam.direction,
            "latitude"      : cam.latitude,
            "longitude"     : cam.longitude,
            "detections_last_hour": count_map.get(cam.camera_id, 0),
        })

    logger.info("GET /api/cameras — returned %d cameras", len(result))
    return result
