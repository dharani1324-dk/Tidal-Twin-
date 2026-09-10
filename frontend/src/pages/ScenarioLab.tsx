import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Activity,
  AlertTriangle,
  CalendarClock,
  Database,
  Droplets,
  FlaskConical,
  Gauge,
  History,
  Loader2,
  MapPin,
  Minus,
  Play,
  RotateCcw,
  SlidersHorizontal,
  TextQuote,
  Thermometer,
  TrendingDown,
  TrendingUp,
  Waves,
  Wind,
} from 'lucide-react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { fetchFuture, fetchLocations, runCounterfactual, runWhatIf } from '../api/client'
import './ScenarioLab.css'

type TabId = 'projection' | 'counterfactual' | 'future'

interface LabLocation {
  id: number
  name: string
  region_type?: string
  latitude?: number | null
  longitude?: number | null
}

interface ScenarioParameters {
  wind_percent: number
  temperature_delta: number
  salinity_delta: number
  mixing_factor: number
}

interface Snapshot {
  sst: number | null
  wave: number | null
  current: number | null
}

interface ProjectionResult {
  scenario: ScenarioParameters
  actual: Snapshot
  projected: Snapshot
  delta: Snapshot
  narrative: string
}

interface ComparisonRow {
  key: string
  field: string
  unit: string
  actual: number | null
  scenario: number | null
  delta: number | null
}

interface CounterFactualResult {
  narrative: string
  rows: ComparisonRow[]
  snapshot: Snapshot
}

interface FutureWindow {
  horizon_days: number
  predicted_temp: number | null
  predicted_wave: number | null
  predicted_current: number | null
  confidence: number | null
  data_sources: string[]
}

interface ProfilePoint {
  label: string
  sstActual: number | null
  sstProjected: number | null
  waveActual: number | null
  waveProjected: number | null
}

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: 'easeOut' as const } },
}

const tooltipStyle = {
  background: 'rgba(10, 22, 40, 0.92)',
  border: '1px solid rgba(34, 211, 238, 0.3)',
  borderRadius: 12,
  color: '#e6f1ff',
  backdropFilter: 'blur(8px)',
}

const PROJECTION_VARS: { key: keyof Snapshot; label: string; icon: ReactNode; color: string; dp: number; unit: string }[] = [
  { key: 'sst', label: 'Sea Surface Temp', icon: <Thermometer size={16} />, color: '#67e8f9', dp: 1, unit: '°C' },
  { key: 'wave', label: 'Wave Height', icon: <Waves size={16} />, color: '#22d3ee', dp: 2, unit: 'm' },
  { key: 'current', label: 'Current Speed', icon: <Gauge size={16} />, color: '#14b8a6', dp: 2, unit: 'm/s' },
]

const TABS: { id: TabId; label: string; icon: ReactNode }[] = [
  { id: 'projection', label: 'Projection', icon: <Activity size={15} /> },
  { id: 'counterfactual', label: 'Counterfactual', icon: <History size={15} /> },
  { id: 'future', label: 'Future Windows', icon: <CalendarClock size={15} /> },
]

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

function pickNum(o: Record<string, unknown>, keys: string[]): number | null {
  for (const k of keys) {
    const v = num(o[k])
    if (v != null) return v
  }
  return null
}

function pickStr(o: Record<string, unknown>, keys: string[]): string {
  for (const k of keys) {
    const v = o[k]
    if (typeof v === 'string' && v.length > 0) return v
  }
  return ''
}

function rounded(v: number, dp: number): number {
  const f = 10 ** dp
  return Math.round(v * f) / f
}

function ramp(a: number | null, b: number | null, f: number): number | null {
  if (b == null) return a
  if (a == null) return b
  return rounded(a + (b - a) * f, 2)
}

function dpFor(unit: string): number {
  return unit === '°C' ? 1 : 2
}

function signed(v: number, dp: number, unit: string): string {
  return `${v > 0 ? '+' : ''}${v.toFixed(dp)}${unit}`
}

function verdictFor(key: string, actual: number | null, projected: number | null): 'improved' | 'degraded' | 'neutral' {
  if (actual == null || projected == null) return 'neutral'
  const d = projected - actual
  if (Math.abs(d) < 0.005) return 'neutral'
  if (key === 'sst' || key === 'wave' || key === 'current') return d > 0 ? 'degraded' : 'improved'
  return 'neutral'
}

function confidenceColor(c: number | null): string {
  if (c == null) return '#5b7493'
  if (c >= 70) return '#10b981'
  if (c >= 50) return '#f59e0b'
  return '#f43f5e'
}

function confidenceClass(c: number | null): string {
  if (c == null) return 'neutral'
  if (c >= 70) return 'positive'
  if (c >= 50) return 'warn'
  return 'negative'
}

function normalizeProjection(raw: unknown): ProjectionResult {
  const r = (raw ?? {}) as Record<string, unknown>
  const inputs = (r.inputs ?? {}) as Record<string, unknown>
  const output = (r.output ?? {}) as Record<string, unknown>
  const projRaw = (r.projected ?? {}) as Record<string, unknown>
  const actRaw = (r.actual ?? {}) as Record<string, unknown>
  const dltRaw = (r.delta ?? {}) as Record<string, unknown>

  const sstProj = pickNum(projRaw, ['sst']) ?? pickNum(output, ['sst', 'projected_sst'])
  const waveProj = pickNum(projRaw, ['wave', 'wave_height']) ?? pickNum(output, ['wave_height', 'wave'])
  const curProj = pickNum(projRaw, ['current', 'current_speed']) ?? pickNum(output, ['current_speed', 'current'])

  const sstAct = pickNum(actRaw, ['sst']) ?? (() => {
    const d = pickNum(dltRaw, ['sst'])
    return d != null && sstProj != null ? rounded(sstProj - d, 2) : null
  })()
  const waveAct = pickNum(actRaw, ['wave', 'wave_height']) ?? (() => {
    const d = pickNum(dltRaw, ['wave'])
    return d != null && waveProj != null ? rounded(waveProj - d, 2) : null
  })()
  const curAct = pickNum(actRaw, ['current', 'current_speed']) ?? (() => {
    const d = pickNum(dltRaw, ['current'])
    return d != null && curProj != null ? rounded(curProj - d, 2) : null
  })()

  return {
    scenario: {
      wind_percent: pickNum(inputs, ['wind_percent']) ?? 0,
      temperature_delta: pickNum(inputs, ['temperature_delta', 'temp_delta']) ?? 0,
      salinity_delta: pickNum(inputs, ['salinity_delta']) ?? 0,
      mixing_factor: pickNum(inputs, ['mixing_factor']) ?? 1,
    },
    actual: { sst: sstAct, wave: waveAct, current: curAct },
    projected: { sst: sstProj, wave: waveProj, current: curProj },
    delta: {
      sst: pickNum(dltRaw, ['sst']) ?? null,
      wave: pickNum(dltRaw, ['wave']) ?? null,
      current: pickNum(dltRaw, ['current']) ?? null,
    },
    narrative: pickStr(r, ['narrative', 'caveat']),
  }
}

function normalizeCounterfactual(raw: unknown): CounterFactualResult {
  const r = (raw ?? {}) as Record<string, unknown>
  const act = (r.actual ?? {}) as Record<string, unknown>
  const scen = (r.scenario ?? {}) as Record<string, unknown>
  const diffs = (r.differences ?? {}) as Record<string, unknown>
  const comp = Array.isArray(r.comparison) ? (r.comparison as Record<string, unknown>[]) : null

  const fields: { key: string; label: string; unit: string; alt: string[] }[] = [
    { key: 'sst', label: 'Sea Surface Temperature', unit: '°C', alt: ['sst'] },
    { key: 'wave', label: 'Wave Height', unit: 'm', alt: ['wave', 'wave_height'] },
    { key: 'salinity', label: 'Salinity', unit: 'PSU', alt: ['salinity'] },
  ]

  const rows: ComparisonRow[] = fields.map(({ key, label, unit, alt }) => {
    if (comp) {
      const c = comp.find((x) => String(x.field ?? '').toLowerCase() === key)
      if (c) {
        const a = pickNum(c, ['actual'])
        const s = pickNum(c, ['scenario', 'value'])
        const d = pickNum(c, ['delta']) ?? (a != null && s != null ? rounded(s - a, 2) : null)
        return { key, field: label, unit, actual: a, scenario: s, delta: d }
      }
    }
    const a = pickNum(act, alt)
    const s = pickNum(scen, alt)
    const d = pickNum(diffs, alt) ?? (a != null && s != null ? rounded(s - a, 2) : null)
    return { key, field: label, unit, actual: a, scenario: s, delta: d }
  })

  return {
    narrative: pickStr(r, ['narrative', 'driver_note']),
    rows: rows.filter((row) => row.actual != null || row.scenario != null || row.delta != null),
    snapshot: {
      sst: pickNum(act, ['sst']),
      wave: pickNum(act, ['wave', 'wave_height']),
      current: pickNum(act, ['current', 'current_speed']),
    },
  }
}

function normalizeFuture(raw: unknown): FutureWindow[] {
  const r = (raw ?? {}) as Record<string, unknown>
  const windows = Array.isArray(r.windows) ? (r.windows as Record<string, unknown>[]) : []
  return windows
    .map((w) => ({
      horizon_days: Math.max(0, Number(w.horizon_days ?? 0)),
      predicted_temp: pickNum(w, ['predicted_temp', 'projected_sst']),
      predicted_wave: pickNum(w, ['predicted_wave', 'projected_wave']),
      predicted_current: pickNum(w, ['predicted_current', 'projected_current', 'projected_current_speed']),
      confidence: pickNum(w, ['confidence']),
      data_sources: (Array.isArray(w.data_sources) ? (w.data_sources as unknown[]) : []).map((s) => String(s)),
    }))
    .sort((a, b) => a.horizon_days - b.horizon_days)
}

function DeltaBadge({ cls, text }: { cls: 'positive' | 'negative' | 'neutral'; text: string }) {
  const Icon = cls === 'positive' ? TrendingUp : cls === 'negative' ? TrendingDown : Minus
  return (
    <span className={`lab-delta ${cls}`}>
      <Icon size={13} />
      {text}
    </span>
  )
}

function LabSlider(props: {
  icon: ReactNode
  label: string
  value: number
  min: number
  max: number
  step: number
  low: string
  high: string
  format: (v: number) => string
  onChange: (v: number) => void
}) {
  const { icon, label, value, min, max, step, low, high, format, onChange } = props
  const pct = Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100))
  return (
    <div className="lab-slider">
      <div className="lab-slider-head">
        <span className="lab-slider-name">
          {icon}
          {label}
        </span>
        <span className="lab-slider-value">{format(value)}</span>
      </div>
      <div className="lab-slider-zone">
        <div className="lab-slider-track">
          <div className="lab-slider-fill" style={{ width: `${pct}%` }} />
        </div>
        <input
          type="range"
          className="lab-range"
          min={min}
          max={max}
          step={step}
          value={value}
          aria-label={label}
          onChange={(e) => onChange(Number(e.target.value))}
        />
      </div>
      <div className="lab-slider-ends">
        <span>{low}</span>
        <span>{high}</span>
      </div>
    </div>
  )
}

function Skeletons({ chart = true }: { chart?: boolean }) {
  return (
    <div className="lab-skel-stack">
      {chart && <div className="lab-skeleton lab-skel-chart" />}
      <div className="lab-skel-row">
        <div className="lab-skeleton lab-skel-card" />
        <div className="lab-skeleton lab-skel-card" />
        <div className="lab-skeleton lab-skel-card" />
      </div>
    </div>
  )
}

function EmptyState({ hasLocation }: { hasLocation: boolean }) {
  return (
    <div className="lab-empty">
      {hasLocation ? <FlaskConical size={30} /> : <MapPin size={30} />}
      <h3>{hasLocation ? 'Ready when you are' : 'Select a location'}</h3>
      <p>
        {hasLocation
          ? 'Tune the simulation parameters and hit Run Simulation to project the ocean response.'
          : 'Pick an ocean region from the dropdown to begin exploring what-if scenarios.'}
      </p>
    </div>
  )
}

function ProjectionPane(props: {
  projection: ProjectionResult
  snapshot: Snapshot
  profile: ProfilePoint[]
}) {
  const { projection, snapshot, profile } = props
  return (
    <>
      <div className="lab-chart">
        <div className="lab-chart-title">
          <Activity size={15} />
          Projected trajectory — next 72h (illustrative)
        </div>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={profile} margin={{ top: 10, right: 20, bottom: 0, left: -10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(120, 190, 255, 0.12)" />
            <XAxis dataKey="label" stroke="#5b7493" fontSize={11} tickLine={false} axisLine={{ stroke: 'rgba(120, 190, 255, 0.2)' }} />
            <YAxis stroke="#5b7493" fontSize={11} tickLine={false} axisLine={false} width={40} />
            <Tooltip contentStyle={tooltipStyle} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line type="monotone" dataKey="sstActual" name="Actual SST (°C)" stroke="#67e8f9" strokeWidth={2} strokeDasharray="5 5" dot={false} />
            <Line type="monotone" dataKey="sstProjected" name="Projected SST (°C)" stroke="#f59e0b" strokeWidth={2.5} dot={false} />
            <Line type="monotone" dataKey="waveActual" name="Actual Wave (m)" stroke="#14b8a6" strokeWidth={2} strokeDasharray="5 5" dot={false} />
            <Line type="monotone" dataKey="waveProjected" name="Projected Wave (m)" stroke="#f43f5e" strokeWidth={2.5} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="lab-comparison">
        {PROJECTION_VARS.map(({ key, label, icon, color, dp, unit }) => {
          const actual = projection.actual[key] ?? snapshot[key]
          const projected = projection.projected[key]
          const delta = actual != null && projected != null ? rounded(projected - actual, dp) : projection.delta[key]
          const v = verdictFor(key, actual, projected)
          const cls = v === 'improved' ? 'positive' : v === 'degraded' ? 'negative' : 'neutral'
          return (
            <div key={key} className="lab-comp-card glass-card">
              <div className="lab-comp-head">
                <span className="lab-comp-icon" style={{ color }}>{icon}</span>
                <span className="lab-comp-name">{label}</span>
              </div>
              <div className="lab-comp-values">
                <div className="lab-comp-value-block">
                  <span className="lab-comp-label">Actual</span>
                  <span className="lab-comp-value">
                    {actual != null ? `${actual.toFixed(dp)}${unit}` : '—'}
                  </span>
                </div>
                <div className="lab-comp-value-block">
                  <span className="lab-comp-label">Projected</span>
                  <span className="lab-comp-value lab-comp-value-proj">
                    {projected != null ? `${projected.toFixed(dp)}${unit}` : '—'}
                  </span>
                </div>
              </div>
              <DeltaBadge cls={cls} text={delta != null ? signed(delta, dp, unit) : 'n/a'} />
            </div>
          )
        })}
      </div>
    </>
  )
}

function CounterPane(props: {
  result: CounterFactualResult
  params: ScenarioParameters
  barData: { field: string; actual: number; scenario: number }[]
}) {
  const { result, params, barData } = props
  const chips = [
    { label: 'Wind', value: params.wind_percent > 0 ? `+${params.wind_percent}%` : `${params.wind_percent}%` },
    { label: 'SST Δ', value: `${params.temperature_delta > 0 ? '+' : ''}${params.temperature_delta.toFixed(1)}°C` },
    { label: 'Salinity Δ', value: `${params.salinity_delta > 0 ? '+' : ''}${params.salinity_delta.toFixed(1)} PSU` },
    { label: 'Mixing', value: `${params.mixing_factor.toFixed(1)}×` },
  ]
  return (
    <>
      <div className="lab-narrative">
        <TextQuote size={15} />
        <p>
          <strong>What would have happened if…</strong>{' '}
          {result.narrative || 'No parameter changes applied — the counterfactual mirrors observed conditions.'}
        </p>
      </div>

      <div className="lab-config-chips">
        {chips.map((c) => (
          <span key={c.label} className="lab-chip">
            {c.label}: <b>{c.value}</b>
          </span>
        ))}
      </div>

      {result.rows.length > 0 && (
        <div className="lab-table-wrap glass-card">
          <table className="lab-table">
            <thead>
              <tr>
                <th>Field</th>
                <th>Actual</th>
                <th>Scenario</th>
                <th>Delta</th>
              </tr>
            </thead>
            <tbody>
              {result.rows.map((row) => {
                const v = verdictFor(row.key, row.actual, row.scenario)
                const cls = v === 'improved' ? 'positive' : v === 'degraded' ? 'negative' : 'neutral'
                const dp = dpFor(row.unit)
                return (
                  <tr key={row.key}>
                    <td>{row.field}</td>
                    <td>{row.actual != null ? `${row.actual.toFixed(dp)}${row.unit}` : '—'}</td>
                    <td>{row.scenario != null ? `${row.scenario.toFixed(dp)}${row.unit}` : '—'}</td>
                    <td>
                      {row.delta != null ? <DeltaBadge cls={cls} text={signed(row.delta, dp, row.unit)} /> : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {barData.length > 0 && (
        <div className="lab-chart">
          <div className="lab-chart-title">
            <History size={15} />
            Actual vs counterfactual comparison
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={barData} barGap={5}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(120, 190, 255, 0.12)" vertical={false} />
              <XAxis dataKey="field" stroke="#5b7493" fontSize={11} tickLine={false} axisLine={{ stroke: 'rgba(120, 190, 255, 0.2)' }} />
              <YAxis stroke="#5b7493" fontSize={11} tickLine={false} axisLine={false} width={40} />
              <Tooltip contentStyle={tooltipStyle} cursor={{ fill: 'rgba(34, 211, 238, 0.06)' }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="actual" name="Actual" fill="#22d3ee" radius={[6, 6, 0, 0]} />
              <Bar dataKey="scenario" name="Scenario" fill="#f59e0b" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </>
  )
}

function FuturePane({ windows, loading }: { windows: FutureWindow[]; loading: boolean }) {
  if (loading && windows.length === 0) return <Skeletons chart={false} />
  if (windows.length === 0) {
    return (
      <div className="lab-empty">
        <CalendarClock size={26} />
        <h3>No future windows available</h3>
        <p>This location has no projection horizons. Try another region.</p>
      </div>
    )
  }

  const confData = windows
    .filter((w) => w.confidence != null)
    .map((w) => ({
      label: `${w.horizon_days}D`,
      confidence: w.confidence as number,
    }))

  return (
    <>
      <div className="lab-horizon-grid">
        {windows.map((w) => {
          const conf = w.confidence
          const cColor = confidenceColor(conf)
          return (
            <div key={w.horizon_days} className="lab-horizon glass-card">
              <span className="lab-horizon-day">{w.horizon_days}-Day Horizon</span>
              <div className="lab-horizon-metric">
                <span>SST</span>
                <b>{w.predicted_temp != null ? `${w.predicted_temp.toFixed(1)}°C` : '—'}</b>
              </div>
              <div className="lab-horizon-metric">
                <span>Wave</span>
                <b>{w.predicted_wave != null ? `${w.predicted_wave.toFixed(2)} m` : '—'}</b>
              </div>
              <div className="lab-horizon-metric">
                <span>Current</span>
                <b>{w.predicted_current != null ? `${w.predicted_current.toFixed(2)} m/s` : '—'}</b>
              </div>
              <div className="lab-horizon-foot">
                <span className={`lab-horizon-conf ${confidenceClass(conf)}`} style={{ color: cColor }}>
                  {conf != null ? `${conf.toFixed(0)}% confidence` : 'Confidence n/a'}
                </span>
              </div>
              <div className="lab-horizon-src">
                <Database size={12} />
                {w.data_sources.length > 0 ? w.data_sources.join(', ') : 'Open-Meteo Marine reanalysis'}
              </div>
            </div>
          )
        })}
      </div>

      {confData.length > 1 && (
        <div className="lab-chart lab-conf-chart">
          <div className="lab-chart-title">
            <CalendarClock size={15} />
            Confidence decay over the horizon
          </div>
          <ResponsiveContainer width="100%" height={170}>
            <AreaChart data={confData} margin={{ top: 10, right: 20, bottom: 0, left: -10 }}>
              <defs>
                <linearGradient id="confGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.5} />
                  <stop offset="100%" stopColor="#22d3ee" stopOpacity={0.04} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(120, 190, 255, 0.12)" vertical={false} />
              <XAxis dataKey="label" stroke="#5b7493" fontSize={11} tickLine={false} axisLine={false} />
              <YAxis domain={[0, 100]} stroke="#5b7493" fontSize={11} tickLine={false} axisLine={false} width={44} />
              <Tooltip contentStyle={tooltipStyle} />
              <ReferenceLine
                y={60}
                stroke="#f59e0b"
                strokeDasharray="4 4"
                label={{ value: 'uncertainty threshold', fill: '#f59e0b', fontSize: 10, position: 'insideTopRight' }}
              />
              <Area type="monotone" dataKey="confidence" name="Confidence (%)" stroke="#22d3ee" strokeWidth={2} fill="url(#confGradient)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </>
  )
}

export default function ScenarioLab() {
  const [locations, setLocations] = useState<LabLocation[]>([])
  const [locLoading, setLocLoading] = useState(true)
  const [locError, setLocError] = useState<string | null>(null)
  const [locationId, setLocationId] = useState<number | null>(null)

  const [windPercent, setWindPercent] = useState(0)
  const [tempDelta, setTempDelta] = useState(0)
  const [salinityDelta, setSalinityDelta] = useState(0)
  const [mixingFactor, setMixingFactor] = useState(1)

  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const [hasRun, setHasRun] = useState(false)
  const [activeTab, setActiveTab] = useState<TabId>('projection')

  const [projection, setProjection] = useState<ProjectionResult | null>(null)
  const [counterfactual, setCounterfactual] = useState<CounterFactualResult | null>(null)

  const [future, setFuture] = useState<FutureWindow[]>([])
  const [futureLoading, setFutureLoading] = useState(false)

  useEffect(() => {
    fetchLocations()
      .then((data) => setLocations((data ?? []) as LabLocation[]))
      .catch(() => setLocError('Could not load locations. Is the backend running?'))
      .finally(() => setLocLoading(false))
  }, [])

  const selectLocation = (id: number) => {
    setLocationId(id)
    setProjection(null)
    setCounterfactual(null)
    setHasRun(false)
    setRunError(null)
    setFuture([])
    setFutureLoading(true)
    fetchFuture(id)
      .then((d) => setFuture(normalizeFuture(d)))
      .catch(() => setFuture([]))
      .finally(() => setFutureLoading(false))
  }

  const runSimulation = async () => {
    if (locationId == null) return
    setRunning(true)
    setRunError(null)
    try {
      const params = {
        wind_percent: windPercent,
        temperature_delta: tempDelta,
        salinity_delta: salinityDelta,
        mixing_factor: mixingFactor,
      }
      const [projRaw, cfRaw] = await Promise.all([
        runWhatIf({ location_id: locationId, ...params }),
        runCounterfactual(locationId, params),
      ])
      setProjection(normalizeProjection(projRaw))
      setCounterfactual(normalizeCounterfactual(cfRaw))
      setHasRun(true)
      setActiveTab('projection')
    } catch {
      setRunError('Simulation failed. Check that the backend is running and try again.')
    } finally {
      setRunning(false)
    }
  }

  const resetSimulation = () => {
    setWindPercent(0)
    setTempDelta(0)
    setSalinityDelta(0)
    setMixingFactor(1)
    setProjection(null)
    setCounterfactual(null)
    setHasRun(false)
    setRunError(null)
  }

  const selectedLocation = locations.find((l) => l.id === locationId) ?? null

  const snapshot = useMemo<Snapshot>(
    () => counterfactual?.snapshot ?? { sst: null, wave: null, current: null },
    [counterfactual],
  )

  const profile = useMemo<ProfilePoint[]>(() => {
    if (!projection) return []
    const sstAct = projection.actual.sst ?? snapshot.sst
    const waveAct = projection.actual.wave ?? snapshot.wave
    const sstProj = projection.projected.sst
    const waveProj = projection.projected.wave
    return Array.from({ length: 12 }, (_, i) => {
      const f = i / 11
      return {
        label: `+${i * 6}h`,
        sstActual: sstAct,
        sstProjected: ramp(sstAct, sstProj, f),
        waveActual: waveAct,
        waveProjected: ramp(waveAct, waveProj, f),
      }
    })
  }, [projection, snapshot])

  const barData = useMemo(
    () =>
      (counterfactual?.rows ?? [])
        .filter((r) => r.actual != null && r.scenario != null)
        .map((r) => ({ field: r.field, actual: r.actual as number, scenario: r.scenario as number })),
    [counterfactual],
  )

  const counterfactualParams: ScenarioParameters = projection?.scenario ?? {
    wind_percent: windPercent,
    temperature_delta: tempDelta,
    salinity_delta: salinityDelta,
    mixing_factor: mixingFactor,
  }

  const sliders = [
    {
      key: 'wind',
      icon: <Wind size={15} />,
      label: 'Wind Speed',
      min: -50,
      max: 100,
      step: 1,
      low: 'Calm',
      high: 'Storm',
      value: windPercent,
      onChange: setWindPercent,
      format: (v: number) => (v > 0 ? `+${v}%` : `${v}%`),
    },
    {
      key: 'temp',
      icon: <Thermometer size={15} />,
      label: 'Temperature Δ',
      min: -3,
      max: 5,
      step: 0.1,
      low: 'Cooling',
      high: 'Warming',
      value: tempDelta,
      onChange: setTempDelta,
      format: (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(1)}°C`,
    },
    {
      key: 'sal',
      icon: <Droplets size={15} />,
      label: 'Salinity Δ',
      min: -2,
      max: 2,
      step: 0.1,
      low: 'Fresher',
      high: 'Saltier',
      value: salinityDelta,
      onChange: setSalinityDelta,
      format: (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(1)} PSU`,
    },
    {
      key: 'mix',
      icon: <Gauge size={15} />,
      label: 'Mixing Factor',
      min: 0.5,
      max: 3,
      step: 0.1,
      low: 'Stratified',
      high: 'Storm churn',
      value: mixingFactor,
      onChange: setMixingFactor,
      format: (v: number) => `${v.toFixed(1)}×`,
    },
  ]

  return (
    <div className="page lab-page animate-in">
      <div className="page-header lab-header">
        <div className="lab-title-row">
          <div className="lab-title-icon">
            <FlaskConical size={22} />
          </div>
          <div>
            <h1 className="page-title title-glow">
              Scenario <span className="text-gradient">Lab</span>
            </h1>
            <p className="page-subtitle">What-If Simulation &amp; Counterfactual Analysis</p>
          </div>
        </div>
      </div>

      <div className="lab-disclaimer">
        <AlertTriangle size={15} />
        <span>All projections are illustrative simulations, not operational forecasts.</span>
      </div>

      <div className="glass-card lab-loc-picker">
        <MapPin size={16} />
        <select
          value={locationId ?? ''}
          onChange={(e) => e.target.value !== '' && selectLocation(Number(e.target.value))}
          disabled={locLoading || locError != null}
        >
          <option value="">
            {locError ? 'Locations unavailable' : locLoading ? 'Loading locations…' : 'Select an ocean location'}
          </option>
          {locations.map((l) => (
            <option key={l.id} value={l.id}>
              {l.name}
            </option>
          ))}
        </select>
        {selectedLocation && (
          <span className="lab-loc-coords">
            {selectedLocation.latitude != null && selectedLocation.longitude != null
              ? `${selectedLocation.latitude.toFixed(2)}°N, ${selectedLocation.longitude.toFixed(2)}°E`
              : (selectedLocation.region_type ?? 'Ocean region')}
          </span>
        )}
      </div>

      <motion.div variants={fadeUp} initial="hidden" animate="show" className="lab-grid">
        <div className="lab-controls glass-card">
          <div className="lab-panel-title">
            <SlidersHorizontal size={16} />
            <span>Simulation Parameters</span>
          </div>
          {sliders.map((s) => (
            <LabSlider
              key={s.key}
              icon={s.icon}
              label={s.label}
              value={s.value}
              min={s.min}
              max={s.max}
              step={s.step}
              low={s.low}
              high={s.high}
              format={s.format}
              onChange={s.onChange}
            />
          ))}
          <div className="lab-run-row">
            <button className="btn-run" onClick={runSimulation} disabled={running || locationId == null}>
              {running ? <Loader2 size={16} className="spin" /> : <Play size={16} />}
              {running ? 'Running…' : 'Run Simulation'}
            </button>
            <button className="btn-reset" onClick={resetSimulation} disabled={running}>
              <RotateCcw size={14} />
              Reset
            </button>
          </div>
          {runError && (
            <div className="lab-error">
              <AlertTriangle size={13} />
              {runError}
            </div>
          )}
        </div>

        <div className="lab-results glass-card">
          <div className="lab-tabs">
            {TABS.map(({ id, label, icon }) => (
              <button
                key={id}
                className={`lab-tab ${activeTab === id ? 'lab-tab-active' : ''}`}
                onClick={() => setActiveTab(id)}
                disabled={!hasRun}
              >
                {icon}
                {label}
              </button>
            ))}
          </div>

          {running ? (
            <Skeletons />
          ) : !hasRun ? (
            <EmptyState hasLocation={locationId != null} />
          ) : (
            <AnimatePresence mode="wait">
              <motion.div
                key={activeTab}
                className="lab-pane"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.25 }}
              >
                {activeTab === 'projection' && projection && (
                  <ProjectionPane projection={projection} snapshot={snapshot} profile={profile} />
                )}
                {activeTab === 'counterfactual' && counterfactual && (
                  <CounterPane result={counterfactual} params={counterfactualParams} barData={barData} />
                )}
                {activeTab === 'future' && <FuturePane windows={future} loading={futureLoading} />}
              </motion.div>
            </AnimatePresence>
          )}
        </div>
      </motion.div>
    </div>
  )
}