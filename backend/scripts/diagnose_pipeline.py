"""
Pipeline Diagnostic Script
===========================
Traces the full detection pipeline and identifies exactly what is broken.
Run from backend/:  python scripts/diagnose_pipeline.py
"""
import sys, os, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, ".")

import cv2
import numpy as np

print("=" * 60)
print("  PHASE 1 — PACKAGE IMPORTS")
print("=" * 60)

for name in ["torch", "ultralytics", "easyocr", "cv2", "numpy"]:
    try:
        m = __import__(name)
        print(f"  OK   {name:15s} {getattr(m,'__version__','?')}")
    except Exception as e:
        print(f"  FAIL {name:15s} {e}")

print()
print("=" * 60)
print("  PHASE 2 — VEHICLE DETECTOR (YOLO)")
print("=" * 60)

# Check ultralytics available flag
from app.models.vehicle_detector import VehicleDetector, _ULTRALYTICS_AVAILABLE
print(f"  _ULTRALYTICS_AVAILABLE = {_ULTRALYTICS_AVAILABLE}")

if _ULTRALYTICS_AVAILABLE:
    vd = VehicleDetector()
    vd._load()
    if vd._model:
        print(f"  Model loaded           : YES")
        print(f"  Model type             : {type(vd._model)}")
        print(f"  Vehicle class IDs used : {list(vd._model.names.items())[:10]}")
        # Show only the IDs we care about
        from app.config import VEHICLE_CLASS_IDS
        print(f"  Config VEHICLE_CLASS_IDS : {VEHICLE_CLASS_IDS}")
        for cid, cname in VEHICLE_CLASS_IDS.items():
            model_name = vd._model.names.get(cid, "NOT FOUND")
            match = "✓" if model_name.lower() == cname.lower() else f"✗ (model says '{model_name}')"
            print(f"    ID {cid}: config='{cname}'  model='{model_name}'  {match}")
    else:
        print("  Model loaded           : NO (None)")
else:
    print("  SKIP — ultralytics not available")

print()
print("=" * 60)
print("  PHASE 3 — SYNTHETIC FRAME TEST (vehicle detection)")
print("=" * 60)

# Create a synthetic 640x480 BGR image with a grey rectangle (fake car)
test_frame = np.full((480, 640, 3), 100, dtype=np.uint8)
cv2.rectangle(test_frame, (80, 100), (560, 380), (70, 70, 70), -1)   # car body
cv2.rectangle(test_frame, (140, 120), (500, 240), (160, 200, 220), -1)  # windscreen

if _ULTRALYTICS_AVAILABLE:
    vd = VehicleDetector()
    detections = vd.detect(test_frame)
    print(f"  Detections on synthetic frame : {len(detections)}")
    for d in detections:
        print(f"    class={d.vehicle_class}  conf={d.confidence}  bbox={d.bbox}")
    if len(detections) == 0:
        print("  NOTE: Synthetic image unlikely to fool YOLO — needs a real photo")
else:
    print("  SKIP — ultralytics not available")

print()
print("=" * 60)
print("  PHASE 4 — PLATE DETECTOR")
print("=" * 60)

from app.models.plate_detector import PlateDetector
pd = PlateDetector()
pd._load()
print(f"  _use_yolo          : {pd._use_yolo}")
print(f"  _model             : {'LOADED' if pd._model else 'None'}")

from app.config import MODELS_DIR, PLATE_MODEL_NAME
model_path = MODELS_DIR / PLATE_MODEL_NAME
print(f"  Model path         : {model_path}")
print(f"  Model file exists  : {model_path.exists()}")
if model_path.exists():
    print(f"  Model file size    : {model_path.stat().st_size:,} bytes")

# Test contour fallback on a test plate image
plate_img = np.full((64, 200, 3), 255, dtype=np.uint8)
cv2.rectangle(plate_img, (5, 5), (195, 59), (0, 0, 0), 2)
cv2.putText(plate_img, "TS09AB1234", (10, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,0,0), 2)

plate_dets = pd.detect(plate_img)
print(f"  Detections on plate image : {len(plate_dets)}")
for p in plate_dets:
    print(f"    conf={p.confidence}  bbox={p.bbox}  crop_shape={p.cropped_image.shape}")

# Test on full frame
frame_dets = pd.detect(test_frame)
print(f"  Detections on full frame  : {len(frame_dets)}")

print()
print("=" * 60)
print("  PHASE 5 — OCR ENGINE")
print("=" * 60)

from app.models.ocr_engine import OCREngine, _EasyOCREngine
from app.config import OCR_ENGINE
print(f"  OCR_ENGINE config  : {OCR_ENGINE}")

try:
    import easyocr
    print(f"  easyocr available  : YES  v{easyocr.__version__}")
    print(f"  Initialising reader (may take ~10s first time)...")
    reader = _EasyOCREngine._get_reader()
    print(f"  Reader ready       : YES  ({type(reader).__name__})")

    # Test on synthetic plate crop
    ocr_engine = OCREngine()
    result = ocr_engine.read_plate(plate_img)
    print(f"  OCR on plate image :")
    print(f"    plate_number  = '{result.plate_number}'")
    print(f"    ocr_confidence= {result.ocr_confidence}")
    print(f"    raw_text      = '{result.raw_text}'")

except Exception as e:
    print(f"  OCR FAILED: {e}")
    import traceback; traceback.print_exc()

print()
print("=" * 60)
print("  PHASE 6 — INGEST_SERVICE SINGLETON CHECK")
print("=" * 60)

from app.services.ingest_service import (
    _vehicle_detector, _plate_detector, _ocr_engine, _ULTRALYTICS_AVAILABLE as IA
)
print(f"  ingest_service._ULTRALYTICS_AVAILABLE = {IA}")
print(f"  _vehicle_detector type : {type(_vehicle_detector)}")
print(f"  _plate_detector type   : {type(_plate_detector)}")
print(f"  _ocr_engine type       : {type(_ocr_engine)}")

# Force-load the vehicle model inside the singleton
_vehicle_detector._load()
print(f"  VehicleDetector._model loaded : {_vehicle_detector._model is not None}")
_plate_detector._load()
print(f"  PlateDetector._use_yolo       : {_plate_detector._use_yolo}")
print(f"  PlateDetector._model          : {_plate_detector._model is not None}")

print()
print("=" * 60)
print("  PHASE 7 — ORPHAN PLATE BUG ANALYSIS")
print("=" * 60)
print()
print("  The '129 Unknown' detections came from the ORPHAN PLATE path.")
print("  When VehicleDetector returns [] (ultralytics not installed),")
print("  the contour fallback runs on EVERY frame and finds ~3 contours/frame.")
print("  44 frames × ~3 contours = ~129 'unknown' orphan detections.")
print("  These were contour detections of trees/signs/shadows — NOT real vehicles.")
print()
print("  With ultralytics now installed:")
if _ULTRALYTICS_AVAILABLE:
    print("  → VehicleDetector will run YOLO — real car/motorcycle/bus/truck classes")
    print("  → Contour orphan path will only run for unmatched plates")
else:
    print("  → Still UNAVAILABLE — check import")

print()
print("=" * 60)
print("  DIAGNOSIS SUMMARY")
print("=" * 60)
print()
issues = []
if not _ULTRALYTICS_AVAILABLE:
    issues.append("CRITICAL: ultralytics not importable — VehicleDetector returns []")
if not _plate_detector._use_yolo and not model_path.exists():
    issues.append("WARNING:  plate model not found — using contour fallback only")
try:
    import easyocr
except ImportError:
    issues.append("CRITICAL: easyocr not installed — OCR will return empty string")

if not issues:
    print("  ALL SYSTEMS GO — pipeline should work correctly now")
    print()
    print("  EXPECTED RESULTS after fix:")
    print("  - vehicle_type will show: car / motorcycle / bus / truck (not 'unknown')")
    print("  - plate detection will run on each vehicle crop + full frame")
    print("  - OCR will extract text from detected plate crops")
else:
    for i in issues:
        print(f"  {i}")
