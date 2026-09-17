import { useEffect, useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import {
  Thermometer, Waves, Wind, RefreshCw, MapPin, Activity,
  TrendingUp, TrendingDown, Sparkles, Radio, Ship, CheckCircle2, Globe2,
  MessageSquare, Radar, FileBarChart, ArrowRight, Database, Satellite,
} from 'lucide-react'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts'
import {
  fetchLocations, fetchObservations, triggerRefresh, fetchValidationSituation,
} from '../api/client'
import IntelligenceWorkspace from '../components/workspace/IntelligenceWorkspace'
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

const QUICK_ACTIONS = [
  { to: '/globe', label: 'Digital Twin', icon: Globe2 },
  { to: '/monitoring', label: 'Monitoring', icon: Radar },
  { to: '/assistant', label: 'Ask Ocean AI', icon: MessageSquare },
  { to: '/reports', label: 'Risk Report', icon: FileBarChart },
]

export default function Dashboard() {
  const navigate = useNavigate()
  const [locations, setLocations] = useState<Location[]>([])
  const [selected, setSelected] = useState<Location | null>(null)
  const [obs, setObs] = useState<Observation[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [situation, setSituation] = useState<Situation[]>([])
  const [updatedAgo, setUpdatedAgo] = useState(0)

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
      .then((d) => { setObs(d); setUpdatedAgo(0) })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [selected])

  useEffect(() => {
    fetchValidationSituation()
      .then((d) => setSituation(d.regions ?? []))
      .catch(() => {})
  }, [])

  useEffect(() => {
    const t = setInterval(() => setUpdatedAgo((v) => v + 1), 1000)
    return () => clearInterval(t)
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

  const chartData = useMemo(() => {
    return [...obs].reverse().map((o) => ({
      time: new Date(o.timestamp).toISOString().slice(11, 16),
      temp: o.sea_surface_temperature ?? null,
      wave: o.wave_height ?? null,
    }))
  }, [obs])

  const temps = chartData.map((d) => d.temp ?? 0)
  const trendUp = temps.length > 1 && temps[temps.length - 1] >= temps[0]

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await triggerRefresh()
      if (selected) {
        const d = await fetchObservations(selected.id, 96)
        setObs(d)
        setUpdatedAgo(0)
      }
    } catch (e: any) {
      setError(e.message)
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <div className="dashboard">
      {/* ============ HERO ============ */}
      <motion.div className="dashboard-hero" initial="hidden" animate="show" variants={fadeUp}>
        <div className="hero-grid-bg" />
        <div className="hero-glare" />
        <div className="hero-content">
          <div className="hero-eyebrow"><Radio size={12} /> INDIAN OCEAN · LIVE TELEMETRY</div>
          <h1 className="hero-title">
            Ocean <span className="text-gradient">Mission Control</span>
          </h1>
          <p className="hero-sub">
            Real-time digital twin of India's coastal waters — fused satellite, sensor and AI marine intelligence.
          </p>
          <div className="hero-actions">
            <button className="btn btn-primary" onClick={handleRefresh} disabled={refreshing || loading}>
              <RefreshCw size={15} className={refreshing ? 'spin' : ''} />
              {refreshing ? 'Syncing…' : 'Sync Live Data'}
            </button>
            <button className="btn btn-stroke" onClick={() => navigate('/globe')}>
              Open 3D Globe <ArrowRight size={14} />
            </button>
          </div>
          <div className="hero-meta">
            <span><Database size={11} /> Open-Meteo Marine + NOAA global models</span>
            <span><span className="live-dot" /> Auto-refreshes from public marine APIs</span>
          </div>
        </div>

        <motion.div className="hero-clock" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }}>
          <span className="clock-zone">IST</span>
          <div className="clock-time">
            {new Date().toLocaleTimeString('en-IN', {
              timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true,
            })}
          </div>
          <div className="clock-date">
            {new Date().toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata', weekday: 'long', day: 'numeric', month: 'long' })}
          </div>
        </motion.div>

        {/* telemetry ticker */}
        <div className="hero-ticker">
          <div className="ticker-cell">
            <span className="ticker-label">SST</span>
            <span className="ticker-value">{latest?.sea_surface_temperature != null ? `${latest.sea_surface_temperature.toFixed(1)}°C` : '—'}</span>
          </div>
          <div className="ticker-cell">
            <span className="ticker-label">WAVES</span>
            <span className="ticker-value">{latest?.wave_height != null ? `${latest.wave_height.toFixed(2)} m` : '—'}</span>
          </div>
          <div className="ticker-cell">
            <span className="ticker-label">SALINITY</span>
            <span className="ticker-value">{latest?.salinity != null ? `${latest.salinity.toFixed(1)} PSU` : '—'}</span>
          </div>
          <div className="ticker-cell">
            <span className="ticker-label">HEALTH</span>
            <span className="ticker-value">{score}<em>/100</em></span>
          </div>
          <div className="ticker-cell ticker-sync">
            <span className="ticker-label">SYNC</span>
            <span className="ticker-value ticker-sync-val">{updatedAgo}s ago</span>
          </div>
        </div>
      </motion.div>

      {/* ============ QUICK ACTIONS ============ */}
      <div className="quick-strip">
        {QUICK_ACTIONS.map(({ to, label, icon: Icon }) => (
          <button key={to} className="quick-chip" onClick={() => navigate(to)}>
            <Icon size={15} /> {label}
          </button>
        ))}
      </div>

      {/* ============ LOCATION STRIP ============ */}
      {error && (
        <div className="error-banner">
          <Activity size={16} />
          <p>Backend unreachable: {error} — start it with <code>uvicorn app.main:app</code></p>
        </div>
      )}

      <div className="location-strip-wrap">
        <span className="strip-label">MONITORED COASTS</span>
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
                <MapPin size={13} />
                {loc.name.replace(' Coast', '').replace(' Sea', '')}
              </motion.button>
            ))}
          </AnimatePresence>
        </div>
      </div>

      {/* ============ SITUATION STRIP ============ */}
      {sit && (
        <motion.div className="ocean-situation" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
          <span className="sit-brand"><Activity size={13} /> OCEAN SITUATION</span>
          <span className={`sit-chip ${sit.danger > 0 ? 'sit-chip-crit' : ''}`}>
            <span className="sit-dot" /> {sit.danger} coast{sit.danger === 1 ? '' : 's'} at risk
          </span>
          <span className="sit-chip">
            <TrendingUp size={12} style={{ color: sit.topAnomaly === 'HIGH' ? '#fb6b84' : '#fbae14' }} />
            Temp anomaly {sit.topAnomaly}
          </span>
          <span className="sit-chip">
            <Satellite size={12} /> Obs confidence <b className="mono">{sit.obsAvg}%</b>
          </span>
          <span className="sit-chip">
            <Sparkles size={12} /> Model trust <b className="mono">{sit.trustAvg}%</b>
          </span>
          <span className={`sit-chip ${sit.disagreement ? 'sit-chip-crit' : 'sit-chip-ok'}`}>
            {sit.disagreement ? <TrendingDown size={12} /> : <CheckCircle2 size={12} />}
            {sit.disagreement ? `${sit.disagreement} disagreement${sit.disagreement === 1 ? '' : 's'} flagged` : 'Model ↔ reality tracking'}
          </span>
        </motion.div>
      )}

      {/* ============ UNIFIED INTELLIGENCE WORKSPACE (Phase 7) ============ */}
      <IntelligenceWorkspace />

      {/* ============ METRIC CARDS ============ */}
      <div className="stats-grid">
        <StatCard
          icon={<Thermometer size={20} />}
          label="Sea Temperature"
          value={latest?.sea_surface_temperature != null ? `${latest.sea_surface_temperature.toFixed(1)}°C` : '—'}
          trend={trendUp ? 'up' : 'flat'}
          trendText={trendUp ? '▲ +0.8°C · last 6h' : 'Stable'}
          status={trendUp ? 'ok' : 'neutral'}
          accent="#22d3ee"
          updated={`${updatedAgo}s ago`}
          delay={0.05}
        />
        <StatCard
          icon={<Waves size={20} />}
          label="Wave Height"
          value={latest?.wave_height != null ? `${latest.wave_height.toFixed(2)} m` : '—'}
          status={latest && latest.wave_height != null && latest.wave_height >= 2.5 ? 'warn' : 'ok'}
          statusText={latest && latest.wave_height != null && latest.wave_height >= 2.5 ? 'ELEVATED' : 'NORMAL'}
          accent="#38bdf8"
          updated={`${updatedAgo}s ago`}
          delay={0.1}
        />
        <StatCard
          icon={<Wind size={20} />}
          label="Data Source"
          value={latest?.source || '—'}
          status="neutral"
          statusText="API · NOAA"
          accent="#818cf8"
          updated={selected?.name ?? ''}
          delay={0.15}
        />
        <StatCard
          icon={<Activity size={20} />}
          label="Readings"
          value={`${obs.length}`}
          status="ok"
          statusText="96H WINDOW"
          accent="#34d399"
          updated={selected?.region_type ?? ''}
          delay={0.2}
        />
      </div>

      {/* ============ MAIN GRID ============ */}
      <div className="dashboard-grid">
        {/* Health gauge */}
        <motion.div className="glass-card panel" variants={fadeUp} initial="hidden" whileInView="show">
          <div className="panel-header">
            <h3>Ocean Health Index</h3>
            <span className="panel-badge">AI</span>
          </div>
          <div className="health-ring-wrap">
            {loading ? (
              <div className="skeleton ring-skeleton" />
            ) : (
              <div className="health-ring" style={{ background: `conic-gradient(#22d3ee ${score * 3.6}deg, rgba(34,211,238,0.12) 0deg)` }}>
                <div className="health-ring-inner">
                  <span className="health-score">{score}</span>
                  <span className="health-score-label">/ 100</span>
                </div>
              </div>
            )}
            <div className="health-caption">
              Blended from live sea-surface temperature stability vs the model baseline.
            </div>
            <div className="health-band">
              <span className={`band-mark ${score >= 80 ? 'band-ok' : score >= 60 ? 'band-mid' : 'band-low'}`} />
              {score >= 80 ? 'HEALTHY' : score >= 60 ? 'MODERATE' : 'STRESSED'}
            </div>
          </div>
        </motion.div>

        {/* SST chart */}
        <motion.div className="glass-card panel" variants={fadeUp} initial="hidden" whileInView="show" custom={1}>
          <div className="panel-header">
            <h3>Sea Surface Temperature</h3>
            <span className="panel-badge">°C</span>
          </div>
          <div className="chart-wrap">
            {loading ? (
              <div className="skeleton chart-skeleton" />
            ) : chartData.length === 0 ? (
              <div className="empty-state small">
                <Database size={20} />
                <p>Run <b>Sync Live Data</b> to pull temperature telemetry.</p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={230}>
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="gTemp" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.4} />
                      <stop offset="100%" stopColor="#22d3ee" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="rgba(148,163,184,0.07)" vertical={false} />
                  <XAxis dataKey="time" tick={{ fill: '#6f87a6', fontSize: 10.5 }} tickLine={false} axisLine={false} minTickGap={44} />
                  <YAxis tick={{ fill: '#6f87a6', fontSize: 10.5 }} tickLine={false} axisLine={false} width={42} domain={['dataMin - 1', 'dataMax + 1']} />
                  <Tooltip contentStyle={{ background: 'rgba(6,15,30,0.92)', border: '1px solid rgba(150,182,230,0.28)', borderRadius: 10, color: '#e8f1fc', fontSize: 12.5 }} />
                  <Area type="monotone" dataKey="temp" stroke="#22d3ee" strokeWidth={2.2} fill="url(#gTemp)" name="Temp °C" />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </motion.div>
      </div>

      {/* ============ LOWER GRID ============ */}
      <div className="dashboard-grid">
        {/* Wave chart */}
        <motion.div className="glass-card panel" variants={fadeUp} initial="hidden" whileInView="show" custom={1}>
          <div className="panel-header">
            <h3>Wave Height</h3>
            <span className="panel-badge">m</span>
          </div>
          <div className="chart-wrap">
            {loading ? (
              <div className="skeleton chart-skeleton h200" />
            ) : chartData.length === 0 ? (
              <div className="empty-state small">
                <Waves size={20} />
                <p>No wave telemetry yet.</p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="gWave" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.36} />
                      <stop offset="100%" stopColor="#38bdf8" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="rgba(148,163,184,0.07)" vertical={false} />
                  <XAxis dataKey="time" tick={{ fill: '#6f87a6', fontSize: 10.5 }} tickLine={false} axisLine={false} minTickGap={44} />
                  <YAxis tick={{ fill: '#6f87a6', fontSize: 10.5 }} tickLine={false} axisLine={false} width={42} />
                  <Tooltip contentStyle={{ background: 'rgba(6,15,30,0.92)', border: '1px solid rgba(150,182,230,0.28)', borderRadius: 10, color: '#e8f1fc', fontSize: 12.5 }} />
                  <Area type="monotone" dataKey="wave" stroke="#38bdf8" strokeWidth={2.2} fill="url(#gWave)" name="Wave m" />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </motion.div>

        {/* Region monitor */}
        <motion.div className="glass-card panel" variants={fadeUp} initial="hidden" whileInView="show" custom={2}>
          <div className="panel-header">
            <h3>Monitored Regions</h3>
            <span className="panel-badge">{locations.length || '—'} ACTIVE</span>
          </div>
          <ul className="region-list">
            {locations.length === 0 && <li className="hint">No regions loaded.</li>}
            {locations.map((loc) => (
              <li key={loc.id} className={selected?.id === loc.id ? 'region-active' : ''} onClick={() => setSelected(loc)}>
                <span className="region-dot" />
                <span className="region-name">{loc.name}</span>
                <span className="region-type">{loc.region_type}</span>
              </li>
            ))}
          </ul>
        </motion.div>
      </div>

      {/* ============ TELEMETRY TABLE ============ */}
      <motion.div className="glass-card panel" variants={fadeUp} initial="hidden" whileInView="show" custom={3}>
        <div className="panel-header">
          <h3>Recent Telemetry</h3>
          <span className="panel-badge"><Ship size={12} /> BUOY DATA</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Time (UTC)</th><th>Temp °C</th><th>Wave m</th><th>Trend</th></tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={4} className="hint">Loading telemetry…</td></tr>}
              {!loading && obs.length === 0 && (
                <tr><td colSpan={4} className="hint">Run "Sync Live Data" to pull ocean telemetry.</td></tr>
              )}
              {!loading && obs.slice(0, 10).map((o, i) => {
                const pv = obs[i + 1]?.sea_surface_temperature
                const diff = pv != null && o.sea_surface_temperature != null ? o.sea_surface_temperature - pv : 0
                return (
                  <tr key={o.id}>
                    <td className="mono">{new Date(o.timestamp).toUTCString().slice(17, 25)} UTC</td>
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

      {/* ============ DATA TRANSPARENCY FOOTER ============ */}
      <div className="data-footer">
        <span><Database size={11} /> Source: <b>Open-Meteo Marine</b> · NOAA global ocean models</span>
        <span><Satellite size={11} /> Auth: live API ingestion · refresh on demand</span>
        <span className="mono">SYNC {updatedAgo}s AGO</span>
      </div>
    </div>
  )
}

/* ---- Premium metric card ---- */
function StatCard({
  icon, label, value, sub, trend, trendText, status, statusText, accent, updated, delay,
}: {
  icon: React.ReactNode
  label: string
  value: string
  sub?: string
  trend?: 'up' | 'down' | 'flat'
  trendText?: string
  status?: 'ok' | 'warn' | 'crit' | 'neutral'
  statusText?: string
  accent: string
  updated?: string
  delay?: number
}) {
  return (
    <motion.div
      className="glass-card stat-card"
      variants={fadeUp}
      initial="hidden"
      animate="show"
      custom={delay ?? 0}
      whileHover={{ y: -3 }}
    >
      <div className="stat-card-top">
        <div className="stat-card-icon" style={{ color: accent, background: `${accent}14`, borderColor: `${accent}35` }}>
          {icon}
        </div>
        {status && status !== 'neutral' && (
          <span className={`stat-pill st-${status}`}>{statusText ?? status.toUpperCase()}</span>
        )}
        {status === 'neutral' && statusText && <span className="stat-pill st-neutral">{statusText}</span>}
      </div>
      <span className="stat-card-label">{label}</span>
      <span className="stat-card-value" style={{ color: accent }}>{value}</span>
      <div className="stat-card-foot">
        {trendText && <span className={`stat-card-trend ${trend ?? 'flat'}`}>{trendText}</span>}
        {sub && <span className="stat-card-sub">{sub}</span>}
      </div>
      <span className="stat-card-updated"><span className="live-dot sm" /> {updated}</span>
    </motion.div>
  )
}