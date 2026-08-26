'use client'
/**
 * CityMapComponent — SIH26127 UrbanEye AI
 * =========================================
 * Real interactive Leaflet map connected to the backend.
 *
 * Data sources (all real backend endpoints — no mock data):
 *   GET /api/cameras              → camera markers (lat/lon from DB)
 *   GET /analytics/traffic-density → traffic density layer
 *   GET /analytics/congestion       → congestion layer
 *   GET /api/trajectory/{plate}     → trajectory polylines
 *   GET /vehicles                   → vehicle list for trajectory picker
 *
 * This file is loaded with next/dynamic { ssr: false } from Pages.tsx
 * because Leaflet uses window/document which are unavailable during SSR.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import {
  MapContainer, TileLayer, Marker, Popup, Polyline,
  useMap, CircleMarker,
} from 'react-leaflet'
import L from 'leaflet'
import {
  Camera, BarChart3, Activity, Navigation2,
  RefreshCw, AlertCircle, Loader2, CheckCircle2,
} from 'lucide-react'
import {
  fetchCameras, fetchTrafficDensity, fetchCongestion,
  fetchVehicles, fetchTrajectory,
  type CameraItem, type TrafficDensityItem, type CongestionItem,
  type TrajectoryResponse, type CameraProcessingResult, ApiError,
} from '@/lib/api'

// ── Leaflet marker icon fix (default icon path breaks in webpack) ─────────────
const _iconCache: Record<string, L.DivIcon> = {}

function makeDotIcon(colour: string): L.DivIcon {
  if (_iconCache[colour]) return _iconCache[colour]
  const icon = L.divIcon({
    className: '',
    html: `<div class="cam-dot" style="background:${colour};width:14px;height:14px;border-radius:50%;border:2.5px solid white;box-shadow:0 1px 5px rgba(0,0,0,.4)"></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
    popupAnchor: [0, -10],
  })
  _iconCache[colour] = icon
  return icon
}

const DENSITY_COLOURS: Record<string, string> = {
  LOW:    '#24ae76',
  MEDIUM: '#eea524',
  HIGH:   '#e07c00',
  SEVERE: '#db5b5d',
}
const CONGESTION_COLOURS = DENSITY_COLOURS
const DEFAULT_CAM_COLOUR = '#08a6d1'

// ── MapBounds — auto-fit to all cameras ──────────────────────────────────────
function AutoFitBounds({ cameras }: { cameras: CameraItem[] }) {
  const map = useMap()
  useEffect(() => {
    if (cameras.length === 0) return
    if (cameras.length === 1) {
      map.setView([cameras[0].latitude, cameras[0].longitude], 14)
      return
    }
    const bounds = L.latLngBounds(cameras.map(c => [c.latitude, c.longitude] as [number, number]))
    map.fitBounds(bounds, { padding: [40, 40] })
  }, [cameras, map])
  return null
}

// ── Layer types ───────────────────────────────────────────────────────────────
type LayerKey = 'cameras' | 'density' | 'congestion' | 'trajectories'

// ── Main component ────────────────────────────────────────────────────────────
export default function CityMapComponent() {
  // Data
  const [cameras,    setCameras]    = useState<CameraItem[]>([])
  const [density,    setDensity]    = useState<TrafficDensityItem[]>([])
  const [congestion, setCongestion] = useState<CongestionItem[]>([])
  const [trajectories, setTrajectories] = useState<TrajectoryResponse[]>([])
  // Per-camera video processing results from localStorage
  const [cameraResults, setCameraResults] = useState<Record<string, CameraProcessingResult>>({})

  // UI state
  const [layers,    setLayers]    = useState<Set<LayerKey>>(new Set(['cameras']))
  const [loading,   setLoading]   = useState(true)
  const [error,     setError]     = useState<string | null>(null)
  const [lastUpdate,setLastUpdate]= useState<string>('')
  const [trajLoading, setTrajLoading] = useState(false)

  // Auto-refresh interval ref
  const refreshRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Load camera processing results from localStorage on mount
  useEffect(() => {
    try {
      const raw = localStorage.getItem('urbaneye_camera_results')
      if (raw) setCameraResults(JSON.parse(raw))
    } catch { /* ignore */ }
    // Re-check every 15 s in case user processes a video in another tab
    const t = setInterval(() => {
      try {
        const raw = localStorage.getItem('urbaneye_camera_results')
        if (raw) setCameraResults(JSON.parse(raw))
      } catch { /* ignore */ }
    }, 15_000)
    return () => clearInterval(t)
  }, [])

  // ── Load cameras ────────────────────────────────────────────────────────────
  const loadCameras = useCallback(async () => {
    try {
      const data = await fetchCameras()
      setCameras(data)
      setError(null)
    } catch (err) {
      const msg = (err instanceof ApiError) ? err.detail : 'Network error'
      setError(`Unable to load camera locations: ${msg}`)
    }
  }, [])

  // ── Load traffic density ────────────────────────────────────────────────────
  const loadDensity = useCallback(async () => {
    try {
      const data = await fetchTrafficDensity(1)
      setDensity(data.items)
    } catch {
      setDensity([])
    }
  }, [])

  // ── Load congestion ─────────────────────────────────────────────────────────
  const loadCongestion = useCallback(async () => {
    try {
      const data = await fetchCongestion(1)
      setCongestion(data.items)
    } catch {
      setCongestion([])
    }
  }, [])

  // ── Load trajectories ───────────────────────────────────────────────────────
  const loadTrajectories = useCallback(async () => {
    setTrajLoading(true)
    try {
      // Get vehicles that have multi-camera detections (camera_count >= 2)
      const vehList = await fetchVehicles(50, 0)
      const multiCam = vehList.vehicles.filter(v => v.camera_count >= 2).slice(0, 8)
      if (multiCam.length === 0) {
        setTrajectories([])
        setTrajLoading(false)
        return
      }
      const trajs = await Promise.allSettled(
        multiCam.map(v => fetchTrajectory(v.plate_number))
      )
      const valid = trajs
        .filter((r): r is PromiseFulfilledResult<TrajectoryResponse> => r.status === 'fulfilled')
        .map(r => r.value)
        .filter(t => t.stops.length >= 2)
      setTrajectories(valid)
    } catch {
      setTrajectories([])
    } finally {
      setTrajLoading(false)
    }
  }, [])

  // ── Initial load + auto-refresh ─────────────────────────────────────────────
  const refreshAll = useCallback(async () => {
    setLoading(true)
    await Promise.all([loadCameras(), loadDensity(), loadCongestion()])
    setLastUpdate(new Date().toLocaleTimeString())
    setLoading(false)
  }, [loadCameras, loadDensity, loadCongestion])

  useEffect(() => {
    refreshAll()
    refreshRef.current = setInterval(refreshAll, 30_000)   // refresh every 30 s
    return () => { if (refreshRef.current) clearInterval(refreshRef.current) }
  }, [refreshAll])

  // Load trajectories when that layer is activated
  useEffect(() => {
    if (layers.has('trajectories') && trajectories.length === 0 && !trajLoading) {
      loadTrajectories()
    }
  }, [layers, trajectories.length, trajLoading, loadTrajectories])

  // ── Layer toggle ─────────────────────────────────────────────────────────────
  const toggleLayer = (key: LayerKey) => {
    setLayers(prev => {
      const next = new Set(prev)
      if (next.has(key)) { next.delete(key) } else { next.add(key) }
      return next
    })
  }

  // ── Build density lookup for camera popups ───────────────────────────────────
  const densityMap = new Map(density.map(d => [d.camera_id, d]))
  const congMap    = new Map(congestion.map(c => [c.camera_id, c]))

  // ── Marker colour for density layer ─────────────────────────────────────────
  const densityColour = (camId: string) => {
    const d = densityMap.get(camId)
    return d ? DENSITY_COLOURS[d.traffic_density] ?? DEFAULT_CAM_COLOUR : DEFAULT_CAM_COLOUR
  }
  const congColour = (camId: string) => {
    const c = congMap.get(camId)
    return c ? CONGESTION_COLOURS[c.congestion_level] ?? DEFAULT_CAM_COLOUR : DEFAULT_CAM_COLOUR
  }

  // ── Trajectory colours by anomaly status ────────────────────────────────────
  const trajColour = (status: string) => {
    if (status === 'IMPOSSIBLE') return '#db5b5d'
    if (status === 'SUSPICIOUS') return '#eea524'
    if (status === 'FAST')       return '#08a6d1'
    return '#24ae76'
  }

  // Centre of Hyderabad — fallback if cameras haven't loaded yet
  const defaultCenter: [number, number] = [17.4065, 78.4772]

  return (
    <div className="city-map-panel" style={{ marginBottom: 0 }}>

      {/* ── Toolbar ──────────────────────────────────────────────────────────── */}
      <div className="city-map-toolbar">
        {([ 
          { key: 'cameras'     as LayerKey, label: 'Cameras',           icon: Camera      },
          { key: 'density'     as LayerKey, label: 'Traffic Density',   icon: BarChart3   },
          { key: 'congestion'  as LayerKey, label: 'Congestion',        icon: Activity    },
          { key: 'trajectories'as LayerKey, label: 'Vehicle Trajectories', icon: Navigation2 },
        ] as const).map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            className={layers.has(key) ? 'active' : ''}
            onClick={() => toggleLayer(key)}
          >
            <Icon size={13} />
            {label}
            {key === 'trajectories' && trajLoading && (
              <Loader2 size={11} style={{ animation: 'spin 1s linear infinite', marginLeft: 2 }} />
            )}
          </button>
        ))}

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
          {loading && <Loader2 size={12} style={{ animation: 'spin 1s linear infinite', color: 'var(--cyan)' }} />}
          <button
            style={{ border: 0, background: 'transparent', color: 'var(--muted-foreground)', cursor: 'pointer', padding: 4 }}
            onClick={refreshAll}
            title="Refresh all layers"
          >
            <RefreshCw size={13} />
          </button>
        </div>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>

      {/* ── Error banner ─────────────────────────────────────────────────────── */}
      {error && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '8px 18px', background: '#fce9e9', color: '#b94040',
          fontSize: 11, borderBottom: '1px solid #f5c0c0',
        }}>
          <AlertCircle size={13} />
          {error}
        </div>
      )}

      {/* ── Map container ────────────────────────────────────────────────────── */}
      <div className="city-map-container">
        <MapContainer
          center={defaultCenter}
          zoom={11}
          scrollWheelZoom
          style={{ height: '100%', width: '100%' }}
          zoomControl
        >
          {/* OpenStreetMap tiles */}
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            maxZoom={19}
          />

          {/* Auto-fit to camera bounds */}
          {cameras.length > 0 && <AutoFitBounds cameras={cameras} />}

          {/* ── LAYER: Cameras ──────────────────────────────────────────────── */}
          {layers.has('cameras') && cameras.map(cam => (
            <Marker
              key={cam.camera_id}
              position={[cam.latitude, cam.longitude]}
              icon={makeDotIcon(
                cameraResults[cam.camera_id]
                  ? DENSITY_COLOURS[cameraResults[cam.camera_id].density_level] ?? DEFAULT_CAM_COLOUR
                  : cam.detections_last_hour > 0 ? '#24ae76' : DEFAULT_CAM_COLOUR
              )}
            >
              <Popup>
                <div style={{ fontFamily: 'Inter, sans-serif', minWidth: 190 }}>
                  <strong style={{ display: 'block', fontSize: 12, marginBottom: 6, color: '#15253a' }}>
                    {cam.camera_id} — {cam.location_name}
                  </strong>
                  {cam.road_name && (
                    <p style={{ fontSize: 10, color: '#6d7f92', margin: '0 0 6px' }}>
                      {cam.road_name}
                    </p>
                  )}

                  {/* Show real processing results if available */}
                  {cameraResults[cam.camera_id] ? (() => {
                    const r = cameraResults[cam.camera_id]
                    return (
                      <>
                        <div style={{ padding: '6px 0', borderTop: '1px solid #edf1f4', marginTop: 4 }}>
                          <span style={{ fontSize: 9, fontWeight: 700, color: '#169266', letterSpacing: '.5px' }}>
                            ✓ VIDEO PROCESSED
                          </span>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 3, fontSize: 10, marginTop: 4 }}>
                          <span style={{ color: '#9aa8b5' }}>Vehicles</span>
                          <strong>{r.total_detections}</strong>
                          <span style={{ color: '#9aa8b5' }}>Verified plates</span>
                          <strong>{r.verified_count}</strong>
                          <span style={{ color: '#9aa8b5' }}>Density</span>
                          <strong style={{ color: DENSITY_COLOURS[r.density_level] ?? '#9aa8b5' }}>
                            {r.density_level.replace('_', ' ')}
                          </strong>
                          {r.vehicles_per_minute !== null && (
                            <>
                              <span style={{ color: '#9aa8b5' }}>Vehicles/min</span>
                              <strong>{r.vehicles_per_minute}</strong>
                            </>
                          )}
                        </div>
                        {r.verified_plates.length > 0 && (
                          <div style={{ marginTop: 6 }}>
                            <span style={{ fontSize: 9, color: '#9aa8b5' }}>Plates: </span>
                            <span style={{ fontSize: 9, color: 'var(--primary)', fontWeight: 700 }}>
                              {r.verified_plates.slice(0, 3).join(', ')}
                              {r.verified_plates.length > 3 ? ` +${r.verified_plates.length - 3}` : ''}
                            </span>
                          </div>
                        )}
                        <p style={{ fontSize: 9, color: '#a0b0c0', margin: '6px 0 0', fontStyle: 'italic' }}>
                          Source: {r.source_file}
                        </p>
                      </>
                    )
                  })() : (
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, fontSize: 10 }}>
                      <span style={{ color: '#9aa8b5' }}>Latitude</span>
                      <span style={{ fontVariantNumeric: 'tabular-nums', color: '#344b60' }}>{cam.latitude.toFixed(4)}</span>
                      <span style={{ color: '#9aa8b5' }}>Longitude</span>
                      <span style={{ fontVariantNumeric: 'tabular-nums', color: '#344b60' }}>{cam.longitude.toFixed(4)}</span>
                      <span style={{ color: '#9aa8b5' }}>Detections/h</span>
                      <span style={{ color: cam.detections_last_hour > 0 ? '#24ae76' : '#9aa8b5', fontWeight: 700 }}>
                        {cam.detections_last_hour}
                      </span>
                      {densityMap.get(cam.camera_id) && (
                        <>
                          <span style={{ color: '#9aa8b5' }}>Density</span>
                          <span style={{ fontWeight: 700, color: DENSITY_COLOURS[densityMap.get(cam.camera_id)!.traffic_density] }}>
                            {densityMap.get(cam.camera_id)!.traffic_density}
                          </span>
                        </>
                      )}
                      <span style={{ color: '#a0b0c0', fontSize: 9, gridColumn: '1/-1', marginTop: 2 }}>
                        No video processed yet
                      </span>
                    </div>
                  )}
                </div>
              </Popup>
            </Marker>
          ))}

          {/* ── LAYER: Traffic Density ──────────────────────────────────────── */}
          {layers.has('density') && density.map(d => (
            <CircleMarker
              key={`dens-${d.camera_id}`}
              center={[d.latitude, d.longitude]}
              radius={Math.max(8, Math.min(32, 8 + d.vehicle_count * 2))}
              pathOptions={{
                color: DENSITY_COLOURS[d.traffic_density] ?? DEFAULT_CAM_COLOUR,
                fillColor: DENSITY_COLOURS[d.traffic_density] ?? DEFAULT_CAM_COLOUR,
                fillOpacity: 0.40,
                weight: 2,
              }}
            >
              <Popup>
                <div style={{ fontFamily: 'Inter, sans-serif', minWidth: 160 }}>
                  <strong style={{ display: 'block', fontSize: 12, marginBottom: 6 }}>
                    Traffic Density — {d.camera_id}
                  </strong>
                  <p style={{ fontSize: 11, margin: '0 0 4px', color: '#344b60' }}>{d.location_name}</p>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, fontSize: 10 }}>
                    <span style={{ color: '#9aa8b5' }}>Vehicles/h</span>
                    <strong>{d.vehicle_count}</strong>
                    <span style={{ color: '#9aa8b5' }}>Density</span>
                    <strong style={{ color: DENSITY_COLOURS[d.traffic_density] }}>{d.traffic_density}</strong>
                  </div>
                  <p style={{ fontSize: 9, color: '#a0b0c0', marginTop: 6, marginBottom: 0 }}>
                    Based on real detection count (last 1 hour)
                  </p>
                </div>
              </Popup>
            </CircleMarker>
          ))}

          {/* ── LAYER: Congestion ───────────────────────────────────────────── */}
          {layers.has('congestion') && congestion.map(c => (
            <CircleMarker
              key={`cong-${c.camera_id}`}
              center={[c.latitude, c.longitude]}
              radius={Math.max(10, Math.min(36, 10 + c.vehicle_count * 2.5))}
              pathOptions={{
                color: CONGESTION_COLOURS[c.congestion_level] ?? DEFAULT_CAM_COLOUR,
                fillColor: CONGESTION_COLOURS[c.congestion_level] ?? DEFAULT_CAM_COLOUR,
                fillOpacity: 0.30,
                weight: 2.5,
                dashArray: '5,3',
              }}
            >
              <Popup>
                <div style={{ fontFamily: 'Inter, sans-serif', minWidth: 170 }}>
                  <strong style={{ display: 'block', fontSize: 12, marginBottom: 6 }}>
                    Congestion — {c.camera_id}
                  </strong>
                  <p style={{ fontSize: 11, margin: '0 0 4px', color: '#344b60' }}>{c.location_name}</p>
                  {c.road_name && <p style={{ fontSize: 10, color: '#9aa8b5', margin: '0 0 6px' }}>{c.road_name}</p>}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, fontSize: 10 }}>
                    <span style={{ color: '#9aa8b5' }}>Level</span>
                    <strong style={{ color: CONGESTION_COLOURS[c.congestion_level] }}>{c.congestion_level}</strong>
                    <span style={{ color: '#9aa8b5' }}>Avg speed</span>
                    <strong>{c.avg_speed_kmh.toFixed(1)} km/h</strong>
                    <span style={{ color: '#9aa8b5' }}>Vehicles/h</span>
                    <strong>{c.vehicle_count}</strong>
                  </div>
                  <p style={{ fontSize: 9, color: '#a0b0c0', marginTop: 6, marginBottom: 0 }}>
                    Congestion formula: avg_speed ≥60→LOW, ≥40→MEDIUM, ≥20→HIGH, &lt;20→SEVERE
                  </p>
                </div>
              </Popup>
            </CircleMarker>
          ))}

          {/* ── LAYER: Vehicle Trajectories ─────────────────────────────────── */}
          {layers.has('trajectories') && trajectories.map(traj => {
            const coords = traj.stops.map(s => [s.latitude, s.longitude] as [number, number])
            const colour = trajColour(traj.overall_status)
            return (
              <Polyline
                key={`traj-${traj.plate_number}`}
                positions={coords}
                pathOptions={{ color: colour, weight: 3, opacity: 0.8 }}
              >
                <Popup>
                  <div style={{ fontFamily: 'Inter, sans-serif', minWidth: 190 }}>
                    <strong style={{ display: 'block', fontSize: 12, marginBottom: 6 }}>
                      Trajectory — {traj.plate_number}
                    </strong>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, fontSize: 10 }}>
                      <span style={{ color: '#9aa8b5' }}>Status</span>
                      <strong style={{ color: colour }}>{traj.overall_status}</strong>
                      <span style={{ color: '#9aa8b5' }}>Cameras</span>
                      <strong>{traj.cameras_visited.length}</strong>
                      <span style={{ color: '#9aa8b5' }}>Distance</span>
                      <strong>{traj.total_distance_km.toFixed(2)} km</strong>
                      <span style={{ color: '#9aa8b5' }}>Duration</span>
                      <strong>{traj.travel_duration_min.toFixed(0)} min</strong>
                      <span style={{ color: '#9aa8b5' }}>Avg speed</span>
                      <strong>{traj.average_speed_kmh.toFixed(1)} km/h</strong>
                    </div>
                    <div style={{ marginTop: 6 }}>
                      {traj.stops.map((s, i) => (
                        <div key={i} style={{ fontSize: 9, color: '#6d7f92', padding: '2px 0', borderBottom: '1px solid #edf1f4' }}>
                          {i + 1}. {s.camera_id} — {s.location}
                          <span style={{ color: '#a0b0c0', marginLeft: 4 }}>
                            {new Date(s.timestamp).toLocaleTimeString()}
                          </span>
                        </div>
                      ))}
                    </div>
                    <p style={{ fontSize: 9, color: '#a0b0c0', marginTop: 6, marginBottom: 0 }}>
                      {traj.data_mode}
                    </p>
                  </div>
                </Popup>
              </Polyline>
            )
          })}
        </MapContainer>
      </div>

      {/* ── Status bar ───────────────────────────────────────────────────────── */}
      <div className="city-map-status">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span
            style={{
              display: 'inline-block', width: 6, height: 6, borderRadius: '50%',
              background: error ? '#db5b5d' : '#24ae76',
            }}
          />
          {error
            ? 'Backend unavailable'
            : `${cameras.length} cameras loaded · Hyderabad, India · OpenStreetMap`}
        </div>
        <div style={{ display: 'flex', align: 'center', gap: 14, flexWrap: 'wrap' }}>
          {/* Legend */}
          {['LOW', 'MEDIUM', 'HIGH', 'SEVERE'].map(lvl => (
            <span key={lvl} style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: DENSITY_COLOURS[lvl], display: 'inline-block' }} />
              {lvl.charAt(0) + lvl.slice(1).toLowerCase()}
            </span>
          ))}
          {lastUpdate && (
            <span style={{ color: '#a0b0c0' }}>Updated {lastUpdate}</span>
          )}
        </div>
      </div>

      {/* No trajectory data message */}
      {layers.has('trajectories') && !trajLoading && trajectories.length === 0 && (
        <div style={{
          padding: '10px 18px', fontSize: 10, color: '#6d7f92',
          background: '#f0f6fb', borderTop: '1px solid var(--border)',
        }}>
          No vehicle trajectories available yet. Process a traffic video with multiple camera sightings to see routes.
        </div>
      )}
    </div>
  )
}
