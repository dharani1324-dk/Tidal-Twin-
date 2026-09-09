import { useEffect, useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Radar, ShieldAlert, ShieldCheck, Activity, ScanLine, Clock,
  Thermometer, Waves, Zap, CheckCircle2, CircleDot,
} from 'lucide-react'
import { fetchAlerts, runAnomalyScan, fetchForecasts } from '../api/client'
import './Monitoring.css'

interface Alert {
  id: number
  location_id: number
  alert_type: string
  severity: string
  description: string
  confidence: number | null
  status: string
  created_at: string
  location_name: string
}

interface ForecastRegion {
  location: string
  forecast: { hours_ahead: number; temperature: number; wave_height?: number }[]
}

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: (i: number) => ({
    opacity: 1, y: 0,
    transition: { delay: i * 0.08, duration: 0.5, ease: 'easeOut' as const },
  }),
}

export default function Monitoring() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [forecasts, setForecasts] = useState<ForecastRegion[]>([])
  const [scanning, setScanning] = useState(false)
  const [filter, setFilter] = useState<'all' | 'active' | 'resolved'>('all')
  const [scanMsg, setScanMsg] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const [a, f] = await Promise.all([fetchAlerts(filter), fetchForecasts()])
      setAlerts(a)
      setForecasts(f.forecasts ?? f)
    } catch {
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter])

  const runScan = async () => {
    setScanning(true)
    setScanMsg(null)
    try {
      const res = await runAnomalyScan()
      const created = res.scan?.alerts_created ?? 0
      const resolved = res.alerts_resolved ?? 0
      setScanMsg(
        created > 0
          ? `⚠️ ${created} new anomaly(s) detected · ${resolved} resolved`
          : `✅ AI radar scanned all regions · ${resolved} resolved`,
      )
      const fresh = await fetchAlerts(filter)
      setAlerts(fresh)
    } catch (e: any) {
      setScanMsg(`Error: ${e.message}`)
    } finally {
      setScanning(false)
    }
  }

  const counts = useMemo(() => {
    const active = alerts.filter((a) => a.status === 'active').length
    const resolved = alerts.filter((a) => a.status === 'resolved').length
    const critical = alerts.filter((a) => a.severity === 'critical').length
    const high = alerts.filter((a) => a.severity === 'high').length
    return { active, resolved, critical, high }
  }, [alerts])

  return (
    <div className="page monitoring-page animate-in">
      <div className="page-header monitoring-header">
        <div>
          <h1 className="page-title title-glow">
            Ocean <span className="text-gradient">Surveillance</span>
          </h1>
          <p className="page-subtitle">
            AI anomaly detection across India's coastal waters — real readings, explainable intelligence.
          </p>
        </div>
        <button className="btn-primary" onClick={runScan} disabled={scanning}>
          <ScanLine size={16} className={scanning ? 'spin' : ''} />
          {scanning ? 'Scanning…' : 'Run AI Radar Scan'}
        </button>
      </div>

      {/* Scan feedback */}
      <AnimatePresence>
        {scanMsg && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="glass-card scan-msg"
          >
            {scanMsg}
          </motion.div>
        )}
      </AnimatePresence>

      {/* ---- Summary cards ---- */}
      <div className="stats-grid monitoring-stats">
        <SumCard icon={<ShieldAlert size={20} />} label="Active Alerts" value={counts.active} accent="#fb7185" delay={0} />
        <SumCard icon={<Zap size={20} />} label="High Severity" value={counts.high} accent="#f59e0b" delay={0.05} />
        <SumCard icon={<CheckCircle2 size={20} />} label="Resolved" value={counts.resolved} accent="#34d399" delay={0.1} />
        <SumCard icon={<Activity size={20} />} label="Total Logged" value={alerts.length} accent="#22d3ee" delay={0.15} />
      </div>

      {/* ---- Main grid ---- */}
      <div className="monitoring-grid">
        {/* AI Radar panel */}
        <motion.div className="glass-card panel radar-panel" variants={fadeUp} initial="hidden" animate="show" custom={0}>
          <div className="panel-header">
            <h3>AI Risk Radar</h3>
            <span className="panel-badge">ML ENGINE</span>
          </div>
          <div className="radar-visual">
            <div className="radar-disc">
              <div className="radar-ring r1" />
              <div className="radar-ring r2" />
              <div className="radar-ring r3" />
              <div className="radar-sweep" />
              <div className="radar-core">
                <Radar size={22} />
              </div>
            </div>
            <div className="radar-label">
              <span className="live-dot" /> AI scanning every region continuously
            </div>
          </div>
        </motion.div>

        {/* Alert feed */}
        <motion.div className="glass-card panel feed-panel" variants={fadeUp} initial="hidden" animate="show" custom={1}>
          <div className="panel-header">
            <h3>Alert Feed</h3>
            <div className="filter-tabs">
              {(['all', 'active', 'resolved'] as const).map((f) => (
                <button
                  key={f}
                  className={`filter-tab ${filter === f ? 'filter-tab-on' : ''}`}
                  onClick={() => setFilter(f)}
                >
                  {f}
                </button>
              ))}
            </div>
          </div>

          <div className="alert-list">
            {loading && <div className="hint">Loading alerts…</div>}
            {!loading && alerts.length === 0 && (
              <div className="hint">
                <ShieldCheck size={18} /> No alerts yet — run an AI scan, or simulate an event for the demo.
              </div>
            )}
            {alerts.map((a) => (
              <AlertCard key={a.id} alert={a} />
            ))}
          </div>
        </motion.div>
      </div>

      {/* ---- Forecast section ---- */}
      <motion.div className="glass-card panel forecast-panel" variants={fadeUp} initial="hidden" animate="show" custom={2}>
        <div className="panel-header">
          <h3>AI 12-Hour Forecast</h3>
          <span className="panel-badge"><Clock size={12} /> NEXT 12H</span>
        </div>
        <div className="forecast-grid">
          {forecasts.slice(0, 8).map((f) => {
            const last = f.forecast[f.forecast.length - 1]
            const isUp = last && f.forecast[0] ? last.wave_height! >= f.forecast[0].wave_height! : true
            return (
              <div key={f.location} className="forecast-card">
                <div className="forecast-name">{f.location.split(' (')[0]}</div>
                <div className="forecast-temp">{last?.temperature?.toFixed(1)}°C</div>
                <div className={`forecast-trend ${isUp ? 'trend-up' : 'trend-down'}`}>
                  {isUp ? '▲ waves rising' : '▼ waves falling'} · {last?.wave_height?.toFixed(2)} m
                </div>
              </div>
            )
          })}
        </div>
      </motion.div>
    </div>
  )
}

/* ---- Summary card ---- */
function SumCard({ icon, label, value, accent, delay }: {
  icon: React.ReactNode; label: string; value: number; accent: string; delay: number
}) {
  return (
    <motion.div
      className="glass-card stat-card"
      variants={fadeUp}
      initial="hidden"
      animate="show"
      custom={delay}
    >
      <div className="stat-icon" style={{ color: accent, background: `${accent}1c`, borderColor: `${accent}40` }}>
        {icon}
      </div>
      <div className="stat-body">
        <span className="stat-label">{label}</span>
        <span className="stat-value" style={{ color: accent }}>{value}</span>
      </div>
    </motion.div>
  )
}

/* ---- Alert card ---- */
function AlertCard({ alert }: { alert: Alert }) {
  const colors: Record<string, string> = {
    critical: '#f43f5e',
    high: '#f59e0b',
    medium: '#22d3ee',
    low: '#34d399',
  }
  const color = colors[alert.severity] ?? '#22d3ee'
  const resolved = alert.status === 'resolved'
  const Icon = alert.alert_type.includes('temperature') ? Thermometer : Waves

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={`alert-card ${resolved ? 'alert-resolved' : ''}`}
    >
      <div className="alert-icon" style={{ color, background: `${color}1a`, borderColor: `${color}40` }}>
        <Icon size={17} />
      </div>
      <div className="alert-body">
        <div className="alert-title">
          {alert.alert_type.replace('_', ' ').toUpperCase()}
          {resolved && <span className="alert-resolved-tag">RESOLVED</span>}
        </div>
        <div className="alert-desc">{alert.description}</div>
        <div className="alert-meta">
          <span className="alert-loc">{alert.location_name}</span>
          <span className="alert-sev" style={{ color }}>{alert.severity.toUpperCase()}</span>
          <span className="alert-conf">
            <CircleDot size={11} /> {Math.round((alert.confidence ?? 0) * 100)}%
          </span>
          {alert.created_at && (
            <span className="alert-time">
              {new Date(alert.created_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
        </div>
      </div>
      <div className="alert-severity-bar" style={{ background: color }} />
    </motion.div>
  )
}