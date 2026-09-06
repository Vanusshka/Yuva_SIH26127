/**
 * UrbanEye AI – API Client
 * ========================
 * Central API layer that connects the frontend to the SIH26127 FastAPI backend.
 *
 * Backend: backend/  (FastAPI, Phase 8, running at NEXT_PUBLIC_API_URL)
 * Docs:    http://localhost:8000/docs
 *
 * All functions return typed responses. On network failure they throw an
 * ApiError so callers can show user-facing error messages.
 */

// ── Config ────────────────────────────────────────────────────────────────────

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') || 'http://localhost:8000'

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === 'true'

// ── Error type ────────────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
    public path?: string,
  ) {
    super(detail)
    this.name = 'ApiError'
  }
}

// ── Core fetch helper ─────────────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  options?: RequestInit,
  timeoutMs = 10_000,
): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)

  try {
    const res = await fetch(`${BASE_URL}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    })

    if (!res.ok) {
      let detail = `HTTP ${res.status}`
      try {
        const body = await res.json()
        detail = body.error ?? body.detail ?? detail
      } catch {
        // ignore JSON parse errors
      }
      throw new ApiError(res.status, detail, path)
    }

    return res.json() as Promise<T>
  } catch (err) {
    if (err instanceof ApiError) throw err
    if ((err as Error).name === 'AbortError') {
      throw new ApiError(408, 'Request timed out — is the backend running?', path)
    }
    throw new ApiError(0, `Network error: ${(err as Error).message}`, path)
  } finally {
    clearTimeout(timer)
  }
}

// ── Response types ────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: string
  version: string
  api_phase: string
  database: string
  total_cameras: number
  total_detections: number
}

export interface VehicleRecord {
  plate_number: string
  vehicle_type: string
  confidence: number
  first_seen: string | null
  last_seen: string | null
  camera_count: number
  total_sightings: number
  status: 'active' | 'suspicious' | 'impossible' | 'unknown'
  last_camera_id: string | null
  last_location: string | null
  is_blacklisted: boolean
  blacklist_reason: string | null
}

export interface VehicleListResponse {
  total: number
  vehicles: VehicleRecord[]
  generated_at: string
}

export interface TrajectoryStop {
  camera_id: string
  location: string
  road_name: string | null
  direction: string | null
  latitude: number
  longitude: number
  timestamp: string
  confidence: number | null
}

export interface TrajectoryHop {
  from_camera: string
  to_camera: string
  distance_km: number
  duration_min: number
  speed_kmh: number
  anomaly: 'NORMAL' | 'FAST' | 'SUSPICIOUS' | 'IMPOSSIBLE'
}

export interface TrajectoryResponse {
  plate_number: string
  total_observations: number
  total_distance_km: number
  travel_duration_min: number
  average_speed_kmh: number
  anomaly_score: number
  overall_status: 'NORMAL' | 'FAST' | 'SUSPICIOUS' | 'IMPOSSIBLE'
  first_seen: string | null
  last_seen: string | null
  cameras_visited: string[]
  stops: TrajectoryStop[]
  hops: TrajectoryHop[]
  data_mode: string
}

export interface VehicleCategoryItem {
  category: string
  count: number
  percentage: number
}

export interface CongestionZone {
  camera_id: string
  location: string
  latitude: number
  longitude: number
  vehicle_count: number
  avg_speed_kmh: number
  congestion_level: string
}

export interface TrafficTrendPoint {
  hour: number
  vehicle_count: number
}

export interface AnalyticsResponse {
  total_vehicles: number
  total_unique_plates: number
  total_cameras: number
  active_alerts: number
  suspicious_vehicles: number
  vehicle_distribution: VehicleCategoryItem[]
  traffic_density_label: string
  average_speed_kmh: number
  congestion_score: number
  congestion_zones: CongestionZone[]
  traffic_trends: TrafficTrendPoint[]
  most_active_camera: string | null
  most_active_location: string | null
  generated_at: string
  window_hours: number
}

export interface AlertItem {
  alert_id: string
  alert_type: string
  severity: 'INFO' | 'WARNING' | 'CRITICAL'
  plate_number: string | null
  location: string | null
  camera_id: string | null
  timestamp: string
  message: string
  status: 'open' | 'acknowledged' | 'resolved'
  demo_data: boolean
}

export interface AlertsResponse {
  total_alerts: number
  critical_count: number
  warning_count: number
  info_count: number
  alerts: AlertItem[]
  demo_disclaimer: string
  generated_at: string
}

export interface CameraItem {
  camera_id: string
  location_name: string
  road_name: string | null
  direction: string | null
  latitude: number
  longitude: number
  detections_last_hour: number
}

export interface ProcessResponse {
  status: string
  pipeline_version: string
  source_file: string
  camera_id: string
  timestamp: string
  latitude: number
  longitude: number
  total_vehicles: number
  total_plates: number
  low_confidence_count: number
  plates_detected: string[]
  annotated_image_url: string | null
  warnings: string[]
}

// ── API functions ─────────────────────────────────────────────────────────────

/**
 * GET /health
 * Extended health check with DB connection status and stats.
 */
export async function fetchHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('/health')
}

/**
 * GET /analytics?window_hours=24
 * Unified dashboard payload — KPIs, vehicle distribution, trends, congestion.
 * Connects to: Overview page KPI cards, TrafficAnalytics charts
 */
export async function fetchAnalytics(windowHours = 24): Promise<AnalyticsResponse> {
  return apiFetch<AnalyticsResponse>(`/analytics?window_hours=${windowHours}`)
}

/**
 * GET /vehicles?limit=&offset=&status_filter=
 * Paginated list of all tracked vehicles.
 * Connects to: VehicleSearch page table
 */
export async function fetchVehicles(
  limit = 100,
  offset = 0,
  statusFilter?: string,
): Promise<VehicleListResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
    ...(statusFilter ? { status_filter: statusFilter } : {}),
  })
  return apiFetch<VehicleListResponse>(`/vehicles?${params}`)
}

/**
 * GET /vehicles/{plate}
 * Single vehicle detail card.
 * Connects to: VehicleSearch → Track Vehicle
 */
export async function fetchVehicle(plate: string): Promise<VehicleRecord> {
  return apiFetch<VehicleRecord>(`/vehicles/${encodeURIComponent(plate.toUpperCase())}`)
}

/**
 * GET /api/trajectory/{plate}
 * Frontend-ready trajectory with anomaly score and ordered stops.
 * Connects to: VehicleSearch trajectory timeline
 */
export async function fetchTrajectory(plate: string): Promise<TrajectoryResponse> {
  return apiFetch<TrajectoryResponse>(
    `/api/trajectory/${encodeURIComponent(plate.toUpperCase())}`,
  )
}

/**
 * GET /alerts?limit=
 * Combined alert feed: blacklist + congestion + anomaly + OCR confidence.
 * Connects to: Alerts page, Overview active alerts
 */
export async function fetchAlerts(limit = 50): Promise<AlertsResponse> {
  return apiFetch<AlertsResponse>(`/alerts?limit=${limit}`)
}

/**
 * GET /api/cameras
 * All trajectory cameras with GPS + detections_last_hour.
 * Connects to: CameraNetwork page, CityMap
 */
export async function fetchCameras(): Promise<CameraItem[]> {
  return apiFetch<CameraItem[]>('/api/cameras')
}

// ── City Map analytics ────────────────────────────────────────────────────────

export interface TrafficDensityItem {
  camera_id: string
  location_name: string
  latitude: number
  longitude: number
  vehicle_count: number
  traffic_density: 'LOW' | 'MEDIUM' | 'HIGH' | 'SEVERE'
}
export interface TrafficDensityResponse {
  window_hours: number
  items: TrafficDensityItem[]
}
export interface CongestionItem {
  camera_id: string
  location_name: string
  latitude: number
  longitude: number
  vehicle_count: number
  avg_speed_kmh: number
  congestion_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'SEVERE'
  road_name?: string | null
}
export interface CongestionResponse {
  items: CongestionItem[]
}

/** GET /analytics/traffic-density?window_hours=1 */
export async function fetchTrafficDensity(windowHours = 1): Promise<TrafficDensityResponse> {
  return apiFetch<TrafficDensityResponse>(`/analytics/traffic-density?window_hours=${windowHours}`)
}

/** GET /analytics/congestion?window_hours=1 */
export async function fetchCongestion(windowHours = 1): Promise<CongestionResponse> {
  return apiFetch<CongestionResponse>(`/analytics/congestion?window_hours=${windowHours}`)
}

// ── Camera processing result ───────────────────────────────────────────────────
// Stored per camera in localStorage after a video is processed.
// All values derive from the real VideoIngestResponse — nothing is fabricated.

export interface CameraProcessingResult {
  camera_id        : string
  source_file      : string
  processed_at     : string          // ISO-8601 timestamp
  total_frames     : number
  frames_processed : number
  frame_skip       : number
  total_detections : number
  verified_plates  : string[]        // VERIFIED only — evidence-supported
  partial_plates   : string[]        // honest partials
  verified_count   : number
  partial_count    : number
  low_confidence_count : number
  unreadable_count : number
  vehicle_type_counts  : Record<string, number>  // e.g. { car: 5, bus: 2 }
  processing_note  : string
  warnings         : string[]
  // Density calculation (transparent formula — see formula_note)
  // density = total_detections / video_duration_minutes
  // LOW < 5/min, MEDIUM 5–15/min, HIGH 15–30/min, SEVERE > 30/min
  density_level    : 'LOW' | 'MEDIUM' | 'HIGH' | 'SEVERE' | 'INSUFFICIENT_DATA'
  vehicles_per_minute : number | null
  formula_note     : string
}

export interface ManualReviewItem {
  id                 : number
  camera_id          : string
  timestamp          : string
  vehicle_type       : string | null
  vehicle_category   : string | null
  ocr_plate_text     : string | null
  ocr_confidence     : number | null
  confidence_tier    : string
  agreement_rate     : number | null
  valid_ocr_reads    : number | null
  matching_ocr_reads : number | null
  source_file        : string | null
  frame_number       : number | null
  track_id           : string | null
  reason             : string
  review_status      : string
  reviewed_plate     : string | null
  reviewer_notes     : string | null
  reviewed_at        : string | null
  created_at         : string
}

/** GET /manual-review — pending review items */
export async function fetchManualReviews(
  status?: string,
  limit = 50,
  offset = 0,
): Promise<{ total: number; items: ManualReviewItem[] }> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (status) params.set('status', status)
  return apiFetch(`/manual-review?${params}`)
}

/** POST /manual-review/{id}/decision */
export async function submitReviewDecision(
  reviewId     : number,
  decision     : 'CONFIRMED' | 'REJECTED' | 'EDITED',
  reviewedPlate?: string,
  notes?       : string,
): Promise<ManualReviewItem> {
  return apiFetch(`/manual-review/${reviewId}/decision`, {
    method  : 'POST',
    body    : JSON.stringify({ decision, reviewed_plate: reviewedPlate, notes }),
  })
}
export async function processVideoForCamera(
  file       : File,
  cameraId   : string,
  frameSkip  : number = 5,
  onProgress?: (pct: number) => void,
): Promise<VideoIngestResponse> {
  // Reuses the existing processVideo() function from api.ts
  return processVideo(file, cameraId, frameSkip, onProgress)
}

/** Derive a CameraProcessingResult from a VideoIngestResponse (no fabrication). */
export function buildCameraResult(
  resp     : VideoIngestResponse,
  cameraId : string,
): CameraProcessingResult {
  // Vehicle type counts from detections
  const vtCounts: Record<string, number> = {}
  for (const d of resp.detections) {
    const t = d.vehicle_type || 'unknown'
    vtCounts[t] = (vtCounts[t] ?? 0) + 1
  }

  // Traffic density — transparent formula
  // duration_minutes = total_frames / (fps*60); we estimate fps=25 if unknown
  const estimatedFps      = 25
  const durationMinutes   = resp.total_frames / (estimatedFps * 60)
  let vehiclesPerMinute: number | null = null
  let densityLevel: CameraProcessingResult['density_level'] = 'INSUFFICIENT_DATA'

  if (durationMinutes > 0.1) {
    vehiclesPerMinute = Math.round((resp.total_detections / durationMinutes) * 10) / 10
    if      (vehiclesPerMinute < 5)  densityLevel = 'LOW'
    else if (vehiclesPerMinute < 15) densityLevel = 'MEDIUM'
    else if (vehiclesPerMinute < 30) densityLevel = 'HIGH'
    else                              densityLevel = 'SEVERE'
  }

  return {
    camera_id          : cameraId,
    source_file        : resp.source_file,
    processed_at       : new Date().toISOString(),
    total_frames       : resp.total_frames,
    frames_processed   : resp.frames_processed,
    frame_skip         : resp.frame_skip,
    total_detections   : resp.total_detections,
    verified_plates    : resp.unique_plates,
    partial_plates     : resp.partial_plates,
    verified_count     : resp.verified_count,
    partial_count      : resp.partial_count,
    low_confidence_count: resp.low_confidence_plates,
    unreadable_count   : resp.unreadable_count,
    vehicle_type_counts: vtCounts,
    processing_note    : resp.processing_note,
    warnings           : resp.warnings,
    density_level      : densityLevel,
    vehicles_per_minute: vehiclesPerMinute,
    formula_note       : 'density = total_detections / video_duration_minutes. Thresholds: LOW<5, MEDIUM 5-15, HIGH 15-30, SEVERE>30 vehicles/minute.',
  }
}

/**
 * POST /process
 * Upload a traffic image → full ANPR pipeline → summary card.
 * Connects to: any future upload UI
 */
export async function processImage(
  file: File,
  cameraId = 'CAM_001',
  timestamp?: string,
): Promise<ProcessResponse> {
  const form = new FormData()
  form.append('file', file)
  form.append('camera_id', cameraId)
  if (timestamp) form.append('timestamp', timestamp)

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 60_000) // 60s for image upload

  try {
    const res = await fetch(`${BASE_URL}/process`, {
      method: 'POST',
      body: form,
      signal: controller.signal,
      // Do NOT set Content-Type — let the browser set multipart boundary
    })

    if (!res.ok) {
      let detail = `HTTP ${res.status}`
      try {
        const body = await res.json()
        detail = body.error ?? body.detail ?? detail
      } catch { /* ignore */ }
      throw new ApiError(res.status, detail, '/process')
    }

    return res.json() as Promise<ProcessResponse>
  } catch (err) {
    if (err instanceof ApiError) throw err
    throw new ApiError(0, `Upload failed: ${(err as Error).message}`, '/process')
  } finally {
    clearTimeout(timer)
  }
}

// ── Video response type ───────────────────────────────────────────────────────

export interface IngestDetection {
  vehicle_type: string
  vehicle_confidence: number
  vehicle_bbox: number[]
  track_id: string
  // VERIFIED plate (complete, evidence-supported)
  plate_number: string | null
  // Honest partial (never fabricated — may be null even if plate_number is null)
  partial_text: string | null
  plate_status: 'verified' | 'partial' | 'low_confidence' | 'unreadable'
  plate_raw_text: string | null
  plate_confidence: number | null
  ocr_confidence: number | null
  plate_bbox: number[] | null
  plate_normalised: boolean
  low_confidence: boolean
  quality_score: number
  preprocessing_method: string
  supporting_frames: number[]
  frame_number: number
  timestamp: string
  camera_id: string
  latitude: number
  longitude: number
  source_file: string
  event_id: number | null
  detection_id: number | null
}

export interface VideoIngestResponse {
  status: string
  source_file: string
  camera_id: string
  total_frames: number
  frames_processed: number
  frame_skip: number
  total_detections: number
  /** VERIFIED plates only — evidence-supported, never fabricated */
  unique_plates: string[]
  /** Honest partial OCR texts — NOT counted as verified unique plates */
  partial_plates: string[]
  verified_count: number
  partial_count: number
  low_confidence_plates: number
  unreadable_count: number
  detections: IngestDetection[]
  warnings: string[]
  processing_note: string
}

/**
 * POST /process/video
 * Upload a traffic video → sampled-frame ANPR pipeline → structured results.
 * Uses the EXISTING Phase-7 backend endpoint — no new endpoint needed.
 *
 * @param file        Video file (MP4 / AVI / MOV / MKV)
 * @param cameraId    Camera identifier (default CAM_001)
 * @param frameSkip   Process every N-th frame (default 10 — reduce for more detections)
 * @param onProgress  Optional callback receiving 0–100 upload progress
 */
export async function processVideo(
  file: File,
  cameraId = 'CAM_001',
  frameSkip = 10,
  onProgress?: (pct: number) => void,
): Promise<VideoIngestResponse> {
  const form = new FormData()
  form.append('file', file)
  form.append('camera_id', cameraId)
  form.append('frame_skip', String(frameSkip))
  form.append('demo_multi_camera', 'true')   // always on — spreads detections across cameras for demo

  return new Promise<VideoIngestResponse>((resolve, reject) => {
    const xhr = new XMLHttpRequest()

    // Upload progress (0 → 100%)
    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100))
      }
    })

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as VideoIngestResponse)
        } catch {
          reject(new ApiError(xhr.status, 'Invalid JSON response from server', '/process/video'))
        }
      } else {
        let detail = `HTTP ${xhr.status}`
        try {
          const body = JSON.parse(xhr.responseText)
          detail = body.error ?? body.detail ?? detail
        } catch { /* ignore */ }
        reject(new ApiError(xhr.status, detail, '/process/video'))
      }
    })

    xhr.addEventListener('error',   () => reject(new ApiError(0, 'Network error — is the backend running?', '/process/video')))
    xhr.addEventListener('timeout', () => reject(new ApiError(408, 'Request timed out (video processing can take several minutes)', '/process/video')))
    xhr.addEventListener('abort',   () => reject(new ApiError(0, 'Upload cancelled', '/process/video')))

    // Video processing can take several minutes on CPU — 20 minute timeout
    xhr.timeout = 20 * 60 * 1000

    xhr.open('POST', `${BASE_URL}/process/video`)
    xhr.send(form)
  })
}

// ── Demo mode fallback data ───────────────────────────────────────────────────
// When NEXT_PUBLIC_DEMO_MODE=true (or backend unreachable), callers can use
// these stubs so the UI doesn't go blank during development.

export const DEMO_HEALTH: HealthResponse = {
  status: 'demo',
  version: '0.8.0',
  api_phase: 'DEMO MODE — backend not connected',
  database: 'demo',
  total_cameras: 15,
  total_detections: 10,
}

export const DEMO_ANALYTICS: AnalyticsResponse = {
  total_vehicles: 12847,
  total_unique_plates: 248,
  total_cameras: 15,
  active_alerts: 7,
  suspicious_vehicles: 2,
  vehicle_distribution: [
    { category: 'car',        count: 7482, percentage: 58.2 },
    { category: 'motorcycle', count: 3541, percentage: 27.5 },
    { category: 'bus',        count: 1261, percentage: 9.8  },
    { category: 'truck',      count: 563,  percentage: 4.5  },
  ],
  traffic_density_label: 'MEDIUM',
  average_speed_kmh: 38,
  congestion_score: 0.49,
  congestion_zones: [],
  traffic_trends: Array.from({ length: 24 }, (_, h) => ({
    hour: h,
    vehicle_count: [0,0,0,1,2,8,32,65,88,72,54,60,58,55,61,70,82,94,78,60,40,22,10,3][h] ?? 0,
  })),
  most_active_camera: 'CAM_001',
  most_active_location: 'Ameerpet Junction',
  generated_at: new Date().toISOString(),
  window_hours: 24,
}
