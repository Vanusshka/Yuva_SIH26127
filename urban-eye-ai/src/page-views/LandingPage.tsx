'use client'
/**
 * Landing Page — UrbanEye AI
 * Signal House–inspired layout:
 *   warm dark brown · cream · amber-gold · traffic light hero
 */
import { useNavigate } from 'react-router-dom'
import {
  LocateFixed, Camera, Car, CreditCard, MapPin,
  BarChart3, ShieldAlert, Zap, ChevronRight,
  ArrowRight, Globe, Activity, Eye,
} from 'lucide-react'

// ── Traffic Light component — large glowing, matches reference image ────────
function TrafficLight() {
  return (
    <div style={{ position: 'relative' }}>
      {/* Ambient background glow behind the whole signal */}
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
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 20,
        boxShadow: '0 12px 60px #00000099, inset 0 1px 0 #4a3a2030, 0 0 40px #c9a84c08',
        position: 'relative',
        zIndex: 1,
      }}>
        {/* Red — STOP — dim, not active */}
        <div style={{ position: 'relative', width: 110, height: 110 }}>
          {/* soft glow behind */}
          <div style={{
            position: 'absolute', inset: -20,
            background: 'radial-gradient(circle, #8b303040 0%, transparent 70%)',
            borderRadius: '50%',
          }} />
          <div style={{
            width: 110, height: 110, borderRadius: '50%',
            background: 'radial-gradient(circle at 38% 35%, #7a2828 0%, #3a0c0c 55%, #1a0606 100%)',
            boxShadow: '0 0 22px #8b303035, inset 0 3px 8px #00000070, inset -2px -2px 10px #6a202010',
            border: '1.5px solid #4a1818',
          }} />
        </div>

        {/* Amber — SLOW — warm glow, most visible */}
        <div style={{ position: 'relative', width: 110, height: 110 }}>
          {/* large soft ambient glow */}
          <div style={{
            position: 'absolute', inset: -28,
            background: 'radial-gradient(circle, #c9a84c55 0%, #c9a84c20 40%, transparent 70%)',
            borderRadius: '50%',
          }} />
          <div style={{
            width: 110, height: 110, borderRadius: '50%',
            background: 'radial-gradient(circle at 38% 35%, #d4a840 0%, #8a6820 50%, #3a2c08 100%)',
            boxShadow: '0 0 40px #c9a84c60, 0 0 80px #c9a84c20, inset 0 3px 8px #00000050',
            border: '1.5px solid #6a5018',
          }} />
        </div>

        {/* Green — GO — active bright glow */}
        <div style={{ position: 'relative', width: 110, height: 110 }}>
          {/* large soft ambient glow */}
          <div style={{
            position: 'absolute', inset: -28,
            background: 'radial-gradient(circle, #22c55e50 0%, #22c55e20 40%, transparent 70%)',
            borderRadius: '50%',
          }} />
          <div style={{
            width: 110, height: 110, borderRadius: '50%',
            background: 'radial-gradient(circle at 38% 35%, #3dcc72 0%, #1a8040 50%, #0a3018 100%)',
            boxShadow: '0 0 40px #22c55e70, 0 0 80px #22c55e25, inset 0 3px 8px #00000050',
            border: '1.5px solid #1a5028',
          }} />
        </div>

        {/* Pole */}
        <div style={{
          width: 8, height: 36, borderRadius: 4,
          background: 'linear-gradient(180deg, #2a2010, #120e06)',
          marginTop: -6,
        }} />
      </div>
    </div>
  )
}

const FEATURES = [
  {
    icon: Camera,    color: '#c9a84c', bg: '#1e1608',
    title: 'Multi-Camera Network',
    desc: 'Monitor 250+ ANPR cameras across the city in real time. Every junction, flyover and arterial road covered.',
  },
  {
    icon: Car,       color: '#4a9e6a', bg: '#0e1a10',
    title: 'AI Vehicle Detection',
    desc: 'YOLOv8-powered detection identifies cars, motorcycles, buses and trucks with 94%+ accuracy at 142 ms latency.',
  },
  {
    icon: CreditCard,color: '#e8a020', bg: '#1e1408',
    title: 'ANPR & OCR',
    desc: 'Automated Number Plate Recognition extracts and normalises plate text with confidence scoring.',
  },
  {
    icon: MapPin,    color: '#c9a84c', bg: '#1e1608',
    title: 'Trajectory Reconstruction',
    desc: 'Haversine-based multi-camera trajectory engine tracks every vehicle\'s route, speed and dwell time across the city.',
  },
  {
    icon: BarChart3, color: '#4a9e6a', bg: '#0e1a10',
    title: 'Traffic Analytics',
    desc: 'Live congestion scores, density heatmaps, hourly trends and peak-hour forecasting — all from real detections.',
  },
  {
    icon: ShieldAlert,color: '#c04040',bg: '#1a0808',
    title: 'Alert Engine',
    desc: 'Instant alerts for blacklisted vehicles, suspicious trajectories, abnormal speeds and low-confidence ANPR reads.',
  },
]

export default function LandingPage() {
  const navigate = useNavigate()

  return (
    <div style={{
      minHeight: '100vh',
      background: '#1a1208',
      color: '#e8dfc8',
      fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
      overflowX: 'hidden',
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap');
        .sh-nav-link { color: #8a7a60; font-size: 13px; text-decoration: none; cursor: pointer; transition: color .2s; }
        .sh-nav-link:hover { color: #e8dfc8; }
        .sh-cta-btn { display: inline-flex; align-items: center; gap: 8px; padding: 12px 24px; border-radius: 50px; border: 1.5px solid #c9a84c; background: transparent; color: #c9a84c; font-size: 13px; font-weight: 600; cursor: pointer; transition: all .2s; }
        .sh-cta-btn:hover { background: #c9a84c; color: #1a1208; }
        .sh-feature-card { background: #221a0e; border: 1px solid #3a2e1e; border-radius: 14px; padding: 28px 24px; transition: border-color .25s, transform .2s; }
        .sh-feature-card:hover { border-color: #c9a84c55; transform: translateY(-2px); }
        @keyframes sh-pulse { 0%,100%{ opacity:1 } 50%{ opacity:.35 } }
      `}</style>

      {/* ── Nav ──────────────────────────────────────────────────────────── */}
      <nav style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '20px 56px',
        borderBottom: '1px solid #2a2010',
        position: 'sticky', top: 0, zIndex: 20,
        background: '#1a1208cc',
        backdropFilter: 'blur(10px)',
      }}>
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 8, height: 8, borderRadius: '50%',
            background: '#c9a84c',
            boxShadow: '0 0 8px #c9a84c',
            animation: 'sh-pulse 2s ease-in-out infinite',
          }} />
          <span style={{ fontWeight: 800, fontSize: 17, letterSpacing: '-.3px', color: '#e8dfc8' }}>
            URBAN<span style={{ color: '#c9a84c' }}>EYE</span>
          </span>
        </div>

        {/* Nav links — removed per design */}
        <div style={{ flex: 1 }} />

        {/* CTA */}
        <button className="sh-cta-btn" onClick={() => navigate('/login')}>
          Enter the system →
        </button>
      </nav>

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section style={{
        display: 'flex', alignItems: 'center',
        justifyContent: 'space-between',
        padding: '80px 56px 70px',
        minHeight: '80vh',
        position: 'relative',
      }}>
        {/* Left: text */}
        <div style={{ maxWidth: 520, flex: '1 1 auto' }}>
          {/* Eyebrow */}
          <p style={{
            fontSize: 10, fontWeight: 700, letterSpacing: '2.5px',
            color: '#8a7a60', textTransform: 'uppercase',
            margin: '0 0 36px',
          }}>
            GOLDEN HOUR — THE CITY NEVER FULLY STOPS
          </p>

          {/* Hero headline */}
          <h1 style={{ margin: '0 0 28px', lineHeight: 1.0, letterSpacing: '-2px' }}>
            <span style={{
              display: 'block', fontSize: 'clamp(64px, 7vw, 96px)',
              fontWeight: 900, color: '#e8dfc8',
            }}>Stop.</span>
            <span style={{
              display: 'block', fontSize: 'clamp(64px, 7vw, 96px)',
              fontWeight: 900, color: '#e8dfc8',
            }}>Slow.</span>
            <span style={{
              display: 'block', fontSize: 'clamp(64px, 7vw, 96px)',
              fontWeight: 900, color: '#c9a84c',
            }}>GO.</span>
          </h1>

          {/* Body */}
          <p style={{
            fontSize: 14, color: '#8a7a60', lineHeight: 1.75,
            margin: '0 0 40px', maxWidth: 420,
          }}>
            URBANEYE is an AI traffic intelligence platform built around the three signals every driver knows.
            We turn the rhythm of the intersection — the wait, the release, the run —
            into real-time vehicle detection, ANPR and city-wide analytics.
          </p>

          {/* CTAs */}
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
            <button
              onClick={() => navigate('/login')}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 8,
                padding: '14px 28px', borderRadius: 50,
                background: '#c9a84c', border: '1.5px solid #c9a84c',
                color: '#1a1208', fontWeight: 800, fontSize: 14,
                cursor: 'pointer', transition: 'all .2s',
                boxShadow: '0 0 20px #c9a84c30',
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = '#dab85c'; (e.currentTarget as HTMLButtonElement).style.boxShadow = '0 0 32px #c9a84c55'; }}
              onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = '#c9a84c'; (e.currentTarget as HTMLButtonElement).style.boxShadow = '0 0 20px #c9a84c30'; }}
            >
              <Zap size={15} /> Launch Dashboard
            </button>
            <button
              onClick={() => navigate('/login')}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 8,
                padding: '13px 24px', borderRadius: 50,
                background: 'transparent', border: '1.5px solid #3a2e1e',
                color: '#8a7a60', fontWeight: 600, fontSize: 14,
                cursor: 'pointer', transition: 'all .2s',
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = '#c9a84c'; (e.currentTarget as HTMLButtonElement).style.color = '#c9a84c'; }}
              onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = '#3a2e1e'; (e.currentTarget as HTMLButtonElement).style.color = '#8a7a60'; }}
            >
              View Live Demo <ArrowRight size={14} />
            </button>
          </div>

          {/* Demo note */}
          <p style={{ fontSize: 10, color: '#4a3a24', marginTop: 20 }}>
            Demo credentials: <strong style={{ color: '#6a5a40' }}>admin / admin123</strong>
            &nbsp;·&nbsp; No real surveillance data is used in this demo.
          </p>
        </div>

        {/* Right: Traffic light — kept exactly as Signal House */}
        <div style={{
          flex: '0 0 auto', display: 'flex', justifyContent: 'center',
          alignItems: 'center', paddingLeft: 40,
        }}>
          <TrafficLight />
        </div>
      </section>

      {/* Divider */}
      <div style={{ height: 1, background: 'linear-gradient(90deg, transparent, #3a2e1e, transparent)', margin: '0 56px' }} />

      {/* ── Features section ─────────────────────────────────────────────── */}
      <section style={{ padding: '80px 56px' }}>
        <div style={{ marginBottom: 52 }}>
          <p style={{ fontSize: 10, color: '#6a5a40', fontWeight: 700, letterSpacing: '2px', textTransform: 'uppercase', margin: '0 0 14px' }}>
            (A) THE SYSTEM
          </p>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 40, flexWrap: 'wrap' }}>
            <h2 style={{ margin: 0, fontSize: 'clamp(28px, 3.5vw, 42px)', fontWeight: 800, letterSpacing: '-1px', color: '#e8dfc8', maxWidth: 500 }}>
              Three signals, one intelligence
            </h2>
            <p style={{ margin: 0, fontSize: 13, color: '#6a5a40', maxWidth: 300, lineHeight: 1.7 }}>
              Every detection, alert and trajectory is keyed to one of the three signals.
              Meaningful, never decorative.
            </p>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 18 }}>
          {FEATURES.map((f, i) => (
            <div className="sh-feature-card" key={f.title}>
              <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                marginBottom: 14, fontSize: 10, fontWeight: 700,
                letterSpacing: '1.5px', textTransform: 'uppercase',
                color: f.color,
              }}>
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: f.color, display: 'inline-block' }} />
                {i < 2 ? 'STOP' : i < 4 ? 'SLOW' : 'GO'} · {String(i + 1).padStart(2, '0')}
              </div>
              <h3 style={{ margin: '0 0 10px', fontSize: 20, fontWeight: 800, letterSpacing: '-.4px', color: '#d8c8a0' }}>
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

      {/* ── CTA ──────────────────────────────────────────────────────────── */}
      <section style={{ padding: '80px 56px', textAlign: 'center' }}>
        <p style={{ fontSize: 10, color: '#6a5a40', fontWeight: 700, letterSpacing: '2px', textTransform: 'uppercase', margin: '0 0 20px' }}>
          (B) THE COMMAND CENTRE
        </p>
        <h2 style={{ margin: '0 0 16px', fontSize: 'clamp(28px, 3vw, 40px)', fontWeight: 800, letterSpacing: '-1px', color: '#e8dfc8' }}>
          Intelligence for the light
        </h2>
        <p style={{ color: '#6a5a40', fontSize: 14, margin: '0 auto 36px', maxWidth: 480, lineHeight: 1.7 }}>
          Sign in to the UrbanEye AI command centre and see live traffic intelligence
          from an entire city camera network.
        </p>
        <button
          onClick={() => navigate('/login')}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 8,
            padding: '14px 32px', borderRadius: 50,
            background: '#c9a84c', border: '1.5px solid #c9a84c',
            color: '#1a1208', fontWeight: 800, fontSize: 14,
            cursor: 'pointer', transition: 'all .2s',
            boxShadow: '0 0 24px #c9a84c30',
          }}
        >
          <Zap size={15} /> Enter the System
        </button>
        <p style={{ color: '#3a2e20', fontSize: 10, marginTop: 18 }}>
          SIH26127 · Smart India Hackathon 2026 · Demo Environment
        </p>
      </section>

      {/* ── Footer ───────────────────────────────────────────────────────── */}
      <footer style={{
        borderTop: '1px solid #2a2010',
        padding: '24px 56px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        flexWrap: 'wrap', gap: 12,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#4a9e6a', display: 'inline-block', boxShadow: '0 0 6px #4a9e6a' }} />
          <span style={{ fontWeight: 800, fontSize: 13, color: '#e8dfc8', letterSpacing: '-.2px' }}>
            URBAN<span style={{ color: '#c9a84c' }}>EYE</span>
          </span>
        </div>
        <p style={{ margin: 0, fontSize: 11, color: '#3a2e20' }}>
          A house of three signals and the intelligence that watches them.
          Crafted where the city meets the golden hour.
        </p>
        <div style={{ display: 'flex', gap: 20 }}>
          {['The Light', 'Rhythm', 'System'].map(l => (
            <span key={l} style={{ fontSize: 11, color: '#4a3a24', cursor: 'pointer' }}>{l}</span>
          ))}
        </div>
      </footer>
    </div>
  )
}
