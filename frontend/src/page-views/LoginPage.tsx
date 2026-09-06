'use client'
/**
 * Login Page — UrbanEye AI
 * Clean dark-themed login with demo credentials helper.
 */
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  LocateFixed, Eye, EyeOff, LogIn, ArrowLeft,
  Camera, MapPin, ShieldAlert, BarChart3, AlertCircle, Loader2,
} from 'lucide-react'
import { login, isAuthenticated } from '@/src/auth'

const FEATURES = [
  { icon: Camera,     color: '#f59e0b', bg: '#261800',
    title: 'Live Camera Network',  desc: '250+ ANPR cameras monitored in real time' },
  { icon: MapPin,     color: '#22c55e', bg: '#081a0e',
    title: 'Vehicle Trajectories', desc: 'Track any vehicle across the city network' },
  { icon: BarChart3,  color: '#f59e0b', bg: '#261800',
    title: 'Traffic Analytics',    desc: 'Congestion, density, and peak-hour data' },
  { icon: ShieldAlert,color: '#ef4444', bg: '#1a0606',
    title: 'Instant Alerts',       desc: 'Blacklist hits and anomaly detections' },
]

export default function LoginPage() {
  const navigate   = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPass, setShowPass] = useState(false)
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState<string | null>(null)

  // Already logged in → go straight to dashboard
  useEffect(() => {
    if (isAuthenticated()) navigate('/dashboard', { replace: true })
  }, [navigate])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password) {
      setError('Please enter both username and password.')
      return
    }
    setLoading(true)
    setError(null)

    // Simulate a brief network delay for realism
    await new Promise(r => setTimeout(r, 600))

    const user = login(username.trim(), password)
    setLoading(false)

    if (!user) {
      setError('Invalid username or password. Try: admin / admin123')
      return
    }

    navigate('/dashboard', { replace: true })
  }

  const fillDemo = () => {
    setUsername('admin')
    setPassword('admin123')
    setError(null)
  }

  return (
    <div className="login-shell">
      {/* ── Left: form ───────────────────────────────────────────────────── */}
      <div className="login-left">
        <div className="login-bg-grid" />
        <div className="login-bg-glow" />

        <div className="login-form-wrap">
          {/* Logo */}
          <div className="login-logo" onClick={() => navigate('/')} style={{ cursor: 'pointer' }}>
            <div className="login-logo-mark"><LocateFixed /></div>
            <div className="login-logo-text">
              <strong>Urban<span style={{ color: '#f59e0b' }}>Eye</span></strong>
              <small>AI TRAFFIC INTELLIGENCE</small>
            </div>
          </div>

          <h1 className="login-title">Welcome back</h1>
          <p className="login-sub">Sign in to the UrbanEye AI Command Centre</p>

          {/* Error banner */}
          {error && (
            <div className="login-error">
              <AlertCircle size={14} style={{ flexShrink: 0 }} />
              {error}
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} autoComplete="on">
            <div className="login-field">
              <label className="login-label" htmlFor="username">USERNAME</label>
              <input
                id="username"
                className="login-input"
                type="text"
                placeholder="e.g. admin"
                autoComplete="username"
                value={username}
                onChange={e => { setUsername(e.target.value); setError(null) }}
              />
            </div>

            <div className="login-field">
              <label className="login-label" htmlFor="password">PASSWORD</label>
              <div className="login-input-wrap">
                <input
                  id="password"
                  className="login-input"
                  type={showPass ? 'text' : 'password'}
                  placeholder="Enter your password"
                  autoComplete="current-password"
                  value={password}
                  style={{ paddingRight: 40 }}
                  onChange={e => { setPassword(e.target.value); setError(null) }}
                />
                <button
                  type="button"
                  className="login-eye"
                  onClick={() => setShowPass(s => !s)}
                  tabIndex={-1}
                  aria-label={showPass ? 'Hide password' : 'Show password'}
                >
                  {showPass ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            <button className="login-btn" type="submit" disabled={loading}>
              {loading
                ? <><Loader2 size={15} style={{ animation: 'spin 1s linear infinite' }} /> Signing in…</>
                : <><LogIn size={15} /> Sign In</>
              }
            </button>
          </form>

          <div className="login-divider">or</div>

          <button className="login-demo-btn" type="button" onClick={fillDemo}>
            Fill demo credentials (admin / admin123)
          </button>

          {/* Credentials hint */}
          <div style={{
            marginTop: 20, padding: '14px', background: '#221a0e',
            border: '1px solid #3a2e1e', borderRadius: 8,
          }}>
            <p style={{ color: '#6a5a40', fontSize: 9, fontWeight: 700, letterSpacing: '.8px', margin: '0 0 8px' }}>
              DEMO ACCOUNTS
            </p>
            {[
              ['admin',    'admin123',    'System Administrator'],
              ['operator', 'operator123', 'Traffic Operator'],
              ['viewer',   'viewer123',   'Read-Only Access'],
            ].map(([u, p, r]) => (
              <div
                key={u}
                style={{ display: 'flex', gap: 8, marginBottom: 5, cursor: 'pointer', alignItems: 'center' }}
                onClick={() => { setUsername(u); setPassword(p); setError(null) }}
              >
                <code style={{ color: '#f59e0b', fontSize: 10, minWidth: 72 }}>{u}</code>
                <code style={{ color: '#5a4a30', fontSize: 10, minWidth: 88 }}>{p}</code>
                <span style={{ color: '#4a3a24', fontSize: 9 }}>{r}</span>
              </div>
            ))}
          </div>

          <button className="login-back" onClick={() => navigate('/')}>
            <ArrowLeft size={13} /> Back to home
          </button>
        </div>
      </div>

      {/* ── Right: feature panel ─────────────────────────────────────────── */}
      <div className="login-right">
        <div className="login-right-glow" />

        <h2>Intelligent Urban Traffic Platform</h2>
        <p>
          UrbanEye AI gives traffic operators a complete real-time view of the city —
          from individual vehicle trajectories to city-wide congestion analysis.
        </p>

        <div className="login-features">
          {FEATURES.map(f => (
            <div className="login-feat" key={f.title}>
              <div className="login-feat-icon" style={{ background: f.bg, border: `1px solid ${f.color}22` }}>
                <f.icon color={f.color} />
              </div>
              <div>
                <strong>{f.title}</strong>
                <p>{f.desc}</p>
              </div>
            </div>
          ))}
        </div>

        <div className="login-right-stats">
          {[
            ['250+', 'CAMERAS'],
            ['142ms', 'AVG LATENCY'],
            ['98.4%', 'ACCURACY'],
            ['6', 'ALERT TYPES'],
          ].map(([v, l]) => (
            <div className="login-right-stat" key={l}>
              <strong>{v}</strong>
              <span>{l}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
