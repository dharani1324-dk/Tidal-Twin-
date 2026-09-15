import { useEffect, useRef, useState } from 'react'
import { Routes, Route, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Waves, Globe2, Radar, MessageSquare, FileBarChart, Home, BookOpen,
  LifeBuoy, Siren, Scale, Search, Brain, FlaskConical, Sparkles, Anchor,
  Bell, Menu, X, Radio, Satellite, Database, CircleUser, Command, ShieldAlert, Sparkle,
  AlertTriangle,
} from 'lucide-react'
import Dashboard from './pages/Dashboard'
import DigitalTwin from './pages/DigitalTwin'
import Assistant from './pages/Assistant'
import Monitoring from './pages/Monitoring'
import Stories from './pages/Stories'
import Reports from './pages/Reports'
import Safety from './pages/Safety'
import RiskMap from './pages/RiskMap'
import Validate from './pages/Validate'
import Forensics from './pages/Forensics'
import Intelligence from './pages/Intelligence'
import ScenarioLab from './pages/ScenarioLab'
import OceanVision from './pages/OceanVision'
import CoastalIntel from './pages/CoastalIntel'
import AnomalyIntel from './pages/AnomalyIntel'
import AssistantFab from './components/assistant/AssistantFab'
import { fetchLocations, fetchAlerts } from './api/client'
import './App.css'

/**
 * Oceaneerse AI — Application Shell
 * Command-platform layout: grouped navigation + live system status bar +
 * notification center + AI quick-access. Fully responsive (mobile drawer).
 */

type Icon = typeof Waves

interface NavSpec {
  section: string
  items: { to: string; label: string; icon: Icon; end?: boolean }[]
}

const NAV_GROUPS: NavSpec[] = [
  {
    section: 'Mission',
    items: [
      { to: '/', label: 'Mission Control', icon: Home, end: true },
      { to: '/globe', label: 'Digital Twin', icon: Globe2 },
      { to: '/monitoring', label: 'Monitoring & Alerts', icon: Radar },
      { to: '/assistant', label: 'Ocean AI Copilot', icon: MessageSquare },
    ],
  },
  {
    section: 'Analysis',
    items: [
      { to: '/validate', label: 'Model Validation', icon: Scale },
      { to: '/anomalies', label: 'Anomaly Intel', icon: AlertTriangle },
      { to: '/forensics', label: 'Ocean Forensics', icon: Search },
      { to: '/intelligence', label: 'Decision Intelligence', icon: Brain },
      { to: '/scenarios', label: 'Scenario Lab', icon: FlaskConical },
    ],
  },
  {
    section: 'Ocean & Coastal',
    items: [
      { to: '/oceanvision', label: 'Ocean Vision', icon: Sparkles },
      { to: '/coastal', label: 'Coastal Intel', icon: Anchor },
      { to: '/safety', label: 'Safety Center', icon: LifeBuoy },
      { to: '/risk', label: 'Risk Map', icon: Siren },
    ],
  },
  {
    section: 'Reporting',
    items: [
      { to: '/stories', label: 'Story Mode', icon: BookOpen },
      { to: '/reports', label: 'Risk Report', icon: FileBarChart },
    ],
  },
]

const FLAT_NAV = NAV_GROUPS.flatMap((g) => g.items)

interface AlertItem {
  id: number
  severity: string
  alert_type: string
  location_name: string
  status: string
  created_at: string
  description?: string
}

export default function App() {
  const location = useLocation()
  const navigate = useNavigate()
  const [regions, setRegions] = useState<number | null>(null)
  const [alerts, setAlerts] = useState<AlertItem[]>([])
  const [connected, setConnected] = useState<boolean | null>(null)
  const [lastSync, setLastSync] = useState<number>(0)
  const [now, setNow] = useState<number>(0)
  const [drawer, setDrawer] = useState(false)
  const [bellOpen, setBellOpen] = useState(false)
  const bellRef = useRef<HTMLDivElement>(null)

  const active = FLAT_NAV.find((n) => (n.end ? location.pathname === n.to : location.pathname.startsWith(n.to)))

  useEffect(() => {
    setLastSync(Date.now())
    setNow(Date.now())
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const [locs, al] = await Promise.all([
          fetchLocations(),
          fetchAlerts().catch(() => []),
        ])
        if (!alive) return
        setRegions(Array.isArray(locs) ? locs.length : 0)
        setAlerts(Array.isArray(al) ? al.filter((a) => a.status !== 'resolved') : [])
        setConnected(true)
        setLastSync(Date.now())
      } catch {
        if (alive) setConnected(false)
      }
    }
    load()
    const poll = setInterval(load, 90000)
    return () => {
      alive = false
      clearInterval(poll)
    }
  }, [])

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (bellRef.current && !bellRef.current.contains(e.target as Node)) setBellOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  useEffect(() => {
    setDrawer(false)
  }, [location.pathname])

  const secondsAgo = Math.max(0, Math.floor((now - lastSync) / 1000))
  const activeAlerts = alerts.filter((a) => a.status === 'active')
  const critical = activeAlerts.filter((a) => a.severity === 'critical' || a.severity === 'high')

  const product = (
    <div className="sidebar-brand" onClick={() => navigate('/')}>
      <div className="logo-wrap">
        <Waves size={22} className="logo-icon" />
      </div>
      <div className="brand-text">
        <span className="brand-name">OceanVerse</span>
        <span className="brand-sub">Ocean Intelligence</span>
      </div>
    </div>
  )

  const nav = (
    <nav className="sidebar-nav" aria-label="Primary">
      {NAV_GROUPS.map((group) => (
        <div className="nav-group" key={group.section}>
          <span className="nav-group-label">{group.section}</span>
          {group.items.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => `nav-item${isActive ? ' nav-item-active' : ''}`}
            >
              <Icon size={17} />
              <span>{label}</span>
              {to === '/assistant' && <Sparkle size={11} className="nav-ai-dot" />}
            </NavLink>
          ))}
        </div>
      ))}
    </nav>
  )

  return (
    <div className="app-shell">
      {/* ---- Sidebar (desktop) ---- */}
      <aside className="sidebar">
        {product}
        {nav}
        <div className="sidebar-footer">
          <span className="status-tag ok"><b>SYS</b> OPERATIONAL</span>
          <span className="sf-ver">v2.0 · Indian Ocean</span>
        </div>
      </aside>

      {/* ---- Main column ---- */}
      <section className="shell-main">
        {/* System status bar */}
        <header className="system-bar">
          <div className="sb-left">
            <button className="sb-menu btn-icon btn-ghost" onClick={() => setDrawer(true)} aria-label="Open navigation">
              <Menu size={18} />
            </button>
            <div className="sb-title">
              <span className="sb-crumb">OCEANVERSE /</span>
              <b>{active?.label ?? 'Mission Control'}</b>
            </div>
          </div>

          <div className="sb-status" role="status">
            <span className={`status-tag ${connected === false ? 'crit' : connected === null ? 'off' : 'ok'}`}>
              <b>SYSTEM</b> {connected === false ? 'NO LINK' : connected === null ? '…' : 'OPERATIONAL'}
            </span>
            <span className={`status-tag ${connected === false ? 'off' : 'ok'}`}>
              <Satellite size={11} /> <b>SAT</b> LINK
            </span>
            <span className={`status-tag ${connected === false ? 'off' : 'ok'}`}>
              <Database size={11} /> <b>{regions ?? '—'}</b> REGIONS
            </span>
            <AnimatePresence>
              {critical.length > 0 && (
                <motion.span
                  className="status-tag crit"
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0 }}
                >
                  <ShieldAlert size={11} /> <b>{critical.length}</b> ALERT{critical.length === 1 ? '' : 'S'}
                </motion.span>
              )}
            </AnimatePresence>
            <span className="status-tag sync-tag" title="Last successful sync with the data server">
              <Radio size={11} /> {secondsAgo < 3 ? 'LIVE' : `UPDATED ${secondsAgo}S AGO`}
            </span>
          </div>

          <div className="sb-actions">
            <button className="ai-cta" onClick={() => navigate('/assistant')}>
              <Command size={13} />
              <span>Ask Ocean AI</span>
              <kbd>⌘K</kbd>
            </button>
            <div className="bell-wrap" ref={bellRef}>
              <button
                className="btn-icon btn-ghost sb-icon-btn"
                onClick={() => setBellOpen((v) => !v)}
                aria-label={`Notifications: ${activeAlerts.length} active`}
              >
                <Bell size={17} />
                {activeAlerts.length > 0 && <span className="bell-badge">{activeAlerts.length}</span>}
              </button>
              <AnimatePresence>
                {bellOpen && (
                  <motion.div
                    className="notify-pop"
                    initial={{ opacity: 0, y: 8, scale: 0.98 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 6, scale: 0.98 }}
                    transition={{ duration: 0.16 }}
                  >
                    <div className="notify-head">
                      <b>Active alerts</b>
                      <span>{activeAlerts.length} live</span>
                    </div>
                    <div className="notify-list">
                      {activeAlerts.length === 0 && (
                        <div className="notify-empty">No active alerts — all systems normal.</div>
                      )}
                      {activeAlerts.slice(0, 8).map((a) => (
                        <button key={a.id} className="notify-item" onClick={() => navigate('/monitoring')}>
                          <span className={`notify-dot sev-${a.severity}`} />
                          <span className="notify-txt">
                            <b>{a.alert_type.replace(/_/g, ' ')}</b>
                            <em>{a.location_name ?? '—'}</em>
                          </span>
                          <span className="notify-sev">{a.severity}</span>
                        </button>
                      ))}
                    </div>
                    <button className="notify-foot" onClick={() => navigate('/monitoring')}>
                      Open Monitoring Center →
                    </button>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
            <button className="user-chip" onClick={() => navigate('/reports')} aria-label="Account">
              <CircleUser size={17} />
              <span>CMD OPS</span>
            </button>
          </div>
        </header>

        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/globe" element={<DigitalTwin />} />
            <Route path="/monitoring" element={<Monitoring />} />
            <Route path="/validate" element={<Validate />} />
            <Route path="/anomalies" element={<AnomalyIntel />} />
            <Route path="/forensics" element={<Forensics />} />
            <Route path="/intelligence" element={<Intelligence />} />
            <Route path="/oceanvision" element={<OceanVision />} />
            <Route path="/coastal" element={<CoastalIntel />} />
            <Route path="/scenarios" element={<ScenarioLab />} />
            <Route path="/safety" element={<Safety />} />
            <Route path="/risk" element={<RiskMap />} />
            <Route path="/stories" element={<Stories />} />
            <Route path="/assistant" element={<Assistant />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="*" element={<Dashboard />} />
          </Routes>
        </main>
      </section>

      {/* ---- Mobile drawer ---- */}
      <AnimatePresence>
        {drawer && (
          <>
            <motion.div
              className="drawer-overlay"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setDrawer(false)}
            />
            <motion.aside
              className="mobile-drawer"
              initial={{ x: '-100%' }}
              animate={{ x: 0 }}
              exit={{ x: '-100%' }}
              transition={{ type: 'tween', duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
            >
              <div className="drawer-top">
                {product}
                <button className="btn-icon btn-ghost" onClick={() => setDrawer(false)} aria-label="Close navigation">
                  <X size={20} />
                </button>
              </div>
              {nav}
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      {/* Floating "Ask Ocean AI" quick access (hidden on the assistant page) */}
      <AssistantFab visible={location.pathname !== '/assistant'} />
    </div>
  )
}