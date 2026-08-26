'use client'

/**
 * UrbanEye AI — Route Pages
 * =========================
 * All 8 dashboard pages live here.
 *
 * Integration status per page:
 *
 * ✅ Overview             — live: /health + /analytics
 * ✅ VehicleSearch        — live: /vehicles/{plate} + /api/trajectory/{plate}
 * ✅ Alerts               — live: /alerts
 * ✅ TrafficAnalytics     — live: /analytics
 * ✅ SystemHealth         — live: /health
 * 🔶 CameraNetwork       — live: /api/cameras (count KPIs); feed thumbnails = placeholder
 * ✅ CityMap             — live: real Leaflet map, /api/cameras + /analytics/traffic-density + /analytics/congestion + /api/trajectory/{plate}
 * 🔶 BlacklistMonitoring — live alert data filtered for BLACKLISTED_VEHICLE type
 */

import { useState, useEffect, useCallback } from 'react'
import dynamic from 'next/dynamic'
import {
  BarChart3, Camera, Car, CheckCircle2, Clock3, Map,
  Search, ShieldAlert, Siren, Wifi, Activity, AlertCircle,
  Loader2, RefreshCw,
} from 'lucide-react'
import {
  fetchHealth, fetchAnalytics, fetchVehicle, fetchTrajectory,
  fetchAlerts, fetchCameras, fetchVehicles,
  type HealthResponse, type AnalyticsResponse, type VehicleRecord,
  type TrajectoryResponse, type AlertsResponse, type CameraItem,
  type VehicleListResponse,
  DEMO_HEALTH, DEMO_ANALYTICS, ApiError,
} from '@/lib/api'

// ── City Map — dynamically imported to avoid SSR Leaflet crash ────────────────
const CityMapComponent = dynamic(
  () => import('@/src/components/CityMapComponent'),
  {
    ssr: false,
    loading: () => (
      <div style={{
        height: 'calc(100vh - 240px)', minHeight: 440,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: '#f0f6fb', borderRadius: 8, color: 'var(--muted-foreground)',
        gap: 10, fontSize: 12,
      }}>
        <div style={{ animation: 'spin 1s linear infinite', display: 'flex' }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
          </svg>
        </div>
        Loading interactive map…
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    ),
  }
)

// ── shared UI helpers ─────────────────────────────────────────────────────────

const Panel = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <article className="panel">
    <div className="panel-header">
      <div><h2>{title}</h2><p>Live operational data</p></div>
    </div>
    <div style={{ padding: '18px' }}>{children}</div>
  </article>
)

const Toolbar = ({ placeholder, value, onChange }: {
  placeholder: string
  value?: string
  onChange?: (v: string) => void
}) => (
  <div className="table-search" style={{ width: '100%', maxWidth: 420 }}>
    <Search />
    <input
      aria-label={placeholder}
      placeholder={placeholder}
      value={value ?? ''}
      onChange={e => onChange?.(e.target.value)}
    />
  </div>
)

/** Loading spinner row */
function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '28px 0', color: 'var(--muted-foreground)' }}>
      <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} />
      <span style={{ fontSize: 12 }}>{label}</span>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}

/** Error banner with optional retry */
function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  // If the backend is simply unreachable and demo mode is on, show a gentle
  // info notice instead of a scary red banner.
  const isNetworkError = message.includes('Failed to fetch') ||
    message.includes('Network error') || message.includes('timed out')
  const demoMode = process.env.NEXT_PUBLIC_DEMO_MODE === 'true'
  const gentle = isNetworkError && demoMode

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '10px 14px', borderRadius: 7,
      background: gentle ? '#f0f8ff' : '#fce9e9',
      color:      gentle ? '#4a7090' : '#b94040',
      border:     `1px solid ${gentle ? '#c0d8e8' : '#f5c0c0'}`,
      fontSize: 11, margin: '0 0 12px',
    }}>
      <AlertCircle size={13} style={{ flexShrink: 0 }} />
      <span style={{ flex: 1 }}>
        {gentle
          ? 'Backend is offline — showing demo data. Start the backend server to see live results.'
          : message}
      </span>
      {onRetry && (
        <button
          onClick={onRetry}
          style={{ border: 'none', background: 'transparent', cursor: 'pointer',
                   color: gentle ? '#4a7090' : '#b94040', padding: 2 }}
          title="Retry"
        >
          <RefreshCw size={13} />
        </button>
      )}
    </div>
  )
}

/** Placeholder badge shown on sections with no live backend API yet */
function PlaceholderBadge() {
  return (
    <span style={{
      display: 'inline-block', padding: '2px 7px', borderRadius: 10,
      background: '#fff3dd', color: '#c28118',
      fontSize: 9, fontWeight: 700, letterSpacing: '.6px', marginLeft: 8,
    }}>
      DEMO DATA
    </span>
  )
}

/** Vertical bar chart using only CSS/divs — no external charting library */
const Chart = ({ data, bars = false }: { data?: number[]; bars?: boolean }) => {
  const values = data ?? [45, 68, 52, 82, 60, 94, 72, 88, 64, 78, 51, 86]
  const max = Math.max(...values, 1)
  return (
    <div style={{
      height: 240, display: 'flex', alignItems: 'end', gap: 10,
      padding: '20px 10px',
      background: 'linear-gradient(to bottom, transparent 49%, var(--border) 50%, transparent 51%)',
    }}>
      {values.map((v, i) => (
        <div
          key={i}
          style={{
            flex: 1, height: `${(v / max) * 100}%`,
            background: bars ? 'var(--amber)' : 'var(--cyan)',
            borderRadius: '5px 5px 0 0', opacity: 0.85,
            transition: 'height .3s ease',
          }}
        />
      ))}
    </div>
  )
}

function Table({ rows }: { rows: string[][] }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr><th>ITEM</th><th>STATUS</th><th>LOCATION</th><th>TIME</th></tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {r.map((c, j) => (
                <td key={j}>{j === 1 ? <span className="status-pill">{c}</span> : c}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Format ISO timestamp to relative "N min ago" */
function relativeTime(iso: string | null): string {
  if (!iso) return '—'
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 60000)
  if (diff < 1) return 'just now'
  if (diff < 60) return `${diff} min ago`
  if (diff < 1440) return `${Math.floor(diff / 60)}h ago`
  return new Date(iso).toLocaleDateString()
}

// ═══════════════════════════════════════════════════════════════════════════════
// OVERVIEW PAGE  ✅ live: /health + /analytics
// ═══════════════════════════════════════════════════════════════════════════════

export function Overview() {
  const [analytics, setAnalytics] = useState<AnalyticsResponse | null>(null)
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchAnalytics(24)
      setAnalytics(data)
    } catch (err) {
      const msg = err instanceof ApiError
        ? `Backend error: ${err.detail}`
        : 'Cannot reach backend. Is it running at localhost:8000?'
      setError(msg)
      // Fall back to demo data so the UI doesn't go blank
      setAnalytics(DEMO_ANALYTICS)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const d = analytics ?? DEMO_ANALYTICS
  const isDemo = error !== null

  const kpis = [
    ['Vehicles Detected', d.total_vehicles.toLocaleString()],
    ['Active Alerts',     String(d.active_alerts)],
    ['Cameras Online',    `${d.total_cameras} active`],
    ['Avg Speed',         `${d.average_speed_kmh} km/h`],
  ]

  const trendData = d.traffic_trends.map(t => t.vehicle_count)

  const recentVehicles = d.vehicle_distribution.map((item, i) => [
    item.category.charAt(0).toUpperCase() + item.category.slice(1),
    `${item.percentage.toFixed(1)}%`,
    d.most_active_location ?? 'Various',
    'Today',
  ])

  return (
    <>
      {loading && <Loading label="Fetching live analytics…" />}
      {error && !loading && <ErrorBanner message={error} onRetry={load} />}
      {isDemo && !loading && (
        <div style={{ marginBottom: 14, fontSize: 11, color: '#5a8090' }}>
          <PlaceholderBadge /> Demo data — start the backend at&nbsp;
          <code style={{ background: '#eef3f7', padding: '1px 5px', borderRadius: 3, fontSize: 10 }}>
            localhost:8000
          </code>
          &nbsp;to see live stats
        </div>
      )}

      <div className="kpi-grid">
        {kpis.map(([label, value]) => (
          <article className="kpi-card" key={label}>
            <span className="kpi-label">{label}</span>
            <strong className="kpi-value">{value}</strong>
            <div className="kpi-trend">
              {label === 'Active Alerts'
                ? <>{d.critical_count ?? 0} critical</>
                : <>Live data</>
              }
            </div>
          </article>
        ))}
      </div>

      <section className="dashboard-grid">
        <Panel title="Traffic Volume (24h)">
          <Chart data={trendData} />
        </Panel>
        <Panel title="Traffic Summary">
          <div className="kpi-grid" style={{ gridTemplateColumns: '1fr 1fr' }}>
            {[
              ['Congestion',  d.traffic_density_label],
              ['Avg speed',   `${d.average_speed_kmh} km/h`],
              ['Cong. score', d.congestion_score.toFixed(2)],
              ['Unique plates', String(d.total_unique_plates)],
            ].map(([a, b]) => (
              <div key={a}><span className="kpi-label">{a}</span><strong>{b}</strong></div>
            ))}
          </div>
        </Panel>
      </section>

      <section className="lower-grid">
        <Panel title="Vehicle Type Distribution">
          {loading
            ? <Loading />
            : <Table rows={recentVehicles} />
          }
        </Panel>
        <Panel title={`Active Alerts${isDemo ? '' : ' (live)'}`}>
          <LiveAlertList limit={3} />
        </Panel>
      </section>
    </>
  )
}

/** Compact alert list widget reused in Overview */
function LiveAlertList({ limit }: { limit: number }) {
  const [data, setData] = useState<AlertsResponse | null>(null)

  useEffect(() => {
    fetchAlerts(limit)
      .then(setData)
      .catch(() => setData(null))
  }, [limit])

  if (!data) {
    return (
      <div className="alert-list">
        {['Blacklisted vehicle detected', 'Camera offline', 'Unusual traffic density'].map(x => (
          <div className="alert-row" key={x}>
            <Siren />
            <span className="alert-copy">
              <strong>{x}</strong>
              <small>Requires your attention</small>
            </span>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="alert-list">
      {data.alerts.slice(0, limit).map(a => (
        <div className="alert-row" key={a.alert_id}>
          <Siren />
          <span className="alert-copy">
            <strong>{a.alert_type.replace(/_/g, ' ')}</strong>
            <small>{a.plate_number ?? a.camera_id ?? a.location ?? '—'}</small>
          </span>
        </div>
      ))}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// VEHICLE SEARCH PAGE  ✅ live: /vehicles/{plate} + /api/trajectory/{plate}
// ═══════════════════════════════════════════════════════════════════════════════

export function VehicleSearch() {
  const [query,    setQuery]    = useState('')
  const [plate,    setPlate]    = useState('')
  const [vehicle,  setVehicle]  = useState<VehicleRecord | null>(null)
  const [traj,     setTraj]     = useState<TrajectoryResponse | null>(null)
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState<string | null>(null)

  const track = useCallback(async (searchPlate: string) => {
    const p = (searchPlate || 'TS09AB1234').trim().toUpperCase()
    setPlate(p)
    setLoading(true)
    setError(null)
    setVehicle(null)
    setTraj(null)

    try {
      const [veh, tr] = await Promise.allSettled([
        fetchVehicle(p),
        fetchTrajectory(p),
      ])

      if (veh.status === 'fulfilled') setVehicle(veh.value)
      else {
        const e = veh.reason as ApiError
        setError(e.status === 404
          ? `No detections found for plate "${p}". Try: TS09AB1234, MH12XY5678, DL01ZZ9999`
          : `Vehicle lookup failed: ${e.detail}`)
      }

      if (tr.status === 'fulfilled') setTraj(tr.value)
    } finally {
      setLoading(false)
    }
  }, [])

  const stops = traj?.stops ?? []

  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Vehicle Search &amp; Trajectory</h1>
          <p>Trace vehicle movement across the camera network.</p>
        </div>
      </div>

      <Panel title="Search registration number">
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <input
            className="table-search"
            style={{ padding: 11, flex: 1, minWidth: 240 }}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && track(query)}
            placeholder="Enter vehicle registration (e.g. TS09AB1234)"
          />
          <button
            className="primary-button"
            onClick={() => track(query)}
            disabled={loading}
          >
            {loading ? <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> : <Search size={14} />}
            Track Vehicle
          </button>
        </div>
        {error && <ErrorBanner message={error} />}
        <p style={{ fontSize: 10, color: 'var(--muted-foreground)', marginTop: 8 }}>
          Demo plates: <code>TS09AB1234</code>, <code>MH12XY5678</code>, <code>DL01ZZ9999</code>
        </p>
      </Panel>

      {loading && <Loading label={`Searching for ${plate}…`} />}

      {vehicle && (
        <section className="dashboard-grid" style={{ marginTop: 17 }}>
          <Panel title={`Vehicle information · ${vehicle.plate_number}`}>
            <div className="kpi-grid" style={{ gridTemplateColumns: '1fr 1fr' }}>
              {[
                ['Type',        vehicle.vehicle_type],
                ['Status',      vehicle.status],
                ['Confidence',  `${(vehicle.confidence * 100).toFixed(1)}%`],
                ['Cameras',     String(vehicle.camera_count)],
                ['First seen',  relativeTime(vehicle.first_seen)],
                ['Last seen',   relativeTime(vehicle.last_seen)],
              ].map(([a, b]) => (
                <div key={a}><span className="kpi-label">{a}</span><strong>{b}</strong></div>
              ))}
            </div>
            {vehicle.is_blacklisted && (
              <div style={{ marginTop: 10, padding: '8px 12px', background: '#fce9e9', borderRadius: 6, fontSize: 11, color: '#b94040' }}>
                ⚠ DEMO Blacklisted — {vehicle.blacklist_reason}
              </div>
            )}
          </Panel>

          <Panel title="Journey summary">
            {traj ? (
              <>
                <p>First detected {relativeTime(traj.first_seen)} · {traj.cameras_visited.length} cameras · {traj.total_distance_km.toFixed(2)} km traced</p>
                <p>Duration: {traj.travel_duration_min.toFixed(0)} min · Avg speed: {traj.average_speed_kmh.toFixed(1)} km/h</p>
                <p>Status: <strong style={{ color: traj.overall_status === 'NORMAL' ? 'var(--green)' : 'var(--red)' }}>{traj.overall_status}</strong></p>
                <p style={{ fontSize: 10, color: 'var(--muted-foreground)' }}>{traj.data_mode}</p>
              </>
            ) : (
              <p style={{ color: 'var(--muted-foreground)', fontSize: 11 }}>No trajectory data available for this plate.</p>
            )}
          </Panel>
        </section>
      )}

      {traj && (
        <section className="dashboard-grid">
          <Panel title="Trajectory map">
            <div className="map-panel" style={{ height: 300 }}>
              <div className="map-art">
                <div className="road road-a" />
                <div className="road road-b" />
                <div className="road road-c" />
                {stops.slice(0, 5).map((s, i) => (
                  <div key={i} className={`map-node node-${i + 1}`}><span /></div>
                ))}
              </div>
            </div>
            <PlaceholderBadge /> Map art is illustrative — GPS coordinates are real
          </Panel>

          <Panel title="Detection timeline">
            <div className="alert-list">
              {stops.map((s, i) => (
                <div className="alert-row" key={i}>
                  <Clock3 />
                  <span className="alert-copy">
                    <strong>{s.location} · {new Date(s.timestamp).toLocaleTimeString()}</strong>
                    <small>{s.camera_id}{s.road_name ? ` · ${s.road_name}` : ''}</small>
                    {traj.hops[i] && (
                      <em>{traj.hops[i].distance_km.toFixed(2)} km · {traj.hops[i].speed_kmh.toFixed(1)} km/h · {traj.hops[i].anomaly}</em>
                    )}
                  </span>
                </div>
              ))}
            </div>
          </Panel>
        </section>
      )}
    </>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// CAMERA NETWORK PAGE  🔶 live: /api/cameras KPI counts; feed thumbnails = placeholder
// ═══════════════════════════════════════════════════════════════════════════════

export function CameraNetwork() {
  const [cameras,  setCameras]  = useState<CameraItem[]>([])
  const [search,   setSearch]   = useState('')
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchCameras()
      setCameras(data)
      setError(null)
    } catch (err) {
      setError(`Camera data unavailable: ${(err as ApiError).detail ?? 'network error'}`)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const filtered = cameras.filter(c =>
    c.camera_id.toLowerCase().includes(search.toLowerCase()) ||
    c.location_name.toLowerCase().includes(search.toLowerCase()),
  )

  const online  = cameras.length
  const active  = cameras.filter(c => c.detections_last_hour > 0).length

  return (
    <>
      <Toolbar placeholder="Search cameras by ID or location" value={search} onChange={setSearch} />

      {loading && <Loading label="Loading camera network…" />}
      {error   && <ErrorBanner message={error} onRetry={load} />}

      <div className="kpi-grid" style={{ marginTop: 17 }}>
        {[
          ['Total Cameras', String(cameras.length || 15)],
          ['Online',        String(online)],
          ['Active (1h)',   String(active)],
          ['Loaded',        cameras.length > 0 ? 'Live' : 'Demo'],
        ].map(([a, b]) => (
          <article className="kpi-card" key={a}>
            <span className="kpi-label">{a}</span>
            <strong className="kpi-value">{b}</strong>
          </article>
        ))}
      </div>

      <div className="dashboard-grid">
        {(filtered.length > 0 ? filtered : [
          { camera_id: 'CAM-042', location_name: 'MG Road Junction',       detections_last_hour: 0, road_name: null, direction: null, latitude: 0, longitude: 0 },
          { camera_id: 'CAM-017', location_name: 'Koramangala 5th Block',  detections_last_hour: 0, road_name: null, direction: null, latitude: 0, longitude: 0 },
          { camera_id: 'CAM-088', location_name: 'Airport Road',           detections_last_hour: 0, road_name: null, direction: null, latitude: 0, longitude: 0 },
          { camera_id: 'CAM-103', location_name: 'Anna Salai',             detections_last_hour: 0, road_name: null, direction: null, latitude: 0, longitude: 0 },
        ] as CameraItem[]).slice(0, 8).map((c, i) => (
          <Panel title={`${c.camera_id} · ${c.location_name}`} key={c.camera_id}>
            <div style={{ height: 130, background: 'var(--navy)', borderRadius: 6, display: 'grid', placeItems: 'center', color: 'var(--cyan)' }}>
              <Camera size={32} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 12, fontSize: 11 }}>
              <span>1080p · 24 FPS</span>
              <span className="status-pill">{c.detections_last_hour > 0 ? `${c.detections_last_hour} det/h` : 'Online'}</span>
            </div>
            {c.road_name && <p style={{ fontSize: 10, color: 'var(--muted-foreground)', marginTop: 6 }}>{c.road_name}</p>}
          </Panel>
        ))}
      </div>
      <p style={{ fontSize: 10, color: 'var(--muted-foreground)', marginTop: 8 }}>
        <PlaceholderBadge /> Camera feed thumbnails require a live RTSP integration (Phase 9)
      </p>
    </>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// TRAFFIC ANALYTICS PAGE  ✅ live: /analytics
// ═══════════════════════════════════════════════════════════════════════════════

export function TrafficAnalytics() {
  const [analytics, setAnalytics] = useState<AnalyticsResponse | null>(null)
  const [loading,   setLoading]   = useState(true)
  const [error,     setError]     = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchAnalytics(24)
      setAnalytics(data)
      setError(null)
    } catch (err) {
      setError(`Analytics unavailable: ${(err as ApiError).detail ?? 'network error'}`)
      setAnalytics(DEMO_ANALYTICS)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const d = analytics ?? DEMO_ANALYTICS
  const trendData = d.traffic_trends.map(t => t.vehicle_count)
  const typeData  = d.vehicle_distribution.map(v => v.count)

  return (
    <>
      {loading && <Loading label="Loading analytics…" />}
      {error   && <ErrorBanner message={error} onRetry={load} />}

      <div className="kpi-grid">
        {[
          ['Average speed',     `${d.average_speed_kmh} km/h`],
          ['Traffic density',   d.traffic_density_label],
          ['Congestion score',  d.congestion_score.toFixed(2)],
          ['Unique plates',     String(d.total_unique_plates)],
        ].map(([a, b]) => (
          <article className="kpi-card" key={a}>
            <span className="kpi-label">{a}</span>
            <strong className="kpi-value">{b}</strong>
          </article>
        ))}
      </div>

      <section className="dashboard-grid">
        <Panel title="Traffic trend (24h)">
          <Chart data={trendData} />
        </Panel>
        <Panel title="Vehicle type distribution">
          <Chart data={typeData} bars />
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', padding: '6px 0', fontSize: 10 }}>
            {d.vehicle_distribution.map(v => (
              <span key={v.category} style={{ color: 'var(--muted-foreground)' }}>
                {v.category}: <strong>{v.percentage.toFixed(1)}%</strong>
              </span>
            ))}
          </div>
        </Panel>
      </section>

      <section className="dashboard-grid">
        <Panel title="Congestion zones">
          {d.congestion_zones.length > 0 ? (
            <Table rows={d.congestion_zones.map(z => [
              z.location, z.congestion_level, z.camera_id,
              `${z.vehicle_count} veh/h`,
            ])} />
          ) : (
            <p style={{ fontSize: 11, color: 'var(--muted-foreground)', padding: '10px 0' }}>
              No HIGH/SEVERE congestion zones in the last hour.
            </p>
          )}
        </Panel>
        <Panel title="Peak traffic hours">
          <Chart data={trendData} />
        </Panel>
      </section>
    </>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// CITY MAP PAGE  ✅ live: real Leaflet map connected to backend data
// ═══════════════════════════════════════════════════════════════════════════════

export function CityMap() {
  return (
    <div style={{ marginTop: -4 }}>
      <CityMapComponent />
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// ALERTS PAGE  ✅ live: /alerts
// ═══════════════════════════════════════════════════════════════════════════════

export function Alerts() {
  const [data,    setData]    = useState<AlertsResponse | null>(null)
  const [search,  setSearch]  = useState('')
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await fetchAlerts(50)
      setData(resp)
      setError(null)
    } catch (err) {
      setError(`Alerts unavailable: ${(err as ApiError).detail ?? 'network error'}`)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const filteredAlerts = (data?.alerts ?? []).filter(a =>
    a.alert_type.toLowerCase().includes(search.toLowerCase()) ||
    (a.plate_number ?? '').toLowerCase().includes(search.toLowerCase()) ||
    (a.location ?? '').toLowerCase().includes(search.toLowerCase()),
  )

  const kpis: [string, number | string][] = data
    ? [['All alerts', data.total_alerts], ['Critical', data.critical_count], ['Warnings', data.warning_count], ['Resolved today', 0]]
    : [['All alerts', '—'], ['Critical', '—'], ['Warnings', '—'], ['Resolved today', '—']]

  const severityColor = (s: string) =>
    s === 'CRITICAL' ? '#b94040' : s === 'WARNING' ? '#d08c16' : '#188eaf'

  return (
    <>
      {loading && <Loading label="Loading alerts…" />}
      {error   && <ErrorBanner message={error} onRetry={load} />}

      <div className="kpi-grid">
        {kpis.map(([a, b]) => (
          <article className="kpi-card" key={a}>
            <span className="kpi-label">{a}</span>
            <strong className="kpi-value">{b}</strong>
          </article>
        ))}
      </div>

      <Panel title="Alert management">
        <Toolbar placeholder="Search alerts by type, plate, or location" value={search} onChange={setSearch} />
        {data?.demo_disclaimer && (
          <p style={{ fontSize: 9, color: 'var(--muted-foreground)', margin: '8px 0 0', fontStyle: 'italic' }}>
            {data.demo_disclaimer}
          </p>
        )}
        <div style={{ marginTop: 16 }}>
          {loading
            ? <Loading />
            : filteredAlerts.length > 0
              ? (
                <Table rows={filteredAlerts.slice(0, 20).map(a => [
                  a.alert_type.replace(/_/g, ' '),
                  a.severity,
                  a.camera_id ?? a.location ?? '—',
                  relativeTime(a.timestamp),
                ])} />
              )
              : <p style={{ fontSize: 11, color: 'var(--muted-foreground)' }}>No alerts match your search.</p>
          }
        </div>
      </Panel>
    </>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// BLACKLIST MONITORING PAGE  ✅ live: /alerts filtered for BLACKLISTED_VEHICLE
// ═══════════════════════════════════════════════════════════════════════════════

export function BlacklistMonitoring() {
  const [search,  setSearch]  = useState('')
  const [alerts,  setAlerts]  = useState<AlertsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState<string | null>(null)

  useEffect(() => {
    fetchAlerts(100)
      .then(data => { setAlerts(data); setLoading(false) })
      .catch(err => { setError((err as ApiError).detail ?? 'Network error'); setLoading(false) })
  }, [])

  const blacklistAlerts = (alerts?.alerts ?? []).filter(
    a => a.alert_type === 'BLACKLISTED_VEHICLE',
  )

  const filtered = blacklistAlerts.filter(a =>
    (a.plate_number ?? '').toLowerCase().includes(search.toLowerCase()) ||
    (a.location ?? '').toLowerCase().includes(search.toLowerCase()),
  )

  return (
    <>
      <Toolbar placeholder="Search blacklisted vehicle registration" value={search} onChange={setSearch} />
      {loading && <Loading label="Loading blacklist data…" />}
      {error   && <ErrorBanner message={error} />}

      <Panel title="Watchlist vehicles (DEMO DATA)">
        {alerts && (
          <p style={{ fontSize: 9, color: 'var(--muted-foreground)', marginBottom: 10, fontStyle: 'italic' }}>
            {alerts.demo_disclaimer}
          </p>
        )}
        {filtered.length > 0 ? (
          <Table rows={filtered.map(a => [
            a.plate_number ?? '—',
            a.severity,
            a.location ?? a.camera_id ?? '—',
            relativeTime(a.timestamp),
          ])} />
        ) : !loading ? (
          <p style={{ fontSize: 11, color: 'var(--muted-foreground)' }}>
            {blacklistAlerts.length === 0
              ? 'No blacklisted vehicles detected in the last 24 hours.'
              : 'No results match your search.'}
          </p>
        ) : null}
      </Panel>
    </>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// SYSTEM HEALTH PAGE  ✅ live: /health
// ═══════════════════════════════════════════════════════════════════════════════

export function SystemHealth() {
  const [health,  setHealth]  = useState<HealthResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchHealth()
      setHealth(data)
      setError(null)
    } catch (err) {
      setError(`Backend unreachable: ${(err as ApiError).detail ?? 'network error'}`)
      setHealth(DEMO_HEALTH)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const h = health ?? DEMO_HEALTH
  const isRunning = h.status === 'running'

  const services = [
    ['Backend API',        isRunning,                h.status],
    ['Database',          h.database === 'connected', h.database],
    ['ANPR Engine',       isRunning,                 'Phase 2–8'],
    ['OCR Engine',        isRunning,                 'EasyOCR'],
    ['Trajectory Engine', isRunning,                 'Phase 4'],
    ['Camera Network',    isRunning,                 `${h.total_cameras} registered`],
  ] as [string, boolean, string][]

  return (
    <>
      {loading && <Loading label="Checking system health…" />}
      {error   && <ErrorBanner message={error} onRetry={load} />}

      <div style={{ marginBottom: 12, fontSize: 11 }}>
        API version: <strong>{h.version}</strong> · {h.api_phase}
      </div>

      <div className="kpi-grid">
        {services.map(([name, ok, detail]) => (
          <article className="kpi-card" key={name}>
            <span className="kpi-icon green-bg" style={ok ? {} : { color: '#c14f52', background: '#fce9e9' }}>
              <Activity />
            </span>
            <span className="kpi-label">{name}</span>
            <strong style={{ display: 'block', marginTop: 15 }}>
              {ok ? 'Operational' : 'Degraded'}
            </strong>
            <div className="kpi-trend" style={ok ? {} : { color: 'var(--amber)' }}>
              <Wifi /> {detail}
            </div>
          </article>
        ))}
      </div>

      <Panel title="System metrics">
        <div className="kpi-grid" style={{ gridTemplateColumns: 'repeat(3,1fr)' }}>
          {[
            ['Total detections', h.total_detections.toLocaleString()],
            ['Active cameras',   String(h.total_cameras)],
            ['API version',      h.version],
          ].map(([a, b]) => (
            <div key={a}><span className="kpi-label">{a}</span><strong>{b}</strong></div>
          ))}
        </div>
      </Panel>
    </>
  )
}
