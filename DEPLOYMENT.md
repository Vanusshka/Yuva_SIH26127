# UrbanEye AI — Deployment Guide

## Architecture

```
Frontend (Next.js) → Vercel
Backend  (FastAPI)  → Render
Database            → Render Postgres (free tier)
AI Models           → Local .pt files in Render build (or HuggingFace Inference API)
```

---

## 1. Backend → Render

### Steps
1. Push repo to GitHub.
2. On Render → **New Web Service** → connect repo → select `backend/` as root directory.
3. Set **Build Command**: `pip install -r requirements-render.txt`
4. Set **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`
5. Set **Health Check Path**: `/health`

### Required Environment Variables (set in Render dashboard)
| Variable | Value |
|---|---|
| `DATABASE_URL` | Render Postgres internal URL (auto-filled if linked) |
| `FRONTEND_URL` | Your Vercel deployment URL, e.g. `https://urbaneye.vercel.app` |
| `MODEL_PROVIDER` | `local` (default) or `huggingface` |
| `OCR_ENGINE` | `easyocr` (recommended for Render free tier — no PaddleOCR dep) |
| `HF_TOKEN` | HuggingFace API token (only if `MODEL_PROVIDER=huggingface`) |
| `HF_VEHICLE_MODEL_URL` | HF Inference endpoint URL for vehicle detector |
| `HF_PLATE_MODEL_URL` | HF Inference endpoint URL for plate detector |

### Model Files
- **Local mode** (`MODEL_PROVIDER=local`): upload `best.pt`, `plate_detector_best_fast.pt`, and the `paddleocr_infer/` + `plates_inference_model_final/` directories to `backend/models/` — these are gitignored so Render won't have them unless you either:
  - Use Render Disk (persistent storage), or
  - Switch to `MODEL_PROVIDER=huggingface` and host models on HuggingFace
- **HuggingFace mode** (`MODEL_PROVIDER=huggingface`): push model files to HuggingFace Hub as private model repos, then set `HF_VEHICLE_MODEL_URL`, `HF_PLATE_MODEL_URL`, and `HF_TOKEN`.

---

## 2. Frontend → Vercel

### Steps
1. On Vercel → **New Project** → connect repo → set **Root Directory** to `frontend/`.
2. Framework should auto-detect as **Next.js**.
3. Add the environment variable below in **Project Settings → Environment Variables**.

### Required Environment Variables
| Variable | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | Your Render backend URL, e.g. `https://urbaneye-ai-backend.onrender.com` |

> `NEXT_PUBLIC_DEMO_MODE=true` is already set in `frontend/.env.production` — remove or set to `false` once live backend is connected.

---

## 3. Hugging Face (optional — only for `MODEL_PROVIDER=huggingface`)

### Steps
1. Create a HuggingFace account and generate a token with **write** scope at https://huggingface.co/settings/tokens.
2. Create two **private model repositories**:
   - `your-org/urbaneye-vehicle-detector` — upload `best.pt`
   - `your-org/urbaneye-plate-detector` — upload `plate_detector_best_fast.pt`
3. Enable **Inference API** on each model page.
4. Set `HF_VEHICLE_MODEL_URL` and `HF_PLATE_MODEL_URL` in Render to the respective inference endpoints.

---

## 4. Local Development

```bash
# Backend
cd backend
cp .env.example .env          # fill in values
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
cp .env.local.example .env.local   # or create manually
# NEXT_PUBLIC_API_URL=http://localhost:8000
pnpm dev
```

---

## 5. Remaining Blockers

| # | Issue | Resolution |
|---|---|---|
| 1 | `.pt` model files are gitignored — Render won't have them | Either use Render Disk to upload manually, or switch to `MODEL_PROVIDER=huggingface` |
| 2 | `paddleocr` is too heavy for Render free tier (512 MB RAM) | `requirements-render.txt` uses `easyocr` instead; set `OCR_ENGINE=easyocr` on Render |
| 3 | PaddleOCR was trained on your dataset — EasyOCR may have lower accuracy on Indian plates | Acceptable for demo; for production, host PaddleOCR model on a paid Render instance |
| 4 | SQLite is not viable on Render (ephemeral filesystem) | Link a Render Postgres database and set `DATABASE_URL` |
