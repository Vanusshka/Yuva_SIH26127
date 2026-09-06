'use client'
/**
 * TrajectoryMap — renders numbered markers + polyline for trajectory explorer.
 * Loaded via next/dynamic (ssr:false) to avoid Leaflet SSR crash.
 */
import { useEffect } from 'react'
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from 'react-leaflet'
import L from 'leaflet'

interface Obs {
  obs_id: number
  camera_id: string
  location_name: string
  area: string
  latitude: number
  longitude: number
  timestamp: string
  confidence: number
}

function NumberedIcon(n: number) {
  return L.divIcon({
    className: '',
    html: `<div style="width:26px;height:26px;border-radius:50%;background:#0c7f9d;color:white;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;border:2px solid white;box-shadow:0 2px 6px rgba(0,0,0,.4)">${n}</div>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
    popupAnchor: [0, -16],
  })
}

function FitBounds({ positions }: { positions: [number, number][] }) {
  const map = useMap()
  useEffect(() => {
    if (positions.length >= 2) {
      map.fitBounds(L.latLngBounds(positions), { padding: [40, 40] })
    } else if (positions.length === 1) {
      map.setView(positions[0], 14)
    }
  }, [positions, map])
  return null
}

export default function TrajectoryMap({ observations }: { observations: Obs[] }) {
  if (!observations.length) return null

  const positions: [number, number][] = observations.map(o => [o.latitude, o.longitude])
  const centre: [number, number] = [17.4065, 78.4772] // Hyderabad

  return (
    <div style={{ height: 340, borderRadius: 8, overflow: 'hidden' }}>
      <MapContainer center={centre} zoom={11} style={{ height: '100%', width: '100%' }} scrollWheelZoom>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitBounds positions={positions} />
        <Polyline
          positions={positions}
          pathOptions={{ color: '#0c7f9d', weight: 3, opacity: 0.85, dashArray: '8 4' }}
        />
        {observations.map((o, i) => (
          <Marker key={o.obs_id} position={[o.latitude, o.longitude]} icon={NumberedIcon(o.obs_id)}>
            <Popup>
              <div style={{ fontFamily: 'Inter,sans-serif', minWidth: 180 }}>
                <strong style={{ display: 'block', fontSize: 12, marginBottom: 4 }}>
                  Stop {o.obs_id} — {o.location_name}
                </strong>
                <div style={{ fontSize: 10, color: '#6d7f92', lineHeight: 1.6 }}>
                  <div>{o.area}</div>
                  <div>{o.camera_id}</div>
                  <div>{new Date(o.timestamp).toLocaleTimeString('en-IN')}</div>
                  <div>Confidence: {(o.confidence * 100).toFixed(1)}%</div>
                </div>
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  )
}
