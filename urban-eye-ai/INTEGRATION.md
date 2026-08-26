# UrbanEye AI — Frontend/Backend Integration Guide

**Project:** SIH26127 – City-Wide AI Engine for Multi-Camera ANPR  
**Frontend:** `urban-eye-ai/` (Next.js 16 + React 19 + TypeScript)  
**Backend:**  `backend/` (FastAPI, Phase 8, Python)  
**AI Script:** `SIH_ANPR/` (Phase 1 offline CLI tool — not a server)

---

## Folder Locations

```
Yuva_SIH26127/
├── backend/          ← FastAPI API server (Phases 2–8, 38 endpoints)
│   ├── app/
│   │   ├── main.py          ← All routes registered here
│   │   ├── services/        ← Business logic (ANPR, analytics, alerts…)
│   │   ├── models/          ← ORM + ML wrappers (YOLOv8, EasyOCR)
│   │   ├── schemas/         ← Pydantic request/response models
│   │   └── trajectory/      ← Haversine + anomaly engine
│   ├── data/
│   │   └── metadata/        ← cameras.json, blacklist.json (DEMO)
│   └── requirements.txt
│
├── urban-eye-ai/     ← React frontend (this project)
│   ├── lib/
│   │   └── api.ts           ← Typed API client (all fetch calls live here)
│   ├── src/
│   │   ├── route-pages/
│   │   │   └── Pages.tsx    ← All 8 dashboard pages
│   │   └── components/
│   │       └── layout/
│   │           └── AppLayout.tsx  ← Sidebar + live API status indicator
│   ├── app/
│   │   ├── page.tsx         ← Next.js entry → React Router SPA
│   │   └── layout.tsx       ← HTML shell
│   ├── .env.local           ← NEXT_PUBLIC_API_URL (not committed)
│   └── next.config.mjs      ← SPA rewrite config
│
└── SIH_ANPR/         ← Phase 1 CLI-only vehicle detection script
    └── src/
        └── detect_vehicles.py   ← Offline video processor (not a server)
```

---

## Running Locally (Two Terminals)

### Terminal 1 — Backend

```bash
cd backend

# Activate virtual environment (Windows)
venv\Scripts\activate
# macOS / Linux:
# source venv/bin/activate

# First-time setup
pip install -r requirements.txt
python -m app.seed_data        # seed Phase-3 ANPR cameras
python -m app.seed_trajectory  # seed trajectory cameras + demo detections

# Start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend available at:
- **API:**       http://localhost:8000
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:**      http://localhost:8000/redoc

### Terminal 2 — Frontend

```bash
cd urban-eye-ai

# First-time setup
pnpm install
pnpm approve-builds   # approve msw post-install script (one-time)

# Start the dev server
pnpm dev
```

Frontend available at: **http://localhost:3000**

The frontend reads `NEXT_PUBLIC_API_URL` from `.env.local`.  
Default: `http://localhost:8000`

---

## API Base URL Configuration

The API base URL is set in `urban-eye-ai/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_DEMO_MODE=false
```

To point to a different backend (staging, production):

```env
NEXT_PUBLIC_API_URL=https://your-backend-domain.com
```

All fetch calls go through `lib/api.ts` — changing the env var is the only
thing needed to switch environments.

**Demo mode:** Set `NEXT_PUBLIC_DEMO_MODE=true` to show hardcoded placeholder
data when the backend is not running. Useful for frontend-only development.

---

## Available Backend APIs

All routes are defined in `backend/app/main.py`. Full Swagger docs at `/docs`.

### Phase 8 — Frontend-ready endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/health` | Liveness + DB stats |
| `POST` | `/process` | Upload image → ANPR summary card |
| `GET`  | `/vehicles` | Paginated vehicle list with status |
| `GET`  | `/vehicles/{plate}` | Single vehicle detail |
| `GET`  | `/api/trajectory/{plate}` | Trajectory with anomaly score + stops |
| `GET`  | `/analytics` | Unified dashboard (KPIs + trends + zones) |
| `GET`  | `/alerts` | Combined alert feed (blacklist + anomaly + congestion) |
| `GET`  | `/api/cameras` | Camera list with GPS + detections_last_hour |

### Phase 7 — Ingestion endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/process/image` | Upload image → full detection array |
| `POST` | `/process/video` | Upload video → sampled frame pipeline |

### Phase 4–5 — Trajectory + Analytics

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/trajectory/{plate}` | Full Phase-4 trajectory (internal schema) |
| `GET`  | `/analytics/overview` | KPI summary |
| `GET`  | `/analytics/traffic-density` | Per-camera density |
| `GET`  | `/analytics/congestion` | Avg speed + congestion level |
| `GET`  | `/analytics/peak-hours` | 24-hour traffic distribution |
| `GET`  | `/analytics/alerts` | Phase-5 alert feed |

### Phase 3 — Camera + Event CRUD

| Method | Path | Description |
|--------|------|-------------|
| `GET/POST` | `/cameras` | List or register ANPR cameras |
| `GET`      | `/events`  | Query detection events with filters |
| `GET`      | `/vehicles/{plate}/history` | Detection history |

---

## Frontend Integration Status

### ✅ Connected to real backend data

| Page | API endpoint(s) used | Notes |
|------|---------------------|-------|
| **Overview** | `GET /analytics` | KPI cards, traffic volume chart, vehicle type distribution, live alert widget |
| **System Health** | `GET /health` | DB connection status, version, camera/detection counts per service |
| **Vehicle Search** | `GET /vehicles/{plate}` + `GET /api/trajectory/{plate}` | Vehicle info card, journey summary, detection timeline with hop metrics |
| **Traffic Analytics** | `GET /analytics` | All 4 KPI cards, traffic trend chart, vehicle type chart, congestion zones table |
| **Alerts** | `GET /alerts` | Full alert table with severity, type, location, timestamp |
| **Blacklist Monitoring** | `GET /alerts` (filtered `BLACKLISTED_VEHICLE`) | Shows only blacklisted vehicle detections from demo blacklist |

### 🔶 Partially connected (some live, some placeholder)

| Page | What's live | What's placeholder | Reason |
|------|------------|-------------------|--------|
| **Camera Network** | KPI counts, location names, `detections_last_hour` | Camera feed thumbnails | Live RTSP/video feed not implemented yet (planned Phase 9) |

### 🔲 Still using placeholder / demo data

| Page | Status | What's needed to connect |
|------|--------|-------------------------|
| **City Map** | Decorative map art only | Mapping library (Leaflet or Mapbox) + GPS from `GET /api/cameras` |

---

## API Client — lib/api.ts

All backend communication is centralised in `urban-eye-ai/lib/api.ts`.

**Key exports:**

```typescript
// API functions
fetchHealth()                              // GET /health
fetchAnalytics(windowHours?)               // GET /analytics
fetchVehicles(limit?, offset?, status?)    // GET /vehicles
fetchVehicle(plate)                        // GET /vehicles/{plate}
fetchTrajectory(plate)                     // GET /api/trajectory/{plate}
fetchAlerts(limit?)                        // GET /alerts
fetchCameras()                             // GET /api/cameras
processImage(file, cameraId?, timestamp?)  // POST /process

// Error type — thrown on non-2xx responses or network errors
class ApiError extends Error {
  status: number   // HTTP status (0 = network error)
  detail: string   // human-readable message
  path?: string    // endpoint path
}

// Demo fallback data (used when backend is unreachable)
DEMO_HEALTH
DEMO_ANALYTICS
```

**Error handling pattern used in all pages:**

```typescript
try {
  const data = await fetchAnalytics()
  setData(data)
} catch (err) {
  const msg = err instanceof ApiError
    ? `Backend error: ${err.detail}`
    : 'Cannot reach backend. Is it running at localhost:8000?'
  setError(msg)
  setData(DEMO_ANALYTICS) // graceful fallback
}
```

---

## Adding a New API Connection

1. Add a typed response interface and fetch function to `lib/api.ts`
2. In the page component, call the function inside `useEffect` with loading/error state
3. Replace the hardcoded/mock value with live data
4. Add a `<PlaceholderBadge />` on sections that still use mock data

Example skeleton:

```typescript
// lib/api.ts
export interface MyNewResponse { ... }
export async function fetchMyData(): Promise<MyNewResponse> {
  return apiFetch<MyNewResponse>('/my-endpoint')
}

// Pages.tsx
const [data, setData] = useState<MyNewResponse | null>(null)
const [loading, setLoading] = useState(true)
const [error, setError] = useState<string | null>(null)

useEffect(() => {
  fetchMyData()
    .then(d => { setData(d); setLoading(false) })
    .catch(e => { setError(e.detail); setLoading(false) })
}, [])
```

---

## SIH_ANPR Folder

`SIH_ANPR/` contains the **Phase 1 standalone CLI script** only.

```
SIH_ANPR/src/detect_vehicles.py
```

It is an **offline video processor** — not a server, not callable via HTTP.

Usage:
```bash
cd SIH_ANPR
venv\Scripts\activate
pip install -r requirements.txt
python src/detect_vehicles.py --input data/videos/traffic.mp4
```

The full ANPR/OCR/trajectory/analytics backend is in `backend/` (Phases 2–8).
The `SIH_ANPR` Phase 1 script was the starting point of the project and is
preserved as-is. Do not modify it.

---

## CORS

The backend accepts cross-origin requests from:

| Origin | Use |
|--------|-----|
| `http://localhost:3000` | Next.js dev server (CRA/Vite default) |
| `http://localhost:5173` | Vite alternative |
| `http://localhost:5174` | Vite alternative |
| `http://localhost:8080` | webpack-dev-server |
| `https://urbaneye-ai.vercel.app` | Vercel production |
| `https://*.vercel.app` | All Vercel preview deploys |

To add a new origin, edit `_ALLOWED_ORIGINS` in `backend/app/main.py`.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| All pages show "Cannot reach backend" | Backend not running | Run `uvicorn app.main:app --reload` in `backend/` |
| "No detections found for plate X" in Vehicle Search | Demo data not seeded | Run `python -m app.seed_trajectory` in `backend/` |
| Dashboard shows placeholder data with yellow badge | `NEXT_PUBLIC_DEMO_MODE=true` or backend unreachable | Check `.env.local` and start backend |
| Sidebar shows orange "API Offline" dot | `/health` request failing | Start backend or check `NEXT_PUBLIC_API_URL` |
| `pnpm install` fails with `ERR_PNPM_IGNORED_BUILDS` | `msw` post-install blocked | Run `pnpm approve-builds` once |
| Build fails with TypeScript errors | Version mismatch | The project has `ignoreBuildErrors: true` in `next.config.mjs` — runtime errors are separate |
| Camera feed shows camera icon, not video | RTSP integration not built | Planned for Phase 9 |
