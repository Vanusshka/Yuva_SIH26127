# SIH26127 – City-Wide AI Engine for Multi-Camera ANPR Trajectory Tracking and Urban Traffic Analytics

## Phase 1 – Vehicle Detection

Detect vehicles (cars, buses, trucks, motorcycles) in a traffic video using a
pretrained YOLOv8 model. No model training required.

---

## Project Structure

```
SIH_ANPR/
├── data/
│   └── videos/          ← Place your input MP4 video(s) here
├── models/              ← YOLO weights auto-downloaded here (optional)
├── output/              ← Annotated output videos are saved here
├── src/
│   └── detect_vehicles.py
├── requirements.txt
└── README.md
```

---

## Setup

### 1. Create and activate a virtual environment (recommended)

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

> **GPU support (optional):** If you have an NVIDIA GPU, install the CUDA-enabled
> build of PyTorch by following the instructions at https://pytorch.org/get-started/locally/
> before running `pip install -r requirements.txt`.

---

## Usage

Place your traffic video in `data/videos/`, then run:

```bash
python src/detect_vehicles.py --input data/videos/your_video.mp4
```

The annotated video is saved automatically to `output/your_video_detected.mp4`.

### All options

| Flag | Default | Description |
|------|---------|-------------|
| `--input` | *(required)* | Path to the input MP4 video |
| `--output` | `output/<stem>_detected.mp4` | Custom path for the output video |
| `--model` | `yolov8n.pt` | YOLO weights (`yolov8n/s/m/l/x.pt`) |
| `--conf` | `0.4` | Confidence threshold (0–1) |
| `--no-display` | off | Disable live preview (headless mode) |

### Examples

```bash
# Use a larger model for higher accuracy
python src/detect_vehicles.py --input data/videos/traffic.mp4 --model yolov8m.pt

# Run without a display window (server / CI)
python src/detect_vehicles.py --input data/videos/traffic.mp4 --no-display

# Custom confidence threshold and output path
python src/detect_vehicles.py --input data/videos/traffic.mp4 --conf 0.5 --output output/result.mp4
```

---

## Model Variants

Ultralytics will automatically download the selected weights on first run.

| Model | Size | Speed | Accuracy |
|-------|------|-------|----------|
| `yolov8n.pt` | ~6 MB | Fastest | Good |
| `yolov8s.pt` | ~22 MB | Fast | Better |
| `yolov8m.pt` | ~50 MB | Medium | High |
| `yolov8l.pt` | ~84 MB | Slower | Higher |
| `yolov8x.pt` | ~131 MB | Slowest | Best |

---

## Detected Classes

| Class | Colour |
|-------|--------|
| Car | Green |
| Motorcycle | Magenta |
| Bus | Orange |
| Truck | Red |

---

## Phase Roadmap

- [x] **Phase 1** – Vehicle detection with YOLOv8
- [ ] Phase 2 – License plate detection & OCR (ANPR)
- [ ] Phase 3 – Multi-camera vehicle tracking & trajectory linking
- [ ] Phase 4 – Urban traffic analytics dashboard
