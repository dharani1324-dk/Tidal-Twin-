import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, ArrowUpRight, Filter, Gauge, Scale, Clock, ShieldCheck, ListOrdered, Database } from 'lucide-react'
import { fetchAnomalies } from '../api/client'
import './AnomalyIntel.css'

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: 'easeOut' as const } },
}

interface AnomalyRow {
  location_id: number
  location: string
  latitude: number | null
  longitude: number | null
  variable: string
  label: string
  unit: string
  model: number | null
  observed: number | null
  difference: number | null
  percent_difference: number | null
  severity: string
  status: string
  confidence: number
  confidence_level: string
  score: number
  magnitude: number
  spatial_extent_pct: number
  duration_h: number
  rate_per_h: number
  supporting_observations: number
  data_status: string
}

const SEV_ORDER: Record<string, number> = { high: 3, medium: 2, low: 1, none: 0 }
const SEV_COLOR: Record<string, string> = {
  high: '#f43f5e', medium: '#f59e0b', low: '#10b981', none: '#64748b',
}
const VAR_LABEL: Record<string, string> = {
  temperature: 'Sea Temperature', wave_height: 'Wave Height', salinity: 'Salinity', current_speed: 'Current Speed',
}

export default function AnomalyIntel() {
  const navigate = useNavigate()
  const [rows, setRows] = useState<AnomalyRow[]>([])
  const [weights, setWeights] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)
  const [variable, setVariable] = useState('')
  const [severity, setSeverity] = useState('')
  const [region, setRegion] = useState('')
  const [minConf, setMinConf] = useState(0)
  const [sort, setSort] = useState('severity')

  useEffect(() => {
    let alive = true
    setLoading(true)
    fetchAnomalies({
      variable: variable || undefined,
      severity: severity || undefined,
      region: region || undefined,
      min_confidence: minConf > 0 ? minConf : undefined,
      sort,
    })
      .then((d) => {
        if (!alive) return
        setRows(d.anomalies ?? [])
        setWeights(d.weights ?? {})
      })
      .catch(() => {
        if (alive) setRows([])
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [variable, severity, region, minConf, sort])

  const sorted = [...rows].sort((a, b) =>
    sort === 'magnitude'
      ? b.score - a.score
      : sort === 'confidence'
      ? b.confidence - a.confidence
      : (SEV_ORDER[b.severity] ?? 0) - (SEV_ORDER[a.severity] ?? 0) || b.score - a.score,
  )

  const goGlobe = (r: AnomalyRow) => {
    navigate(`/globe?focus=${r.location_id}&var=${r.variable}`)
  }

  return (
    <div className="page anomaly-intel animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title title-glow">
            Anomaly <span className="text-gradient">Intelligence</span>
          </h1>
          <p className="page-subtitle">
            Every anomaly is ranked by a defined, transparent score — magnitude, spatial extent, duration,
            confidence, supporting observations and rate of change. No random values.
          </p>
        </div>
        <div className="an-count glass-card">
          <AlertTriangle size={16} />
          <span>{loading ? '…' : sorted.length} RANKED</span>
        </div>
      </div>

      {/* Scoring transparency card */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="glass-card score-note">
        <div className="score-note-title">
          <Gauge size={15} />
          <b>How the anomaly score is computed</b>
        </div>
        <div className="score-weights">
          {(Object.entries(weights) as [string, number][]).map(([k, v]) => (
            <span key={k} className="sw-item">
              <i className="sw-bar" style={{ width: `${v * 100}%` }} />
              <em>{k.replace(/_/g, ' ')}</em>
              <b>{Math.round(v * 100)}%</b>
            </span>
          ))}
        </div>
      </motion.div>

      {/* Filters */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="glass-card an-filters">
        <Filter size={15} className="an-filter-icon" />
        <select className="an-select" value={variable} onChange={(e) => setVariable(e.target.value)} aria-label="Variable">
          <option value="">All variables</option>
          {Object.entries(VAR_LABEL).map(([k, l]) => (
            <option key={k} value={k}>{l}</option>
          ))}
        </select>
        <select className="an-select" value={severity} onChange={(e) => setSeverity(e.target.value)} aria-label="Severity">
          <option value="">All severities</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
        <input
          className="an-input"
          placeholder="Region…"
          value={region}
          onChange={(e) => setRegion(e.target.value)}
        />
        <label className="an-minconf">
          <span>Min confidence <b>{minConf}%</b></span>
          <input type="range" min={0} max={100} step={5} value={minConf} onChange={(e) => setMinConf(Number(e.target.value))} />
        </label>
        <select className="an-select an-sort" value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort">
          <option value="severity">Sort · Severity</option>
          <option value="magnitude">Sort · Score</option>
          <option value="confidence">Sort · Confidence</option>
        </select>
      </motion.div>

      {/* Table */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="glass-card an-table-card">
        {loading ? (
          <div className="hint">Scanning the network…</div>
        ) : sorted.length === 0 ? (
          <div className="hint">
            No anomalies above threshold in available data. This is an honest reading of a calm ocean.
          </div>
        ) : (
          <table className="an-table">
            <thead>
              <tr>
                <th>Region</th>
                <th>Variable</th>
                <th>Model</th>
                <th>Observed</th>
                <th>Δ</th>
                <th>Δ%</th>
                <th>Severity</th>
                <th>Conf</th>
                <th>Score</th>
                <th>Duration</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((r) => (
                <tr key={`${r.location_id}-${r.variable}`} className="an-row" onClick={() => goGlobe(r)}>
                  <td className="an-region">
                    <b>{r.location}</b>
                    <em>{r.latitude != null ? `${r.latitude.toFixed(2)}°N, ${r.longitude?.toFixed(2)}°E` : '—'}</em>
                  </td>
                  <td>{VAR_LABEL[r.variable] ?? r.variable}</td>
                  <td className="num">{r.model != null ? r.model.toFixed(2) : '—'}{r.unit === '°C' ? '°C' : ''}</td>
                  <td className="num">{r.observed != null ? r.observed.toFixed(2) : '—'}{r.unit === '°C' ? '°C' : ''}</td>
                  <td className="num" style={{ color: (r.difference ?? 0) >= 0 ? '#f87171' : '#22d3ee', fontWeight: 700 }}>
                    {r.difference != null ? `${r.difference > 0 ? '+' : ''}${r.difference.toFixed(2)}` : '—'}
                  </td>
                  <td className="num">{r.percent_difference != null ? `${r.percent_difference.toFixed(1)}%` : '—'}</td>
                  <td>
                    <span className="an-sev" style={{ color: SEV_COLOR[r.severity] ?? '#64748b' }}>
                      {r.severity.toUpperCase()}
                    </span>
                  </td>
                  <td className="num">
                    <span className="an-confcell">
                      {r.confidence}
                      <i className="an-confbar"><i style={{ width: `${r.confidence}%`, background: r.confidence >= 80 ? '#34d399' : r.confidence >= 55 ? '#fbbf24' : '#f87171' }} /></i>
                    </span>
                  </td>
                  <td className="num an-score">{r.score?.toFixed(1) ?? '—'}</td>
                  <td className="num">{r.duration_h != null ? `${r.duration_h}h` : '—'}</td>
                  <td>
                    <span className={`an-status an-status-${r.data_status ?? 'unknown'}`}>
                      {(r.data_status ?? 'unknown').toUpperCase()}
                    </span>
                  </td>
                  <td><ArrowUpRight size={15} className="an-arrow" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <div className="an-footnote">
          <span><Clock size={12} /> Duration = consecutive hours beyond the history-conditioned normal</span>
          <span><Scale size={12} /> Magnitude scaled against the variable's high band</span>
          <span><ShieldCheck size={12} /> Confidence shared with the compare engine</span>
          <span><Database size={12} /> Status reflects the provenance of the underlying rows</span>
          <span><ListOrdered size={12} /> Click any row to fly to it on the 3D globe</span>
        </div>
      </motion.div>
    </div>
  )
}