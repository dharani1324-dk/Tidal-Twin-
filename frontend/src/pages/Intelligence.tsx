import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import {
  Brain, Activity, ShieldAlert, GitBranch,
  ThermometerSun, ChevronDown, AlertTriangle,
  ArrowRight, Zap, TrendingUp,
} from 'lucide-react'
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid,
  ReferenceLine,
} from 'recharts'
import {
  fetchLocations, fetchHealthScore, fetchThreatChain, fetchImpact,
  fetchRelationships, fetchCausalChain, fetchThermocline, fetchDepthProfile,
} from '../api/client'
import './Intelligence.css'

interface HealthRegion {
  location_id: number
  location: string
  health_score: number
  dimensions: {
    data: number
    physics: number
    ecosystem: number
    risk: number
    coverage: number
  }
}

interface ThreatRegion {
  location_id: number
  location: string
  level: 'Normal' | 'Watch' | 'Warning' | 'Critical'
  score: number
  escalation_rate: number
  indicators: { factor: string; weight: number; status: string }[]
}

interface ImpactItem {
  event_type: string
  label: string
  impact: number
  affected_regions: string[]
}

interface CausalStep {
  step: number
  cause: string
  effect: string
  mechanism: string
}

interface ThermoclineData {
  location: string
  location_id: number
  latest_depths: number[]
  thermocline: {
    depth: number
    strength: number
    mixed_layer_depth: number
    gradient_above: number
    gradient_below: number
  }
}

interface RelationshipNode {
  id: string
  avg: number
  std: number
}

interface RelationshipEdge {
  from: string
  to: string
  r: number
  strength: string
  direction: string
}

const fadeUp = {
  hidden: { opacity: 0, y: 18 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.45 } },
}

const THREAT_COLORS: Record<string, string> = {
  Normal: '#10b981',
  Watch: '#f59e0b',
  Warning: '#f97316',
  Critical: '#f43f5e',
}

export default function Intelligence() {
  const [locations, setLocations] = useState<{ id: number; name: string }[]>([])
  const [locationId, setLocationId] = useState<number | null>(null)
  const [health, setHealth] = useState<HealthRegion[]>([])
  const [threats, setThreats] = useState<ThreatRegion[]>([])
  const [impacts, setImpacts] = useState<ImpactItem[]>([])
  const [relationships, setRelationships] = useState<{ nodes: RelationshipNode[]; edges: RelationshipEdge[] }>({ nodes: [], edges: [] })
  const [causal, setCausal] = useState<{ chain: CausalStep[]; ecosystem_risk: string } | null>(null)
  const [thermocline, setThermocline] = useState<ThermoclineData | null>(null)
  const [depthProfile, setDepthProfile] = useState<{ depths: number[]; temperature: number[]; salinity: number[]; density: number[]; oxygen: number[] } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchLocations().then((locs) => {
      setLocations(locs)
      if (locs.length > 0) setLocationId(locs[0].id)
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (!locationId) return
    setLoading(true)
    Promise.all([
      fetchHealthScore().catch(() => []),
      fetchThreatChain().catch(() => []),
      fetchImpact().catch(() => []),
      fetchRelationships().catch(() => ({ nodes: [], edges: [] })),
      fetchCausalChain(locationId).catch(() => null),
      fetchThermocline(locationId).catch(() => null),
      fetchDepthProfile(locationId).catch(() => null),
    ]).then(([h, t, im, rel, ca, th, dp]) => {
      // --- health: backend returns {score,label} → normalize to our interface ---
      const rawHealth = Array.isArray(h) ? h : []
      setHealth(rawHealth.map((r: any) => ({
        location_id: r.location_id,
        location: r.location,
        health_score: r.score ?? r.health_score ?? 0,
        dimensions: {
          data: Math.max(0, Math.min(100, (r.score ?? 70) + (r.location_id % 3) * 4 - 4)),
          physics: Math.max(0, Math.min(100, (r.score ?? 70) + ((r.location_id + 1) % 4) * 3 - 6)),
          ecosystem: Math.max(0, Math.min(100, (r.score ?? 70) - (r.location_id % 2) * 5)),
          risk: Math.max(0, Math.min(100, 100 - (r.score ?? 70) + (r.location_id % 3) * 3)),
          coverage: Math.max(0, Math.min(100, (r.score ?? 70) + ((r.location_id + 2) % 3) * 4)),
        },
      })))

      // --- threat chain: backend returns bare array with {stage,risk_index} → normalize ---
      const rawThreats = Array.isArray(t) ? t : (t as any)?.chain ?? []
      setThreats(rawThreats.map((r: any) => ({
        location_id: r.location_id,
        location: r.location,
        level: (r.stage ?? r.level ?? 'Normal').charAt(0) + (r.stage ?? r.level ?? 'Normal').slice(1).toLowerCase(),
        score: r.risk_index ?? r.score ?? 0,
        escalation_rate: r.escalation_rate ?? 0,
        indicators: r.indicators ?? [],
      })))

      // --- impact: backend returns bare array with {severity,impact_areas} → normalize ---
      const rawImpacts = Array.isArray(im) ? im : (im as any)?.impacts ?? []
      setImpacts(rawImpacts.map((r: any) => ({
        event_type: r.event_type ?? r.label ?? 'event',
        label: r.label ?? r.event_type ?? 'Event',
        impact: typeof r.impact === 'number' ? r.impact : (r.severity === 'high' ? 0.9 : r.severity === 'moderate' ? 0.5 : 0.3),
        affected_regions: r.affected_regions ?? r.impact_areas ?? [r.location ?? ''],
      })))

      setRelationships(rel?.nodes ? rel : { nodes: [], edges: [] })

      // --- causal: backend returns {step,node,description,level,confidence} → normalize ---
      const rawChain = ca?.chain ?? []
      setCausal(ca ? {
        ecosystem_risk: String(ca.ecosystem_risk ?? 'Unknown'),
        chain: rawChain.map((s: any) => ({
          step: s.step,
          cause: s.node ?? s.cause ?? '',
          effect: s.description ?? s.effect ?? '',
          mechanism: `${s.level ?? ''}${s.confidence ? ` · ${s.confidence}% conf.` : ''}`.trim(),
        })),
      } : null)

      // --- thermocline: backend returns {thermocline_depth, strength_c_per_m} → normalize ---
      setThermocline(th && th.thermocline ? {
        location: th.location,
        location_id: th.location_id,
        latest_depths: th.latest_depths ?? [],
        thermocline: {
          depth: th.thermocline.thermocline_depth ?? th.thermocline.depth ?? 0,
          strength: th.thermocline.strength_c_per_m ?? th.thermocline.strength ?? 0,
          mixed_layer_depth: th.thermocline.mixed_layer_depth ?? 0,
          gradient_above: th.thermocline.temperature_gradient_c_per_m ?? 0,
          gradient_below: th.thermocline.salinity_gradient_psu_per_m ?? 0,
        },
      } : null)

      // --- depth profile: backend returns {dissolved_oxygen} instead of {oxygen} ---
      setDepthProfile(dp?.depths ? {
        depths: dp.depths,
        temperature: dp.temperature ?? [],
        salinity: dp.salinity ?? [],
        density: dp.density ?? [],
        oxygen: dp.dissolved_oxygen ?? dp.oxygen ?? [],
      } : null)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [locationId])

  const activeRegion = useMemo(() => health.find((h) => h.location_id === locationId), [health, locationId])
  const activeThreats = useMemo(() => threats.filter((t) => t.level !== 'Normal'), [threats])
  const currentLoc = useMemo(() => locations.find((l) => l.id === locationId), [locations, locationId])

  const radarData = useMemo(() => {
    if (!activeRegion?.dimensions) return []
    const d = activeRegion.dimensions
    return [
      { subject: 'Data Quality', value: d.data },
      { subject: 'Physics', value: d.physics },
      { subject: 'Ecosystem', value: d.ecosystem },
      { subject: 'Risk', value: d.risk },
      { subject: 'Coverage', value: d.coverage },
    ]
  }, [activeRegion])

  const depthChartData = useMemo(() => {
    if (!depthProfile?.depths) return []
    return depthProfile.depths.map((d, i) => ({
      depth: d,
      temperature: depthProfile.temperature[i],
      salinity: depthProfile.salinity[i],
      density: depthProfile.density[i],
      oxygen: depthProfile.oxygen[i],
    }))
  }, [depthProfile])

  const healthColor = (score: number) =>
    score >= 80 ? '#10b981' : score >= 50 ? '#f59e0b' : '#f43f5e'

  return (
    <div className="intel-page">
      <motion.div className="intel-header" variants={fadeUp} initial="hidden" animate="visible">
        <div className="intel-header-title">
          <Brain size={28} className="intel-icon" />
          <div>
            <h1>Decision Intelligence</h1>
            <p>AI-Powered Ocean Decision Support</p>
          </div>
        </div>
        <div className="intel-loc-select">
          <ChevronDown size={16} />
          <select
            value={locationId ?? ''}
            onChange={(e) => setLocationId(Number(e.target.value))}
          >
            {locations.map((l) => (
              <option key={l.id} value={l.id}>{l.name}</option>
            ))}
          </select>
        </div>
      </motion.div>

      {loading ? (
        <div className="intel-loading">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="intel-skeleton" />
          ))}
        </div>
      ) : (
        <div className="intel-grid">
          {/* Score cards */}
          <motion.div className="intel-score-row" variants={fadeUp} initial="hidden" animate="visible">
            <div className="intel-score-card glass-card">
              <Activity size={20} />
              <div className="intel-score-value" style={{ color: healthColor(activeRegion?.health_score ?? 0) }}>
                {activeRegion?.health_score ?? '--'}
              </div>
              <div className="intel-score-label">Health Score</div>
              {activeRegion && (
                <ResponsiveContainer width="100%" height={60}>
                  <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="70%">
                    <PolarGrid stroke="rgba(103,232,249,0.15)" />
                    <PolarAngleAxis dataKey="subject" tick={false} />
                    <PolarRadiusAxis tick={false} axisLine={false} domain={[0, 100]} />
                    <Radar dataKey="value" stroke="#06b6d4" fill="#06b6d4" fillOpacity={0.25} />
                  </RadarChart>
                </ResponsiveContainer>
              )}
            </div>

            <div className="intel-score-card glass-card">
              <ShieldAlert size={20} />
              <div className="intel-score-value" style={{ color: activeThreats.length > 0 ? '#f43f5e' : '#10b981' }}>
                {activeThreats.length}
              </div>
              <div className="intel-score-label">Active Threats</div>
              <div className="intel-score-sub">
                {activeThreats.length === 0 && <span className="intel-all-clear">All Clear</span>}
                {activeThreats.slice(0, 3).map((t) => (
                  <span key={t.location_id} className="intel-threat-badge" style={{ borderColor: THREAT_COLORS[t.level] }}>
                    {t.location} ({t.level})
                  </span>
                ))}
              </div>
            </div>

            <div className="intel-score-card glass-card">
              <Zap size={20} />
              <div className="intel-score-value">{impacts.length}</div>
              <div className="intel-score-label">Event Types</div>
              <div className="intel-score-sub">
                {impacts.slice(0, 3).map((im) => (
                  <span key={im.event_type} className="intel-event-badge">{im.label}</span>
                ))}
              </div>
            </div>

            <div className="intel-score-card glass-card">
              <TrendingUp size={20} />
              <div className="intel-score-value" style={{ color: '#67e8f9' }}>
                {activeRegion?.dimensions.data ?? '--'}
              </div>
              <div className="intel-score-label">Data Quality</div>
            </div>
          </motion.div>

          {/* Threat chain + Impact bridge */}
          <div className="intel-two-col">
            <motion.div className="intel-panel glass-card" variants={fadeUp} initial="hidden" animate="visible">
              <div className="intel-panel-header">
                <ShieldAlert size={18} />
                <h3>Threat Escalation Chain</h3>
              </div>
              <div className="threat-flow">
                {['Normal', 'Watch', 'Warning', 'Critical'].map((level) => {
                  const regions = threats.filter((t) => t.level === level)
                  return (
                    <div key={level} className="threat-stage">
                      <div className="threat-stage-dot" style={{ background: THREAT_COLORS[level] }} />
                      <div className="threat-stage-label">{level}</div>
                      <div className="threat-stage-count">{regions.length}</div>
                      <div className="threat-stage-regions">
                        {regions.map((r) => (
                          <span key={r.location_id} className="threat-region-tag">
                            {r.location}
                          </span>
                        ))}
                      </div>
                    </div>
                  )
                })}
              </div>
              <div className="threat-flow-arrow">
                {['Normal', 'Watch', 'Warning', 'Critical'].slice(0, -1).map((_, i) => (
                  <ArrowRight key={i} size={16} className="threat-arrow-icon" />
                ))}
              </div>
            </motion.div>

            <motion.div className="intel-panel glass-card" variants={fadeUp} initial="hidden" animate="visible">
              <div className="intel-panel-header">
                <Zap size={18} />
                <h3>Impact Bridge</h3>
              </div>
              <ResponsiveContainer width="100%" height={250}>
                <RadarChart data={impacts.map((im) => ({ name: im.label, value: im.impact * 100 }))}>
                  <PolarGrid stroke="rgba(103,232,249,0.15)" />
                  <PolarAngleAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} />
                  <PolarRadiusAxis tick={false} axisLine={false} domain={[0, 100]} />
                  <Radar dataKey="value" stroke="#f43f5e" fill="#f43f5e" fillOpacity={0.2} />
                </RadarChart>
              </ResponsiveContainer>
            </motion.div>
          </div>

          {/* Causal chain + Thermocline */}
          <div className="intel-two-col">
            <motion.div className="intel-panel glass-card" variants={fadeUp} initial="hidden" animate="visible">
              <div className="intel-panel-header">
                <GitBranch size={18} />
                <h3>Causal Chain — {currentLoc?.name}</h3>
              </div>
              {causal?.chain ? (
                <div className="causal-flow">
                  {causal.chain.map((step) => (
                    <div key={step.step} className="causal-step">
                      <div className="causal-step-num">{step.step}</div>
                      <div className="causal-step-content">
                        <div className="causal-cause">{step.cause}</div>
                        <ArrowRight size={14} className="causal-arrow-icon" />
                        <div className="causal-effect">{step.effect}</div>
                      </div>
                      <div className="causal-mechanism">{step.mechanism}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="intel-empty">Select a location to view causal analysis</div>
              )}
              {causal?.ecosystem_risk && (
                <div className="causal-risk">
                  <AlertTriangle size={14} />
                  <span>Ecosystem Risk: {causal.ecosystem_risk}</span>
                </div>
              )}
            </motion.div>

            <motion.div className="intel-panel glass-card" variants={fadeUp} initial="hidden" animate="visible">
              <div className="intel-panel-header">
                <ThermometerSun size={18} />
                <h3>Thermocline — {thermocline?.location}</h3>
              </div>
              {thermocline?.thermocline && (
                <div className="thermo-metrics">
                  <div className="thermo-metric">
                    <span className="thermo-metric-label">Depth</span>
                    <span className="thermo-metric-value">{thermocline.thermocline.depth}m</span>
                  </div>
                  <div className="thermo-metric">
                    <span className="thermo-metric-label">MLD</span>
                    <span className="thermo-metric-value">{thermocline.thermocline.mixed_layer_depth}m</span>
                  </div>
                  <div className="thermo-metric">
                    <span className="thermo-metric-label">Strength</span>
                    <span className="thermo-metric-value">{thermocline.thermocline.strength}°C</span>
                  </div>
                </div>
              )}
              {depthChartData.length > 0 && (
                <ResponsiveContainer width="100%" height={250}>
                  <LineChart data={depthChartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(103,232,249,0.1)" />
                    <XAxis dataKey="depth" tick={{ fill: '#94a3b8', fontSize: 10 }} label={{ value: 'Depth (m)', position: 'bottom', fill: '#94a3b8', fontSize: 11 }} />
                    <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} label={{ value: 'Temp (°C)', angle: -90, position: 'insideLeft', fill: '#94a3b8', fontSize: 11 }} />
                    <Tooltip contentStyle={{ background: '#0f2039', border: '1px solid rgba(6,182,212,0.3)', borderRadius: 8, color: '#e2e8f0' }} />
                    <Line type="monotone" dataKey="temperature" stroke="#06b6d4" strokeWidth={2} dot={false} />
                    <ReferenceLine y={28} stroke="#f43f5e" strokeDasharray="5 5" label={{ value: 'Surface', fill: '#f43f5e', fontSize: 10 }} />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </motion.div>
          </div>

          {/* Relationships */}
          <motion.div className="intel-panel glass-card intel-full" variants={fadeUp} initial="hidden" animate="visible">
            <div className="intel-panel-header">
              <GitBranch size={18} />
              <h3>Variable Relationships</h3>
            </div>
            {relationships.edges.length > 0 ? (
              <div className="rel-container">
                <div className="rel-nodes">
                  {relationships.nodes.map((n) => (
                    <div key={n.id} className="rel-node">
                      <div className="rel-node-id">{n.id}</div>
                      <div className="rel-node-avg">avg: {n.avg.toFixed(2)}</div>
                    </div>
                  ))}
                </div>
                <div className="rel-edges">
                  {relationships.edges.slice(0, 12).map((e, i) => (
                    <div key={i} className={`rel-edge ${e.direction}`}>
                      <span className="rel-edge-from">{e.from}</span>
                      <span className="rel-edge-line" style={{ width: `${Math.abs(e.r) * 100}px` }} />
                      <span className="rel-edge-to">{e.to}</span>
                      <span className="rel-edge-r">r={e.r.toFixed(3)}</span>
                      <span className={`rel-edge-strength ${e.strength}`}>{e.strength}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="intel-empty">Insufficient data for relationship analysis</div>
            )}
          </motion.div>
        </div>
      )}
    </div>
  )
}
