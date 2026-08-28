'use client'
/**
 * SIH26127 UrbanEye AI — Root page
 *
 * This file is a Next.js App Router page that hosts the entire React Router SPA.
 *
 * SSR fix: we render nothing on the server (return null until mounted).
 * This eliminates the hydration mismatch caused by:
 *   - BrowserRouter vs MemoryRouter switching
 *   - sessionStorage auth check being unavailable on server
 *   - Route-dependent className differences between SSR and client
 */

import { useEffect, useState } from 'react'
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  useNavigate,
  useLocation,
} from 'react-router-dom'

import LandingPage from '@/src/page-views/LandingPage'
import LoginPage   from '@/src/page-views/LoginPage'
import { AppLayout } from '@/src/components/layout/AppLayout'
import {
  Overview, VehicleSearch, CameraNetwork, TrafficAnalytics,
  CityMap, Alerts, BlacklistMonitoring, SystemHealth, ManualReviewPage,
} from '@/src/route-pages/Pages'
import VideoUpload from '@/src/components/VideoUpload'
import { isAuthenticated } from '@/src/auth'

// ─────────────────────────────────────────────────────────────────────────────
// Page frame wrapper
// ─────────────────────────────────────────────────────────────────────────────
function PageFrame({ children }: { children: React.ReactNode }) {
  const today = new Date().toLocaleDateString('en-GB', { day:'numeric', month:'short', year:'numeric' })
  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'
  return (
    <div className="page-heading">
      <div><h1>{typeof children === 'string' && children === 'Good morning, Admin'
        ? `${greeting}, Admin` : children}</h1></div>
      <div className="heading-actions">
        <button className="date-button">{today}</button>
        <button className="primary-button">Generate Report</button>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Auth guard — client-only, no SSR
// ─────────────────────────────────────────────────────────────────────────────
function RequireAuth({ children }: { children: React.ReactNode }) {
  // This component only ever runs after the client has hydrated (see root gate),
  // so sessionStorage is always available here — no SSR mismatch possible.
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}

// ─────────────────────────────────────────────────────────────────────────────
// Route tree
// ─────────────────────────────────────────────────────────────────────────────
function AppRoutes() {
  return (
    <Routes>
      {/* ── Public ── */}
      <Route path="/"      element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />

      {/* ── Protected dashboard ── */}
      <Route
        path="/dashboard"
        element={<RequireAuth><AppLayout /></RequireAuth>}
      >
        <Route index                    element={<><PageFrame>Good morning, Admin</PageFrame><Overview /></>} />
        <Route path="vehicle-search"    element={<><PageFrame>Vehicle Search</PageFrame><VehicleSearch /></>} />
        <Route path="upload-video"      element={<><PageFrame>Upload &amp; Process Video</PageFrame><VideoUpload /></>} />
        <Route path="cameras"           element={<><PageFrame>Live Camera Network</PageFrame><CameraNetwork /></>} />
        <Route path="traffic-analytics" element={<><PageFrame>Traffic Analytics</PageFrame><TrafficAnalytics /></>} />
        <Route path="city-map"          element={<><PageFrame>City Traffic Map</PageFrame><CityMap /></>} />
        <Route path="alerts"            element={<><PageFrame>Alerts</PageFrame><Alerts /></>} />
        <Route path="blacklist"         element={<><PageFrame>Blacklist Monitoring</PageFrame><BlacklistMonitoring /></>} />
        <Route path="system-health"     element={<><PageFrame>System Health</PageFrame><SystemHealth /></>} />
        <Route path="manual-review"     element={<><PageFrame>Manual Review Queue</PageFrame><ManualReviewPage /></>} />
      </Route>

      {/* ── Legacy redirect shims ── */}
      {[
        ['vehicle-search',    'vehicle-search'],
        ['cameras',           'cameras'],
        ['traffic-analytics', 'traffic-analytics'],
        ['city-map',          'city-map'],
        ['alerts',            'alerts'],
        ['blacklist',         'blacklist'],
        ['system-health',     'system-health'],
        ['upload-video',      'upload-video'],
        ['manual-review',     'manual-review'],
      ].map(([from, to]) => (
        <Route
          key={from}
          path={`/${from}`}
          element={<Navigate to={`/dashboard/${to}`} replace />}
        />
      ))}

      {/* ── 404 ── */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Root — SSR gate
// Render null on the server; mount the full SPA only after client hydration.
// This is the canonical fix for React Router + Next.js App Router hydration
// mismatches caused by window/sessionStorage being unavailable on the server.
// ─────────────────────────────────────────────────────────────────────────────
export default function Page() {
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  // During SSR and first render on the client we output a minimal shell
  // that matches exactly on both sides — no className mismatch possible.
  if (!mounted) {
    return (
      <div
        style={{
          minHeight: '100vh',
          background: '#060d18',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {/* Intentionally empty — content loads after hydration */}
      </div>
    )
  }

  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  )
}
