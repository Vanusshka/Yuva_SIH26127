'use client'

import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import {
  Activity,
  BarChart3,
  Bell,
  ChevronRight,
  FileSearch,
  Gauge,
  MapPinned,
  Radio,
  ShieldAlert,
  LocateFixed,
  Menu,
  X,
  Upload,
  LogOut,
  Navigation2,
  MessageSquare
} from 'lucide-react'
import { useState, useEffect } from 'react'
import { fetchHealth } from '@/lib/api'
import { getUser, logout } from '@/src/auth'

const items = [
  ['Overview', '/dashboard', Gauge],
  ['Vehicle Search', '/dashboard/vehicle-search', FileSearch],
  ['Upload Video', '/dashboard/upload-video', Upload],
  ['Camera Network', '/dashboard/cameras', Radio],
  ['Traffic Analytics', '/dashboard/traffic-analytics', BarChart3],
  ['City Map', '/dashboard/city-map', MapPinned],
  ['Trajectory Explorer', '/dashboard/trajectory-explorer', Navigation2],
  ['NL Query', '/dashboard/nl-query', MessageSquare],
  ['Alerts', '/dashboard/alerts', Bell],
  ['Manual Review', '/dashboard/manual-review', ShieldAlert],
  ['Blacklist', '/dashboard/blacklist', ShieldAlert],
  ['System Health', '/dashboard/system-health', Activity]
] as const

/* -------------------------------------------------------------------------- */
/* API STATUS                                                                  */
/* -------------------------------------------------------------------------- */

function ApiStatus() {
  const [status, setStatus] = useState<
    'checking' | 'waking' | 'connected' | 'disconnected'
  >('checking')

  const [version, setVersion] = useState('')

  const checkBackend = async () => {
    try {
      setStatus(current =>
        current === 'connected' ? 'connected' : 'waking'
      )

      const health = await fetchHealth()

      /*
       * Backend returns:
       * {
       *   status: "running",
       *   version: "0.8.0",
       *   database: "connected"
       * }
       */

      if (
        health &&
        health.status === 'running' &&
        health.database === 'connected'
      ) {
        setVersion(health.version || '')
        setStatus('connected')
      } else {
        setStatus('disconnected')
      }
    } catch (error) {
      console.error('UrbanEye backend health check failed:', error)
      setStatus('disconnected')
    }
  }

  useEffect(() => {
    let mounted = true

    const check = async () => {
      if (!mounted) return
      await checkBackend()
    }

    check()

    // Check every 30 seconds
    const interval = window.setInterval(check, 30_000)

    return () => {
      mounted = false
      window.clearInterval(interval)
    }
  }, [])

  const label =
    status === 'connected'
      ? `API v${version || '0.8.0'}`
      : status === 'disconnected'
        ? 'API Offline'
        : 'Connecting…'

  const subtitle =
    status === 'connected'
      ? 'Backend connected'
      : status === 'waking'
        ? 'Waking backend…'
        : status === 'disconnected'
          ? 'Backend unreachable'
          : 'Connecting…'

  const dotStyle =
    status === 'connected'
      ? {
          background: '#24ae76',
          boxShadow: '0 0 0 4px #224c49'
        }
      : status === 'disconnected'
        ? {
            background: '#db5b5d',
            boxShadow: '0 0 0 4px #4c2222'
          }
        : {
            background: '#eea524',
            boxShadow: '0 0 0 4px #4c3a12'
          }

  return (
    <div className="api-status">
      <span className="pulse" style={dotStyle} />

      <div>
        <strong
          style={{
            color:
              status === 'disconnected'
                ? '#e88'
                : '#c8d9e8'
          }}
        >
          {label}
        </strong>

        <small>{subtitle}</small>
      </div>
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* SIDEBAR                                                                     */
/* -------------------------------------------------------------------------- */

export function Sidebar({
  open,
  close
}: {
  open: boolean
  close: () => void
}) {
  const navigate = useNavigate()

  const go = (path: string) => {
    navigate(path)
    close()
  }

  const user = getUser()

  const initials =
    user?.name
      ?.split(' ')
      .map(w => w[0])
      .join('')
      .slice(0, 2)
      .toUpperCase() || 'AS'

  const handleLogout = () => {
    logout()
    navigate('/', { replace: true })
  }

  return (
    <>
      <aside
        className={`sidebar ${
          open ? 'sidebar-open' : ''
        }`}
      >
        <div className="brand">
          <div className="brand-mark">
            <LocateFixed />
          </div>

          <div>
            <strong>
              Urban<span>Eye</span>
            </strong>

            <small>AI TRAFFIC INTELLIGENCE</small>
          </div>

          <button
            className="sidebar-close"
            onClick={close}
          >
            <X />
          </button>
        </div>

        <div className="workspace">
          <span className="eyebrow">
            WORKSPACE
          </span>

          <button className="workspace-select">
            Operations HQ
          </button>
        </div>

        <nav
          className="nav-list"
          aria-label="Primary navigation"
        >
          <span className="eyebrow nav-label">
            MONITORING
          </span>

          {items
            .slice(0, 10)
            .map(([label, path, Icon]) => (
              <NavLink
                end={path === '/dashboard'}
                key={path}
                to={path}
                onClick={() => go(path)}
                className={({ isActive }) =>
                  `nav-item ${
                    isActive ? 'active' : ''
                  }`
                }
              >
                <Icon />

                <span>{label}</span>

                {label === 'Alerts' && <b>!</b>}

                <ChevronRight className="nav-chevron" />
              </NavLink>
            ))}

          <span className="eyebrow nav-label system-label">
            SYSTEM
          </span>

          {items
            .slice(10)
            .map(([label, path, Icon]) => (
              <NavLink
                key={path}
                to={path}
                onClick={() => go(path)}
                className={({ isActive }) =>
                  `nav-item ${
                    isActive ? 'active' : ''
                  }`
                }
              >
                <Icon />
                <span>{label}</span>
              </NavLink>
            ))}
        </nav>

        <div className="sidebar-bottom">
          <ApiStatus />

          <div className="user-card">
            <div className="avatar">
              {initials}
            </div>

            <div>
              <strong>
                {user?.name || 'Admin'}
              </strong>

              <small>
                {user?.role ||
                  'System Administrator'}
              </small>
            </div>

            <button
              onClick={handleLogout}
              style={{
                marginLeft: 'auto',
                border: 0,
                background: 'transparent',
                color: '#4a6880',
                cursor: 'pointer',
                padding: 4
              }}
              title="Sign out"
            >
              <LogOut size={14} />
            </button>
          </div>
        </div>
      </aside>

      {open && (
        <button
          aria-label="Close navigation"
          className="mobile-scrim"
          onClick={close}
        />
      )}
    </>
  )
}

/* -------------------------------------------------------------------------- */
/* HEADER                                                                      */
/* -------------------------------------------------------------------------- */

export function Header({
  open
}: {
  open: () => void
}) {
  return (
    <header className="topbar">
      <button
        className="menu-button"
        onClick={open}
      >
        <Menu />
      </button>

      <div className="topbar-left">
        <span className="live-indicator">
          <span />
          SYSTEM LIVE
        </span>

        <span className="topbar-separator" />

        <span className="topbar-note">
          SIH26127 · UrbanEye AI
        </span>
      </div>

      <div className="topbar-actions">
        <button
          className="notification-button"
          aria-label="Notifications"
        >
          <Bell />
          <span>!</span>
        </button>

        <div className="topbar-avatar">
          AS
        </div>
      </div>
    </header>
  )
}

/* -------------------------------------------------------------------------- */
/* APP LAYOUT                                                                  */
/* -------------------------------------------------------------------------- */

export function AppLayout() {
  const [open, setOpen] = useState(false)

  const apiUrl =
    process.env.NEXT_PUBLIC_API_URL ||
    'https://urban-eye-backend-ssq1.onrender.com'

  return (
    <div className="app-shell">
      <Sidebar
        open={open}
        close={() => setOpen(false)}
      />

      <main className="main-content">
        <Header
          open={() => setOpen(true)}
        />

        <div className="content-inner">
          <div className="breadcrumbs">
            <span>Operations</span>
            <ChevronRight />
            <strong>UrbanEye AI</strong>
          </div>

          <Outlet />

          <footer className="footer">
            <span>
              UrbanEye AI v0.8.0
            </span>

            <span>
              Powered by SIH26127 Backend
            </span>

            <span>
              API: {apiUrl}
            </span>
          </footer>
        </div>
      </main>
    </div>
  )
}