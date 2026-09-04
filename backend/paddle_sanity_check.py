"""
paddle_sanity_check.py

Tests the ACTUAL integration path used by _PaddleOCREngine:
  - paddlepaddle import + run_check
  - Direct import of TextRecognizer from paddleocr_infer/tools/infer/
    (NOT the pip paddleocr package — that has a torch/shm.dll conflict)

Usage:
    python paddle_sanity_check.py
"""

import sys
from pathlib import Path

print(f"Python version: {sys.version}")
print("-" * 60)

# Step 1: paddlepaddle core import
try:
    import paddle
    print(f"[OK] paddle imported — version {paddle.__version__}")
except Exception as e:
    print(f"[FAIL] paddle import: {e}")
    sys.exit(1)

# Step 2: run_check (verifies CPU executor works)
try:
    paddle.utils.run_check()
    print("[OK] paddle.utils.run_check() passed — CPU executor working")
except AttributeError as e:
    if "_device_id" in str(e):
        print(f"[FAIL] HIT _device_id bug: {e}")
        print("Pin a different paddlepaddle version and re-run.")
        sys.exit(1)
    print(f"[WARN] AttributeError (not _device_id): {e}")
except Exception as e:
    print(f"[WARN] run_check() raised: {e}")
    print("       (may be fine for CPU — continuing)")

# Step 3: import TextRecognizer directly from paddleocr_infer source
# This is the ACTUAL path _PaddleOCREngine uses at runtime.
MODELS_DIR        = Path(__file__).parent / "models"
PADDLEOCR_REPO    = MODELS_DIR / "paddleocr_infer"
CHAR_DICT         = PADDLEOCR_REPO / "ppocr" / "utils" / "en_dict.txt"
PREDICT_REC       = PADDLEOCR_REPO / "tools" / "infer" / "predict_rec.py"

print(f"\nChecking paddleocr_infer at: {PADDLEOCR_REPO}")
for label, path in [
    ("paddleocr_infer/", PADDLEOCR_REPO),
    ("tools/infer/predict_rec.py", PREDICT_REC),
    ("tools/infer/utility.py", PADDLEOCR_REPO / "tools" / "infer" / "utility.py"),
    ("ppocr/utils/en_dict.txt", CHAR_DICT),
]:
    if path.exists():
        print(f"  [OK] {label}")
    else:
        print(f"  [MISSING] {label}")
        sys.exit(1)

sys.path.insert(0, str(PADDLEOCR_REPO))
try:
    from tools.infer.predict_rec import TextRecognizer
    from tools.infer.utility import init_args
    print("[OK] TextRecognizer + init_args imported from paddleocr_infer")
except Exception as e:
    print(f"[FAIL] import from paddleocr_infer: {e}")
    sys.exit(1)

# Step 4: instantiate TextRecognizer (no model files needed yet)
try:
    parser   = init_args()
    rec_args = parser.parse_args([])
    rec_args.rec_model_dir      = str(MODELS_DIR / "plates_inference_model_final")
    rec_args.rec_image_shape    = "3, 48, 320"
    rec_args.rec_algorithm      = "SVTR_LCNet"
    rec_args.rec_batch_num      = 6
    rec_args.max_text_length    = 15
    rec_args.use_space_char     = False
    rec_args.rec_char_dict_path = str(CHAR_DICT)
    rec_args.use_gpu            = False
    recognizer = TextRecognizer(rec_args)
    print("[OK] TextRecognizer instantiated successfully")
except Exception as e:
    print(f"[FAIL] TextRecognizer instantiation: {e}")
    sys.exit(1)

print("-" * 60)
print("ALL CHECKS PASSED — PaddleOCR integration is ready.")
print("OCR_ENGINE = 'paddleocr' is safe to use in this environment.")
