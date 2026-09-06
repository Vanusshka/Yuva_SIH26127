'use client'
/**
 * Landing Page — UrbanEye AI  ·  SIH26127
 */
import { useNavigate } from 'react-router-dom'
import {
  LocateFixed, Camera, Car, CreditCard, MapPin,
  BarChart3, ShieldAlert, Zap,
} from 'lucide-react'

// ── Traffic Light ──────────────────────────────────────────────────────────
function TrafficLight() {
  return (
    <div style={{ position: 'relative' }}>
      {/* Ambient background glow */}
      <div style={{
        position: 'absolute', inset: '-60px',
        background: 'radial-gradient(ellipse 60% 70% at 65% 50%, #c9a84c18, transparent 70%)',
        pointerEvents: 'none',
      }} />
      {/* Housing */}
      <div style={{
        width: 180,
        background: 'linear-gradient(180deg, #1a1410 0%, #0e0c08 100%)',
        border: '1.5px solid #3a3020',
        borderRadius: 36,
        padding: '32px 28px 20px',
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 20,
        boxShadow: '0 12px 60px #00000099, inset 0 1px 0 #4a3a2030, 0 0 40px #c9a84c08',
        position: 'relative', zIndex: 1,
      }}>
        {/* Red */}
        <div style={{ position: 'relative', width: 110, height: 110 }}>
          <div style={{ position: 'absolute', inset: -20, background: 'radial-gradient(circle, #8b303040 0%, transparent 70%)', borderRadius: '50%' }} />
          <div style={{ width: 110, height: 110, borderRadius: '50%', background: 'radial-gradient(circle at 38% 35%, #7a2828 0%, #3a0c0c 55%, #1a0606 100%)', boxShadow: '0 0 22px #8b303035, inset 0 3px 8px #00000070', border: '1.5px solid #4a1818' }} />
        </div>
        {/* Amber */}
        <div style={{ position: 'relative', width: 110, height: 110 }}>
          <div style={{ position: 'absolute', inset: -28, background: 'radial-gradient(circle, #c9a84c55 0%, #c9a84c20 40%, transparent 70%)', borderRadius: '50%' }} />
          <div style={{ width: 110, height: 110, borderRadius: '50%', background: 'radial-gradient(circle at 38% 35%, #d4a840 0%, #8a6820 50%, #3a2c08 100%)', boxShadow: '0 0 40px #c9a84c60, 0 0 80px #c9a84c20, inset 0 3px 8px #00000050', border: '1.5px solid #6a5018' }} />
        </div>
        {/* Green */}
        <div style={{ position: 'relative', width: 110, height: 110 }}>
          <div style={{ position: 'absolute', inset: -28, background: 'radial-gradient(circle, #22c55e50 0%, #22c55e20 40%, transparent 70%)', borderRadius: '50%' }} />
          <div style={{ width: 110, height: 110, borderRadius: '50%', background: 'radial-gradient(circle at 38% 35%, #3dcc72 0%, #1a8040 50%, #0a3018 100%)', boxShadow: '0 0 40px #22c55e70, 0 0 80px #22c55e25, inset 0 3px 8px #00000050', border: '1.5px solid #1a5028' }} />
        </div>
        {/* Pole */}
        <div style={{ width: 8, height: 36, borderRadius: 4, background: 'linear-gradient(180deg, #2a2010, #120e06)', marginTop: -6 }} />
      </div>
    </div>
  )
}

// ── Feature cards — NO signal labels ──────────────────────────────────────
const FEATURES = [
  {
    icon: Camera,
    color: '#f59e0b', bg: '#261800',
    title: 'Multi-Camera Network',
    desc: 'Monitor 250+ ANPR cameras across the city in real time. Every junction, flyover and arterial road covered.',
  },
  {
    icon: Car,
    color: '#22c55e', bg: '#081a0e',
    title: 'AI Vehicle Detection',
    desc: 'YOLOv8-powered detection identifies cars, motorcycles, buses and trucks with 94%+ accuracy at 142 ms latency.',
  },
  {
    icon: CreditCard,
    color: '#f59e0b', bg: '#261800',
    title: 'ANPR & OCR',
    desc: 'Automated Number Plate Recognition extracts and normalises plate text with confidence scoring.',
  },
  {
    icon: MapPin,
    color: '#f59e0b', bg: '#261800',
    title: 'Trajectory Reconstruction',
    desc: 'Haversine-based multi-camera trajectory engine tracks every vehicle\'s route, speed and dwell time across the city.',
  },
  {
    icon: BarChart3,
    color: '#22c55e', bg: '#081a0e',
    title: 'Traffic Analytics',
    desc: 'Live congestion scores, density heatmaps, hourly trends and peak-hour forecasting — all from real detections.',
  },
  {
    icon: ShieldAlert,
    color: '#ef4444', bg: '#1a0606',
    title: 'Alert Engine',
    desc: 'Instant alerts for blacklisted vehicles, suspicious trajectories, abnormal speeds and low-confidence ANPR reads.',
  },
]

export default function LandingPage() {
  const navigate = useNavigate()

  const goToDashboard = () => navigate('/dashboard')

  return (
    <div style={{
      minHeight: '100vh',
      background: '#1a1208',
      color: '#e8dfc8',
      fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
      overflowX: 'hidden',
    }}>
      <style>{`
        .sh-cta-btn { display: inline-flex; align-items: center; gap: 8px; padding: 12px 24px; border-radius: 50px; border: 1.5px solid #f59e0b; background: transparent; color: #f59e0b; font-size: 13px; font-weight: 600; cursor: pointer; transition: all .2s; }
        .sh-cta-btn:hover { background: #f59e0b; color: #1a1208; }
        .sh-feature-card { background: #221a0e; border: 1px solid #3a2e1e; border-radius: 14px; padding: 28px 24px; transition: border-color .25s, transform .2s; }
        .sh-feature-card:hover { border-color: #f59e0b55; transform: translateY(-2px); }
        @keyframes sh-pulse { 0%,100%{ opacity:1 } 50%{ opacity:.35 } }
      `}</style>

      {/* ── Nav ────────────────────────────────────────────────────────── */}
      <nav style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '20px 56px', borderBottom: '1px solid #2a2010',
        position: 'sticky', top: 0, zIndex: 20,
        background: '#1a1208cc', backdropFilter: 'blur(10px)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 8, height: 8, borderRadius: '50%', background: '#f59e0b',
            boxShadow: '0 0 8px #f59e0b', animation: 'sh-pulse 2s ease-in-out infinite',
          }} />
          <span style={{ fontWeight: 800, fontSize: 17, letterSpacing: '-.3px', color: '#e8dfc8' }}>
            URBAN<span style={{ color: '#f59e0b' }}>EYE</span>
          </span>
          <span style={{ fontSize: 9, color: '#4a3a24', letterSpacing: '1.5px', marginLeft: 4, textTransform: 'uppercase' }}>
            AI Traffic Intelligence
          </span>
        </div>
        <div style={{ flex: 1 }} />
        <button className="sh-cta-btn" onClick={goToDashboard}>
          Launch Dashboard →
        </button>
      </nav>

      {/* ── Hero ───────────────────────────────────────────────────────── */}
      <section style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '80px 56px 70px', minHeight: '80vh', position: 'relative',
      }}>
        {/* Left */}
        <div style={{ maxWidth: 560, flex: '1 1 auto' }}>

          {/* Live badge */}
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 8,
            padding: '7px 16px', borderRadius: 20,
            background: '#221a0e', border: '1px solid #3a2e1e', marginBottom: 32,
          }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#22c55e', boxShadow: '0 0 6px #22c55e', display: 'inline-block', animation: 'sh-pulse 2s ease-in-out infinite' }} />
            <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '1.8px', color: '#6a5a40', textTransform: 'uppercase' }}>
              LIVE · SIH26127 SMART CITY AI ENGINE
            </span>
          </div>

          {/* Main title — from screenshot */}
          <h1 style={{ margin: '0 0 24px', lineHeight: 1.1, letterSpacing: '-1.5px' }}>
            <span style={{ display: 'block', fontSize: 'clamp(36px, 5vw, 64px)', fontWeight: 900, color: '#e8dfc8' }}>
              City-Wide AI Engine for
            </span>
            <span style={{ display: 'block', fontSize: 'clamp(36px, 5vw, 64px)', fontWeight: 900, color: '#f59e0b' }}>
              Multi-Camera ANPR
            </span>
            <span style={{ display: 'block', fontSize: 'clamp(36px, 5vw, 64px)', fontWeight: 900, color: '#e8dfc8' }}>
              Traffic Intelligence
            </span>
          </h1>

          {/* Description — from screenshot */}
          <p style={{ fontSize: 15, color: '#8a7a60', lineHeight: 1.75, margin: '0 0 40px', maxWidth: 480 }}>
            Real-time vehicle detection, license plate recognition, trajectory tracking
            and urban traffic analytics — powered by YOLOv8 and EasyOCR across
            an entire city camera network.
          </p>

          {/* Single CTA */}
          <button
            onClick={goToDashboard}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 8,
              padding: '14px 32px', borderRadius: 50,
              background: '#f59e0b', border: '1.5px solid #f59e0b',
              color: '#120e06', fontWeight: 800, fontSize: 15,
              cursor: 'pointer', transition: 'all .2s',
              boxShadow: '0 0 24px #f59e0b35',
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = '#fbbf24'; (e.currentTarget as HTMLButtonElement).style.boxShadow = '0 0 36px #f59e0b55'; }}
            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = '#f59e0b'; (e.currentTarget as HTMLButtonElement).style.boxShadow = '0 0 24px #f59e0b35'; }}
          >
            <Zap size={16} /> Launch Dashboard
          </button>

          <p style={{ fontSize: 10, color: '#4a3a24', marginTop: 16 }}>
            Demo credentials: <strong style={{ color: '#6a5a40' }}>admin / admin123</strong>
            &nbsp;·&nbsp; No real surveillance data is used in this demo.
          </p>
        </div>

        {/* Right: Traffic light */}
        <div style={{ flex: '0 0 auto', display: 'flex', justifyContent: 'center', alignItems: 'center', paddingLeft: 60 }}>
          <TrafficLight />
        </div>
      </section>

      {/* Divider */}
      <div style={{ height: 1, background: 'linear-gradient(90deg, transparent, #3a2e1e, transparent)', margin: '0 56px' }} />

      {/* ── Features ───────────────────────────────────────────────────── */}
      <section style={{ padding: '80px 56px' }}>
        {/* Section header — clean, no "Three signals" */}
        <div style={{ marginBottom: 52 }}>
          <p style={{ fontSize: 10, color: '#6a5a40', fontWeight: 700, letterSpacing: '2px', textTransform: 'uppercase', margin: '0 0 14px' }}>
            PLATFORM CAPABILITIES
          </p>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 40, flexWrap: 'wrap' }}>
            <h2 style={{ margin: 0, fontSize: 'clamp(26px, 3vw, 38px)', fontWeight: 800, letterSpacing: '-1px', color: '#e8dfc8', maxWidth: 480 }}>
              Everything you need to run a smart city
            </h2>
            <p style={{ margin: 0, fontSize: 13, color: '#6a5a40', maxWidth: 300, lineHeight: 1.7 }}>
              Six integrated modules — from edge camera capture to city-level analytics and real-time alerts.
            </p>
          </div>
        </div>

        {/* Feature cards — NO STOP/SLOW/GO labels */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 18 }}>
          {FEATURES.map(f => (
            <div className="sh-feature-card" key={f.title}>
              {/* Icon */}
              <div style={{
                width: 38, height: 38, borderRadius: 9,
                background: f.bg, border: `1px solid ${f.color}30`,
                display: 'grid', placeItems: 'center', marginBottom: 16,
              }}>
                <f.icon size={18} color={f.color} />
              </div>
              <h3 style={{ margin: '0 0 10px', fontSize: 18, fontWeight: 800, letterSpacing: '-.3px', color: '#d8c8a0' }}>
                {f.title}
              </h3>
              <p style={{ margin: 0, fontSize: 12, color: '#6a5a40', lineHeight: 1.7 }}>
                {f.desc}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Divider */}
      <div style={{ height: 1, background: 'linear-gradient(90deg, transparent, #3a2e1e, transparent)', margin: '0 56px' }} />

      {/* ── Stats bar ──────────────────────────────────────────────────── */}
      <section style={{ padding: '60px 56px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 1, border: '1px solid #3a2e1e', borderRadius: 12, background: '#3a2e1e', overflow: 'hidden' }}>
          {[
            ['12,847+', 'VEHICLES DETECTED'],
            ['250+',    'CAMERAS MONITORED'],
            ['98.4%',   'DETECTION ACCURACY'],
            ['142 ms',  'AVG PIPELINE LATENCY'],
            ['6',       'ALERT TYPES'],
          ].map(([v, l]) => (
            <div key={l} style={{ background: '#1a1208', padding: '28px 24px', textAlign: 'center' }}>
              <div style={{ fontSize: 28, fontWeight: 800, color: '#f59e0b', letterSpacing: '-1px' }}>{v}</div>
              <div style={{ fontSize: 9, color: '#4a3a24', letterSpacing: '1.2px', marginTop: 6 }}>{l}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Footer ─────────────────────────────────────────────────────── */}
      <footer style={{
        borderTop: '1px solid #2a2010', padding: '24px 56px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        flexWrap: 'wrap', gap: 12,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#22c55e', display: 'inline-block', boxShadow: '0 0 6px #22c55e' }} />
          <span style={{ fontWeight: 800, fontSize: 13, color: '#e8dfc8' }}>
            URBAN<span style={{ color: '#f59e0b' }}>EYE</span>
          </span>
          <span style={{ fontSize: 10, color: '#4a3a24', marginLeft: 4 }}>AI Traffic Intelligence · SIH26127</span>
        </div>
        <p style={{ margin: 0, fontSize: 11, color: '#3a2e20' }}>
          Smart India Hackathon 2026 · Demo Environment · No real surveillance data
        </p>
        <button
          onClick={goToDashboard}
          style={{ background: 'transparent', border: '1px solid #3a2e1e', borderRadius: 6, padding: '7px 16px', color: '#6a5a40', fontSize: 11, cursor: 'pointer' }}
        >
          Launch Dashboard →
        </button>
      </footer>
    </div>
  )
}
