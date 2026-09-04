'use client'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { Activity, BarChart3, Bell, ChevronRight, FileSearch, Gauge, MapPinned, Radio, ShieldAlert, LocateFixed, Menu, X, Upload, LogOut, Navigation2, MessageSquare } from 'lucide-react'
import { useState, useEffect } from 'react'
import { fetchHealth } from '@/lib/api'
import { getUser, logout } from '@/src/auth'

const items=[['Overview','/dashboard',Gauge],['Vehicle Search','/dashboard/vehicle-search',FileSearch],['Upload Video','/dashboard/upload-video',Upload],['Camera Network','/dashboard/cameras',Radio],['Traffic Analytics','/dashboard/traffic-analytics',BarChart3],['City Map','/dashboard/city-map',MapPinned],['Trajectory Explorer','/dashboard/trajectory-explorer',Navigation2],['NL Query','/dashboard/nl-query',MessageSquare],['Alerts','/dashboard/alerts',Bell],['Manual Review','/dashboard/manual-review',ShieldAlert],['Blacklist Monitoring','/dashboard/blacklist',ShieldAlert],['System Health','/dashboard/system-health',Activity]] as const

/** Live API connectivity indicator shown in the sidebar bottom */
function ApiStatus() {
  const [status, setStatus] = useState<'checking'|'connected'|'disconnected'>('checking')
  const [version, setVersion] = useState('')

  useEffect(() => {
    let failCount = 0
    const check = () => {
      fetchHealth()
        .then(h => { setStatus('connected'); setVersion(h.version); failCount = 0 })
        .catch(() => {
          failCount++
          // Only show disconnected after 2 consecutive failures (avoids flicker on single timeout)
          if (failCount >= 2) setStatus('disconnected')
        })
    }
    check()
    const t = setInterval(check, 30_000)
    return () => clearInterval(t)
  }, [])

  const label = status === 'connected' ? `API v${version}` : status === 'checking' ? 'Connecting…' : 'API Offline'
  const dotStyle = status === 'connected'
    ? { background: '#24ae76', boxShadow: '0 0 0 4px #224c49' }
    : status === 'disconnected'
    ? { background: '#db5b5d', boxShadow: '0 0 0 4px #4c2222' }
    : { background: '#eea524', boxShadow: '0 0 0 4px #4c3a12' }

  return (
    <div className="api-status">
      <span className="pulse" style={dotStyle}/>
      <div>
        <strong style={{ color: status === 'disconnected' ? '#e88' : '#c8d9e8' }}>
          {label}
        </strong>
        <small>
          {status === 'connected' ? 'Backend connected' : status === 'disconnected' ? 'Start backend server' : 'localhost:8000'}
        </small>
      </div>
    </div>
  )
}

export function Sidebar({open,close}:{open:boolean;close:()=>void}){
  const navigate=useNavigate()
  const go=(path:string)=>{navigate(path);close()}
  const user=getUser()
  const initials=user?.name?.split(' ').map(w=>w[0]).join('').slice(0,2).toUpperCase()||'AS'
  const handleLogout=()=>{logout();navigate('/',{replace:true})}
  return <><aside className={`sidebar ${open?'sidebar-open':''}`}><div className="brand"><div className="brand-mark"><LocateFixed/></div><div><strong>Urban<span>Eye</span></strong><small>AI TRAFFIC INTELLIGENCE</small></div><button className="sidebar-close" onClick={close}><X/></button></div><div className="workspace"><span className="eyebrow">WORKSPACE</span><button className="workspace-select">Operations HQ</button></div><nav className="nav-list" aria-label="Primary navigation"><span className="eyebrow nav-label">MONITORING</span>{items.slice(0,10).map(([label,path,Icon])=><NavLink end={path==='/dashboard'} key={path} to={path} onClick={()=>go(path)} className={({isActive})=>`nav-item ${isActive?'active':''}`}><Icon/><span>{label}</span>{label==='Alerts'&&<b>!</b>}<ChevronRight className="nav-chevron"/></NavLink>)}<span className="eyebrow nav-label system-label">SYSTEM</span>{items.slice(10).map(([label,path,Icon])=><NavLink key={path} to={path} onClick={()=>go(path)} className={({isActive})=>`nav-item ${isActive?'active':''}`}><Icon/><span>{label}</span></NavLink>)}</nav><div className="sidebar-bottom"><ApiStatus/><div className="user-card"><div className="avatar">{initials}</div><div><strong>{user?.name||'Admin'}</strong><small>{user?.role||'System Administrator'}</small></div><button onClick={handleLogout} style={{marginLeft:'auto',border:0,background:'transparent',color:'#4a6880',cursor:'pointer',padding:4}} title="Sign out"><LogOut size={14}/></button></div></div></aside>{open&&<button aria-label="Close navigation" className="mobile-scrim" onClick={close}/>}</>
}
export function Header({open}:{open:()=>void}){return <header className="topbar"><button className="menu-button" onClick={open}><Menu/></button><div className="topbar-left"><span className="live-indicator"><span/>SYSTEM LIVE</span><span className="topbar-separator"/><span className="topbar-note">SIH26127 · UrbanEye AI</span></div><div className="topbar-actions"><button className="notification-button" aria-label="Notifications"><Bell/><span>!</span></button><div className="topbar-avatar">AS</div></div></header>}
export function AppLayout(){const [open,setOpen]=useState(false);return <div className="app-shell"><Sidebar open={open} close={()=>setOpen(false)}/><main className="main-content"><Header open={()=>setOpen(true)}/><div className="content-inner"><div className="breadcrumbs"><span>Operations</span><ChevronRight/><strong>UrbanEye AI</strong></div><Outlet/><footer className="footer"><span>UrbanEye AI v0.8.0</span><span>Powered by SIH26127 Backend</span><span>API: {process.env.NEXT_PUBLIC_API_URL ?? 'localhost:8000'}</span></footer></div></main></div>}
