#!/usr/bin/env bash
# UrbanEye AI — Render build script
# Runs during Render's build phase (before the app starts).
# Downloads model files that are gitignored (too large for git).
#
# Set these environment variables in the Render dashboard:
#   MODEL_VEHICLE_URL   — direct download URL for best.pt
#   MODEL_PLATE_URL     — direct download URL for plate_detector_best_fast.pt
#   MODEL_PADDLE_URL    — direct download URL for plates_inference_model_final.zip
#   MODEL_PADDLEINFER_URL — direct download URL for paddleocr_infer.zip
#
# If the URLs are not set, the build skips downloading and the app will run
# in contour-fallback mode (no .pt files = no YOLO, EasyOCR only).

set -e

echo "=== UrbanEye AI — Render Build Script ==="

# Install Python dependencies first
pip install -r requirements-render.txt

# Create models directory
mkdir -p models

# ── Download model files if URLs are provided ──────────────────────────────
if [ -n "$MODEL_VEHICLE_URL" ]; then
  echo "[Build] Downloading vehicle detector (best.pt)..."
  curl -L -o models/best.pt "$MODEL_VEHICLE_URL"
  echo "[Build] best.pt downloaded ($(du -sh models/best.pt | cut -f1))"
else
  echo "[Build] MODEL_VEHICLE_URL not set — skipping best.pt download"
fi

if [ -n "$MODEL_PLATE_URL" ]; then
  echo "[Build] Downloading plate detector..."
  curl -L -o models/plate_detector_best_fast.pt "$MODEL_PLATE_URL"
  echo "[Build] plate_detector_best_fast.pt downloaded"
else
  echo "[Build] MODEL_PLATE_URL not set — skipping plate detector download"
fi

if [ -n "$MODEL_PADDLE_URL" ]; then
  echo "[Build] Downloading PaddleOCR inference model..."
  curl -L -o models/plates_inference_model_final.zip "$MODEL_PADDLE_URL"
  cd models && unzip -q -o plates_inference_model_final.zip && cd ..
  echo "[Build] plates_inference_model_final/ extracted"
else
  echo "[Build] MODEL_PADDLE_URL not set — skipping PaddleOCR model download"
fi

if [ -n "$MODEL_PADDLEINFER_URL" ]; then
  echo "[Build] Downloading paddleocr_infer source..."
  curl -L -o models/paddleocr_infer.zip "$MODEL_PADDLEINFER_URL"
  cd models && unzip -q -o paddleocr_infer.zip && cd ..
  echo "[Build] paddleocr_infer/ extracted"
else
  echo "[Build] MODEL_PADDLEINFER_URL not set — skipping paddleocr_infer download"
fi

echo "=== Build complete ==="
ls -lh models/
