# UrbanEye AI — Model Files

This directory contains the trained AI model weights used by the backend pipeline.

## Files required (not tracked in git — download/copy manually)

| File | Description | Size | Used by |
|------|-------------|------|---------|
| `vehicle.pt` (= `best.pt`) | YOLOv8 vehicle detector — trained on 6-class Indian traffic dataset (car, motorcycle, auto_rickshaw, bus, truck, bicycle) | ~22 MB | `backend/app/models/vehicle_detector.py` |
| `plate.pt` (= `plate_detector_best_fast.pt`) | YOLOv8 plate detector — mAP50 0.984 on test set | ~6 MB | `backend/app/models/plate_detector.py` |
| `plates_inference_model_final/` | PaddleOCR SVTR_LCNet fine-tuned OCR model — 75.4% exact-match on Indian plates | ~9 MB | `backend/app/models/ocr_engine.py` |
| `paddleocr_infer/` | PaddleOCR inference source (ppocr/ + tools/infer/) — required for the fine-tuned OCR | ~4 MB | `backend/app/models/ocr_engine.py` |

## Setup instructions

Copy the model files to `backend/models/`:

```
backend/models/
  best.pt                          ← vehicle detector
  plate_detector_best_fast.pt      ← plate detector  
  plates_inference_model_final/
    inference.pdiparams
    inference.json
    inference.yml
  paddleocr_infer/
    ppocr/
    tools/infer/
```

The config in `backend/app/config.py` references:
- `VEHICLE_MODEL_NAME = "best.pt"`
- `PLATE_MODEL_NAME   = "plate_detector_best_fast.pt"`
- `PADDLE_REC_MODEL_DIR = MODELS_DIR / "plates_inference_model_final"`
- `PADDLEOCR_REPO_DIR   = MODELS_DIR / "paddleocr_infer"`

## Why models are not in git

Model `.pt` files and PaddleOCR weights are 5–22 MB each and are excluded via `.gitignore`.
They must be placed manually before running the backend.
