'use client'

/**
 * UrbanEye AI - Route Pages
 * =========================
 * All 8 dashboard pages live here.
 *
 * Integration status per page:
 *
 * âœ… Overview             - live: /health + /analytics
 * âœ… VehicleSearch        - live: /vehicles/{plate} + /api/trajectory/{plate}
 * âœ… Alerts               - live: /alerts
 * âœ… TrafficAnalytics     - live: /analytics
 * âœ… SystemHealth         - live: /health
 * âœ… CameraNetwork       - live: /api/cameras + per-camera video upload + real AI pipeline
 * âœ… CityMap             - live: real Leaflet map, /api/cameras + /analytics/traffic-density + /analytics/congestion + /api/trajectory/{plate}
 * ðŸ”¶ BlacklistMonitoring - live alert data filtered for BLACKLISTED_VEHICLE type
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
  fetchManualReviews, submitReviewDecision,
  type HealthResponse, type AnalyticsResponse, type VehicleRecord,
  type TrajectoryResponse, type AlertsResponse, type CameraItem,
  type VehicleListResponse, type ManualReviewItem,
  ApiError,
} from '@/lib/api'

// â”€â”€ Dynamic import for CameraCard (avoids SSR issues with localStorage) â”€â”€â”€â”€â”€â”€
const CameraCardDynamic = dynamic(
  () => import('@/src/components/CameraCard').then(m => ({ default: m.CameraCard })),
  { ssr: false, loading: () => <div className="panel" style={{ minHeight: 200 }} /> }
)
const CityMapComponent = dynamic(
  () => import('@/src/components/CityMapComponent'),
  {
    ssr: false,
    loading: () => (
      <div style={{
        height: 'calc(100vh - 240px)', minHeight: 440,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'var(--muted)', borderRadius: 8, color: 'var(--muted-foreground)',
        gap: 10, fontSize: 12,
      }}>
        <div style={{ animation: 'spin 1s linear infinite', display: 'flex' }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
          </svg>
        </div>
        Loading interactive mapâ€¦
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    ),
  }
)

// â”€â”€ shared UI helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const Panel = ({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) => (
  <article className="panel">
    <div className="panel-header">
      <div><h2>{title}</h2><p>{subtitle ?? 'Live operational data'}</p></div>
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
function Loading({ label = 'Loadingâ€¦' }: { label?: string }) {
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
          ? 'Backend is offline - showing demo data. Start the backend server to see live results.'
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
      background: '#1a1000', color: '#c28118',
      fontSize: 9, fontWeight: 700, letterSpacing: '.6px', marginLeft: 8,
    }}>
      DEMO DATA
    </span>
  )
}

/** Vertical bar chart using only CSS/divs - no external charting library */
const Chart = ({ data, bars = false, xLabels }: { data?: number[]; bars?: boolean; xLabels?: string[] }) => {
  const values = data ?? [45, 68, 52, 82, 60, 94, 72, 88, 64, 78, 51, 86]
  const max    = Math.max(...values, 1)
  const ticks  = 4  // number of horizontal grid lines

  // X-axis labels: use provided, else 0/6/12/18/23 for 24-point data, else indices
  const showXLabels = values.length === 24
    ? values.map((_, i) => i % 3 === 0 ? `${i}h` : '')
    : (xLabels ?? values.map((_, i) => String(i + 1)))

  return (
    <div style={{ padding: '8px 4px 0', userSelect: 'none' }}>
      {/* Chart area */}
      <div style={{ display: 'flex', gap: 0 }}>
        {/* Y-axis labels */}
        <div style={{
          display: 'flex', flexDirection: 'column-reverse', justifyContent: 'space-between',
          width: 32, paddingBottom: 20, paddingRight: 4, flexShrink: 0,
        }}>
          {Array.from({ length: ticks + 1 }, (_, i) => (
            <span key={i} style={{ fontSize: 9, color: 'var(--muted-foreground)', textAlign: 'right', lineHeight: 1 }}>
              {Math.round((max / ticks) * i)}
            </span>
          ))}
        </div>

        {/* Bars + grid */}
        <div style={{ flex: 1, position: 'relative' }}>
          {/* Horizontal grid lines */}
          {Array.from({ length: ticks + 1 }, (_, i) => (
            <div key={i} style={{
              position: 'absolute',
              bottom: `calc(20px + ${(i / ticks) * (100 - 20 / 200 * 100)}%)`,
              left: 0, right: 0,
              borderTop: `1px ${i === 0 ? 'solid' : 'dashed'} var(--border)`,
              opacity: i === 0 ? 1 : 0.5,
            }} />
          ))}

          {/* Bar columns */}
          <div style={{
            display: 'flex', alignItems: 'flex-end', gap: 3,
            height: 180, paddingBottom: 20,
          }}>
            {values.map((v, i) => (
              <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', height: '100%', justifyContent: 'flex-end' }}>
                <div
                  title={`${showXLabels[i] || i}: ${v}`}
                  style={{
                    width: '100%',
                    height: `${Math.max((v / max) * 100, v > 0 ? 2 : 0)}%`,
                    background: bars
                      ? 'linear-gradient(to top, #d97706, #fbbf24)'
                      : 'linear-gradient(to top, #0891b2, #67e8f9)',
                    borderRadius: '3px 3px 0 0',
                    opacity: 0.85,
                    transition: 'height .3s ease',
                    minHeight: v > 0 ? 3 : 0,
                  }}
                />
              </div>
            ))}
          </div>

          {/* X-axis labels */}
          <div style={{ display: 'flex', gap: 3, marginTop: 2 }}>
            {showXLabels.map((lbl, i) => (
              <div key={i} style={{ flex: 1, textAlign: 'center', fontSize: 8, color: 'var(--muted-foreground)', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                {lbl}
              </div>
            ))}
          </div>
        </div>
      </div>
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
  if (!iso) return '-'
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 60000)
  if (diff < 1) return 'just now'
  if (diff < 60) return `${diff} min ago`
  if (diff < 1440) return `${Math.floor(diff / 60)}h ago`
  return new Date(iso).toLocaleDateString()
}

// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
// OVERVIEW PAGE  âœ… live: /health + /analytics
// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

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
      // DO NOT fall back to DEMO_ANALYTICS - show empty state so users
      // know the data is not real. Analytics remain null until backend responds.
      setAnalytics(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const d = analytics
  const isDemo = error !== null

  // When backend is offline, show zeros/empty rather than fake numbers
  const kpis = d ? [
    ['Vehicles Detected', d.total_vehicles.toLocaleString()],
    ['Active Alerts',     String(d.active_alerts)],
    ['Cameras Online',    `${d.total_cameras} active`],
    ['Avg Speed',         `${d.average_speed_kmh} km/h`],
  ] : [
    ['Vehicles Detected', '-'],
    ['Active Alerts',     '-'],
    ['Cameras Online',    '-'],
    ['Avg Speed',         '-'],
  ]

  const trendData = d?.traffic_trends.map(t => t.vehicle_count) ?? []

  const recentVehicles = d ? d.vehicle_distribution.map((item) => [
    item.category.charAt(0).toUpperCase() + item.category.slice(1),
    `${item.percentage.toFixed(1)}%`,
    d.most_active_location ?? 'Various',
    'Today',
  ]) : []

  return (
    <>
      {loading && <Loading label="Fetching live analyticsâ€¦" />}
      {error && !loading && <ErrorBanner message={error} onRetry={load} />}
      {isDemo && !loading && (
        <div style={{ marginBottom: 14, fontSize: 11, color: 'var(--muted-foreground)', padding: '8px 12px', background: 'var(--muted)', borderRadius: 6 }}>
          Backend offline - showing empty state. Start the backend at&nbsp;
          <code style={{ background: 'var(--border)', padding: '1px 5px', borderRadius: 3, fontSize: 10 }}>
            localhost:8000
          </code>
          &nbsp;to see live data.
        </div>
      )}

      <div className="kpi-grid">
        {kpis.map(([label, value]) => (
          <article className="kpi-card" key={label}>
            <span className="kpi-label">{label}</span>
            <strong className="kpi-value">{value}</strong>
            <div className="kpi-trend">
              {label === 'Active Alerts'
                ? <>{d?.critical_count ?? 0} critical</>
                : <>Live data</>
              }
            </div>
          </article>
        ))}
      </div>

      <section className="dashboard-grid">
        <Panel title="Traffic Volume (24h)" subtitle="Vehicles detected per hour">
          <Chart data={trendData} />
        </Panel>
        <Panel title="Traffic Summary">
          <div className="kpi-grid" style={{ gridTemplateColumns: '1fr 1fr' }}>
            {(d ? [
              ['Congestion',    d.traffic_density_label],
              ['Avg speed',     `${d.average_speed_kmh} km/h`],
              ['Cong. score',   d.congestion_score.toFixed(2)],
              ['Unique plates', String(d.total_unique_plates)],
            ] : [
              ['Congestion', '-'], ['Avg speed', '-'],
              ['Cong. score', '-'], ['Unique plates', '-'],
            ]).map(([a, b]) => (
              <div key={a}><span className="kpi-label">{a}</span><strong>{b}</strong></div>
            ))}
          </div>
        </Panel>
      </section>

      <section className="lower-grid">
        <Panel title="Vehicle Type Distribution">
          {loading
            ? <Loading />
            : d && d.vehicle_distribution.length > 0
            ? <Table rows={recentVehicles} />
            : <p style={{ fontSize: 11, color: 'var(--muted-foreground)', padding: '10px 0' }}>
                No vehicle data available. Process a video to see real distribution.
              </p>
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
  const [error, setError] = useState(false)

  useEffect(() => {
    fetchAlerts(limit)
      .then(d => { setData(d); setError(false) })
      .catch(() => { setData(null); setError(true) })
  }, [limit])

  if (error) {
    return (
      <p style={{ fontSize: 11, color: 'var(--muted-foreground)', padding: '10px 0' }}>
        Unable to load alerts - backend offline.
      </p>
    )
  }

  if (!data) return <Loading label="Loading alertsâ€¦" />

  if (data.alerts.length === 0) {
    return (
      <p style={{ fontSize: 11, color: 'var(--muted-foreground)', padding: '10px 0' }}>
        No active alerts.
      </p>
    )
  }

  return (
    <div className="alert-list">
      {data.alerts.slice(0, limit).map(a => (
        <div className="alert-row" key={a.alert_id}>
          <Siren />
          <span className="alert-copy">
            <strong>{a.alert_type.replace(/_/g, ' ')}</strong>
            <small>{a.plate_number ?? a.camera_id ?? a.location ?? '-'}</small>
          </span>
        </div>
      ))}
    </div>
  )
}

// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
// VEHICLE SEARCH PAGE  âœ… live: /vehicles/{plate} + /api/trajectory/{plate}
// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

export function VehicleSearch() {
  const [query,    setQuery]    = useState('')
  const [plate,    setPlate]    = useState('')
  const [vehicle,  setVehicle]  = useState<VehicleRecord | null>(null)
  const [traj,     setTraj]     = useState<TrajectoryResponse | null>(null)
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState<string | null>(null)

  const track = useCallback(async (searchPlate: string) => {
    const p = searchPlate.trim().toUpperCase()
    if (!p) {
      setError('Enter a plate number to search.')
      return
    }
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
          ? `No detections found for plate "${p}". Process a video first, then search by the detected plate.`
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
          Search any verified plate number from processed videos.
          {' '}If you have seeded demo data, try: <code>TS09AB1234</code>
        </p>
      </Panel>

      {loading && <Loading label={`Searching for ${plate}â€¦`} />}

      {vehicle && (
        <section className="dashboard-grid" style={{ marginTop: 17 }}>
          <Panel title={`Vehicle information Â· ${vehicle.plate_number}`}>
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
              <div style={{ marginTop: 10, padding: '8px 12px', background: '#1a0508', borderRadius: 6, fontSize: 11, color: '#b94040' }}>
                âš  DEMO Blacklisted - {vehicle.blacklist_reason}
              </div>
            )}
          </Panel>

          <Panel title="Journey summary">
            {traj ? (
              <>
                <p>First detected {relativeTime(traj.first_seen)} Â· {traj.cameras_visited.length} cameras Â· {traj.total_distance_km.toFixed(2)} km traced</p>
                <p>Duration: {traj.travel_duration_min.toFixed(0)} min Â· Avg speed: {traj.average_speed_kmh.toFixed(1)} km/h</p>
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
            <PlaceholderBadge /> Map art is illustrative - GPS coordinates are real
          </Panel>

          <Panel title="Detection timeline">
            <div className="alert-list">
              {stops.map((s, i) => (
                <div className="alert-row" key={i}>
                  <Clock3 />
                  <span className="alert-copy">
                    <strong>{s.location} Â· {new Date(s.timestamp).toLocaleTimeString()}</strong>
                    <small>{s.camera_id}{s.road_name ? ` Â· ${s.road_name}` : ''}</small>
                    {traj.hops[i] && (
                      <em>{traj.hops[i].distance_km.toFixed(2)} km Â· {traj.hops[i].speed_kmh.toFixed(1)} km/h Â· {traj.hops[i].anomaly}</em>
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

// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
// CAMERA NETWORK PAGE  ðŸ”¶ live: /api/cameras KPI counts; feed thumbnails = placeholder
// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
// CAMERA NETWORK PAGE  âœ… live: /api/cameras + per-camera video upload + real AI pipeline
// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

export function CameraNetwork() {
  const [cameras,  setCameras]  = useState<CameraItem[]>([])
  const [search,   setSearch]   = useState('')
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState<string | null>(null)
  const [results,  setResults]  = useState<Record<string, any>>({})

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

  // Load stored processing results from localStorage on mount (client-side only)
  useEffect(() => {
    if (typeof window !== 'undefined') {
      try {
        const raw = localStorage.getItem('urbaneye_camera_results')
        if (raw) setResults(JSON.parse(raw))
      } catch { /* ignore parse errors */ }
    }
    load()
  }, [load])

  const filtered = cameras.filter(c =>
    c.camera_id.toLowerCase().includes(search.toLowerCase()) ||
    c.location_name.toLowerCase().includes(search.toLowerCase()),
  )

  const processedCount = Object.keys(results).length
  const withDetections = Object.values(results).filter((r: any) => (r?.total_detections ?? 0) > 0).length

  return (
    <>
      <Toolbar placeholder="Search cameras by ID or location" value={search} onChange={setSearch} />

      {loading && <Loading label="Loading camera networkâ€¦" />}
      {error   && <ErrorBanner message={error} onRetry={load} />}

      {/* KPI cards - honest labels */}
      <div className="kpi-grid" style={{ marginTop: 17 }}>
        {[
          ['Total Cameras',    String(cameras.length)],
          ['Configured',       String(cameras.length)],
          ['Videos Processed', String(processedCount)],
          ['With Detections',  String(withDetections)],
        ].map(([a, b]) => (
          <article className="kpi-card" key={a}>
            <span className="kpi-label">{a}</span>
            <strong className="kpi-value">{b}</strong>
          </article>
        ))}
      </div>

      {/* Honest status notice */}
      <div style={{
        padding: '8px 14px', background: 'var(--muted)', borderRadius: 7,
        fontSize: 10, color: 'var(--muted-foreground)', marginBottom: 17,
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <Camera size={12} />
        These are <strong style={{ margin: '0 3px' }}>configured camera locations</strong>
        - not live CCTV streams. Click any card to upload a real traffic video and run the AI pipeline.
      </div>

      {/* Interactive camera grid using real CameraCard components */}
      <div className="dashboard-grid">
        {(filtered.length > 0 ? filtered : cameras).slice(0, 8).map(c => (
          <CameraCardDynamic
            key={c.camera_id}
            camera={c}
            stored={results[c.camera_id] ?? null}
            onUpdate={(r: any) => setResults(prev => ({ ...prev, [r.camera_id]: r }))}
          />
        ))}
      </div>

      {filtered.length === 0 && cameras.length > 0 && !loading && (
        <p style={{ textAlign: 'center', color: 'var(--muted-foreground)', fontSize: 12, padding: '20px 0' }}>
          No cameras match &ldquo;{search}&rdquo;.
        </p>
      )}

      {/* Usage instructions */}
      <div style={{
        marginTop: 16, padding: '12px 16px', background: 'var(--muted)',
        borderRadius: 8, fontSize: 10, color: 'var(--muted-foreground)',
      }}>
        <strong style={{ display: 'block', marginBottom: 4, color: 'var(--foreground)' }}>How to use</strong>
        1.&nbsp;Click a camera card to open its details.&nbsp;&nbsp;
        2.&nbsp;Upload a real traffic video (MP4 / AVI / MOV / MKV).&nbsp;&nbsp;
        3.&nbsp;Click &ldquo;Process Video&rdquo; - vehicle detection, plate OCR, and analytics run via the AI backend.&nbsp;&nbsp;
        4.&nbsp;Results appear in the card and on the City Traffic Map.
        <br /><br />
        Free traffic videos:&nbsp;
        <a href="https://www.pexels.com/search/videos/traffic/" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--primary)' }}>Pexels</a>
        &nbsp;Â·&nbsp;
        <a href="https://pixabay.com/videos/search/traffic/" target="_blank" rel="noopener noreferrer" style={{ color: 'var(--primary)' }}>Pixabay</a>
        &nbsp;(download manually, then upload above)
      </div>
    </>
  )
}

// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
// TRAFFIC ANALYTICS PAGE  âœ… live: /analytics
// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

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
      setAnalytics(null)   // show empty state, not fake data
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const d = analytics
  const trendData = d?.traffic_trends.map(t => t.vehicle_count) ?? []
  const typeData  = d?.vehicle_distribution.map(v => v.count) ?? []

  return (
    <>
      {loading && <Loading label="Loading analyticsâ€¦" />}
      {error   && <ErrorBanner message={error} onRetry={load} />}

      <div className="kpi-grid">
        {[
          ['Average speed',     d ? `${d.average_speed_kmh} km/h` : '-'],
          ['Traffic density',   d?.traffic_density_label ?? '-'],
          ['Congestion score',  d ? d.congestion_score.toFixed(2) : '-'],
          ['Unique plates',     d ? String(d.total_unique_plates) : '-'],
        ].map(([a, b]) => (
          <article className="kpi-card" key={a}>
            <span className="kpi-label">{a}</span>
            <strong className="kpi-value">{b}</strong>
          </article>
        ))}
      </div>

      <section className="dashboard-grid">
        <Panel title="Traffic trend (24h)" subtitle="Vehicles detected per hour — last 24h">
          <Chart data={trendData} />
        </Panel>
        <Panel title="Vehicle type distribution" subtitle="Count by vehicle class">
          <Chart data={typeData} bars xLabels={d?.vehicle_distribution.map(v => v.category.slice(0,4)) ?? []} />
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', padding: '6px 0', fontSize: 10 }}>
            {(d?.vehicle_distribution ?? []).map(v => (
              <span key={v.category} style={{ color: 'var(--muted-foreground)' }}>
                {v.category}: <strong>{v.percentage.toFixed(1)}%</strong>
              </span>
            ))}
          </div>
        </Panel>
      </section>

      <section className="dashboard-grid">
        <Panel title="Congestion zones">
          {d && d.congestion_zones.length > 0 ? (
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
        <Panel title="Peak traffic hours" subtitle="Hourly vehicle count — last 24h">
          <Chart data={trendData} />
        </Panel>
      </section>
    </>
  )
}

// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
// CITY MAP PAGE  âœ… live: real Leaflet map connected to backend data
// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

export function CityMap() {
  return (
    <div style={{ marginTop: -4 }}>
      <CityMapComponent />
    </div>
  )
}

// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
// ALERTS PAGE  âœ… live: /alerts
// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

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
    : [['All alerts', '-'], ['Critical', '-'], ['Warnings', '-'], ['Resolved today', '-']]

  const severityColor = (s: string) =>
    s === 'CRITICAL' ? '#b94040' : s === 'WARNING' ? '#d08c16' : '#188eaf'

  return (
    <>
      {loading && <Loading label="Loading alertsâ€¦" />}
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
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr><th>TYPE</th><th>SEVERITY</th><th>PLATE</th><th>LOCATION</th><th>TIME</th></tr>
                    </thead>
                    <tbody>
                      {filteredAlerts.slice(0, 20).map(a => (
                        <tr key={a.alert_id}>
                          <td>
                            <span style={{
                              fontSize: 9, fontWeight: 700, letterSpacing: '.4px',
                              padding: '3px 7px', borderRadius: 10,
                              background:
                                a.alert_type === 'BLACKLISTED_VEHICLE'  ? '#fce8e8' :
                                a.alert_type === 'COMPLIANCE_ANOMALY'   ? '#fff0d5' :
                                a.alert_type.includes('TRAJECTORY')     ? '#eae8fa' :
                                a.alert_type === 'CONGESTION'           ? '#fff3dd' :
                                '#e0f4f9',
                              color:
                                a.alert_type === 'BLACKLISTED_VEHICLE'  ? '#b94040' :
                                a.alert_type === 'COMPLIANCE_ANOMALY'   ? '#c28118' :
                                a.alert_type.includes('TRAJECTORY')     ? '#7769ca' :
                                a.alert_type === 'CONGESTION'           ? '#c28118' :
                                '#0c7f9d',
                            }}>
                              {a.alert_type.replace(/_/g, ' ')}
                            </span>
                          </td>
                          <td><span className={`status-pill ${a.severity === 'CRITICAL' ? 'red' : a.severity === 'WARNING' ? 'amber' : 'cyan'}`}>{a.severity}</span></td>
                          <td>{a.plate_number || '-'}</td>
                          <td>{a.location ?? a.camera_id ?? '-'}</td>
                          <td>{relativeTime(a.timestamp)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
              : <p style={{ fontSize: 11, color: 'var(--muted-foreground)' }}>
                  {data ? 'No alerts match your search.' : 'No alerts found.'}
                </p>
          }
        </div>
      </Panel>
    </>
  )
}

// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
// BLACKLIST MONITORING PAGE  âœ… live: /alerts filtered for BLACKLISTED_VEHICLE
// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

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
      {loading && <Loading label="Loading blacklist dataâ€¦" />}
      {error   && <ErrorBanner message={error} />}

      <Panel title="Watchlist vehicles (DEMO DATA)">
        {alerts && (
          <p style={{ fontSize: 9, color: 'var(--muted-foreground)', marginBottom: 10, fontStyle: 'italic' }}>
            {alerts.demo_disclaimer}
          </p>
        )}
        {filtered.length > 0 ? (
          <Table rows={filtered.map(a => [
            a.plate_number ?? '-',
            a.severity,
            a.location ?? a.camera_id ?? '-',
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

// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
// SYSTEM HEALTH PAGE  âœ… live: /health
// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

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
      setHealth(null)   // do not substitute fake health data
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const h = health
  const isRunning = h?.status === 'running'

  const services = h ? [
    ['Backend API',        isRunning,                  h.status],
    ['Database',          h.database === 'connected',  h.database],
    ['ANPR Engine',       isRunning,                   'Phase 2â€“8'],
    ['OCR Engine',        isRunning,                   'EasyOCR'],
    ['Trajectory Engine', isRunning,                   'Phase 4'],
    ['Camera Network',    isRunning,                   `${h.total_cameras} registered`],
  ] as [string, boolean, string][] : []

  return (
    <>
      {loading && <Loading label="Checking system healthâ€¦" />}
      {error   && <ErrorBanner message={error} onRetry={load} />}

      {h && (
        <div style={{ marginBottom: 12, fontSize: 11 }}>
          API version: <strong>{h.version}</strong> Â· {h.api_phase}
        </div>
      )}
      {!h && !loading && !error && (
        <p style={{ fontSize: 11, color: 'var(--muted-foreground)' }}>Backend is offline.</p>
      )}

      {h && (<>
      <div className="kpi-grid">
        {services.map(([name, ok, detail]) => (
          <article className="kpi-card" key={name}>
            <span className="kpi-icon green-bg" style={ok ? {} : { color: '#c14f52', background: '#1a0508' }}>
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
      </>)}
    </>
  )
}


// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
// MANUAL REVIEW PAGE  âœ… live: /manual-review  (Change 6 - Reliability Upgrade)
// â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

export function ManualReviewPage() {
  const [items,    setItems]    = useState<ManualReviewItem[]>([])
  const [total,    setTotal]    = useState(0)
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState<string | null>(null)
  const [filter,   setFilter]   = useState<string>('PENDING')
  const [submitting, setSubmitting] = useState<number | null>(null)
  const [editPlate,  setEditPlate]  = useState<string>('')
  const [editId,     setEditId]     = useState<number | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchManualReviews(filter === 'ALL' ? undefined : filter, 50, 0)
      setItems(data.items)
      setTotal(data.total)
      setError(null)
    } catch (err) {
      setError(`${(err as ApiError).detail ?? 'Network error'}`)
    } finally {
      setLoading(false)
    }
  }, [filter])

  useEffect(() => { load() }, [load])

  const decide = useCallback(async (
    id: number,
    decision: 'CONFIRMED' | 'REJECTED' | 'EDITED',
    plate?: string,
  ) => {
    setSubmitting(id)
    try {
      await submitReviewDecision(id, decision, plate)
      await load()
    } catch (err) {
      alert(`Decision failed: ${(err as ApiError).detail ?? (err as Error).message}`)
    } finally {
      setSubmitting(null)
      setEditId(null)
      setEditPlate('')
    }
  }, [load])

  const tierColour = (tier: string) => ({
    HIGH:   { bg: '#dff5ec', color: '#169266' },
    MEDIUM: { bg: '#fff3dd', color: '#c28118' },
    LOW:    { bg: '#fce9e9', color: '#b94040' },
  }[tier.toUpperCase()] ?? { bg: '#eef3f7', color: '#6d7f92' })

  const statusColour = (st: string) => ({
    PENDING:   { bg: '#e0f4f9', color: '#0c7f9d' },
    CONFIRMED: { bg: '#dff5ec', color: '#169266' },
    REJECTED:  { bg: '#fce9e9', color: '#b94040' },
    EDITED:    { bg: '#eae8fa', color: '#7769ca' },
  }[st.toUpperCase()] ?? { bg: '#eef3f7', color: '#6d7f92' })

  return (
    <>
      <div style={{ marginBottom: 14, padding: '8px 14px', background: '#1a1200', borderRadius: 7, fontSize: 10, color: '#c28118', border: '1px solid #f8d38b' }}>
        <strong>Change 5 - Blacklist Safety Gate:</strong> LOW-confidence plate reads never auto-trigger blacklist alerts.
        They appear here for human verification before any action is taken.
        Only CONFIRMED or EDITED items become eligible for blacklist matching.
      </div>

      {/* Filter tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 17, flexWrap: 'wrap' }}>
        {['PENDING', 'CONFIRMED', 'REJECTED', 'EDITED', 'ALL'].map(s => (
          <button
            key={s}
            className={filter === s ? 'primary-button' : 'date-button'}
            style={{ fontSize: 11, padding: '7px 14px' }}
            onClick={() => setFilter(s)}
          >
            {s}
          </button>
        ))}
        <div style={{ marginLeft: 'auto' }}>
          <button className="date-button" onClick={load} style={{ fontSize: 11 }}>
            <RefreshCw size={12} /> Refresh
          </button>
        </div>
      </div>

      {loading && <Loading label="Loading review queueâ€¦" />}
      {error   && <ErrorBanner message={error} onRetry={load} />}

      {!loading && items.length === 0 && (
        <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--muted-foreground)', fontSize: 12 }}>
          No {filter === 'ALL' ? '' : filter.toLowerCase()} review items.
          {filter === 'PENDING' && ' Process a video to populate this queue.'}
        </div>
      )}

      {/* Review items */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {items.map(item => {
          const tc = tierColour(item.confidence_tier)
          const sc = statusColour(item.review_status)
          const isEditing = editId === item.id
          return (
            <div key={item.id} className="panel" style={{ padding: 0 }}>
              <div style={{ padding: '14px 18px' }}>
                {/* Header row */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--foreground)' }}>
                        {item.ocr_plate_text || '(no plate text)'}
                      </span>
                      <span style={{ fontSize: 9, fontWeight: 700, padding: '2px 7px', borderRadius: 10, background: tc.bg, color: tc.color }}>
                        {item.confidence_tier} CONFIDENCE
                      </span>
                      <span style={{ fontSize: 9, fontWeight: 700, padding: '2px 7px', borderRadius: 10, background: sc.bg, color: sc.color }}>
                        {item.review_status}
                      </span>
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--muted-foreground)', display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                      <span>ðŸ“· {item.camera_id}</span>
                      <span>ðŸš— {item.vehicle_type ?? '-'} ({item.vehicle_category ?? '-'})</span>
                      <span>ðŸ• {new Date(item.timestamp).toLocaleString()}</span>
                      <span>ðŸ“ {item.source_file ?? '-'}</span>
                      {item.frame_number !== null && <span>Frame #{item.frame_number}</span>}
                    </div>
                  </div>
                  {item.review_status === 'PENDING' && (
                    <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                      <button
                        className="date-button"
                        style={{ fontSize: 10, padding: '5px 10px', color: '#169266', borderColor: '#169266' }}
                        disabled={submitting === item.id}
                        onClick={() => decide(item.id, 'CONFIRMED')}
                      >
                        {submitting === item.id ? <Loader2 size={10} style={{ animation: 'spin 1s linear infinite' }} /> : 'âœ“'} Confirm
                      </button>
                      <button
                        className="date-button"
                        style={{ fontSize: 10, padding: '5px 10px' }}
                        onClick={() => { setEditId(item.id); setEditPlate(item.ocr_plate_text ?? '') }}
                      >
                        âœ Edit
                      </button>
                      <button
                        className="date-button"
                        style={{ fontSize: 10, padding: '5px 10px', color: '#b94040', borderColor: '#b94040' }}
                        disabled={submitting === item.id}
                        onClick={() => decide(item.id, 'REJECTED')}
                      >
                        âœ— Reject
                      </button>
                    </div>
                  )}
                </div>

                {/* Evidence row */}
                <div style={{ marginTop: 10, display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 8, fontSize: 10 }}>
                  {[
                    ['Agreement rate', item.agreement_rate !== null ? `${((item.agreement_rate ?? 0) * 100).toFixed(0)}%` : '-'],
                    ['Valid OCR reads', String(item.valid_ocr_reads ?? '-')],
                    ['Matching reads',  String(item.matching_ocr_reads ?? '-')],
                    ['OCR confidence',  item.ocr_confidence !== null ? `${((item.ocr_confidence ?? 0) * 100).toFixed(1)}%` : '-'],
                  ].map(([k, v]) => (
                    <div key={k} style={{ padding: '6px 10px', background: 'var(--muted)', borderRadius: 6 }}>
                      <span style={{ display: 'block', color: 'var(--muted-foreground)', marginBottom: 2 }}>{k}</span>
                      <strong>{v}</strong>
                    </div>
                  ))}
                </div>

                <p style={{ fontSize: 9, color: '#9aa8b5', marginTop: 6 }}>
                  Reason: {item.reason} Â· Track: {item.track_id ?? '-'} Â· Created: {new Date(item.created_at).toLocaleString()}
                </p>

                {/* Inline edit panel */}
                {isEditing && (
                  <div style={{ marginTop: 10, padding: '10px 12px', background: 'var(--muted)', borderRadius: 7, display: 'flex', gap: 8, alignItems: 'center' }}>
                    <span style={{ fontSize: 10, fontWeight: 700 }}>Corrected plate:</span>
                    <input
                      style={{ flex: 1, padding: '6px 10px', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12, fontWeight: 700 }}
                      value={editPlate}
                      onChange={e => setEditPlate(e.target.value.toUpperCase())}
                      placeholder="e.g. TS09AB1234"
                    />
                    <button
                      className="primary-button"
                      style={{ fontSize: 11, padding: '6px 14px' }}
                      disabled={!editPlate.trim() || submitting === item.id}
                      onClick={() => decide(item.id, 'EDITED', editPlate.trim())}
                    >
                      Save
                    </button>
                    <button className="date-button" style={{ fontSize: 11 }} onClick={() => setEditId(null)}>Cancel</button>
                  </div>
                )}

                {/* Confirmed / edited outcome */}
                {item.review_status !== 'PENDING' && item.reviewed_plate && (
                  <div style={{ marginTop: 8, fontSize: 10, color: '#169266' }}>
                    âœ“ Verified plate: <strong>{item.reviewed_plate}</strong>
                    {item.reviewer_notes && <span style={{ color: 'var(--muted-foreground)', marginLeft: 8 }}>{item.reviewer_notes}</span>}
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      <p style={{ fontSize: 9, color: 'var(--muted-foreground)', marginTop: 14 }}>
        Total: {total} items Â· Showing {items.length} Â· Only CONFIRMED/EDITED items are eligible for blacklist matching.
      </p>
    </>
  )
}
