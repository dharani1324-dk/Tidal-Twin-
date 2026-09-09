import { useEffect, useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Thermometer, Waves, Wind, RefreshCw, MapPin, Activity,
  TrendingUp, TrendingDown, Sparkles, Radio, Ship, CheckCircle2,
} from 'lucide-react'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'
import {
  fetchLocations, fetchObservations, triggerRefresh, fetchValidationSituation,
} from '../api/client'
import './Dashboard.css'

interface Situation {
  location_id: number
  location: string
  status: 'safe' | 'caution' | 'danger'
  temperature_anomaly: string
  wave_state: string
  observation_confidence: number
  model_trust: number
  disagreement: boolean
  headline: string
}

interface Location {
  id: number
  name: string
  region_type: string
  country: string
  latitude: number | null
  longitude: number | null
}

interface Observation {
  id: number
  timestamp: string
  sea_surface_temperature: number | null
  wave_height: number | null
  salinity: number | null
  current_speed: number | null
  source: string
}

/** Simple ocean health score (0-100) from live readings */
function healthScore(obs: Observation[]): number {
  if (obs.length === 0) return 65
  const stops = obs.slice(0, 12).map((o) => o.sea_surface_temperature ?? 0)
  const avg = stops.reduce((a, b) => a + b, 0) / Math.max(stops.length, 1)
  const range = Math.max(avg - 24, 0)
  const tempPts = Math.max(0, 100 - range * 4)
  const stablePts = stops.length > 1 && Math.abs(stops[stops.length - 1] - stops[0]) < 0.6 ? 12 : 5
  return Math.min(98, Math.round(tempPts + stablePts))
}

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: (i: number) => ({
    opacity: 1, y: 0,
    transition: { delay: i * 0.08, duration: 0.5, ease: 'easeOut' as const },
  }),
}

export default function Dashboard() {
  const [locations, setLocations] = useState<Location[]>([])
  const [selected, setSelected] = useState<Location | null>(null)
  const [obs, setObs] = useState<Observation[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [situation, setSituation] = useState<Situation[]>([])

  useEffect(() => {
    fetchLocations()
      .then((data) => {
        setLocations(data)
        setSelected(data[0] ?? null)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!selected) return
    setLoading(true)
    fetchObservations(selected.id, 96)
      .then(setObs)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [selected])

  useEffect(() => {
    fetchValidationSituation()
      .then((d) => setSituation(d.regions ?? []))
      .catch(() => {})
  }, [])

  const sit = useMemo(() => {
    if (situation.length === 0) return null
    const n = situation.length
    const danger = situation.filter((s) => s.status === 'danger').length
    const caution = situation.filter((s) => s.status === 'caution').length
    const disagreement = situation.filter((s) => s.disagreement).length
    const obsAvg = Math.round(situation.reduce((a, s) => a + s.observation_confidence, 0) / n)
    const trustAvg = Math.round(situation.reduce((a, s) => a + s.model_trust, 0) / n)
    const topAnomaly = ['HIGH', 'MODERATE'].find((lv) => situation.some((s) => s.temperature_anomaly === lv)) ?? 'LOW'
    return { danger, caution, obsAvg, trustAvg, disagreement, topAnomaly }
  }, [situation])

  const latest = obs[0]
  const score = healthScore(obs)

  // Build chart data (chronological, labeled HH:00)
  const chartData = useMemo(() => {
    return [...obs].reverse().map((o) => ({
      time: new Date(o.timestamp).toISOString().slice(11, 16),
      temp: o.sea_surface_temperature ?? null,
      wave: o.wave_height ?? null,
    }))
  }, [obs])

  // Sparkline values
  const temps = chartData.map((d) => d.temp ?? 0)
  const trendUp = temps.length > 1 && temps[temps.length - 1] >= temps[0]

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await triggerRefresh()
      if (selected) setObs(await fetchObservations(selected.id, 96))
    } catch (e: any) {
      setError(e.message)
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <div className="page dashboard animate-in">
      {/* ============ CINEMATIC HEADER ============ */}
      <motion.div className="dashboard-hero glass-card" initial="hidden" animate="show">
        <div className="hero-bg" />
        <div className="hero-content">
          <div className="hero-eyebrow">
            <Radio size={13} /> INDIAN OCEAN · LIVE TELEMETRY
          </div>
          <h1 className="hero-title">
            Ocean <span className="text-gradient">Mission Control</span>
          </h1>
          <p className="hero-sub">
            Real-time digital twin of India's coastal waters · live satellite & marine intelligence
          </p>
          <div className="hero-actions">
            <button className="btn-primary" onClick={handleRefresh} disabled={refreshing}>
              <RefreshCw size={16} className={refreshing ? 'spin' : ''} />
              {refreshing ? 'Syncing…' : 'Sync Live Data'}
            </button>
            <span className="hero-live">
              <span className="live-dot" /> <Sparkles size={13} /> Auto-refreshes from public marine APIs
            </span>
          </div>
        </div>

        {/* Live time — pinned to IST so the demo always shows India time */}
        <motion.div className="hero-clock" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.6 }}>
          <div className="clock-time">
            {new Date().toLocaleTimeString('en-IN', {
              timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true,
            })}
            <span className="clock-zone">IST</span>
          </div>
          <div className="clock-date">
            {new Date().toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata', weekday: 'long', day: 'numeric', month: 'long' })}
          </div>
        </motion.div>
      </motion.div>

      {/* ============ LOCATION STRIP ============ */}
      <div className="location-strip">
        <AnimatePresence>
          {locations.map((loc, i) => (
            <motion.button
              key={loc.id}
              variants={fadeUp}
              initial="hidden"
              animate="show"
              custom={i}
              className={`location-chip ${selected?.id === loc.id ? 'location-chip-active' : ''}`}
              onClick={() => setSelected(loc)}
            >
              <MapPin size={14} />
              {loc.name.replace(' Coast', '').replace(' Sea', '')}
            </motion.button>
          ))}
        </AnimatePresence>
      </div>

      {error && (
        <div className="glass-card error-banner">
          <p>⚠️ {error} — is the backend running? (uvicorn app.main:app)</p>
        </div>
      )}

      {/* ============ OCEAN SITUATION STRIP ============ */}
      {sit && (
        <motion.div
          className="ocean-situation glass-card"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25, duration: 0.4 }}
        >
          <span className="sit-brand"><Activity size={14} /> OCEAN SITUATION</span>
          <span className="sit-chip">
            <span className={`sit-dot sit-dot-${sit.danger > 0 ? 'danger' : 'ok'}`} />
            {sit.danger} coast{sit.danger === 1 ? '' : 's'} at risk
          </span>
          <span className="sit-chip">
            <TrendingUp size={12} style={{ color: sit.topAnomaly === 'HIGH' ? '#f43f5e' : '#f59e0b' }} />
            Temp anomaly {sit.topAnomaly}
          </span>
          <span className="sit-chip">
            <Radio size={12} />
            Obs confidence <b>{sit.obsAvg}%</b>
          </span>
          <span className="sit-chip">
            <Sparkles size={12} />
            Model trust <b>{sit.trustAvg}%</b>
          </span>
          <span className={`sit-chip sit-chip-agree ${sit.disagreement ? 'sit-chip-alert' : ''}`}>
            {sit.disagreement ? <TrendingDown size={12} /> : <CheckCircle2 size={12} />}
            {sit.disagreement ? `${sit.disagreement} disagreement${sit.disagreement === 1 ? '' : 's'} flagged` : 'Model ↔ reality tracking'}
          </span>
        </motion.div>
      )}

      {/* ============ HERO METRIC CARDS ============ */}
      <div className="stats-grid">
        <MetricCard
          icon={<Thermometer size={22} />}
          label="Sea Temperature"
          value={latest?.sea_surface_temperature != null ? `${latest.sea_surface_temperature.toFixed(1)}°C` : '—'}
          sub={trendUp ? 'Rising' : 'Stable'}
          subIcon={trendUp ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
          accent="#22d3ee"
          delay={0.05}
        />
        <MetricCard
          icon={<Waves size={22} />}
          label="Wave Height"
          value={latest?.wave_height != null ? `${latest.wave_height.toFixed(2)} m` : '—'}
          sub="Significant wave"
          accent="#3b82f6"
          delay={0.1}
        />
        <MetricCard
          icon={<Wind size={22} />}
          label="Data Source"
          value={latest?.source || '—'}
          sub="Open-Meteo Marine · NOAA models"
          accent="#818cf8"
          delay={0.15}
        />
        <MetricCard
          icon={<Activity size={22} />}
          label="Readings"
          value={`${obs.length}`}
          sub={selected?.name ?? ''}
          accent="#34d399"
          delay={0.2}
        />
      </div>

      {/* ============ MAIN GRID ============ */}
      <div className="dashboard-grid">
        {/* Health gauge */}
        <motion.div className="glass-card panel health-panel" variants={fadeUp} initial="hidden" whileInView="show">
          <div className="panel-header">
            <h3>Ocean Health Index</h3>
            <span className="panel-badge">AI</span>
          </div>
          <div className="health-ring-wrap">
            <div
              className="health-ring"
              style={{ background: `conic-gradient(#22d3ee ${score * 3.6}deg, rgba(34,211,238,0.12) 0deg)` }}
            >
              <div className="health-ring-inner">
                <span className="health-score">{score}</span>
                <span className="health-score-label">/ 100</span>
              </div>
            </div>
            <div className="health-caption">Computed from live sea surface temperature readings.</div>
          </div>
        </motion.div>

        {/* Temperature trend */}
        <motion.div className="glass-card panel chart-panel" variants={fadeUp} initial="hidden" whileInView="show" custom={1}>
          <div className="panel-header">
            <h3>Sea Surface Temperature</h3>
            <span className="panel-badge">°C</span>
          </div>
          <div className="chart-wrap">
            {loading ? (
              <div className="hint">Loading telemetry…</div>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="gTemp" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.45} />
                      <stop offset="100%" stopColor="#22d3ee" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="rgba(148,163,184,0.08)" vertical={false} />
                  <XAxis dataKey="time" tick={{ fill: '#5b7493', fontSize: 11 }} tickLine={false} axisLine={false}
                    minTickGap={40} />
                  <YAxis tick={{ fill: '#5b7493', fontSize: 11 }} tickLine={false} axisLine={false} width={40}
                    domain={['dataMin - 1', 'dataMax + 1']} />
                  <Tooltip contentStyle={{ background: 'rgba(6,18,40,0.9)', border: '1px solid rgba(34,211,238,0.3)', borderRadius: 12, color: '#e6f1ff' }} />
                  <Area type="monotone" dataKey="temp" stroke="#22d3ee" strokeWidth={2.5} fill="url(#gTemp)"
                    name="Temp °C" />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </motion.div>
      </div>

      {/* ============ LOWER GRID ============ */}
      <div className="dashboard-grid">
        {/* Wave height trend */}
        <motion.div className="glass-card panel chart-panel" variants={fadeUp} initial="hidden" whileInView="show" custom={1}>
          <div className="panel-header">
            <h3>Wave Height</h3>
            <span className="panel-badge">m</span>
          </div>
          <div className="chart-wrap">
            {loading ? (
              <div className="hint">Loading telemetry…</div>
            ) : (
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="gWave" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.4} />
                      <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="rgba(148,163,184,0.08)" vertical={false} />
                  <XAxis dataKey="time" tick={{ fill: '#5b7493', fontSize: 11 }} tickLine={false} axisLine={false}
                    minTickGap={40} />
                  <YAxis tick={{ fill: '#5b7493', fontSize: 11 }} tickLine={false} axisLine={false} width={40} />
                  <Tooltip contentStyle={{ background: 'rgba(6,18,40,0.9)', border: '1px solid rgba(59,130,246,0.3)', borderRadius: 12 }} />
                  <Area type="monotone" dataKey="wave" stroke="#3b82f6" strokeWidth={2.5} fill="url(#gWave)"
                    name="Wave m" />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </motion.div>

        {/* Region monitor list */}
        <motion.div className="glass-card panel" variants={fadeUp} initial="hidden" whileInView="show" custom={2}>
          <div className="panel-header">
            <h3>Monitored Regions</h3>
            <span className="panel-badge">{locations.length} ACTIVE</span>
          </div>
          <ul className="region-list">
            {locations.map((loc) => (
              <li
                key={loc.id}
                className={`${selected?.id === loc.id ? 'region-active' : ''}`}
                onClick={() => setSelected(loc)}
              >
                <span className="region-dot" />
                <span className="region-name">{loc.name}</span>
                <span className="region-type">{loc.region_type}</span>
              </li>
            ))}
          </ul>
        </motion.div>
      </div>

      {/* ============ RECENT READINGS TABLE ============ */}
      <motion.div className="glass-card panel table-panel" variants={fadeUp} initial="hidden" whileInView="show" custom={3}>
        <div className="panel-header">
          <h3>Recent Telemetry</h3>
          <span className="panel-badge"><Ship size={12} /> BUOY DATA</span>
        </div>
        <div className="readings-table">
          <table>
            <thead>
              <tr><th>Time (UTC)</th><th>Temp °C</th><th>Wave m</th><th>Trend</th></tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={4} className="hint">Loading real data…</td></tr>}
              {!loading && obs.length === 0 && (
                <tr><td colSpan={4} className="hint">Run "Sync Live Data" to pull ocean telemetry.</td></tr>
              )}
              {!loading && obs.slice(0, 10).map((o, i) => {
                const pv = obs[i + 1]?.sea_surface_temperature
                const diff = pv != null && o.sea_surface_temperature != null ? o.sea_surface_temperature - pv : 0
                return (
                  <tr key={o.id}>
                    <td>{new Date(o.timestamp).toUTCString().slice(17, 25)} UTC</td>
                    <td>{o.sea_surface_temperature?.toFixed(1) ?? '—'}</td>
                    <td>{o.wave_height?.toFixed(2) ?? '—'}</td>
                    <td>
                      {Math.abs(diff) < 0.01 ? (
                        <span className="trend-flat">—</span>
                      ) : diff > 0 ? (
                        <span className="trend-up">▲ {diff.toFixed(1)}</span>
                      ) : (
                        <span className="trend-down">▼ {Math.abs(diff).toFixed(1)}</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </motion.div>
    </div>
  )
}

/* ---- Premium metric card ---- */
function MetricCard({
  icon, label, value, sub, subIcon, accent, delay,
}: {
  icon: React.ReactNode
  label: string
  value: string
  sub?: string
  subIcon?: React.ReactNode
  accent: string
  delay?: number
}) {
  return (
    <motion.div
      className="glass-card metric-card"
      variants={fadeUp}
      initial="hidden"
      animate="show"
      custom={delay ?? 0}
      whileHover={{ y: -4 }}
    >
      <div className="metric-icon" style={{ color: accent, background: `${accent}1c`, borderColor: `${accent}40` }}>
        {icon}
      </div>
      <div className="metric-body">
        <span className="metric-label">{label}</span>
        <span className="metric-value" style={{ color: accent }}>{value}</span>
        {sub && (
          <span className="metric-sub">
            {subIcon ?? null} {sub}
          </span>
        )}
      </div>
      <div className="metric-glow" style={{ background: `radial-gradient(circle, ${accent}30, transparent 70%)` }} />
    </motion.div>
  )
}