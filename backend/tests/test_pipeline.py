"""
Quick smoke-test for the ANPR pipeline.

Usage (from backend/ directory):
    python -m pytest tests/ -v
    -- or --
    python tests/test_pipeline.py
"""

import sys
from pathlib import Path

# Make sure `app` is importable when running from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import cv2

from app.models.vehicle_detector import VehicleDetector
from app.models.plate_detector   import PlateDetector
from app.models.ocr_engine       import OCREngine, _clean_plate_text, _is_valid_indian_plate


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_blank_image(w=640, h=480):
    """Create a synthetic BGR image (dark grey, no vehicles)."""
    img = np.full((h, w, 3), 60, dtype=np.uint8)
    return img


def _make_plate_image(text="TS09AB1234"):
    """Render a fake white plate with black text for OCR testing."""
    plate = np.full((64, 256, 3), 255, dtype=np.uint8)
    cv2.putText(plate, text, (10, 48),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2, cv2.LINE_AA)
    return plate


# ── tests ─────────────────────────────────────────────────────────────────────

def test_vehicle_detector_loads():
    det = VehicleDetector()
    assert det is not None
    print("  [PASS] VehicleDetector instantiates.")


def test_vehicle_detector_blank_image():
    det      = VehicleDetector()
    blank    = _make_blank_image()
    results  = det.detect(blank)
    assert isinstance(results, list), "detect() must return a list"
    print(f"  [PASS] VehicleDetector on blank image → {len(results)} detections (expected 0).")


def test_plate_detector_loads():
    det = PlateDetector()
    assert det is not None
    print("  [PASS] PlateDetector instantiates.")


def test_plate_detector_blank_image():
    det     = PlateDetector()
    blank   = _make_blank_image()
    results = det.detect(blank)
    assert isinstance(results, list)
    print(f"  [PASS] PlateDetector on blank image → {len(results)} detections.")


def test_ocr_engine_loads():
    eng = OCREngine()
    assert eng is not None
    print("  [PASS] OCREngine instantiates.")


def test_ocr_on_synthetic_plate():
    eng    = OCREngine()
    plate  = _make_plate_image("TS09AB1234")
    result = eng.read_plate(plate)
    assert hasattr(result, "plate_number")
    assert hasattr(result, "ocr_confidence")
    print(f"  [PASS] OCR on synthetic plate → '{result.plate_number}'  conf={result.ocr_confidence}")


def test_clean_plate_text():
    assert _clean_plate_text("ts 09 ab 1234") == "TS09AB1234"
    assert _clean_plate_text("MH-12-AB-1234") == "MH12AB1234"
    assert _clean_plate_text("  DL 3C AB 0001 ") == "DL3CAB0001"
    print("  [PASS] _clean_plate_text works correctly.")


def test_indian_plate_validation():
    assert _is_valid_indian_plate("TS09AB1234")
    assert _is_valid_indian_plate("MH12AB1234")
    assert not _is_valid_indian_plate("ABCDEFG")
    print("  [PASS] _is_valid_indian_plate works correctly.")


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_vehicle_detector_loads,
        test_vehicle_detector_blank_image,
        test_plate_detector_loads,
        test_plate_detector_blank_image,
        test_ocr_engine_loads,
        test_ocr_on_synthetic_plate,
        test_clean_plate_text,
        test_indian_plate_validation,
    ]

    passed = failed = 0
    for t in tests:
        try:
            print(f"\nRunning {t.__name__} ...")
            t()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {e}")
            failed += 1

    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed")
    print("="*40)
    sys.exit(1 if failed else 0)
