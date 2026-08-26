# UrbanEye AI — SIH26127

**City-Wide AI Engine for Multi-Camera ANPR Trajectory Tracking and Urban Traffic Analytics**

Smart India Hackathon 2026 · Problem Statement SIH26127

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/Vanusshka/Yuva_SIH26127&root=urban-eye-ai)

> **Live Frontend:** [https://yuva-sih26127.vercel.app](https://yuva-sih26127.vercel.app) *(deploys from `urban-eye-ai/` folder)*
>
> **Demo credentials:** `admin / admin123`
>
> **Note:** The AI backend (FastAPI) requires a separate server. The frontend runs in demo mode on Vercel.

---

## Project Structure

```
Yuva_SIH26127/
├── urban-eye-ai/          ← Next.js 16 frontend (deployed to Vercel)
│   ├── app/               ← Next.js App Router (single page.tsx entry)
│   ├── src/
│   │   ├── route-pages/   ← All 9 dashboard pages
│   │   ├── components/    ← CameraCard, VideoUpload, CityMapComponent, etc.
│   │   └── page-views/    ← Landing + Login pages
│   ├── lib/api.ts         ← Centralised API client (all fetch calls)
│   └── package.json
│
├── backend/               ← FastAPI Python backend (run locally or on a server)
│   ├── app/
│   │   ├── main.py        ← 42 API routes
│   │   ├── models/        ← YOLOv8 + EasyOCR + ORM models
│   │   ├── services/      ← ANPR, analytics, alerts, manual review
│   │   └── trajectory/    ← Haversine + fuzzy matching engine
│   ├── data/metadata/     ← cameras.json, blacklist.json (DEMO)
│   └── requirements.txt
│
└── SIH_ANPR/              ← Phase 1 offline CLI script (not a server)
```

---

## Quick Start (Local Development)

### Prerequisites
- Node.js 20+ and pnpm
- Python 3.13 and pip

### Terminal 1 — Backend

```bash
cd backend

# First-time setup
python -m venv venv313
venv313\Scripts\activate          # Windows
# source venv313/bin/activate     # Linux/macOS

pip install -r requirements.txt   # includes torch, ultralytics, easyocr

# Seed demo data
python -m app.seed_data
python -m app.seed_trajectory

# Start
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Backend available at: **http://localhost:8000**
Swagger docs: **http://localhost:8000/docs**

### Terminal 2 — Frontend

```bash
cd urban-eye-ai
pnpm install
pnpm dev
```

Frontend available at: **http://localhost:3000**

### Environment variables (local)

Create `urban-eye-ai/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_DEMO_MODE=false
```

---

## Vercel Deployment (Frontend)

The frontend is a **Next.js 16** app and deploys to Vercel with zero configuration.

### Deploy via Vercel Dashboard

1. Go to [vercel.com/new](https://vercel.com/new)
2. Import the GitHub repository: `Vanusshka/Yuva_SIH26127`
3. Set **Root Directory** to `urban-eye-ai`
4. Set **Framework Preset** to `Next.js`
5. Add environment variable:
   ```
   NEXT_PUBLIC_API_URL = https://your-backend-url.com
   NEXT_PUBLIC_DEMO_MODE = true
   ```
6. Click **Deploy**

### Deploy via Vercel CLI

```bash
cd urban-eye-ai
npx vercel --prod
```

### Important: Backend on Vercel

The FastAPI Python backend **cannot** run on Vercel (Vercel supports only Edge/Node.js serverless, not Python with torch/ultralytics).

Options for the backend:
| Option | Description |
|--------|-------------|
| **Railway** | `railway up` from `backend/` — supports Python + large packages |
| **Render** | Free tier, supports Python Docker deploys |
| **Google Cloud Run** | Docker container — best for production |
| **Local** | For development only (`uvicorn app.main:app --reload`) |

When backend is not connected, the frontend automatically shows **DEMO DATA** banners — it never crashes.

---

## Features

### Dashboard Pages

| Page | Data Source | Status |
|------|-------------|--------|
| Overview | `GET /analytics` | ✅ Live |
| Vehicle Search | `GET /vehicles/{plate}` + trajectory | ✅ Live |
| Upload Video | `POST /process/video` | ✅ Live |
| Camera Network | `GET /api/cameras` + per-camera video | ✅ Live |
| Traffic Analytics | `GET /analytics` | ✅ Live |
| City Traffic Map | Leaflet + `/api/cameras` + density + congestion | ✅ Live |
| Alerts | `GET /alerts` (6 alert types) | ✅ Live |
| Manual Review Queue | `GET /manual-review` | ✅ Live |
| Blacklist Monitoring | `GET /alerts` filtered | ✅ Live |
| System Health | `GET /health` | ✅ Live |

### AI Pipeline (Phase 2–9)

```
Video Upload
  ↓
Vehicle Detection (YOLOv8n)
  ├── Car / Commercial  (conf >= 0.40)
  └── Two-Wheeler       (conf >= 0.30, plate crop upscaled)
  ↓
Vehicle Tracking (IoU-based, per-video)
  ↓
Plate Detection (YOLO plate model + contour fallback)
  ↓
Multi-Frame OCR (EasyOCR, 3–6 preprocessing variants)
  ↓
Majority Vote Consensus
  ├── agreement_rate = matching_reads / valid_reads
  └── confidence_tier: HIGH | MEDIUM | LOW
  ↓
  ├── HIGH/MEDIUM → Blacklist check allowed
  ├── LOW         → Manual Review Queue (NEVER auto-alerts)
  └── NO PLATE    → COMPLIANCE_ANOMALY alert
  ↓
Trajectory Engine (Haversine + fuzzy matching + travel-time validation)
  ↓
Traffic Analytics + Alert Engine
  ↓
Frontend Dashboard
```

### Alert Types

| Alert | Severity | Trigger |
|-------|----------|---------|
| `BLACKLISTED_VEHICLE` | CRITICAL | HIGH/MEDIUM confidence plate matches demo blacklist |
| `CONGESTION` | WARNING/CRITICAL | Camera with HIGH/SEVERE traffic density |
| `IMPOSSIBLE_TRAJECTORY` | CRITICAL | Speed > 200 km/h or negative time gap |
| `SUSPICIOUS_TRAJECTORY` | WARNING | Speed 120–200 km/h or anomalous hop |
| `LOW_CONFIDENCE_ANPR` | INFO | OCR confidence < 0.50 |
| `COMPLIANCE_ANOMALY` | WARNING | Vehicle detected, no plate readable |

### OCR Confidence Tiers

| Tier | Condition | Blacklist Alert |
|------|-----------|-----------------|
| HIGH | agreement_rate ≥ 75% AND ≥ 2 valid reads | ✅ Allowed |
| MEDIUM | agreement_rate ≥ 40% | ✅ Allowed |
| LOW | agreement_rate < 40% or only 1 read | ❌ Manual Review only |

### Trajectory Engine

- **Exact matching**: `GET /trajectory/{plate}` — original exact string match
- **Fuzzy matching**: `GET /api/trajectory/{plate}/fuzzy` — Levenshtein distance ≤ 1
- **Travel-time validation**: Hops rejected if physically impossible (configurable threshold)

---

## API Reference

Full Swagger UI at `http://localhost:8000/docs`

### Key Endpoints

```bash
# Health
GET /health

# Video processing
POST /process/video          # file + camera_id + frame_skip

# Vehicles
GET /vehicles                # paginated list
GET /vehicles/{plate}        # single vehicle detail
GET /api/trajectory/{plate}  # frontend-ready trajectory

# Analytics
GET /analytics               # unified dashboard payload

# Alerts
GET /alerts                  # 6 alert types

# Manual Review (Change 6)
GET  /manual-review                     # list all
GET  /manual-review/pending             # pending only
POST /manual-review/{id}/decision       # CONFIRMED | REJECTED | EDITED

# Cameras
GET /api/cameras             # 15 Hyderabad cameras with GPS + stats

# Fuzzy trajectory (Change 7+8)
GET /api/trajectory/{plate}/fuzzy
```

---

## Demo Data

All camera metadata and blacklist data is **DEMO / SIMULATED** for SIH26127 development.

| Data | Label | Source |
|------|-------|--------|
| Camera locations | "DEMO / SIMULATED" in JSON | `data/metadata/cameras.json` |
| Blacklist entries | `demo_data: true` on all alerts | `data/metadata/blacklist.json` |
| Trajectory data | "DEMO / SIMULATED TRAJECTORY" | `app/seed_trajectory.py` |

Demo accounts:

| Username | Password | Role |
|----------|----------|------|
| `admin` | `admin123` | System Administrator |
| `operator` | `operator123` | Traffic Operator |
| `viewer` | `viewer123` | Read-Only Access |

---

## Technology Stack

### Frontend
- **Next.js 16.3** + React 19 + TypeScript
- **Tailwind CSS v4** + shadcn/ui
- **React Router DOM v7** (SPA inside Next.js)
- **Leaflet 1.9** + react-leaflet 5 (interactive map)
- **Vercel Analytics** (production)

### Backend
- **FastAPI 0.111** + Python 3.13
- **SQLAlchemy 2.0** + SQLite (swap to PostgreSQL in production)
- **YOLOv8n** (Ultralytics 8.4) — vehicle detection
- **EasyOCR 1.7** — license plate OCR
- **Custom plate YOLO model** (HuggingFace, auto-downloaded)

---

## Phase History

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Vehicle detection CLI (`SIH_ANPR/`) | ✅ |
| 2 | Plate detection + OCR + FastAPI | ✅ |
| 3 | Database + camera event management | ✅ |
| 4 | Trajectory reconstruction (Haversine) | ✅ |
| 5 | Traffic analytics API | ✅ |
| 6 | Analytics consolidation | ✅ |
| 7 | Video ingestion + plate normalisation | ✅ |
| 8 | Backend integration + API readiness | ✅ |
| 9 | Multi-variant OCR + quality analysis | ✅ |
| Frontend | UrbanEye AI dashboard (Next.js) | ✅ |
| Map | Leaflet interactive map | ✅ |
| Camera | Per-camera video upload + pipeline | ✅ |
| Reliability | Confidence tiers, fuzzy trajectory, compliance alerts | ✅ |
| **Vercel** | **Frontend deployed** | ✅ |
| Next | RTSP live feeds + PostgreSQL + GPU inference | 🔜 |
