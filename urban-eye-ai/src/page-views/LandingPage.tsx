'use client'
/**
 * Landing Page — UrbanEye AI
 * Traffic-themed hero + features + pipeline + CTA
 */
import { useNavigate } from 'react-router-dom'
import {
  LocateFixed, Camera, Car, CreditCard, MapPin,
  BarChart3, ShieldAlert, Zap, ChevronRight,
  ArrowRight, Globe, Activity, Eye, Radio,
} from 'lucide-react'

const FEATURES = [
  {
    icon: Camera,
    color: '#08a6d1', bg: '#061e30',
    title: 'Multi-Camera Network',
    desc: 'Monitor 250+ ANPR cameras across the city in real time. Every junction, flyover and arterial road covered.',
  },
  {
    icon: Car,
    color: '#24ae76', bg: '#061e18',
    title: 'AI Vehicle Detection',
    desc: 'YOLOv8-powered detection identifies cars, motorcycles, buses and trucks with 94%+ accuracy at 142 ms latency.',
  },
  {
    icon: CreditCard,
    color: '#eea524', bg: '#1e1606',
    title: 'ANPR & OCR',
    desc: 'Automated Number Plate Recognition extracts and normalises plate text (e.g. ts 08 ab 1234 → TS08AB1234) with confidence scoring.',
  },
  {
    icon: MapPin,
    color: '#7c70d8', bg: '#110e25',
    title: 'Trajectory Reconstruction',
    desc: 'Haversine-based multi-camera trajectory engine tracks every vehicle\'s route, speed and dwell time across the city.',
  },
  {
    icon: BarChart3,
    color: '#08a6d1', bg: '#061e30',
    title: 'Traffic Analytics',
    desc: 'Live congestion scores, density heatmaps, hourly trends and peak-hour forecasting — all from real detections.',
  },
  {
    icon: ShieldAlert,
    color: '#db5b5d', bg: '#200e0e',
    title: 'Alert Engine',
    desc: 'Instant alerts for blacklisted vehicles, suspicious trajectories, abnormal speeds and low-confidence ANPR reads.',
  },
]

const PIPELINE = [
  { icon: Camera,     label: 'Camera\nCapture' },
  { icon: Eye,        label: 'Vehicle\nDetect' },
  { icon: CreditCard, label: 'Plate\nDetect' },
  { icon: Activity,   label: 'OCR &\nNormalise' },
  { icon: MapPin,     label: 'Trajectory\nEngine' },
  { icon: BarChart3,  label: 'Analytics\n& Alerts' },
]

export default function LandingPage() {
  const navigate = useNavigate()

  return (
    <div className="land-shell">
      <div className="land-bg" />
      <div className="land-bg-glow" />
      <div className="land-content">

        {/* ── Top nav ────────────────────────────────────────────────────── */}
        <nav className="land-nav">
          <div className="land-logo">
            <div className="land-logo-mark"><LocateFixed /></div>
            <div className="land-logo-text">
              <strong>Urban<span style={{ color: '#55d1eb' }}>Eye</span></strong>
              <small>AI TRAFFIC INTELLIGENCE</small>
            </div>
          </div>

          <div className="land-nav-links">
            {['Features', 'Pipeline', 'Analytics', 'About'].map(l => (
              <span key={l} className="land-nav-link" style={{ cursor: 'default' }}>{l}</span>
            ))}
          </div>

          <div className="land-nav-cta">
            <button className="land-btn land-btn-ghost" onClick={() => navigate('/login')}>
              Sign In
            </button>
            <button className="land-btn land-btn-primary" onClick={() => navigate('/login')}>
              Launch Dashboard <ChevronRight size={13} />
            </button>
          </div>
        </nav>

        {/* animated road strip */}
        <div className="land-road-strip" />

        {/* ── Hero ───────────────────────────────────────────────────────── */}
        <section className="land-hero">
          <div className="land-badge">
            <span /> LIVE · SIH26127 SMART CITY AI ENGINE
          </div>

          <h1 className="land-h1">
            City-Wide AI Engine for<br />
            <span>Multi-Camera ANPR</span><br />
            Traffic Intelligence
          </h1>

          <p className="land-subtitle">
            Real-time vehicle detection, license plate recognition, trajectory tracking
            and urban traffic analytics — powered by YOLOv8 and EasyOCR across
            an entire city camera network.
          </p>

          <div className="land-hero-actions">
            <button
              className="land-btn land-btn-primary land-btn-xl"
              onClick={() => navigate('/login')}
            >
              <Zap size={16} />
              Open Dashboard
            </button>
            <button
              className="land-btn land-btn-outline-xl"
              onClick={() => navigate('/login')}
            >
              View Live Demo <ArrowRight size={14} />
            </button>
          </div>

          <p className="land-hero-note">
            Demo credentials: <strong style={{ color: '#5592b8' }}>admin / admin123</strong>
            &nbsp;·&nbsp; No real surveillance data is used in this demo.
          </p>

          {/* Stats bar */}
          <div className="land-stats">
            {[
              ['12,847+', 'VEHICLES DETECTED'],
              ['250+',    'CAMERAS MONITORED'],
              ['98.4%',   'DETECTION ACCURACY'],
              ['142 ms',  'AVG PIPELINE LATENCY'],
              ['6',       'ALERT TYPES'],
            ].map(([v, l]) => (
              <div className="land-stat" key={l}>
                <div className="land-stat-value">{v}</div>
                <div className="land-stat-label">{l}</div>
              </div>
            ))}
          </div>
        </section>

        {/* ── Features ───────────────────────────────────────────────────── */}
        <section className="land-section">
          <div className="land-section-title">
            <h2>Everything You Need to Run a Smart City</h2>
            <p>Six integrated modules — from edge camera capture to city-level analytics</p>
          </div>

          <div className="land-features">
            {FEATURES.map(f => (
              <div className="land-feature-card" key={f.title}>
                <div className="land-feature-icon" style={{ background: f.bg, border: `1px solid ${f.color}22` }}>
                  <f.icon color={f.color} />
                </div>
                <h3>{f.title}</h3>
                <p>{f.desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ── Pipeline ───────────────────────────────────────────────────── */}
        <section className="land-section" style={{ paddingTop: 0 }}>
          <div className="land-section-title">
            <h2>End-to-End Processing Pipeline</h2>
            <p>From raw video frame to actionable intelligence in under 200 ms</p>
          </div>

          <div className="land-pipeline">
            {PIPELINE.map((step, i) => (
              <div key={step.label} style={{ display: 'flex', alignItems: 'center' }}>
                <div className="land-pipe-step">
                  <div className="land-pipe-icon" style={{ background: '#0b1e30' }}>
                    <step.icon />
                  </div>
                  <span className="land-pipe-label">
                    {step.label.split('\n').map((l, j) => (
                      <span key={j} style={{ display: 'block' }}>{l}</span>
                    ))}
                  </span>
                </div>
                {i < PIPELINE.length - 1 && (
                  <span className="land-pipe-arrow">›</span>
                )}
              </div>
            ))}
          </div>
        </section>

        {/* ── CTA ────────────────────────────────────────────────────────── */}
        <section className="land-cta">
          <Globe size={36} color="#1a3d5c" style={{ margin: '0 auto 20px', display: 'block' }} />
          <h2>Ready to Monitor Your City?</h2>
          <p>Sign in to the UrbanEye AI command centre and see live traffic intelligence.</p>
          <div style={{ display: 'flex', justifyContent: 'center', gap: 14, flexWrap: 'wrap' }}>
            <button
              className="land-btn land-btn-primary land-btn-xl"
              onClick={() => navigate('/login')}
            >
              <Zap size={16} /> Get Started — It's Free
            </button>
          </div>
          <p style={{ color: '#2a4a64', fontSize: 10, marginTop: 16 }}>
            SIH26127 · Smart India Hackathon 2026 · Demo Environment
          </p>
        </section>

        {/* ── Footer ─────────────────────────────────────────────────────── */}
        <footer className="land-footer">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <LocateFixed size={13} color="#1a4060" />
            <span>UrbanEye AI © 2026 · SIH26127</span>
          </div>
          <div className="land-footer-links">
            {['Demo Only', 'No Real Surveillance Data', 'v0.8.0'].map(l => (
              <span key={l} style={{ color: '#1e3d5c' }}>{l}</span>
            ))}
          </div>
        </footer>

      </div>
    </div>
  )
}
