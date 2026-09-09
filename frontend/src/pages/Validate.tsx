import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import {
  Scale, ThermometerSun, Waves, Gauge, GitCompareArrows,
  ShieldAlert, CheckCircle2, Activity, MapPin, Sparkles,
} from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from 'recharts'
import {
  fetchLocations, fetchComparison, fetchValidationDifference,
  fetchValidationConfidence, fetchValidationSituation,
} from '../api/client'
import './Validate.css'

interface DiffField {
  field: string
  label: string
  unit: string
  model: number | null
  observed: number | null
  deviation: number | null
  deviation_level: 'high' | 'moderate' | 'low' | 'unknown'
  direction: 'above' | 'below' | 'at'
}

interface RegionDiff {
  location_id: number
  location: string
  latest_time: string | null
  window_hours: number
  fields: DiffField[]
  explanation: {
    headline: string
    possible_cause: string
    affected_note: string
    confidence: number
    focus_field?: string
  }
}

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

interface Confidence {
  location_id: number
  location: string
  observation_confidence: number
  freshness_hours: number | null
  field_coverage: number
  sample_size: number
  agreement: number
  model_trust: number
  drift: boolean
  disagreement: boolean
  interpretation: string
}

interface ComparePoint {
  time: string
  forecast_temperature?: number | null
  observed_temperature?: number | null
  forecast_wave?: number | null
  observed_wave?: number | null
}

interface Region {
  id: number
  name: string
  latitude: number | null
  longitude: number | null
}

const STATUS_META = {
  safe: { color: '#34d399', label: 'SAFE' },
  caution: { color: '#f59e0b', label: 'CAUTION' },
  danger: { color: '#f43f5e', label: 'DANGER' },
}

const LEVEL_COLOR: Record<string, string> = {
  high: '#f43f5e',
  moderate: '#f59e0b',
  low: '#34d399',
  unknown: '#64748b',
}

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: (i: number) => ({
    opacity: 1, y: 0,
    transition: { delay: i * 0.07, duration: 0.5, ease: 'easeOut' as const },
  }),
}

export default function Validate() {
  const [locs, setLocs] = useState<Region[]>([])
  const [selected, setSelected] = useState<Region | null>(null)
  const [diff, setDiff] = useState<RegionDiff | null>(null)
  const [sit, setSit] = useState<Situation | null>(null)
  const [conf, setConf] = useState<Confidence | null>(null)
  const [compare, setCompare] = useState<{ temp: ComparePoint[]; wave: ComparePoint[] }>({ temp: [], wave: [] })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchLocations()
      .then((data) => {
        setLocs(data)
        setSelected(data[0] ?? null)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!selected) return
    setLoading(true)

    const byId = (regions: { location_id: number }[]) => regions.find((r) => r.location_id === selected.id)

    Promise.all([
      fetchValidationDifference(selected.id),
      fetchValidationSituation(),
      fetchValidationConfidence(),
      fetchComparison(selected.id),
    ])
      .then(([d, s, cf, cmp]) => {
        setDiff(d.region ?? null)
        setSit(byId(s.regions ?? []) as Situation | null)
        setConf(byId(cf.regions ?? []) as Confidence | null)
        const series: ComparePoint[] = cmp?.series ?? []
        setCompare({
          temp: series.map((p: ComparePoint) => ({
            time: new Date(p.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            forecast_temperature: p.forecast_temperature ?? null,
            observed_temperature: p.observed_temperature ?? null,
          })),
          wave: series.map((p: ComparePoint) => ({
            time: new Date(p.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            forecast_wave: p.forecast_wave ?? null,
            observed_wave: p.observed_wave ?? null,
          })),
        })
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [selected])

  const situationChips = useMemo(() => {
    if (!sit) return []
    const status = STATUS_META[sit.status]
    return [
      { label: 'Coastal status', value: status.label, color: status.color },
      { label: 'Temp anomaly', value: sit.temperature_anomaly, color: sit.temperature_anomaly === 'HIGH' ? '#f43f5e' : sit.temperature_anomaly === 'MODERATE' ? '#f59e0b' : '#34d399' },
      { label: 'Wave intensity', value: sit.wave_state, color: sit.wave_state === 'HIGH' ? '#f43f5e' : sit.wave_state === 'MODERATE' ? '#f59e0b' : '#34d399' },
      { label: 'Observation confidence', value: `${sit.observation_confidence}%`, color: '#22d3ee' },
      { label: 'Agreement', value: sit.disagreement ? 'DISAGREEMENT' : 'TRACKING MODEL', color: sit.disagreement ? '#f43f5e' : '#34d399' },
    ]
  }, [sit])

  return (
    <div className="page validate-page animate-in">
      <div className="page-header validate-header">
        <div>
          <h1 className="page-title title-glow">
            Model <span className="text-gradient">Validation</span> Workspace
          </h1>
          <p className="page-subtitle">
            Where the AI model meets reality — deviation per field, observation confidence, and what the gap means.
          </p>
        </div>
        <div className="validate-count glass-card">
          <Scale size={16} />
          <span>{loading ? '…' : 'MODEL ↔ REALITY'}</span>
        </div>
      </div>

      {/* ---- region strip ---- */}
      <div className="location-strip">
        {locs.map((loc, i) => (
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
      </div>

      {loading && !diff && <div className="glass-card hint-panel"><div className="hint">Loading validation telemetry…</div></div>}

      {/* ---- disagreement banner ---- */}
      {sit?.disagreement && (
        <motion.div className="glass-card disagreement-banner" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          <ShieldAlert size={18} />
          <span>HIGH MODEL–OBSERVATION DISAGREEMENT DETECTED — {sit.headline}.</span>
        </motion.div>
      )}

      {/* ---- situation strip ---- */}
      {situationChips.length > 0 && (
        <div className="val-situation">
          {situationChips.map((c) => (
            <div key={c.label} className="val-chip" style={{ '--chip': c.color } as React.CSSProperties}>
              <span className="val-chip-label">{c.label}</span>
              <span className="val-chip-value" style={{ color: c.color }}>{c.value}</span>
            </div>
          ))}
        </div>
      )}

      <div className="val-grid">
        {/* ---- MODEL | OBSERVED | DEVIATION ---- */}
        <motion.div className="glass-card panel val-diff-panel" variants={fadeUp} initial="hidden" animate="show" custom={0}>
          <div className="panel-header">
            <h3>MODEL <GitCompareArrows size={14} /> REALITY</h3>
            <span className="panel-badge"><Activity size={12} /> LATEST HOUR</span>
          </div>
          <div className="diff-columns">
            <div className="diff-col diff-col-model"><span>MODEL</span></div>
            <div className="diff-col diff-col-obs"><span>OBSERVED</span></div>
            <div className="diff-col diff-col-dev"><span>DEVIATION</span></div>
          </div>
          <div className="diff-rows">
            {diff?.fields.length === 0 && <div className="hint">No measured fields to compare yet.</div>}
            {diff?.fields.map((f) => (
              <div key={f.field} className="diff-row">
                <div className="diff-field-name">
                  <span>{f.label}</span>
                  <span className="diff-unit">{f.unit}</span>
                </div>
                <div className="diff-val">{f.model != null ? f.model.toFixed(2) : '—'}</div>
                <div className="diff-val diff-val-obs">{f.observed != null ? f.observed.toFixed(2) : '—'}</div>
                <div className="diff-dev" style={{ color: LEVEL_COLOR[f.deviation_level] }}>
                  {f.deviation == null ? '—' : `${f.deviation > 0 ? '+' : f.deviation < 0 ? '−' : ''}${Math.abs(f.deviation).toFixed(2)}`}
                  <span className="diff-dev-tag">{f.direction === 'at' ? 'baseline' : f.direction}</span>
                </div>
              </div>
            ))}
          </div>
          <div className="diff-note">
            Model = AI baseline (recent conditional normal). Observed = latest in-situ reading. Deviation = observed − model.
          </div>
        </motion.div>

        {/* ---- Interpretation (WHY) ---- */}
        <motion.div className="glass-card panel val-why-panel" variants={fadeUp} initial="hidden" animate="show" custom={1}>
          <div className="panel-header">
            <h3>Why it matters</h3>
            <span className="panel-badge"><Sparkles size={12} /> INTERPRETED</span>
          </div>
          {diff?.explanation ? (
            <>
              <p className="val-why-headline">{diff.explanation.headline}</p>
              <p className="val-why-cause"><strong>Possible cause:</strong> {diff.explanation.possible_cause}</p>
              {diff.explanation.affected_note && (
                <p className="val-why-cause"><strong>Affects:</strong> {diff.explanation.affected_note}</p>
              )}
              <div className="val-why-conf">
                <Gauge size={14} />
                <span>Interpretation confidence</span>
                <b>{diff.explanation.confidence}%</b>
              </div>
            </>
          ) : (
            <div className="hint">Select a coast to interpret.</div>
          )}
        </motion.div>

        {/* ---- Confidence meters ---- */}
        <motion.div className="glass-card panel val-conf-panel" variants={fadeUp} initial="hidden" animate="show" custom={2}>
          <div className="panel-header">
            <h3>Confidence & Trust</h3>
            <span className="panel-badge"><CheckCircle2 size={12} /> ENGINE</span>
          </div>
          {conf ? (
            <div className="conf-meters">
              <Meter label="Observation" value={conf.observation_confidence} color="#22d3ee" />
              <Meter label="Model trust" value={conf.model_trust} color="#818cf8" />
              <div className="conf-facts">
                <span>Coverage <b>{Math.round(conf.field_coverage * 100)}%</b> of fields</span>
                <span>Sampling <b>{conf.sample_size}</b> readings</span>
                <span>Freshness <b>{conf.freshness_hours != null ? `${conf.freshness_hours}h` : '—'}</b></span>
                <span>Agreement <b>{Math.round(conf.agreement * 100)}%</b></span>
              </div>
              <p className="conf-interpretation">{conf.interpretation}</p>
            </div>
          ) : (
            <div className="hint">Loading confidence…</div>
          )}
        </motion.div>

        {/* ---- Model vs observed chart ---- */}
        <motion.div className="glass-card panel val-chart-panel" variants={fadeUp} initial="hidden" animate="show" custom={3}>
          <div className="panel-header">
            <h3>Forecast track verification</h3>
            <span className="panel-badge"><ThermometerSun size={12} /> °C</span>
          </div>
          <div className="val-chart">
            <CompareChart data={compare.temp} aKey="forecast_temperature" bKey="observed_temperature" aName="Model forecast" bName="Observed" />
          </div>
          <div className="panel-header val-chart-sub">
            <h3>Wave height verification</h3>
            <span className="panel-badge"><Waves size={12} /> m</span>
          </div>
          <div className="val-chart">
            <CompareChart data={compare.wave} aKey="forecast_wave" bKey="observed_wave" aName="Model forecast" bName="Observed" />
          </div>
        </motion.div>
      </div>
    </div>
  )
}

function Meter({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="conf-meter">
      <div className="conf-meter-top">
        <span>{label} confidence</span>
        <b style={{ color }}>{value}%</b>
      </div>
      <div className="conf-meter-bar">
        <div className="conf-meter-fill" style={{ width: `${Math.min(100, value)}%`, background: color }} />
      </div>
    </div>
  )
}

function CompareChart({ data, aKey, bKey, aName, bName }: {
  data: ComparePoint[]; aKey: string; bKey: string; aName: string; bName: string
}) {
  const gray = 'rgba(148,163,184,0.12)'
  return (
    <ResponsiveContainer width="100%" height={180}>
      <LineChart data={data} margin={{ top: 6, right: 12, bottom: 0, left: -14 }}>
        <CartesianGrid stroke={gray} vertical={false} />
        <XAxis dataKey="time" tick={{ fill: '#5b7493', fontSize: 10 }} tickLine={false} axisLine={false} minTickGap={40} />
        <YAxis tick={{ fill: '#5b7493', fontSize: 10 }} tickLine={false} axisLine={false} width={44} domain={['dataMin - 0.4', 'dataMax + 0.4']} />
        <Tooltip contentStyle={{ background: 'rgba(6,18,40,0.92)', border: '1px solid rgba(34,211,238,0.3)', borderRadius: 12, color: '#e6f1ff', fontSize: 12 }} />
        <Legend wrapperStyle={{ fontSize: 11, color: '#94a3b8' }} iconType="plainline" />
        <Line type="monotone" dataKey={aKey} name={aName} stroke="#818cf8" strokeWidth={2.2} dot={false} />
        <Line type="monotone" dataKey={bKey} name={bName} stroke="#34d399" strokeWidth={2.2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}