"""
Central configuration for the SIH26127 ANPR backend.
All paths and tuneable constants live here.
"""

from pathlib import Path

# ── Base Paths ────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).resolve().parents[1]   # backend/
DATA_DIR    = BASE_DIR / "data"
INPUT_DIR   = DATA_DIR / "input"
OUTPUT_DIR  = DATA_DIR / "output"
MODELS_DIR  = BASE_DIR / "models"

# Ensure directories exist at import time
for _d in (INPUT_DIR, OUTPUT_DIR, MODELS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── Database ──────────────────────────────────────────────────────────────────
# SQLite for development.  Swap DATABASE_URL for PostgreSQL in production:
#   postgresql+psycopg2://user:password@host:5432/dbname
DATABASE_URL = f"sqlite:///{DATA_DIR / 'traffic.db'}"

# ── Vehicle Detection (YOLOv8) ────────────────────────────────────────────────
VEHICLE_MODEL_NAME   = "yolov8n.pt"          # auto-downloaded by Ultralytics
VEHICLE_CONF_THRESH  = 0.40
VEHICLE_CLASS_IDS    = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}

# ── Plate Detection ───────────────────────────────────────────────────────────
# YOLO model trained on license plates.
# URLs tried in order by plate_detector.py; first successful download wins.
PLATE_MODEL_NAME     = "license_plate_detector.pt"
# The original GitHub URL was 404. plate_detector.py now tries multiple sources.
PLATE_MODEL_URL      = (
    "https://huggingface.co/Koushim/yolov8-license-plate-detection/resolve/main/best.pt"
)
PLATE_CONF_THRESH    = 0.30

# ── OCR ───────────────────────────────────────────────────────────────────────
OCR_ENGINE           = "easyocr"   # "easyocr" | "tesseract"
OCR_LANGUAGES        = ["en"]

# ── API ───────────────────────────────────────────────────────────────────────
API_TITLE   = "SIH26127 ANPR API"
API_VERSION = "0.5.0"
# ── Video ingestion ───────────────────────────────────────────────────────────
# Default frame skip — changed from 10 → 5 (Phase 9) for better plate coverage.
# Lower = more frames analysed = better multi-frame consensus but slower.
# Frontend lets user override this (1–300 range).
MAX_UPLOAD_MB = 20

# ── Video ingestion ───────────────────────────────────────────────────────────
# Default frame skip — changed from 10 → 5 (Phase 9) for better plate coverage.
# Lower = more frames = better multi-frame consensus, but slower.
# Frontend lets the user override this (1–300 range).
DEFAULT_FRAME_SKIP = 5

# ── Trajectory thresholds ─────────────────────────────────────────────────────
# Speed above this → FAST classification
SPEED_FAST_KMPH         = 80.0
# Speed above this → SUSPICIOUS classification
SPEED_SUSPICIOUS_KMPH   = 120.0
# Speed physically impossible on city roads → IMPOSSIBLE
SPEED_IMPOSSIBLE_KMPH   = 200.0
# Duplicate detection: same plate + same camera within this many seconds
DUPLICATE_WINDOW_SECS   = 30
# Minimum believable distance between two different cameras (km)
MIN_INTER_CAMERA_KM     = 0.05
