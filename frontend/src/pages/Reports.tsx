import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import {
  FileBarChart, Download, ShieldAlert,
  Waves, Thermometer, Activity, Shield, ArrowUpRight, ArrowDownRight,
} from 'lucide-react'
import { fetchSummary, fetchRiskIndex, downloadCsv } from '../api/client'
import './Reports.css'

interface Region {
  location_id: number
  location: string
  index: number
  band: string
  signal: number
  volatility: number
  wave_height: number
  active_alerts: number
  latest_temperature: number | null
}

interface RiskIndex {
  generated_at: string
  regions: Region[]
  model: { safe_wave_m: number }
}

const BAND_COLORS: Record<string, string> = {
  CRITICAL: '#f43f5e',
  ELEVATED: '#f59e0b',
  MODERATE: '#22d3ee',
  STABLE: '#34d399',
}

export default function Reports() {
  const [index, setIndex] = useState<RiskIndex | null>(null)
  const [summary, setSummary] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [downloading, setDownloading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const [idx, summ] = await Promise.all([fetchRiskIndex(), fetchSummary()])
      setIndex(idx)
      setSummary(summ.summary)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const stats = useMemo(() => {
    const regions = index?.regions ?? []
    const critical = regions.filter((r) => r.band === 'CRITICAL').length
    const elevated = regions.filter((r) => r.band === 'ELEVATED').length
    const stable = regions.filter((r) => r.band === 'STABLE').length
    const avg = regions.length
      ? regions.reduce((a, r) => a + r.index, 0) / regions.length
      : 0
    return { critical, elevated, stable, avg: Math.round(avg) }
  }, [index])

  const handleDownload = async () => {
    setDownloading(true)
    try { downloadCsv() } finally {
      setTimeout(() => setDownloading(false), 1500)
    }
  }

  return (
    <div className="page reports-page animate-in">
      <div className="page-header reports-header">
        <div>
          <h1 className="page-title title-glow">
            National <span className="text-gradient">Risk Report</span>
          </h1>
          <p className="page-subtitle">
            Decision intelligence for India's coastal waters — live composite risk assessment.
          </p>
        </div>
        <button className="btn-primary" onClick={handleDownload} disabled={downloading || loading}>
          <Download size={16} />
          {downloading ? 'Preparing…' : 'Download CSV Report'}
        </button>
      </div>

      {/* ---- National gauge + summary headline ---- */}
      <div className="reports-hero glass-card">
        <div className="national-gauge">
          <div
            className="gauge-arc"
            style={{
              background: `conic-gradient(
                ${nationalColor(stats.avg)} ${(stats.avg / 100) * 360}deg,
                rgba(120,190,255,0.12) 0deg
              )`,
            }}
          >
            <div className="gauge-hole">
              <span className="gauge-num">{loading ? '—' : stats.avg}</span>
              <span className="gauge-label">national risk</span>
            </div>
          </div>
        </div>

        <div className="hero-body">
          <div className="hero-title">
            <span className="live-dot" /> National Ocean Risk Index
          </div>
          <h3 className="hero-headline">
            {loading ? 'Computing…' : summaryHeadline(stats, index)}
          </h3>
          <div className="hero-breakdown">
            <span className="b-chip crit">{stats.critical} critical</span>
            <span className="b-chip elev">{stats.elevated} elevated</span>
            <span className="b-chip stable">{stats.stable} stable</span>
          </div>
        </div>
      </div>

      {/* ---- Executive summary ---- */}
      <motion.div
        className="glass-card panel exec-panel"
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="panel-header">
          <h3><FileBarChart size={15} /> Auto-generated Executive Summary</h3>
          <span className="panel-badge">AI WRITTEN</span>
        </div>
        {summary ? (
          <div className="exec-text">{summary.split('\n').map((l, i) => (
            <p key={i} className={l.startsWith('This report') ? 'exec-fineprint' : ''}>{l || '\u00a0'}</p>
          ))}</div>
        ) : (
          <div className="hint">Generating summary…</div>
        )}
      </motion.div>

      {/* ---- Risk ranking ---- */}
      <motion.div
        className="glass-card panel"
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
      >
        <div className="panel-header">
          <h3>Regional Risk Ranking</h3>
          <span className="panel-badge">LIVE</span>
        </div>

        {loading && <div className="hint">Loading risk index…</div>}

        <div className="risk-table">
          <div className="risk-row risk-head">
            <span className="c-rank">#</span>
            <span className="c-region">Region</span>
            <span className="c-score">Risk score</span>
            <span className="c-band">Status</span>
            <span className="c-temp">Temp signal</span>
            <span className="c-wave">Waves</span>
            <span className="c-alert">Alerts</span>
          </div>

          {index?.regions.map((r, i) => {
            const bandColor = BAND_COLORS[r.band] ?? '#22d3ee'
            const isTop = r.index > 25
            return (
              <motion.div
                key={r.location_id}
                className={`risk-row ${isTop ? 'risk-highlight' : ''}`}
                initial={{ opacity: 0, x: -14 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05 }}
              >
                <span className="c-rank rank-num">{i + 1}</span>
                <span className="c-region">
                  <span className="region-dot" style={{ background: bandColor }} />
                  <span className="region-name">{r.location}</span>
                </span>
                <span className="c-score">
                  <div className="score-bar-track">
                    <motion.div
                      className="score-bar-fill"
                      style={{ background: bandColor }}
                      initial={{ width: 0 }}
                      animate={{ width: `${Math.max(3, r.index)}%` }}
                      transition={{ delay: 0.2 + i * 0.05, duration: 0.7 }}
                    />
                  </div>
                  <span className="score-num">{r.index}</span>
                </span>
                <span className="c-band">
                  <span className={`band-pill ${r.band.toLowerCase()}`} style={{ color: bandColor, borderColor: bandColor + '66' }}>
                    {r.band}
                  </span>
                </span>
                <span className="c-temp">
                  {r.signal > 0.1 ? (
                    <span className="signal-hot">
                      <ArrowUpRight size={13} /> +{r.signal.toFixed(1)}°C
                    </span>
                  ) : (
                    <span className="signal-ok">
                      <ArrowDownRight size={13} /> {r.signal.toFixed(1)}°C
                    </span>
                  )}
                </span>
                <span className="c-wave">
                  <Waves size={12} className="inline-icon" /> {r.wave_height.toFixed(2)}m
                </span>
                <span className="c-alert">
                  {r.active_alerts > 0 ? (
                    <ShieldAlert size={14} className="alert-flag" />
                  ) : (
                    <Shield size={14} className="clear-flag" />
                  )}
                  <span className="alert-count">{r.active_alerts}</span>
                </span>
              </motion.div>
            )
          })}
        </div>

        <p className="model-note">
          Risk score = weighted blend of temperature anomaly (35%), active alerts (30%),
          wave height vs {index?.model?.safe_wave_m?.toFixed(1)}m small-craft threshold (20%), and short-term volatility (15%).
        </p>
      </motion.div>

      {/* ---- Factor mini-cards ---- */}
      <div className="reports-factors">
        {FACTORS.map((f, i) => (
          <motion.div
            className="glass-card factor-card"
            key={f.title}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 + i * 0.06 }}
          >
            <div className="factor-icon" style={{ color: f.color, background: `${f.color}18` }}>
              {f.icon}
            </div>
            <div className="factor-title">{f.title}</div>
            <div className="factor-desc">{f.desc}</div>
          </motion.div>
        ))}
      </div>
    </div>
  )
}

const FACTORS = [
  { title: 'Temperature Anomaly', desc: 'How far the sea is above its recent normal. Spikes signal heatwaves.', color: '#fb7185', icon: <Thermometer size={16} /> },
  { title: 'Active AI Alerts', desc: 'Unresolved anomaly detections, weighted by severity from low to critical.', color: '#f59e0b', icon: <ShieldAlert size={16} /> },
  { title: 'Wave Safety', desc: 'Wave height against the 1.0m small-craft limit — risk grows beyond it.', color: '#38bdf8', icon: <Waves size={16} /> },
  { title: 'Short-Term Volatility', desc: 'Hour-to-hour instability; rapid change often precedes dangerous events.', color: '#34d399', icon: <Activity size={16} /> },
]

function nationalColor(avg: number) {
  if (avg >= 60) return '#f43f5e'
  if (avg >= 35) return '#f59e0b'
  if (avg >= 15) return '#22d3ee'
  return '#34d399'
}

function summaryHeadline(stats: { critical: number; elevated: number; stable: number; avg: number }, index: RiskIndex | null) {
  if (stats.critical > 0) {
    return `Critical conditions across ${stats.critical} region${stats.critical > 1 ? 's' : ''} — national watch activated`
  }
  if (stats.elevated > 0) {
    const top = index?.regions?.[0]
    return `${top?.location.split(' (')[0] ?? 'A coastal region'} is elevated at ${top?.index}/100 — targeted advisories recommended`
  }
  return `Indian coastal waters broadly stable — normal maritime operations can proceed`
}