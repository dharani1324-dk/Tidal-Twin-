import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import {
  Fish, Sun, Ship, Droplets, LifeBuoy, Banknote, Sparkles, Play,
} from 'lucide-react'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Cell,
} from 'recharts'
import {
  fetchFisheries, fetchCoral, postDriftSim, fetchSLR, fetchBeachSafety, fetchEconomicImpact,
} from '../api/client'
import './CoastalIntel.css'

type TabId = 'fisheries' | 'coral' | 'spill' | 'slr' | 'beach' | 'impact'

const fadeUp = {
  hidden: { opacity: 0, y: 18 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.45 } },
}

const TABS: { id: TabId; icon: typeof Fish; label: string; desc: string }[] = [
  { id: 'fisheries', icon: Fish, label: 'Fisheries', desc: 'Fish aggregation zones' },
  { id: 'coral', icon: Sun, label: 'Coral Stress', desc: 'Bleaching risk index' },
  { id: 'spill', icon: Ship, label: 'Spill & SAR', desc: 'Drift response planning' },
  { id: 'slr', icon: Droplets, label: 'Sea Rise', desc: 'Inundation simulator' },
  { id: 'beach', icon: LifeBuoy, label: 'Beach Safety', desc: 'Rip-current flags' },
  { id: 'impact', icon: Banknote, label: 'Impact ₹', desc: 'Disaster economics' },
]

const FAZ_COLOR: Record<string, string> = {
  prime: '#10b981', good: '#22d3ee', fair: '#facc15', poor: '#f43f5e',
}
const FLAG_COLOR: Record<string, string> = {
  safe: '#22c55e', caution: '#facc15', danger: '#ef4444',
}
const LEVEL_COLOR: Record<string, string> = { no_stress: '#22c55e', watch: '#facc15', warning: '#f59e0b', critical: '#f43f5e' }

interface FisheriesRegion {
  location_id: number
  location: string
  faz_score: number
  category: string
  sst: number
  chlorophyll: number
  top_species: { name: string; likelihood: number }[]
  drivers: { driver: string; contribution: number; note: string }[]
  seasonal_calendar: { month: string; index: number }[]
  this_month_index: number
}

interface CoralRegion {
  location_id: number
  location: string
  sst: number
  dhw: number
  level: string
  level_label: string
  color: string
  bleaching_risk_pct: number
  sensitivity: string
  recommendation: string
}

interface DriftZone {
  location_id: number
  location: string
  distance_km: number
  eta_hours: number
  probability_pct: number
}

interface TrajectoryPoint {
  hour: number
  lat: number
  lon: number
  spread_km: number
}

interface DriftResult {
  scenario: string
  origin: { location: string; lat: number; lon: number }
  trajectory: TrajectoryPoint[]
  response_priority: DriftZone[]
  landfall_zones: DriftZone[]
  recommendation: string
  forcing?: { current_bearing_deg: number }
}

interface SlrRegion {
  location_id: number
  location: string
  affected_towns: string[]
  damaged: number
  affected_count: number
  impact_pct: number
  land_area_lost_km2: number
  population_at_risk: number
  level: string
}

interface BeachRegion {
  location_id: number
  location: string
  wave_height: number
  current_speed: number
  flag: string
  flag_label: string
  color: string
  rip_current_index: number
  reasons: string[]
  action: string
}

interface ImpactRow {
  location: string
  event_type: string
  label: string
  intensity: string
  duration_h: number
  fishing_loss_inr: number
  port_disruption_inr: number
  tourism_loss_inr: number
  total_inr: number
}

const inr = (n: number) => '₹' + (n >= 1e7 ? (n / 1e7).toFixed(1) + ' cr' : (n / 1e5).toFixed(1) + ' lakh')

export default function CoastalIntel() {
  const [tab, setTab] = useState<TabId>('fisheries')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  // fisheries
  const [fisheries, setFisheries] = useState<FisheriesRegion[]>([])
  const [fisheriesSummary, setFisheriesSummary] = useState<Record<string, unknown>>({})
  // coral
  const [coral, setCoral] = useState<CoralRegion[]>([])
  // spill
  const [drift, setDrift] = useState<DriftResult | null>(null)
  const [spillScenario, setSpillScenario] = useState<'spill' | 'sar'>('spill')
  const [spillLoc, setSpillLoc] = useState<number>(3)
  const [spillHours, setSpillHours] = useState(24)
  // slr
  const [slrScenario, setSlrScenario] = useState(1.0)
  const [slr, setSlr] = useState<{ regions: SlrRegion[]; summary: Record<string, unknown> } | null>(null)
  // beach
  const [beach, setBeach] = useState<{ regions: BeachRegion[]; summary: Record<string, number> } | null>(null)
  // impact
  const [impact, setImpact] = useState<{ line_items: ImpactRow[]; summary: Record<string, unknown> } | null>(null)

  useEffect(() => {
    let alive = true
    Promise.all([fetchFisheries(), fetchCoral(), fetchBeachSafety(), fetchEconomicImpact(), fetchSLR(1.0)])
      .then(([f, cr, b, im, sl]) => {
        if (!alive) return
        setFisheries(f.regions ?? [])
        setFisheriesSummary(f.summary ?? {})
        setCoral(cr.regions ?? [])
        setBeach(b)
        setImpact(im)
        setSlr(sl)
      })
      .catch(() => setError(true))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [])

  const runDrift = async () => {
    setLoading(true)
    try {
      const d = await postDriftSim({
        scenario: spillScenario, location_id: spillLoc, duration_h: spillHours,
      })
      setDrift(d)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }

  const runSLR = async (m: number) => {
    setSlrScenario(m)
    try {
      const s = await fetchSLR(m)
      setSlr(s)
    } catch { /* keep previous */ }
  }

  return (
    <div className="page coastal-page animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title title-glow">
            Coastal <span className="text-gradient">Intelligence</span>
          </h1>
          <p className="page-subtitle">
            Livelihood, ecology and disaster-response intelligence for India's coasts — fisheries, coral reefs, spill/SAR, sea rise, beach safety and economic impact.
          </p>
        </div>
        <div className="coastal-tag glass-card">
          <Sparkles size={15} />
          <span>6 DECISION ENGINES</span>
        </div>
      </div>

      <div className="ov-tabs">
        {TABS.map(({ id, icon: Icon, label, desc }) => (
          <button key={id} className={`ov-tab ${tab === id ? 'ov-tab-on' : ''}`} onClick={() => setTab(id)}>
            <Icon size={16} />
            <span>
              <b>{label}</b>
              <i>{desc}</i>
            </span>
          </button>
        ))}
      </div>

      <motion.div key={tab} variants={fadeUp} initial="hidden" animate="visible" className="coastal-content">
        {loading ? <div className="ov-loading">Loading ocean intelligence…</div> : error ? (
          <div className="ov-loading">Couldn't reach the backend — is it running?</div>
        ) : (
          <>
            {tab === 'fisheries' && <FisheriesView regions={fisheries} summary={fisheriesSummary} />}
            {tab === 'coral' && <CoralView regions={coral} />}
            {tab === 'spill' && (
              <SpillView
                drift={drift} scenario={spillScenario} locationId={spillLoc} hours={spillHours}
                setScenario={setSpillScenario} setLocation={setSpillLoc} setHours={setSpillHours}
                onRun={runDrift} locations={fisheries.map((r) => ({ id: r.location_id, name: r.location }))}
              />
            )}
            {tab === 'slr' && <SlrView slr={slr} scenario={slrScenario} onScenario={runSLR} />}
            {tab === 'beach' && <BeachView beach={beach} />}
            {tab === 'impact' && <ImpactView impact={impact} />}
          </>
        )}
      </motion.div>
    </div>
  )
}

/* ------------------------------ Fisheries ------------------------------ */
function FisheriesView({ regions, summary }: { regions: FisheriesRegion[]; summary: Record<string, unknown> }) {
  const best = summary.best_zone as string
  const bestScore = summary.best_score as number
  return (
    <div className="coastal-stack">
      <div className="ov-hero">
        <Fish size={18} />
        <span>
          <b>{typeof summary.coasts === 'number' ? summary.coasts : 0} coasts</b> scored for fishing productivity · best zone{' '}
          <em>{best}</em> (FAZ {bestScore}/100) — driver-by-driver explainable.
        </span>
      </div>
      <div className="ov-grid">
        {regions.map((r) => (
          <div key={r.location_id} className="glass-card ov-card">
            <div className="ov-card-head">
              <b>{r.location}</b>
              <span className="badge" style={{ background: FAZ_COLOR[r.category], color: '#04121f' }}>
                {r.category.toUpperCase()} · {r.faz_score}/100
              </span>
            </div>
            <div className="score-bar">
              <div className="score-fill" style={{ width: `${r.faz_score}%`, background: FAZ_COLOR[r.category] }} />
            </div>
            <div className="species-list">
              {r.top_species.map((s) => (
                <span key={s.name} className="species-chip">
                  <em>{s.name}</em> <b>{s.likelihood}%</b>
                </span>
              ))}
            </div>
            <div className="month-bars" title="Seasonal fishing calendar (this month highlighted)">
              {r.seasonal_calendar.map((mm, i) => (
                <div key={mm.month} className={`month-col ${mm.month === r.seasonal_calendar[new Date().getMonth()].month ? 'month-now' : ''}`}>
                  <div className="month-fill" style={{ height: `${mm.index}%`, background: i === new Date().getMonth() ? '#22d3ee' : '#0e7490' }} />
                  <span>{mm.month}</span>
                </div>
              ))}
            </div>
            <div className="driver-row">
              {r.drivers.map((d) => (
                <span key={d.driver} title={d.note}>
                  <b>{d.contribution}</b> {d.driver.replace('Temperature', 'Temp')}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ------------------------------ Coral ------------------------------ */
function CoralView({ regions }: { regions: CoralRegion[] }) {
  const critical = regions.filter((r) => r.level === 'critical' || r.level === 'warning').length
  return (
    <div className="coastal-stack">
      <div className="ov-hero">
        <Sun size={18} />
        <span>
          NOAA-style <b>Degree-Heating-Week</b> thermal stress · <b>{critical}</b> reef(s) in warning/critical right now.
        </span>
      </div>
      <div className="ov-grid">
        {regions.map((r) => (
          <div key={r.location_id} className="glass-card ov-card coral-card" style={{ borderColor: r.color + '55' }}>
            <div className="ov-card-head">
              <b>{r.location}</b>
              <span className="badge" style={{ background: LEVEL_COLOR[r.level], color: '#04121f' }}>
                {r.level_label.toUpperCase()}
              </span>
            </div>
            <div className="coral-metrics">
              <div><span>SST now</span><b>{r.sst.toFixed(1)}°C</b></div>
              <div><span>DHW</span><b>{r.dhw}</b></div>
              <div><span>Risk</span><b>{r.bleaching_risk_pct}%</b></div>
              <div><span>Species</span><b className="cap">{r.sensitivity}</b></div>
            </div>
            <p className="coral-reco">💡 {r.recommendation}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ------------------------------ Spill / SAR ------------------------------ */
function SpillView({ drift, scenario, locationId, hours, setScenario, setLocation, setHours, onRun, locations }: {
  drift: DriftResult | null
  scenario: 'spill' | 'sar'
  locationId: number
  hours: number
  setScenario: (s: 'spill' | 'sar') => void
  setLocation: (n: number) => void
  setHours: (n: number) => void
  onRun: () => void
  locations: { id: number; name: string }[]
}) {
  const pts = drift?.trajectory ?? []
  const minLat = Math.min(...pts.map((p) => p.lat)), maxLat = Math.max(...pts.map((p) => p.lat))
  const minLon = Math.min(...pts.map((p) => p.lon)), maxLon = Math.max(...pts.map((p) => p.lon))
  const spanLon = Math.max(0.01, maxLon - minLon), spanLat = Math.max(0.01, maxLat - minLat)
  const path = pts.map((p) => `${(((p.lon - minLon) / spanLon) * 220 + 8).toFixed(1)},${(130 - ((p.lat - minLat) / spanLat) * 110).toFixed(1)}`).join(' ')

  return (
    <div className="coastal-stack">
      <div className="ov-hero sim-controls">
        <select value={scenario} onChange={(e) => setScenario(e.target.value as 'spill' | 'sar')}>
          <option value="spill">🛢️ Oil-spill slick</option>
          <option value="sar">🛟 Search & rescue (person/boat)</option>
        </select>
        <select value={locationId} onChange={(e) => setLocation(Number(e.target.value))}>
          {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
        </select>
        <select value={hours} onChange={(e) => setHours(Number(e.target.value))}>
          {[12, 24, 36, 48, 72].map((h) => <option key={h} value={h}>{h}h window</option>)}
        </select>
        <button className="btn-primary run-btn" onClick={onRun}><Play size={13} /> Run drift</button>
      </div>

      <div className="drift-grid">
        <div className="glass-card drift-track">
          <div className="ov-card-head"><b>Drift corridor</b><span className="badge dim">{scenario.toUpperCase()}</span></div>
          {drift ? (
            <>
              <svg className="drift-svg" viewBox="0 0 236 138" preserveAspectRatio="none">
                <circle cx={8} cy={130} r={5} fill="#22d3ee" opacity={0.5} />
                <polyline points={path} fill="none" stroke={scenario === 'spill' ? '#f59e0b' : '#22d3ee'} strokeWidth={2.5} strokeLinejoin="round" />
                {pts.filter((p) => p.hour % 8 === 0).map((p) => {
                  const x = ((p.lon - minLon) / spanLon) * 220 + 8
                  const y = 130 - ((p.lat - minLat) / spanLat) * 110
                  return (
                    <g key={p.hour}>
                      <circle cx={x} cy={y} r={4 + p.spread_km / 3} fill="none" stroke={scenario === 'spill' ? '#f59e0b' : '#22d3ee'} strokeWidth={1} opacity={0.65} />
                      <text x={x} y={y - 6} fontSize={6.5} fill="#a5f3fc">{p.hour}h</text>
                    </g>
                  )
                })}
              </svg>
              <p className="drift-note">
                Origin {drift.origin.location} ({drift.origin.lat}, {drift.origin.lon}) · bearing {drift.forcing?.current_bearing_deg ?? '—'}° ·
                circles = growing search/spread radius.
              </p>
            </>
          ) : <p className="ov-loading">Set origin & hit Run.</p>}
        </div>

        <div className="glass-card drift-priority">
          <div className="ov-card-head"><b>Response priority</b></div>
          {drift && drift.response_priority.length ? (
            <table className="ci-table">
              <thead><tr><th>Coast</th><th>Dist</th><th>ETA</th><th>Prob.</th></tr></thead>
              <tbody>
                {drift.response_priority.map((z) => (
                  <tr key={z.location_id}>
                    <td>{z.location}</td>
                    <td>{z.distance_km} km</td>
                    <td>{z.eta_hours}h</td>
                    <td><b className="prob-badge">{z.probability_pct}%</b></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <p className="ov-loading">Priority list appears after a run.</p>}
          {drift && <p className="drift-note">{drift.recommendation}</p>}
        </div>
      </div>
    </div>
  )
}

/* ------------------------------ SLR ------------------------------ */
function SlrView({ slr, scenario, onScenario }: { slr: { regions: SlrRegion[]; summary: Record<string, unknown> } | null; scenario: number; onScenario: (m: number) => void }) {
  return (
    <div className="coastal-stack">
      <div className="ov-hero sim-controls">
        <span className="sim-label">Sea-level rise scenario</span>
        {[0.3, 0.5, 1.0, 2.0].map((m) => (
          <button key={m} className={`scenario-btn ${scenario === m ? 'scenario-btn-on' : ''}`} onClick={() => onScenario(m)}>
            +{m} m
          </button>
        ))}
      </div>

      <div className="ov-hero slr-summary">
        <Droplets size={18} />
        <span>
          At <b>+{scenario} m</b>: <b>{slr?.summary?.towns_inundated as number ?? 0}</b> coastal towns inundated,
          ~<b>{inr(slr?.summary?.total_population_at_risk as number ?? 0)}</b> people at risk
          {slr?.summary?.most_affected ? <><em> — {slr.summary.most_affected as string}</em> hardest hit</> : null}.
        </span>
      </div>

      <div className="slr-grid">
        {(slr?.regions ?? []).map((r) => (
          <div key={r.location_id} className="glass-card ov-card">
            <div className="ov-card-head">
              <b>{r.location}</b>
              <span className="badge" style={{ background: r.level === 'severe' ? '#f43f5e' : r.level === 'high' ? '#f59e0b' : r.level === 'moderate' ? '#facc15' : '#10b981', color: '#04121f' }}>
                {r.level.toUpperCase()}
              </span>
            </div>
            <div className="coral-metrics">
              <div><span>Towns hit</span><b>{r.affected_count}</b></div>
              <div><span>Land lost</span><b>{r.land_area_lost_km2} km²</b></div>
              <div><span>Pop. at risk</span><b>{inr(r.population_at_risk)}</b></div>
            </div>
            <div className="affected-list">
              {r.affected_towns.length ? r.affected_towns.map((t) => <span key={t}>{t}</span>) : <span className="dim">no settlements affected</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ------------------------------ Beach ------------------------------ */
function BeachView({ beach }: { beach: { regions: BeachRegion[]; summary: Record<string, number> } | null }) {
  const rows = beach?.regions ?? []
  return (
    <div className="coastal-stack">
      <div className="ov-hero">
        <LifeBuoy size={18} />
        <span>
          <b>{beach?.summary?.safe ?? 0} SAFE</b> · <b>{beach?.summary?.caution ?? 0} CAUTION</b> ·{' '}
          <b style={{ color: '#f87171' }}>{beach?.summary?.danger ?? 0} DANGER</b> flags across {beach?.summary?.total ?? 0} beaches.
        </span>
      </div>
      <div className="ov-grid">
        {rows.slice(0, 8).map((r) => (
          <div key={r.location_id} className="glass-card ov-card beach-card" style={{ borderColor: FLAG_COLOR[r.flag] + '55' }}>
            <div className="ov-card-head">
              <b>{r.location}</b>
              <span className="flag-pill" style={{ background: FLAG_COLOR[r.flag], color: '#0a0f1e' }}>
                {r.flag_label}
              </span>
            </div>
            <div className="beach-metric">
              <span>Rip index</span>
              <div className="score-bar"><div className="score-fill" style={{ width: `${r.rip_current_index}%`, background: FLAG_COLOR[r.flag] }} /></div>
              <b>{r.rip_current_index}/100</b>
            </div>
            <div className="beach-facts">
              <span>Waves <b>{r.wave_height} m</b></span>
              <span>Current <b>{r.current_speed} m/s</b></span>
            </div>
            <ul className="reasons">{r.reasons.map((x) => <li key={x}>{x}</li>)}</ul>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ------------------------------ Impact ------------------------------ */
function ImpactView({ impact }: { impact: { line_items: ImpactRow[]; summary: Record<string, unknown> } | null }) {
  const s = impact?.summary ?? {} as Record<string, unknown>
  const chart = (impact?.line_items ?? []).slice(0, 8).map((i) => ({
    name: i.location.replace(' Coast', ''),
    total: i.total_inr,
  }))
  const breakdown = s.breakdown as Record<string, number> | undefined
  return (
    <div className="coastal-stack">
      <div className="impact-cards">
        <div className="glass-card impact-card">
          <span>Total estimated loss</span>
          <b>{inr(s.total_estimated_loss_inr as number ?? 0)}</b>
          <em>across {s.coasts_impacted as number ?? 0} coasts</em>
        </div>
        <div className="glass-card impact-card">
          <span>Fisheries</span>
          <b>{inr(breakdown?.fishing_loss_inr ?? 0)}</b>
          <em>fleet hours + landing value</em>
        </div>
        <div className="glass-card impact-card">
          <span>Ports</span>
          <b>{inr(breakdown?.port_loss_inr ?? 0)}</b>
          <em>throughput disruption</em>
        </div>
        <div className="glass-card impact-card">
          <span>Tourism</span>
          <b>{inr(breakdown?.tourism_loss_inr ?? 0)}</b>
          <em>arrival spend shortfall</em>
        </div>
      </div>

      <div className="glass-card chart-card">
        <b className="chart-title">Coast-wise estimated damage (₹)</b>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={chart} margin={{ left: 30, right: 12, top: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(120,190,255,0.1)" />
            <XAxis dataKey="name" tick={{ fill: '#7dd3fc', fontSize: 10 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => `₹${(v / 1e7).toFixed(0)}cr`} />
            <Tooltip contentStyle={{ background: '#0a1a33', border: '1px solid rgba(120,190,255,0.2)', borderRadius: 8 }} formatter={(v) => [inr(Number(v)), 'Total']} cursor={{ fill: 'rgba(34,211,238,0.06)' }} />
            <Bar dataKey="total" radius={[6, 6, 0, 0]}>
              {chart.map((_, i) => <Cell key={i} fill={['#22d3ee', '#38bdf8', '#818cf8', '#f59e0b', '#10b981', '#f43f5e', '#a78bfa', '#facc15'][i % 8]} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="glass-card">
        <div className="ov-card-head"><b>Event line-items</b></div>
        <table className="ci-table">
          <thead><tr><th>Coast</th><th>Event</th><th>Intensity</th><th>Hrs</th><th>Fishing</th><th>Port</th><th>Tourism</th><th>Total</th></tr></thead>
          <tbody>
            {(impact?.line_items ?? []).map((i, idx) => (
              <tr key={idx}>
                <td><b>{i.location.replace(' Coast', '')}</b></td>
                <td>{i.label}</td>
                <td><span className={`int-badge ${i.intensity}`}>{i.intensity}</span></td>
                <td>{i.duration_h}</td>
                <td>{inr(i.fishing_loss_inr)}</td>
                <td>{inr(i.port_disruption_inr)}</td>
                <td>{inr(i.tourism_loss_inr)}</td>
                <td><b>{inr(i.total_inr)}</b></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}