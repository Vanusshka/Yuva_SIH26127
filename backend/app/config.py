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
DATABASE_URL = f"sqlite:///{DATA_DIR / 'traffic.db'}"

# ── Vehicle Detection (YOLOv8) ────────────────────────────────────────────────
VEHICLE_MODEL_NAME   = "best.pt"
VEHICLE_CONF_THRESH  = 0.40

# Class indices for the trained 6-class vehicle detector (best.pt).
# These are NOT COCO indices — they are the model's own 0-based indices
# matching the order used during training:
#   0=car, 1=motorcycle, 2=auto_rickshaw, 3=bus, 4=truck, 5=bicycle
VEHICLE_CLASS_IDS = {
    0: "car",
    1: "motorcycle",
    2: "auto_rickshaw",
    3: "bus",
    4: "truck",
    5: "bicycle",
}

# Vehicle category groupings (used for two-wheeler plate upscaling etc.)
TWO_WHEELER_CLASSES     = {1, 5}       # motorcycle, bicycle
CAR_COMMERCIAL_CLASSES  = {0, 2, 3, 4} # car, auto_rickshaw, bus, truck

# Two-wheeler specific detection parameters
TWO_WHEELER_CONF_THRESH   = 0.30
TWO_WHEELER_MIN_PLATE_W   = 40
TWO_WHEELER_PLATE_UPSCALE = 2.0


def get_vehicle_category(vehicle_class: str) -> str:
    """
    Return a human-readable category for a detected vehicle class.

    Returns
    -------
    "two_wheeler"     for motorcycle, bicycle
    "three_wheeler"   for auto_rickshaw
    "car_commercial"  for car, bus, truck
    "unknown"         if class is not recognised
    """
    _MAP = {
        "car"           : "car_commercial",
        "bus"           : "car_commercial",
        "truck"         : "car_commercial",
        "motorcycle"    : "two_wheeler",
        "bicycle"       : "two_wheeler",
        "auto_rickshaw" : "three_wheeler",
    }
    return _MAP.get(vehicle_class.lower(), "unknown")


# ── Plate Detection ───────────────────────────────────────────────────────────
PLATE_MODEL_NAME  = "plate_detector_best_fast.pt"   # trained model, mAP50 0.984
PLATE_CONF_THRESH = 0.30

# ── OCR ───────────────────────────────────────────────────────────────────────
# Switch to "paddleocr" to use the fine-tuned SVTR_LCNet recognizer.
# Switch to "easyocr" or "tesseract" for the generic fallbacks.
OCR_ENGINE           = "paddleocr"  # fine-tuned SVTR_LCNet — paddleocr_infer/ verified on disk
OCR_LANGUAGES        = ["en"]

# ── PaddleOCR fine-tuned recognizer paths ────────────────────────────────────
# Only used when OCR_ENGINE == "paddleocr".
#
# PADDLEOCR_REPO_DIR   : directory containing ppocr/ and tools/infer/ subtrees
#                        (NOT the full PaddleOCR repo — only those two folders).
# PADDLE_REC_MODEL_DIR : exported inference model directory
#                        (inference.pdiparams + inference.json inside).
# PADDLE_CHAR_DICT_PATH: character dictionary used during training.
PADDLEOCR_REPO_DIR    = MODELS_DIR / "paddleocr_infer"
PADDLE_REC_MODEL_DIR  = MODELS_DIR / "plates_inference_model_final"
PADDLE_CHAR_DICT_PATH = PADDLEOCR_REPO_DIR / "ppocr" / "utils" / "en_dict.txt"

# ── API ───────────────────────────────────────────────────────────────────────
API_TITLE   = "SIH26127 ANPR API"
API_VERSION = "0.5.0"
MAX_UPLOAD_MB = 20

# ── Video ingestion ───────────────────────────────────────────────────────────
DEFAULT_FRAME_SKIP = 5

# ── Trajectory thresholds ─────────────────────────────────────────────────────
SPEED_FAST_KMPH         = 80.0
SPEED_SUSPICIOUS_KMPH   = 120.0
SPEED_IMPOSSIBLE_KMPH   = 200.0
DUPLICATE_WINDOW_SECS   = 30
MIN_INTER_CAMERA_KM     = 0.05

# ── Change 7+8: Fuzzy trajectory matching ────────────────────────────────────
# Maximum Levenshtein edit distance for a plate to be considered a possible
# OCR variation of another plate in the trajectory engine.
# 0 = exact match only (original behaviour)
# 1 = allow 1-character difference (e.g. TS09AB1234 vs TS09A81234)
# Keep conservative — fuzzy match ALONE does not confirm a trajectory.
TRAJECTORY_FUZZY_MAX_EDIT_DISTANCE = 1   # configurable

# Minimum real-world travel time (minutes) per km between cameras.
# Used to reject physically impossible trajectory hops.
# 120 km/h city speed limit → 0.5 min/km is the absolute minimum.
# We use 0.4 min/km (150 km/h) as the hard rejection threshold.
TRAJECTORY_MIN_MINUTES_PER_KM = 0.4     # configurable

# ── Change 2+3: OCR Multi-frame confidence tiers ─────────────────────────────
# These thresholds are applied to the multi-frame AGREEMENT RATE (0.0–1.0).
# agreement_rate = matching_ocr_reads / valid_ocr_reads
# where valid_ocr_reads = reads with char_count >= MIN_CHARS_PARTIAL
#
# Tier assignment (configurable):
#   HIGH   : agreement_rate >= HIGH_AGREEMENT_THRESH
#   MEDIUM : agreement_rate >= MEDIUM_AGREEMENT_THRESH
#   LOW    : agreement_rate <  MEDIUM_AGREEMENT_THRESH (or only 1 read)
#
# Additionally, a minimum number of valid reads is required for HIGH.
OCR_HIGH_AGREEMENT_THRESH   = 0.75   # >= 75 % of valid reads agree → HIGH
OCR_MEDIUM_AGREEMENT_THRESH = 0.40   # >= 40 % agree → MEDIUM; else LOW
OCR_MIN_READS_FOR_HIGH      = 2      # need at least 2 valid reads for HIGH

# ── Change 5: Blacklist confidence gate ──────────────────────────────────────
# Only confidence tiers at or above this level may auto-trigger a blacklist alert.
# LOW-confidence reads are sent to the manual review queue instead.
BLACKLIST_MIN_TIER_FOR_ALERT = "MEDIUM"   # "HIGH" | "MEDIUM"

# ── Change 9: Compliance anomaly ─────────────────────────────────────────────
# How many consecutive frames a vehicle must be tracked without any plate
# detection before a COMPLIANCE_ANOMALY alert is considered.
COMPLIANCE_ANOMALY_MIN_FRAMES_WITHOUT_PLATE = 3
