import { Routes, Route, NavLink } from 'react-router-dom'
import { Waves, Globe2, Radar, MessageSquare, FileBarChart, Home, Activity } from 'lucide-react'
import Dashboard from './pages/Dashboard'
import DigitalTwin from './pages/DigitalTwin'
import Assistant from './pages/Assistant'
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
          {/* Placeholder routes for upcoming pages */}
          <Route path="/globe" element={<DigitalTwin />} />
          <Route path="/monitoring" element={<PagePlaceholder title="Ocean Monitoring" note="Live anomaly detection & alerts" />} />
          <Route path="/assistant" element={<Assistant />} />
          <Route path="/reports" element={<PagePlaceholder title="Reports & Insights" note="PDF/CSV reports, model comparisons" />} />
        </Routes>
      </main>
    </div>
  )
}

/** A simple, elegant placeholder page for upcoming modules */
function PagePlaceholder({ title, note }: { title: string; note: string }) {
  return (
    <div className="page animate-in">
      <div className="page-header">
        <h1 className="page-title">{title}</h1>
        <p className="page-subtitle">{note}</p>
      </div>
      <div className="glass-card placeholder-card">
        <Waves size={48} className="placeholder-icon" />
        <p>This module is under construction — coming in the next step.</p>
      </div>
    </div>
  )
}