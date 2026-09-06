'use client'
/**
 * Trajectory Explorer — SIH26127 UrbanEye AI
 * ============================================
 * Demonstrates multi-camera vehicle trajectory reconstruction
 * using a built-in demo dataset.
 *
 * Data source: GET /trajectory-explorer/vehicles
 *              GET /trajectory-explorer/{vehicle_id}
 *
 * ⚠ DEMO / SAMPLE DATA — Not from real CCTV cameras.
 */

import { useState, useEffect, useCallback } from 'react'
import dynamic from 'next/dynamic'
import {
  Search, MapPin, Clock, Car, CreditCard, BarChart3,
  AlertCircle, Loader2, Download, ChevronRight, Shield,
  Navigation2, FileText,
} from 'lucide-react'
import { ApiError } from '@/lib/api'

// Leaflet map — SSR-safe dynamic import
const TrajectoryMap = dynamic(
  () => import('@/src/components/TrajectoryMap'),
  { ssr: false, loading: () => <div style={{ height: 340, background: 'var(--muted)', borderRadius: 8, display: 'grid', placeItems: 'center', color: 'var(--muted-foreground)', fontSize: 12 }}>Loading map...</div> }
)

// ── types ─────────────────────────────────────────────────────────────────────
interface DemoObservation {
  obs_id: number
  camera_id: string
  location_name: string
  area: string
  road_name: string
  latitude: number
  longitude: number
  timestamp: string
  confidence: number
  direction: string
}

interface DemoVehicleSummary {
  vehicle_id: string
  plate_number: string
  vehicle_type: string
  make_model: string
  total_obs: number
  first_seen: string
  last_seen: string
  cameras: string[]
  data_source: string
  notes: string
}

interface DemoVehicle {
  vehicle_id: string
  plate_number: string
  vehicle_type: string
  make_model: string
  data_source: string
  disclaimer: string
  observations: DemoObservation[]
  hops: {
    from_location: string
    to_location: string
    distance_km: number
    duration_min: number
    speed_kmh: number
  }[]
  summary: {
    total_observations: number
    total_cameras: number
    total_distance_km: number
    total_duration_min: number
    first_seen: string
    last_seen: string
    first_location: string
    last_location: string
    first_area: string
    last_area: string
  }
}

// ── helpers ───────────────────────────────────────────────────────────────────
const BASE = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') || 'http://localhost:8000'

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new ApiError(res.status, `HTTP ${res.status}`, path)
  return res.json()
}

function fmtTime(iso: string) {
  try {
    const d = new Date(iso)
    return { date: d.toLocaleDateString('en-IN'), time: d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) }
  } catch { return { date: '—', time: '—' } }
}

function fmtDuration(mins: number) {
  if (mins < 60) return `${Math.round(mins)} min`
  return `${Math.floor(mins/60)}h ${Math.round(mins%60)}m`
}

// ── Report Generator ──────────────────────────────────────────────────────────
function generateReport(v: DemoVehicle) {
  const now = new Date()
  const obs = v.observations

  const rows = obs.map((o, i) => {
    const { date, time } = fmtTime(o.timestamp)
    return `      <tr>
        <td>${i+1}</td>
        <td>${o.area}</td>
        <td>${o.location_name}<br><small style="color:#666">${o.camera_id}</small></td>
        <td>${date}</td>
        <td>${time}</td>
        <td>${(o.confidence*100).toFixed(1)}%</td>
      </tr>`
  }).join('\n')

  const movement = obs.map((o, i) => {
    const { time } = fmtTime(o.timestamp)
    if (i === 0) return `Vehicle <strong>${v.plate_number}</strong> was first spotted at <strong>${o.area} — ${o.location_name}</strong> at <strong>${time}</strong>`
    if (i === obs.length - 1) return `and finally detected at <strong>${o.area} — ${o.location_name}</strong> at <strong>${time}</strong>`
    return `then detected at <strong>${o.area} — ${o.location_name}</strong> at <strong>${time}</strong>`
  }).join(', ')

  const firstObs = fmtTime(v.summary.first_seen)
  const lastObs  = fmtTime(v.summary.last_seen)

  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Trajectory Report — ${v.plate_number}</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Segoe UI', Arial, sans-serif; color: #1a2636; background: #fff; padding: 40px; }
    .header { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 3px solid #0c7f9d; padding-bottom: 18px; margin-bottom: 28px; }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand-icon { width: 44px; height: 44px; border-radius: 10px; background: linear-gradient(135deg, #0c7f9d, #05c5ef); display: grid; place-items: center; color: white; font-weight: 900; font-size: 18px; }
    .brand h1 { font-size: 22px; color: #0c7f9d; letter-spacing: -0.5px; }
    .brand p { font-size: 10px; color: #8a9ab0; letter-spacing: 1.2px; margin-top: 2px; }
    .meta { text-align: right; font-size: 11px; color: #6d7f92; }
    .meta strong { display: block; font-size: 13px; color: #344b60; }
    .demo-badge { display: inline-block; padding: 3px 10px; background: #fff3dd; color: #c28118; border: 1px solid #f8d38b; border-radius: 12px; font-size: 9px; font-weight: 700; letter-spacing: .8px; margin-bottom: 20px; }
    .vehicle-card { background: linear-gradient(135deg, #f0f8ff, #e8f4fb); border: 1px solid #c8e0ef; border-radius: 10px; padding: 20px 24px; margin-bottom: 24px; display: flex; justify-content: space-between; align-items: flex-start; }
    .vehicle-card h2 { font-size: 28px; letter-spacing: -1px; color: #0c7f9d; }
    .vehicle-card .vid { font-size: 13px; color: #6d7f92; margin-top: 4px; }
    .vehicle-card .type { font-size: 12px; color: #5a7a90; margin-top: 2px; }
    .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 24px; }
    .stat { background: #f6f9fb; border: 1px solid #dde5ec; border-radius: 8px; padding: 14px 16px; }
    .stat .label { font-size: 9px; color: #8a9ab0; letter-spacing: .8px; font-weight: 700; margin-bottom: 6px; }
    .stat .value { font-size: 18px; font-weight: 800; color: #15253a; letter-spacing: -0.5px; }
    .stat .sub { font-size: 10px; color: #8a9ab0; margin-top: 3px; }
    h3 { font-size: 14px; color: #15253a; margin-bottom: 12px; padding-bottom: 6px; border-bottom: 1px solid #dde5ec; }
    table { width: 100%; border-collapse: collapse; margin-bottom: 24px; font-size: 12px; }
    th { background: #0c7f9d; color: white; padding: 10px 12px; text-align: left; font-size: 10px; letter-spacing: .5px; }
    td { padding: 10px 12px; border-bottom: 1px solid #edf1f4; color: #344b60; }
    tr:last-child td { border-bottom: none; }
    tr:nth-child(even) td { background: #f8fbfd; }
    .conf-high { color: #169266; font-weight: 700; }
    .conf-med  { color: #c28118; font-weight: 700; }
    .movement-summary { background: #f6f9fb; border-left: 4px solid #0c7f9d; padding: 16px 20px; border-radius: 0 8px 8px 0; margin-bottom: 24px; font-size: 13px; line-height: 1.7; color: #344b60; }
    .footer { margin-top: 32px; padding-top: 16px; border-top: 1px solid #dde5ec; font-size: 10px; color: #9aa8b5; display: flex; justify-content: space-between; }
    .disclaimer { background: #fff8ee; border: 1px solid #f8d38b; border-radius: 6px; padding: 10px 14px; font-size: 10px; color: #c28118; margin-bottom: 24px; }
    @media print { body { padding: 20px; } }
  </style>
</head>
<body>
  <div class="header">
    <div class="brand">
      <div class="brand-icon">UE</div>
      <div>
        <h1>UrbanEye AI</h1>
        <p>CITY-WIDE ANPR TRAJECTORY SYSTEM · SIH26127</p>
      </div>
    </div>
    <div class="meta">
      <strong>Vehicle Trajectory Report</strong>
      Generated: ${now.toLocaleDateString('en-IN')} at ${now.toLocaleTimeString('en-IN')}
    </div>
  </div>

  <div class="demo-badge">⚠ DEMO / SAMPLE DATA — NOT FROM REAL CCTV CAMERAS</div>

  <div class="disclaimer">
    ${v.disclaimer}
  </div>

  <div class="vehicle-card">
    <div>
      <h2>${v.plate_number}</h2>
      <div class="vid">Vehicle ID: ${v.vehicle_id}</div>
      <div class="type">${v.vehicle_type} — ${v.make_model}</div>
    </div>
    <div style="text-align:right">
      <div style="font-size:11px;color:#6d7f92">First spotted</div>
      <div style="font-size:13px;font-weight:700;color:#344b60">${firstObs.date} ${firstObs.time}</div>
      <div style="font-size:11px;color:#6d7f92;margin-top:8px">Last spotted</div>
      <div style="font-size:13px;font-weight:700;color:#344b60">${lastObs.date} ${lastObs.time}</div>
    </div>
  </div>

  <div class="stats">
    <div class="stat">
      <div class="label">TOTAL OBSERVATIONS</div>
      <div class="value">${v.summary.total_observations}</div>
      <div class="sub">camera sightings</div>
    </div>
    <div class="stat">
      <div class="label">CAMERAS VISITED</div>
      <div class="value">${v.summary.total_cameras}</div>
      <div class="sub">distinct locations</div>
    </div>
    <div class="stat">
      <div class="label">TOTAL DISTANCE</div>
      <div class="value">${v.summary.total_distance_km} km</div>
      <div class="sub">estimated route</div>
    </div>
    <div class="stat">
      <div class="label">TOTAL DURATION</div>
      <div class="value">${fmtDuration(v.summary.total_duration_min)}</div>
      <div class="sub">first to last sighting</div>
    </div>
  </div>

  <h3>Chronological Movement Summary</h3>
  <div class="movement-summary">${movement}.</div>

  <h3>Observation Timeline</h3>
  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>Area / Location</th>
        <th>Camera</th>
        <th>Date</th>
        <th>Time</th>
        <th>Confidence</th>
      </tr>
    </thead>
    <tbody>
${rows}
    </tbody>
  </table>

  <h3>Route Details</h3>
  <table>
    <thead><tr><th>Hop</th><th>From</th><th>To</th><th>Distance</th><th>Duration</th><th>Est. Speed</th></tr></thead>
    <tbody>
      ${v.hops.map((h,i) => `
      <tr>
        <td>${i+1}</td>
        <td>${h.from_location}</td>
        <td>${h.to_location}</td>
        <td>${h.distance_km} km</td>
        <td>${fmtDuration(h.duration_min)}</td>
        <td>${h.speed_kmh} km/h</td>
      </tr>`).join('')}
    </tbody>
  </table>

  <div class="footer">
    <span>UrbanEye AI — SIH26127 Smart City Intelligence Platform</span>
    <span>Report ID: RPT-${Date.now().toString(36).toUpperCase()}</span>
    <span>Confidential — For authorised use only</span>
  </div>
</body>
</html>`

  const blob = new Blob([html], { type: 'text/html' })
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement('a')
  a.href     = url
  a.download = `Trajectory_Report_${v.plate_number}_${now.toISOString().split('T')[0]}.html`
  a.click()
  URL.revokeObjectURL(url)
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function TrajectoryExplorer() {
  const [vehicles, setVehicles]   = useState<DemoVehicleSummary[]>([])
  const [selected, setSelected]   = useState<DemoVehicle | null>(null)
  const [query,    setQuery]      = useState('')
  const [loading,  setLoading]    = useState(true)
  const [detLoading, setDetLoading] = useState(false)
  const [error,    setError]      = useState<string | null>(null)

  // Load vehicle list
  useEffect(() => {
    apiFetch<any>('/trajectory-explorer/vehicles')
      .then(d => { setVehicles(d.vehicles); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const selectVehicle = useCallback(async (id: string) => {
    setDetLoading(true)
    setError(null)
    try {
      const data = await apiFetch<DemoVehicle>(`/trajectory-explorer/${encodeURIComponent(id)}`)
      setSelected(data)
    } catch {
      setError('Could not load vehicle data.')
    } finally {
      setDetLoading(false)
    }
  }, [])

  const filteredVehicles = vehicles.filter(v =>
    !query ||
    v.plate_number.toLowerCase().includes(query.toLowerCase()) ||
    v.vehicle_id.toLowerCase().includes(query.toLowerCase()) ||
    v.vehicle_type.toLowerCase().includes(query.toLowerCase())
  )

  const obs = selected?.observations ?? []

  return (
    <div style={{ maxWidth: 1400, margin: '0 auto' }}>

      {/* ── Demo data banner ─────────────────────────────────────────────── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '10px 16px', background: '#1a1200',
        border: '1px solid #f8d38b', borderRadius: 8, marginBottom: 20,
        fontSize: 11, color: '#c28118',
      }}>
        <Shield size={14} style={{ flexShrink: 0 }} />
        <span>
          <strong>DEMO DATASET</strong> — This feature uses built-in sample observations to demonstrate
          multi-camera vehicle trajectory reconstruction. Data is NOT from real CCTV cameras.
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: 17 }}>

        {/* ── Vehicle selector ───────────────────────────────────────────── */}
        <div>
          <div className="panel">
            <div className="panel-header">
              <div>
                <h2>🧪 Test Cases</h2>
                <p>10 vehicles · 6 cameras · 2026-09-05</p>
              </div>
            </div>
            <div style={{ padding: '10px 14px 6px', borderBottom: '1px solid var(--border)', marginBottom: 6 }}>
              <p style={{ fontSize: 9, color: 'var(--muted-foreground)', margin: 0, lineHeight: 1.5 }}>
                Source: <code style={{ fontSize: 8, background: 'var(--muted)', padding: '1px 4px', borderRadius: 3 }}>urbaneye-synthetic-trajectory-demo.csv</code>
              </p>
            </div>
            <div style={{ padding: '6px 14px 12px' }}>
              <div className="table-search" style={{ width: '100%', marginBottom: 10 }}>
                <Search size={13} />
                <input
                  placeholder="Search plate, vehicle ID or type…"
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                />
              </div>
              {loading && <div style={{ fontSize: 11, color: 'var(--muted-foreground)', padding: '8px 0' }}>Loading…</div>}
              {filteredVehicles.map((v, idx) => (
                <div
                  key={v.vehicle_id}
                  onClick={() => selectVehicle(v.vehicle_id)}
                  style={{
                    padding: '10px 12px', borderRadius: 7, cursor: 'pointer', marginBottom: 5,
                    background: selected?.vehicle_id === v.vehicle_id ? 'var(--muted)' : 'transparent',
                    border: `1px solid ${selected?.vehicle_id === v.vehicle_id ? 'var(--primary)' : 'var(--border)'}`,
                    transition: 'all .15s',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{
                        fontSize: 8, fontWeight: 800, padding: '1px 5px', borderRadius: 3,
                        background: 'var(--muted)', color: 'var(--muted-foreground)',
                        letterSpacing: '.5px',
                      }}>{v.vehicle_id}</span>
                      <strong style={{ fontSize: 12, color: 'var(--primary)', fontFamily: 'Courier New, monospace' }}>
                        {v.plate_number}
                      </strong>
                    </div>
                    <span style={{ fontSize: 9, color: 'var(--muted-foreground)' }}>
                      {v.total_obs} cams
                    </span>
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--muted-foreground)', marginTop: 3, display: 'flex', gap: 6 }}>
                    <span>🚗 {v.vehicle_type}</span>
                    <span style={{ color: 'var(--border)' }}>·</span>
                    <span>{v.cameras.join(' → ')}</span>
                  </div>
                </div>
              ))}
              {filteredVehicles.length === 0 && !loading && (
                <p style={{ fontSize: 11, color: 'var(--muted-foreground)', padding: '8px 0' }}>
                  No vehicles match "{query}"
                </p>
              )}
            </div>
          </div>
        </div>

        {/* ── Main panel ─────────────────────────────────────────────────── */}
        <div>
          {detLoading && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '20px 0', color: 'var(--muted-foreground)', fontSize: 12 }}>
              <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} />
              Loading trajectory…
              <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
            </div>
          )}
          {error && (
            <div style={{ padding: '12px 14px', background: '#1a0508', color: '#b94040', borderRadius: 7, fontSize: 11, marginBottom: 14 }}>
              <AlertCircle size={13} style={{ marginRight: 6 }} />{error}
            </div>
          )}

          {!selected && !detLoading && (
            <div className="panel" style={{ padding: '40px', textAlign: 'center', color: 'var(--muted-foreground)' }}>
              <Navigation2 size={36} style={{ margin: '0 auto 14px', display: 'block', opacity: .3 }} />
              <p style={{ fontSize: 13 }}>Select a demo vehicle from the list to explore its trajectory</p>
            </div>
          )}

          {selected && !detLoading && (
            <>
              {/* Header */}
              <div className="panel" style={{ marginBottom: 17 }}>
                <div style={{ padding: '16px 20px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <h2 style={{ fontSize: 22, letterSpacing: '-.5px', color: 'var(--primary)' }}>{selected.plate_number}</h2>
                    <p style={{ fontSize: 12, color: 'var(--muted-foreground)', margin: '3px 0' }}>
                      {selected.vehicle_id} · {selected.vehicle_type} · {selected.make_model}
                    </p>
                    <span style={{ fontSize: 9, fontWeight: 700, padding: '2px 8px', borderRadius: 10, background: '#1a1000', color: '#c28118', border: '1px solid #f8d38b' }}>
                      DEMO DATASET
                    </span>
                  </div>
                  <button
                    className="primary-button"
                    style={{ fontSize: 11, padding: '8px 16px' }}
                    onClick={() => generateReport(selected)}
                  >
                    <Download size={13} /> Generate Report
                  </button>
                </div>

                {/* KPI row */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 0, borderTop: '1px solid var(--border)' }}>
                  {[
                    ['Observations', String(selected.summary.total_observations), 'camera sightings'],
                    ['Cameras',      String(selected.summary.total_cameras),      'distinct locations'],
                    ['Distance',     `${selected.summary.total_distance_km} km`,  'estimated route'],
                    ['Duration',     fmtDuration(selected.summary.total_duration_min), 'first to last'],
                  ].map(([label, value, sub], i) => (
                    <div key={label} style={{ padding: '14px 18px', borderRight: i < 3 ? '1px solid var(--border)' : 'none' }}>
                      <span className="kpi-label">{label}</span>
                      <strong style={{ display: 'block', fontSize: 18, marginTop: 4, letterSpacing: '-.3px' }}>{value}</strong>
                      <span style={{ fontSize: 10, color: 'var(--muted-foreground)' }}>{sub}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Map */}
              <div className="panel" style={{ marginBottom: 17 }}>
                <div className="panel-header">
                  <div><h2>Trajectory Map</h2><p>Route visualisation — demo data</p></div>
                </div>
                <div style={{ padding: '0 18px 18px' }}>
                  <TrajectoryMap observations={obs} />
                </div>
              </div>

              {/* Timeline */}
              <div className="panel">
                <div className="panel-header">
                  <div><h2>Observation Timeline</h2><p>Chronological sightings across camera network</p></div>
                </div>
                <div style={{ padding: '0 18px 18px' }}>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>#</th>
                          <th>AREA / LOCATION</th>
                          <th>CAMERA</th>
                          <th>DATE</th>
                          <th>TIME</th>
                          <th>CONFIDENCE</th>
                        </tr>
                      </thead>
                      <tbody>
                        {obs.map((o, i) => {
                          const { date, time } = fmtTime(o.timestamp)
                          const isLast = i === obs.length - 1
                          return (
                            <tr key={o.obs_id}>
                              <td>
                                <span style={{
                                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                                  width: 22, height: 22, borderRadius: '50%', background: 'var(--primary)',
                                  color: 'white', fontSize: 10, fontWeight: 700,
                                }}>{o.obs_id}</span>
                              </td>
                              <td>
                                <div className="plate">
                                  <div className="plate-mark" />
                                  {o.area}
                                </div>
                                <div style={{ fontSize: 10, color: 'var(--muted-foreground)', marginTop: 2 }}>{o.location_name}</div>
                              </td>
                              <td>
                                <span style={{ fontSize: 10, fontWeight: 700 }}>{o.camera_id}</span>
                                <div style={{ fontSize: 9, color: 'var(--muted-foreground)' }}>{o.road_name}</div>
                              </td>
                              <td style={{ fontSize: 11 }}>{date}</td>
                              <td>
                                <span style={{ fontVariantNumeric: 'tabular-nums', fontSize: 11, fontWeight: 600, color: '#0c7f9d' }}>{time}</span>
                              </td>
                              <td>
                                <span className={`confidence`} style={{ color: o.confidence >= 0.85 ? '#169266' : o.confidence >= 0.70 ? '#c28118' : '#b94040' }}>
                                  {(o.confidence * 100).toFixed(1)}%
                                </span>
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>

                  {/* Movement summary */}
                  <div style={{
                    marginTop: 16, padding: '12px 16px',
                    background: 'var(--muted)', borderLeft: '4px solid var(--primary)',
                    borderRadius: '0 7px 7px 0', fontSize: 12, color: '#b0cce0', lineHeight: 1.7,
                  }}>
                    <strong>Movement Summary:</strong>{' '}
                    {obs.map((o, i) => {
                      const { time } = fmtTime(o.timestamp)
                      if (i === 0) return `Vehicle ${selected.plate_number} was first spotted at ${o.area} (${o.location_name}) at ${time}`
                      if (i === obs.length - 1) return `, and finally detected at ${o.area} (${o.location_name}) at ${time}.`
                      return `, then detected at ${o.area} (${o.location_name}) at ${time}`
                    }).join('')}
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
