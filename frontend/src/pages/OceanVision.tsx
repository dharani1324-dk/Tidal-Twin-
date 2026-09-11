import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import {
  Sparkles, Crosshair, Waves, Lightbulb, Satellite, Target,
  Thermometer, Wind, Droplets, CheckCircle2, AlertTriangle,
  FlaskConical, Gauge, ArrowRight, Activity, Cpu,
} from 'lucide-react'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  Cell,
} from 'recharts'
import {
  fetchAdaptive, fetchCarbon, fetchLightPollution, fetchRemoteSensing, fetchRecommendations,
} from '../api/client'
import './OceanVision.css'

type TabId = 'adaptive' | 'carbon' | 'light' | 'sensing' | 'recommend'

const fadeUp = {
  hidden: { opacity: 0, y: 18 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.45 } },
}

const TABS: { id: TabId; icon: typeof Crosshair; label: string; desc: string }[] = [
  { id: 'adaptive', icon: Gauge, label: 'Adaptive Detection', desc: 'Self-calibrating thresholds' },
  { id: 'carbon', icon: Activity, label: 'Carbon Flux', desc: 'Air-sea CO2 exchange' },
  { id: 'light', icon: Lightbulb, label: 'Light Pollution', desc: 'ALAN impact on coasts' },
  { id: 'sensing', icon: Satellite, label: 'Remote Sensing', desc: 'Satellite fusion layer' },
  { id: 'recommend', icon: Target, label: 'Observation Planner', desc: 'Where to sample next' },
]

const CATEGORY_COLOR: Record<string, string> = {
  'strong sink': '#10b981',
  'moderate sink': '#22d3ee',
  'near-neutral': '#94a3b8',
  source: '#f43f5e',
}

interface AdaptiveVar {
  variable: string
  label: string
  unit: string
  current: number
  deviation_from_baseline: number
  adaptive_threshold: number
  static_threshold: number
  maturity: string
  sample_count: number
  strategy: string
  adapted: boolean
  k_sigma?: number
  static_flag: boolean
  adaptive_flag: boolean
  classification_changed: boolean
}

interface AdaptiveRegion {
  location_id: number
  location: string
  learning_hours: number
  sample_count: number
  adaptation_index: number
  maturity: string
  variables: AdaptiveVar[]
}

interface CarbonFlux {
  pco2_seawater: number
  pco2_atmosphere: number
  pco2_gradient: number
  flux_mol_per_m2_day: number
  flux_gc_per_m2_yr: number
  category: string
  gas_transfer_velocity_cm_per_h: number
}

interface CarbonRegion {
  location_id: number
  location: string
  sst: number
  wind_estimate_ms: number
  flux: CarbonFlux
  regional_uptake_ktC_per_yr: number
}

interface LightRegion {
  location_id: number
  location: string
  aln_exposure_score: number
  severity: string
  color: string
  biota_impact: Record<string, number>
  recommendation: string
}

interface SrcVar {
  variable: string
  primary_satellite: string
  resolution: number
  revisit_h: number
  latency_h: number
  reliability: number
  availability: number
  active: boolean
}

interface SensingRegion {
  location_id: number
  location: string
  variables: SrcVar[]
  fused_confidence_boost_pct: number
  single_source_confidence: number
  harmonized_confidence: number
  sources_used: string[]
}

interface RecoNeed {
  variable: string
  platforms: string[]
  reason: string
}

interface RecoRegion {
  location_id: number
  location: string
  region_type: string
  obs_need: number
  count_in_window: number
  recency_h: number | null
  uncertainty: number
  active_event: boolean
  decision_impact: number
  variables_to_sample: string[]
  needs: RecoNeed[]
  action: string
}

const MATURITY_COLOR: Record<string, string> = {
  warmup: '#94a3b8',
  active: '#f59e0b',
  confident: '#10b981',
}

export default function OceanVision() {
  const [tab, setTab] = useState<TabId>('adaptive')
  const [loading, setLoading] = useState(true)

  const [adaptive, setAdaptive] = useState<AdaptiveRegion[]>([])
  const [carbon, setCarbon] = useState<CarbonRegion[]>([])
  const [carbonMeta, setCarbonMeta] = useState({ national_total_uptake_MtC_per_yr: 0, strongest_co2_sink: '—', atmosphere_reference_pco2: 420 })
  const [light, setLight] = useState<LightRegion[]>([])
  const [sensing, setSensing] = useState<SensingRegion[]>([])
  const [recos, setRecos] = useState<RecoRegion[]>([])
  const [recoSummary, setRecoSummary] = useState({ network_average_obs_need: 0, estimated_observations_needed: 0, summary: '' })

  useEffect(() => {
    Promise.all([
      fetchAdaptive().catch(() => ({ regions: [] })),
      fetchCarbon().catch(() => ({ regions: [], national_total_uptake_MtC_per_yr: 0, strongest_co2_sink: '—', atmosphere_reference_pco2: 420 })),
      fetchLightPollution().catch(() => ({ regions: [] })),
      fetchRemoteSensing().catch(() => ({ regions: [] })),
      fetchRecommendations(0).catch(() => ({ recommendations: [], network_average_obs_need: 0, estimated_observations_needed: 0, summary: '' })),
    ]).then(([a, c, l, s, r]) => {
      setAdaptive(Array.isArray(a.regions) ? a.regions : [])
      setCarbon(Array.isArray(c.regions) ? c.regions : [])
      setCarbonMeta({ national_total_uptake_MtC_per_yr: c.national_total_uptake_MtC_per_yr, strongest_co2_sink: c.strongest_co2_sink, atmosphere_reference_pco2: c.atmosphere_reference_pco2 })
      setLight(Array.isArray(l.regions) ? l.regions : [])
      setSensing(Array.isArray(s.regions) ? s.regions : [])
      setRecos(Array.isArray(r.recommendations) ? r.recommendations : [])
      setRecoSummary({ network_average_obs_need: r.network_average_obs_need, estimated_observations_needed: r.estimated_observations_needed, summary: r.summary })
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  const carbonChart = carbon
    .map((c) => ({ name: c.location.split(' (')[0], uptake: c.regional_uptake_ktC_per_yr, flux: c.flux.flux_gc_per_m2_yr, category: c.flux.category }))
    .sort((a, b) => a.uptake - b.uptake)

  const confidentRegions = adaptive.filter((r) => r.maturity === 'confident').length
  const avgAdaptIndex = adaptive.length ? Math.round(adaptive.reduce((s, r) => s + r.adaptation_index, 0) / adaptive.length) : 0
  const extremeCoasts = light.filter((l) => l.severity === 'extreme').length

  return (
    <div className="ov-page">
      <motion.div className="ov-header" variants={fadeUp} initial="hidden" animate="visible">
        <div className="ov-header-title">
          <Sparkles size={28} className="ov-icon" />
          <div>
            <h1>Ocean Vision</h1>
            <p>OceanVerse Apex Intelligence Engines — advanced decision support</p>
          </div>
        </div>
        <div className="ov-badge-row">
          <span className="ov-badge"><Cpu size={14} /> 5 engines online</span>
          <span className="ov-badge ov-badge-live"><span className="ov-live-dot" /> LIVE</span>
        </div>
      </motion.div>

      <motion.div className="ov-tabs" variants={fadeUp} initial="hidden" animate="visible">
        {TABS.map(({ id, icon: Icon, label, desc }) => (
          <button key={id} className={`ov-tab ${tab === id ? 'ov-tab-on' : ''}`} onClick={() => setTab(id)}>
            <Icon size={16} />
            <span className="ov-tab-label">
              <span className="ov-tab-name">{label}</span>
              <span className="ov-tab-desc">{desc}</span>
            </span>
          </button>
        ))}
      </motion.div>

      {loading ? (
        <div className="ov-loading">
          {[0, 1, 2, 3].map((i) => <div key={i} className="ov-skeleton" />)}
        </div>
      ) : (
        <div className="ov-body">
          {/* ---------- ADAPTIVE ---------- */}
          {tab === 'adaptive' && (
            <div className="ov-tab-page">
              <div className="ov-score-row">
                <div className="ov-score-card glass-card">
                  <Gauge size={20} />
                  <div className="ov-score-value">{confidentRegions}</div>
                  <div className="ov-score-label">Regions confident</div>
                </div>
                <div className="ov-score-card glass-card">
                  <Activity size={20} />
                  <div className="ov-score-value">{avgAdaptIndex}</div>
                  <div className="ov-score-label">Avg adaptation index</div>
                </div>
                <div className="ov-score-card glass-card">
                  <Thermometer size={20} />
                  <div className="ov-score-value">{adaptive.length}</div>
                  <div className="ov-score-label">Locations learning</div>
                </div>
              </div>

              <div className="ov-panel glass-card">
                <div className="ov-panel-header"><Cpu size={16} /><h3>Self-calibrating detection thresholds</h3></div>
                <p className="ov-note">
                  Each region prices its own baseline variance into anomaly detection. Bands never tighten below 60% of the static rule.
                </p>
                <div className="ov-table">
                  <table>
                    <thead>
                      <tr>
                        <th>Region</th><th>Maturity</th><th>Variable</th>
                        <th>Current</th><th>Dev</th>
                        <th>Adaptive band</th><th>Static rule</th><th>Δ rule</th>
                      </tr>
                    </thead>
                    <tbody>
                      {adaptive.flatMap((r) =>
                        r.variables.map((v, i) => (
                          <tr key={`${r.location_id}-${i}`}>
                            {i === 0 && (
                              <td rowSpan={r.variables.length} className="ov-cell-main">
                                <div className="ov-cell-loc">{r.location}</div>
                                <div className="ov-cell-sub">{r.sample_count} samples · {r.learning_hours}h</div>
                              </td>
                            )}
                            {i === 0 && (
                              <td rowSpan={r.variables.length}>
                                <span className="ov-maturity" style={{ color: MATURITY_COLOR[r.maturity.replace('-', '')] }}>
                                  {r.maturity}
                                </span>
                              </td>
                            )}
                            <td>{v.label}</td>
                            <td>{v.current ?? '—'}{v.unit}</td>
                            <td style={{ color: Math.abs(v.deviation_from_baseline) >= v.static_threshold ? '#f43f5e' : '#94a3b8' }}>
                              {v.deviation_from_baseline >= 0 ? '+' : ''}{v.deviation_from_baseline}{v.unit}
                            </td>
                            <td><b style={{ color: v.adapted ? '#22d3ee' : '#94a3b8' }}>{v.adaptive_threshold}</b>{v.unit} <span className="ov-cell-sub">({v.k_sigma ? `${v.k_sigma}σ` : 'n&lt;3'})</span></td>
                            <td>{v.static_threshold ?? '—'}{v.unit}</td>
                            <td>
                              {v.classification_changed ? (
                                <span className="ov-flag ov-flag-changed"><AlertTriangle size={12} /> Changed</span>
                              ) : (
                                <span className="ov-flag"><CheckCircle2 size={12} /> Same</span>
                              )}
                            </td>
                          </tr>
                        )),
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* ---------- CARBON ---------- */}
          {tab === 'carbon' && (
            <div className="ov-tab-page">
              <div className="ov-score-row">
                <div className="ov-score-card glass-card">
                  <Waves size={20} />
                  <div className="ov-score-value" style={{ color: carbonMeta.national_total_uptake_MtC_per_yr < 0 ? '#10b981' : '#f43f5e' }}>
                    {Math.abs(carbonMeta.national_total_uptake_MtC_per_yr)}
                  </div>
                  <div className="ov-score-label">
                    {carbonMeta.national_total_uptake_MtC_per_yr < 0 ? 'Mt C absorbed / yr (sink)' : 'Mt C emitted / yr (source)'}
                  </div>
                </div>
                <div className="ov-score-card glass-card">
                  <CheckCircle2 size={20} />
                  <div className="ov-score-value" style={{ fontSize: '1.05rem' }}>{carbonMeta.strongest_co2_sink}</div>
                  <div className="ov-score-label">Strongest CO2 sink</div>
                </div>
                <div className="ov-score-card glass-card">
                  <Wind size={20} />
                  <div className="ov-score-value">{carbonMeta.atmosphere_reference_pco2}</div>
                  <div className="ov-score-label">Atmosphere pCO2 (µatm)</div>
                </div>
              </div>

              <div className="ov-two-col">
                <div className="ov-panel glass-card">
                  <div className="ov-panel-header"><Activity size={16} /><h3>Regional net uptake (kt C / yr)</h3></div>
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart data={carbonChart} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(103,232,249,0.1)" />
                      <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                      <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} />
                      <Tooltip contentStyle={{ background: '#0f2039', border: '1px solid rgba(6,182,212,0.3)', borderRadius: 8, color: '#e2e8f0' }} />
                      <Bar dataKey="uptake" radius={[6, 6, 0, 0]}>
                        {carbonChart.map((c) => <Cell key={c.name} fill={CATEGORY_COLOR[c.category] ?? '#94a3b8'} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                <div className="ov-panel glass-card">
                  <div className="ov-panel-header"><FlaskConical size={16} /><h3>Per-region CO2 flux</h3></div>
                  <div className="ov-list">
                    {carbon.map((c) => (
                      <div key={c.location_id} className="ov-list-item">
                        <div className="ov-list-top">
                          <span className="ov-list-loc">{c.location}</span>
                          <span className="ov-pill" style={{ borderColor: CATEGORY_COLOR[c.flux.category], color: CATEGORY_COLOR[c.flux.category] }}>
                            {c.flux.category}
                          </span>
                        </div>
                        <div className="ov-list-meta">
                          <span>{c.flux.pco2_gradient >= 0 ? '+' : ''}{c.flux.pco2_gradient} µatm ΔpCO2</span>
                          <span>{c.flux.flux_mol_per_m2_day} mol/m²/d</span>
                          <span>{c.flux.flux_gc_per_m2_yr} gC/m²/yr</span>
                        </div>
                        <div className="ov-list-sub">{c.sst}°C · wind ~{c.wind_estimate_ms} m/s · k_w {c.flux.gas_transfer_velocity_cm_per_h} cm/h</div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ---------- LIGHT ---------- */}
          {tab === 'light' && (
            <div className="ov-tab-page">
              <div className="ov-score-row">
                <div className="ov-score-card glass-card">
                  <Lightbulb size={20} />
                  <div className="ov-score-value" style={{ color: extremeCoasts ? '#f43f5e' : '#10b981' }}>{extremeCoasts}</div>
                  <div className="ov-score-label">Extreme-exposure coasts</div>
                </div>
                <div className="ov-score-card glass-card">
                  <Waves size={20} />
                  <div className="ov-score-value">{light.length}</div>
                  <div className="ov-score-label">Regions assessed</div>
                </div>
                <div className="ov-score-card glass-card">
                  <Droplets size={20} />
                  <div className="ov-score-value" style={{ fontSize: '1.05rem' }}>{light[0]?.location.split(' (')[0] ?? '—'}</div>
                  <div className="ov-score-label">Most light-polluted</div>
                </div>
              </div>

              <div className="ov-panel glass-card">
                <div className="ov-panel-header"><Lightbulb size={16} /><h3>Artificial light at night — exposure & impact</h3></div>
                <div className="ov-list">
                  {light.map((l) => (
                    <div key={l.location_id} className="ov-list-item">
                      <div className="ov-list-top">
                        <span className="ov-list-loc">{l.location}</span>
                        <span className="ov-pill" style={{ borderColor: l.color, color: l.color }}>{l.severity}</span>
                      </div>
                      <div className="ov-bar-track">
                        <div className="ov-bar-fill" style={{ width: `${l.aln_exposure_score}%`, background: l.color }} />
                      </div>
                      <div className="ov-list-meta">
                        <span>{l.aln_exposure_score}/100 exposure</span>
                        <span>{l.biota_impact.sea_turtle_hatchling_disorientation}% turtle disorientation</span>
                        <span>{l.biota_impact.zooplankton_diel_migration_disruption}% zooplankton disruption</span>
                      </div>
                      <div className="ov-list-sub dot">{l.recommendation}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ---------- SENSING ---------- */}
          {tab === 'sensing' && (
            <div className="ov-tab-page">
              <div className="ov-score-row">
                <div className="ov-score-card glass-card">
                  <Satellite size={20} />
                  <div className="ov-score-value">{sensing.length}</div>
                  <div className="ov-score-label">Regions harmonized</div>
                </div>
                <div className="ov-score-card glass-card">
                  <Activity size={20} />
                  <div className="ov-score-value">
                    {sensing.length ? Math.round(sensing.reduce((s, r) => s + r.harmonized_confidence, 0) / sensing.length) : '—'}
                  </div>
                  <div className="ov-score-label">Avg harmonized confidence</div>
                </div>
                <div className="ov-score-card glass-card">
                  <Crosshair size={20} />
                  <div className="ov-score-value">
                    {sensing.length ? Math.max(...sensing.map((r) => r.fused_confidence_boost_pct)) : 0}%
                  </div>
                  <div className="ov-score-label">Best fusion gain</div>
                </div>
              </div>

              <div className="ov-panel glass-card">
                <div className="ov-panel-header"><Satellite size={16} /><h3>Multi-instrument fusion — harmonized confidence</h3></div>
                <div className="ov-list">
                  {sensing.map((r) => (
                    <div key={r.location_id} className="ov-list-item">
                      <div className="ov-list-top">
                        <span className="ov-list-loc">{r.location}</span>
                        <span className="ov-pill" style={{ borderColor: '#22d3ee', color: '#22d3ee' }}>
                          +{r.fused_confidence_boost_pct}% fusion gain
                        </span>
                      </div>
                      <div className="ov-bar-track">
                        <div className="ov-bar-fill" style={{ width: `${r.harmonized_confidence}%`, background: '#22d3ee' }} />
                      </div>
                      <div className="ov-list-meta">
                        <span>{r.harmonized_confidence}/100 harmonized</span>
                        <span>{r.single_source_confidence}/100 single source</span>
                        <span>{r.sources_used.join(' · ')}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="ov-panel glass-card">
                <div className="ov-panel-header"><Crosshair size={16} /><h3>Satellite capability catalogue</h3></div>
                <div className="ov-table">
                  <table>
                    <thead>
                      <tr><th>Satellite</th><th>Serves</th><th>Resolution</th><th>Revisit</th><th>Latency</th><th>Reliability</th></tr>
                    </thead>
                    <tbody>
                      {sensing[0]?.variables?.length ? (
                        sensing[0].variables.map((v, i) => (
                          <tr key={i}>
                            <td className="ov-cell-main">{v.primary_satellite}</td>
                            <td>{v.variable}</td>
                            <td>{v.resolution >= 1000 ? `${(v.resolution / 1000).toFixed(1)} km` : `${v.resolution} m`}</td>
                            <td>{v.revisit_h}h</td>
                            <td>{v.latency_h}h</td>
                            <td>{Math.round(v.reliability * 100)}%</td>
                          </tr>
                        ))
                      ) : (
                        <tr><td colSpan={6} className="ov-empty">No catalogue data</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* ---------- RECOMMEND ---------- */}
          {tab === 'recommend' && (
            <div className="ov-tab-page">
              <div className="ov-score-row">
                <div className="ov-score-card glass-card">
                  <Target size={20} />
                  <div className="ov-score-value">{recoSummary.network_average_obs_need}</div>
                  <div className="ov-score-label">Network avg obs need</div>
                </div>
                <div className="ov-score-card glass-card">
                  <Crosshair size={20} />
                  <div className="ov-score-value">{recoSummary.estimated_observations_needed}</div>
                  <div className="ov-score-label">Sampling passes recommended</div>
                </div>
                <div className="ov-score-card glass-card">
                  <AlertTriangle size={20} />
                  <div className="ov-score-value">{recos.filter((r) => r.active_event).length}</div>
                  <div className="ov-score-label">Active-event regions</div>
                </div>
              </div>

              <div className="ov-panel glass-card">
                <div className="ov-panel-header"><ArrowRight size={16} /><h3>Day plan</h3></div>
                <p className="ov-note">{recoSummary.summary}</p>
              </div>

              {recos.length === 0 && (
                <div className="ov-panel glass-card">
                  <p className="ov-empty">Observation coverage is healthy network-wide — no immediate sampling action required.</p>
                </div>
              )}

              <div className="ov-reco-grid">
                {recos.map((r) => (
                  <motion.div key={r.location_id} className="ov-reco-card glass-card" variants={fadeUp} initial="hidden" animate="visible">
                    <div className="ov-reco-top">
                      <div className="ov-reco-loc">
                        <span className="ov-reco-name">{r.location}</span>
                        <span className="ov-cell-sub">{r.region_type} · {r.count_in_window} readings · last {r.recency_h != null ? `${r.recency_h}h` : '—'} ago</span>
                      </div>
                      <div className="ov-reco-impact">
                        <span className="ov-reco-impact-val">{r.decision_impact}</span>
                        <span className="ov-cell-sub">impact</span>
                      </div>
                    </div>

                    <div className="ov-reco-need">
                      <span className="ov-reco-need-label">Observation need</span>
                      <div className="ov-bar-track">
                        <div className="ov-bar-fill" style={{ width: `${r.obs_need}%`, background: r.obs_need >= 30 ? '#f43f5e' : r.obs_need >= 15 ? '#f59e0b' : '#10b981' }} />
                      </div>
                      <span className="ov-reco-need-val">{r.obs_need}/100</span>
                    </div>

                    {r.active_event && (
                      <div className="ov-reco-event"><AlertTriangle size={13} /> Active event — escalate sampling cadence</div>
                    )}

                    <div className="ov-reco-vars">
                      {r.needs.map((n) => (
                        <div key={n.variable} className="ov-reco-var">
                          <div className="ov-reco-var-head">
                            <Thermometer size={13} />
                            <b className="ov-reco-var-name">{n.variable.replace('_', ' ')}</b>
                            <div className="ov-reco-platforms">
                              {n.platforms.map((p) => <span key={p} className="ov-pill ov-pill-sm">{p}</span>)}
                            </div>
                          </div>
                          <div className="ov-list-sub">{n.reason}</div>
                        </div>
                      ))}
                    </div>

                    <div className="ov-reco-action">{r.action}</div>
                  </motion.div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}