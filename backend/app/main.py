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

Analytics advanced (C3/C4/C5)
  GET /analytics/heatmap       – C3 per-camera density + GeoJSON heatmap
  GET /analytics/od-matrix     – C4 origin-destination flow matrix + GeoJSON arcs
  GET /analytics/bottlenecks   – C5 sustained congestion bottleneck ranking

Natural Language Query
  POST /query                  – plain-English question → structured DB results

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
    file         : UploadFile    = File(...,  description="Traffic image (JPEG/PNG/BMP/WebP)"),
    camera_id    : str           = Form(default="CAM_001", description="Camera ID (from cameras.json)"),
    timestamp    : Optional[str] = Form(default=None,      description="ISO-8601 timestamp (defaults to UTC now)"),
    privacy_mode : bool          = Form(default=True,       description="Blur face regions before detection. Default: True (recommended for all deployments)."),
    db           : Session       = Depends(get_db),
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
            image_path   = saved_path,
            camera_id    = camera_id,
            timestamp    = ts,
            db           = db,
            privacy_mode = privacy_mode,
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
    file             : UploadFile    = File(...,  description="Traffic video (MP4/AVI/MOV/MKV)"),
    camera_id        : str           = Form(default="CAM_001", description="Camera ID"),
    timestamp        : Optional[str] = Form(default=None,      description="ISO-8601 timestamp of first frame"),
    frame_skip       : int           = Form(default=5,          description="Process every N-th frame (default 5). Lower=more detections, slower. Set to 2-3 for best ANPR results."),
    demo_multi_camera: bool          = Form(default=False,      description=(
        "⚠ DEMO ONLY — assign detections to synthetic cameras from DEMO_CAMERA_SEQUENCE "
        "(round-robin per tracked vehicle) so trajectory/GIS features can be demonstrated "
        "from a single video source. Detection data is real; camera locations are synthetic."
    )),
    privacy_mode     : bool          = Form(default=True,       description=(
        "Blur detected face regions on every frame BEFORE plate detection runs. "
        "Recommended True for all real deployments. Default: PRIVACY_MODE from config."
    )),
    db               : Session       = Depends(get_db),
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

    **Note:** Processing runs in a background thread so the API stays responsive
    (health checks, alerts, analytics) during heavy CPU video processing.
    """
    from starlette.concurrency import run_in_threadpool

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
        # Run the CPU-heavy pipeline in a thread pool so the event loop
        # stays free to answer /health, /alerts, /analytics during processing.
        result = await run_in_threadpool(
            ingest_video,
            saved_path,
            camera_id,
            ts,
            frame_skip,
            db,
            demo_multi_camera,
            privacy_mode,
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


# ── Advanced Analytics: C3 Heatmap · C4 OD Matrix · C5 Bottlenecks ───────────

from app.services.advanced_analytics_service import (
    get_heatmap,
    get_od_matrix,
    get_bottlenecks,
)
from app.schemas.c3_c5 import (
    HeatmapResponse,
    ODMatrixResponse,
    BottleneckResponse,
)


@app.get(
    "/analytics/heatmap",
    response_model = HeatmapResponse,
    tags           = ["Analytics – Advanced"],
    summary        = "C3 Traffic density heatmap — per-camera intensity + GeoJSON",
)
def analytics_heatmap(
    window_hours: int = Query(1, ge=1, le=24,
                              description="Look-back window in hours (default 1h)"),
    db: Session = Depends(get_db),
):
    """
    **C3 — Traffic Flow Heatmap**

    Returns per-camera vehicle density with GeoJSON FeatureCollection for
    direct map layer rendering.

    **Intensity** is normalised 0.0–1.0 (busiest camera = 1.0). Feed this
    value to Leaflet `L.heatLayer()` or Mapbox `addSource(type='geojson')`.

    **GeoJSON format:** FeatureCollection of Point features with properties:
    - `camera_id`, `location_name`
    - `vehicle_count` — raw count in the window
    - `density_label` — LOW | MEDIUM | HIGH | SEVERE
    - `intensity` — normalised weight for heatmap rendering

    Statistical method: vehicle count per camera per time window.
    No ML model — pure aggregation from the Detection table.
    """
    return get_heatmap(db, window_hours=window_hours)


@app.get(
    "/analytics/od-matrix",
    response_model = ODMatrixResponse,
    tags           = ["Analytics – Advanced"],
    summary        = "C4 Origin-Destination matrix — camera-pair flow counts + GeoJSON arcs",
)
def analytics_od_matrix(
    window_hours: int = Query(24, ge=1, le=168,
                              description="Look-back window in hours (default 24h)"),
    top_n       : int = Query(20, ge=1, le=100,
                              description="Maximum OD pairs to return, ranked by volume"),
    db: Session = Depends(get_db),
):
    """
    **C4 — Origin-Destination Pattern Detection**

    Derives travel patterns from the real Detection table:
    - origin = first camera a plate was seen at in the window
    - destination = last camera that same plate was seen at
    - count = number of distinct plates making that journey

    Also returns `avg_duration_min` and `avg_distance_km` per OD pair, and a
    **GeoJSON FeatureCollection of LineString arcs** for desire-line map rendering
    (feed to Leaflet polyline or Mapbox line layer).

    Plates seen at only one camera are excluded (no journey to measure).

    Data pipeline method: GROUP BY (first_camera, last_camera) on Detection table.
    No ML model.
    """
    return get_od_matrix(db, window_hours=window_hours, top_n=top_n)


@app.get(
    "/analytics/bottlenecks",
    response_model = BottleneckResponse,
    tags           = ["Analytics – Advanced"],
    summary        = "C5 Congestion bottleneck ranking — sustained congestion by persistence score",
)
def analytics_bottlenecks(
    window_hours      : int = Query(3,  ge=1, le=24,
                                   description="Total look-back window (default 3h)"),
    sub_window_minutes: int = Query(30, ge=5, le=120,
                                   description="Sub-window size in minutes (default 30min)"),
    top_n             : int = Query(10, ge=1, le=50,
                                   description="Maximum bottlenecks to return"),
    db: Session = Depends(get_db),
):
    """
    **C5 — Congestion Bottleneck Detection**

    Identifies cameras with *sustained* congestion rather than momentary spikes.

    **Method:**
    1. Divide the look-back window into sub-windows of `sub_window_minutes`
    2. For each sub-window × camera: label HIGH or SEVERE if count ≥ threshold
    3. `persistence` = fraction of sub-windows where camera was HIGH/SEVERE (0.0–1.0)
    4. `bottleneck_score` = total_vehicle_count × persistence
    5. Rank by bottleneck_score descending

    **Why this beats simple density:**
    A camera with 3 vehicles/hour right now ranks lower than one that has been
    SEVERE for the past 2 hours — this finds structural bottlenecks, not noise.

    **`congested_since`** — ISO timestamp of the first sub-window where congestion
    was detected, useful for "congested for X minutes" labels in the UI.

    Rule-based method (threshold on density per sub-window). No ML model required.
    Optional upgrade: replace persistence threshold with z-score or Isolation Forest
    on the per-camera time series for anomaly-detection framing.
    """
    return get_bottlenecks(
        db,
        window_hours       = window_hours,
        sub_window_minutes = sub_window_minutes,
        top_n              = top_n,
    )


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


# ═══════════════════════════════════════════════════════════════════════════════
# RELIABILITY UPGRADE — Manual Review API endpoints (Change 6)
# ═══════════════════════════════════════════════════════════════════════════════

from app.services.manual_review_service import (
    get_pending_reviews,
    get_all_reviews,
    get_review_by_id,
    submit_decision,
    REVIEW_PENDING, REVIEW_CONFIRMED, REVIEW_REJECTED, REVIEW_EDITED,
)
from app.models.manual_review import ManualReview as ManualReviewModel
from pydantic import BaseModel as _BaseModel
from typing import Optional as _Opt


class ManualReviewOut(_BaseModel):
    """API response shape for a ManualReview item."""
    id                 : int
    camera_id          : str
    timestamp          : str
    vehicle_type       : _Opt[str]
    vehicle_category   : _Opt[str]
    ocr_plate_text     : _Opt[str]
    ocr_confidence     : _Opt[float]
    confidence_tier    : str
    agreement_rate     : _Opt[float]
    valid_ocr_reads    : _Opt[int]
    matching_ocr_reads : _Opt[int]
    source_file        : _Opt[str]
    frame_number       : _Opt[int]
    track_id           : _Opt[str]
    reason             : str
    review_status      : str
    reviewed_plate     : _Opt[str]
    reviewer_notes     : _Opt[str]
    reviewed_at        : _Opt[str]
    created_at         : str

    @classmethod
    def from_orm_obj(cls, m: ManualReviewModel) -> "ManualReviewOut":
        return cls(
            id=m.id, camera_id=m.camera_id,
            timestamp=m.timestamp.isoformat() if m.timestamp else "",
            vehicle_type=m.vehicle_type, vehicle_category=m.vehicle_category,
            ocr_plate_text=m.ocr_plate_text, ocr_confidence=m.ocr_confidence,
            confidence_tier=m.confidence_tier, agreement_rate=m.agreement_rate,
            valid_ocr_reads=m.valid_ocr_reads, matching_ocr_reads=m.matching_ocr_reads,
            source_file=m.source_file, frame_number=m.frame_number, track_id=m.track_id,
            reason=m.reason, review_status=m.review_status,
            reviewed_plate=m.reviewed_plate, reviewer_notes=m.reviewer_notes,
            reviewed_at=m.reviewed_at.isoformat() if m.reviewed_at else None,
            created_at=m.created_at.isoformat() if m.created_at else "",
        )


class ReviewDecisionIn(_BaseModel):
    decision       : str                # CONFIRMED | REJECTED | EDITED
    reviewed_plate : _Opt[str] = None   # required when decision == EDITED
    notes          : _Opt[str] = None


@app.get(
    "/manual-review",
    tags    = ["Manual Review – Reliability"],
    summary = "List manual review items (pending by default)",
)
def list_manual_reviews(
    status : _Opt[str] = Query(None,  description="Filter: PENDING|CONFIRMED|REJECTED|EDITED"),
    limit  : int        = Query(50,   ge=1, le=200),
    offset : int        = Query(0,    ge=0),
    db     : Session    = Depends(get_db),
):
    """
    Return manual review items for plates that could not be auto-verified.

    LOW-confidence OCR reads are routed here instead of triggering automatic
    blacklist alerts (Change 5 safety gate).

    Returns honest evidence: ocr_plate_text, confidence_tier, agreement_rate,
    valid_ocr_reads, matching_ocr_reads.
    No fabricated data.
    """
    items = get_all_reviews(db, status=status, limit=limit, offset=offset)
    return {
        "total"  : len(items),
        "items"  : [ManualReviewOut.from_orm_obj(m) for m in items],
    }


@app.get(
    "/manual-review/pending",
    tags    = ["Manual Review – Reliability"],
    summary = "List only PENDING review items",
)
def list_pending_reviews(
    limit  : int     = Query(50, ge=1, le=200),
    offset : int     = Query(0,  ge=0),
    db     : Session = Depends(get_db),
):
    items = get_pending_reviews(db, limit=limit, offset=offset)
    return {
        "total"  : len(items),
        "items"  : [ManualReviewOut.from_orm_obj(m) for m in items],
    }


@app.get(
    "/manual-review/{review_id}",
    tags    = ["Manual Review – Reliability"],
    summary = "Get a single review item by ID",
)
def get_single_review(review_id: int, db: Session = Depends(get_db)):
    item = get_review_by_id(db, review_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Review {review_id} not found.")
    return ManualReviewOut.from_orm_obj(item)


@app.post(
    "/manual-review/{review_id}/decision",
    tags    = ["Manual Review – Reliability"],
    summary = "Submit a review decision (CONFIRMED | REJECTED | EDITED)",
)
def submit_review_decision(
    review_id : int,
    body      : ReviewDecisionIn,
    db        : Session = Depends(get_db),
):
    """
    Record an operator decision for a review item.

    - CONFIRMED : plate text is correct as-is
    - REJECTED  : plate could not be verified (do not alert)
    - EDITED    : operator corrected the plate text (reviewed_plate required)

    Only CONFIRMED or EDITED items become eligible for blacklist matching.
    REJECTED items are never matched.
    """
    try:
        item = submit_decision(
            db            = db,
            review_id     = review_id,
            decision      = body.decision,
            reviewed_plate= body.reviewed_plate,
            notes         = body.notes,
        )
        return ManualReviewOut.from_orm_obj(item)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ── Reliability: fuzzy trajectory endpoint ────────────────────────────────────

@app.get(
    "/api/trajectory/{plate}/fuzzy",
    tags    = ["Trajectory – Reliability Upgrade"],
    summary = "Trajectory reconstruction with fuzzy plate matching (Change 7+8)",
)
def get_trajectory_fuzzy(plate: str, db: Session = Depends(get_db)):
    """
    **Change 7+8: Fuzzy trajectory reconstruction.**

    Uses Levenshtein edit distance <= TRAJECTORY_FUZZY_MAX_EDIT_DISTANCE (default 1)
    to find near-identical OCR variations (e.g. TS09AB1234 vs TS09A81234).

    **Change 8: Travel-time feasibility validation.**
    Hops where the observed travel time is physically impossible given the GPS
    distance are classified as IMPOSSIBLE even if the speed calculation alone
    would not flag them.

    Fuzzy-matched hops are marked SUSPICIOUS in the response.
    Fuzzy match alone does NOT confirm a trajectory — it flags candidates
    for human review.
    """
    from app.trajectory.engine import reconstruct_fuzzy
    return reconstruct_fuzzy(db, plate)


# ═══════════════════════════════════════════════════════════════════════════════
# TRAJECTORY EXPLORER — Demo Dataset endpoints
# ═══════════════════════════════════════════════════════════════════════════════

from app.services.trajectory_demo import get_all_demo_vehicles, get_demo_vehicle


@app.get(
    "/trajectory-explorer/vehicles",
    tags    = ["Trajectory Explorer"],
    summary = "List all demo vehicles available in the Trajectory Explorer",
)
def trajectory_explorer_list():
    """
    Returns the built-in demo vehicle list for the Trajectory Explorer feature.

    ⚠ **DEMO / SAMPLE DATA** — Not from real CCTV cameras.
    Built-in dataset to demonstrate multi-camera trajectory reconstruction.
    """
    return {
        "data_source": "DEMO_DATASET",
        "disclaimer" : "DEMO / SAMPLE DATA — Not from real CCTV. Built-in demo observations only.",
        "vehicles"   : get_all_demo_vehicles(),
    }


@app.get(
    "/trajectory-explorer/{vehicle_id}",
    tags    = ["Trajectory Explorer"],
    summary = "Get full trajectory for a demo vehicle by Vehicle ID or Plate Number",
)
def trajectory_explorer_detail(vehicle_id: str):
    """
    Returns chronological observations + hop metrics for a demo vehicle.

    `vehicle_id` can be either the Vehicle ID (e.g. VH-DEMO-001)
    or the number plate (e.g. TS09AB1234).

    ⚠ **DEMO / SAMPLE DATA** — Not from real CCTV cameras.
    """
    data = get_demo_vehicle(vehicle_id)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Demo vehicle '{vehicle_id}' not found. "
                   f"Try: VH-DEMO-001, TS09AB1234, MH12XY5678, DL01ZZ9999"
        )
    return data

# ═══════════════════════════════════════════════════════════════════════════════
# NATURAL-LANGUAGE QUERY  (POST /query)
# ═══════════════════════════════════════════════════════════════════════════════

from app.services.nl_query_service import process_nl_query
from app.schemas.nl_query import NLQueryRequest, NLQueryResponse as NLQueryResp


@app.post(
    "/query",
    response_model = NLQueryResp,
    tags           = ["Natural Language Query"],
    summary        = "Ask a plain-English question about vehicle/traffic data",
)
def natural_language_query(
    request: NLQueryRequest,
    db     : Session = Depends(get_db),
):
    """
    **Natural Language Query — ask questions in plain English.**

    Type a question and get structured results from the live detection database.

    **Supported question types:**

    | Pattern | Example |
    |---------|---------|
    | Vehicles at a location | "Which vehicles crossed Ameerpet Junction in the last hour?" |
    | Count at a location | "How many vehicles at Begumpet in the last 2 hours?" |
    | Plate lookup | "Find plate TS09AB1234" |
    | Time range | "Show vehicles between 6 PM and 7 PM" |
    | Recent activity | "Vehicles in the last 30 minutes" |
    | Suspicious vehicles | "Show suspicious vehicles" |
    | Multi-camera tracking | "Vehicles seen at more than 2 cameras" |
    | Help | "Help" or "What can I ask?" |

    **Response fields:**
    - `answer_text` — one-sentence plain-English answer (show this prominently)
    - `interpreted_as` — what the parser understood (for transparency)
    - `rows` + `columns` — tabular results for table rendering
    - `suggestions` — follow-up questions to show as chips in the UI
    - `confidence` — HIGH | MEDIUM | LOW (parser certainty)

    **Location matching** is fuzzy — "ameerpet", "HITEC", "CAM_001",
    "begumpet junction" all resolve to the correct camera(s).

    No external LLM required — deterministic intent parser, 100% offline.
    """
    logger.info("[NLQuery] POST /query: %r", request.question)
    try:
        return process_nl_query(request, db)
    except Exception as exc:
        logger.error("[NLQuery] Unexpected error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Query processing error: {exc}") from exc


# ═══════════════════════════════════════════════════════════════════════════════
# PRIVACY POLICY  (GET /privacy)
# ═══════════════════════════════════════════════════════════════════════════════

@app.get(
    "/privacy",
    tags    = ["System"],
    summary = "Machine-readable data-handling and privacy policy for this deployment",
)
def privacy_policy():
    """
    **SIH26127 UrbanEye AI — Data Handling & Privacy Policy**

    Returns a machine-readable JSON document describing what data is collected,
    how it is stored, who can access it, and the retention policy.

    Relevant legislation:
    - Information Technology (Amendment) Act 2008
    - Draft Digital Personal Data Protection Act 2023 (India)
    - MeitY AI Governance Guidelines

    This endpoint exists to demonstrate that the system has been designed with
    privacy-by-design principles — a differentiator for city-scale CCTV AI
    deployments where data protection is a real regulatory requirement.
    """
    from app.config import PRIVACY_MODE
    from datetime import date

    return {
        "system"          : "UrbanEye AI — SIH26127 ANPR Backend",
        "version"         : "0.8.0",
        "policy_date"     : str(date.today()),
        "contact"         : "sih26127-urbaneyeai@example.com",

        "data_collected": {
            "plate_text"          : "Detected license plate strings (OCR output)",
            "vehicle_type"        : "Vehicle class (car/motorcycle/bus/truck/auto_rickshaw/bicycle)",
            "detection_confidence": "OCR and detection confidence scores (0.0–1.0)",
            "camera_id"           : "Identifier of the camera that captured the detection",
            "timestamp"           : "UTC timestamp of each detection event",
            "bounding_boxes"      : "Pixel coordinates of vehicle and plate regions",
        },

        "data_NOT_collected": {
            "raw_video_frames"  : "Video frames are processed in-memory and immediately discarded. No raw frames are persisted to disk.",
            "driver_identity"   : "No driver or passenger face data is stored.",
            "vehicle_owner_info": "No ownership or registration database is queried.",
            "location_tracking" : "GPS coordinates are fixed camera locations — not tracked from vehicles.",
        },

        "privacy_mode": {
            "enabled"    : PRIVACY_MODE,
            "description": (
                "When privacy_mode=True, OpenCV Haar cascade face detection runs on every "
                "frame BEFORE plate detection. Detected face regions are Gaussian-blurred "
                "in-memory before any output image is generated. "
                "This ensures no face data enters stored annotated images or debug crops."
            ),
            "implementation": "backend/app/utils/image_utils.py — blur_faces(), redact_frame()",
        },

        "data_retention": {
            "detection_events"  : "Stored in local SQLite DB. No automatic expiry (operator-configured).",
            "annotated_images"  : "Stored in data/output/. Recommend purging after 30 days.",
            "manual_review_items": "Stored until reviewed and closed by an operator.",
            "audit_logs"        : "Standard FastAPI access logs — not persisted by this system.",
        },

        "access_control": {
            "current"   : "Single-instance local deployment — network-level access control required.",
            "recommended": "Deploy behind an authenticated reverse proxy (nginx + OAuth2/JWT).",
        },

        "legal_basis"    : "Law enforcement / public safety under IT Act 2008, Section 69. Data processed by authorised municipal/traffic authorities only.",
        "demo_disclaimer": (
            "This deployment is a SIH2026 competition prototype. "
            "All detection data in the current DB is from test videos, not real CCTV feeds. "
            "Blacklist entries are entirely fictitious."
        ),
    }
