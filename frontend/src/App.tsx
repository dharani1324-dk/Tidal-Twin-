import { Routes, Route, NavLink } from 'react-router-dom'
import { Waves, Globe2, Radar, MessageSquare, FileBarChart, Home, Activity, BookOpen, LifeBuoy, Siren, Scale, Search, Brain, FlaskConical } from 'lucide-react'
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
import './App.css'

/**
 * App Shell
 * ==========
 * This is the overall frame of the app:
 * - A sleek sidebar navigation ("mission control" feel)
 * - The main content area where each page renders
 *
 * We'll add more pages (Globe, AI Assistant, Reports) in later steps.
 */

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: Home, end: true },
  { to: '/globe', label: 'Digital Twin', icon: Globe2 },
  { to: '/monitoring', label: 'Monitoring', icon: Activity },
  { to: '/validate', label: 'Model Validation', icon: Scale },
  { to: '/forensics', label: 'Forensics', icon: Search },
  { to: '/intelligence', label: 'Intelligence', icon: Brain },
  { to: '/scenarios', label: 'Scenario Lab', icon: FlaskConical },
  { to: '/safety', label: 'Safety Center', icon: LifeBuoy },
  { to: '/risk', label: 'Risk Map', icon: Siren },
  { to: '/stories', label: 'Story Mode', icon: BookOpen },
  { to: '/assistant', label: 'Ocean AI', icon: MessageSquare },
  { to: '/reports', label: 'Reports', icon: FileBarChart },
]

export default function App() {
  return (
    <div className="app-shell">
      {/* ---- Sleek Sidebar ---- */}
      <aside className="sidebar glass-card">
        <div className="sidebar-brand">
          <div className="logo-wrap">
            <Waves size={26} className="logo-icon" />
          </div>
          <div className="brand-text">
            <span className="brand-name">OceanVerse</span>
            <span className="brand-sub">AI Digital Twin</span>
          </div>
        </div>

        <nav className="sidebar-nav">
          {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `nav-item ${isActive ? 'nav-item-active' : ''}`
              }
            >
              <Icon size={18} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <Radar size={14} className="pulse-dot" />
          <span>LIVE · Indian Ocean</span>
        </div>
      </aside>

      {/* ---- Main Content ---- */}
      <main className="main-content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/globe" element={<DigitalTwin />} />
          <Route path="/monitoring" element={<Monitoring />} />
          <Route path="/validate" element={<Validate />} />
          <Route path="/forensics" element={<Forensics />} />
          <Route path="/intelligence" element={<Intelligence />} />
          <Route path="/scenarios" element={<ScenarioLab />} />
          <Route path="/safety" element={<Safety />} />
          <Route path="/risk" element={<RiskMap />} />
          <Route path="/stories" element={<Stories />} />
          <Route path="/assistant" element={<Assistant />} />
          <Route path="/reports" element={<Reports />} />
        </Routes>
      </main>
    </div>
  )
}