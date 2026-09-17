import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import {
  Loader2, AlertTriangle, MapPin, Thermometer, Waves, Dna, FileText, Crosshair,
  BarChart3, ChevronRight, Activity, Shield, RotateCcw, Info, Target, Radio,
  ShieldAlert, Droplets, Search, History, ShieldCheck,
} from 'lucide-react'
import {
  fetchTideCandidates,
  fetchTideExplanation,
  fetchTideVerdict,
  fetchTideEventContext,
  runVirtualObservation,
} from '../api/client'
import type {
  TideCandidate, TideVerdict, TideEventContext,
  TideExplanation, VirtualObservationSimulation,
} from '../types/tide'
import './Tide.css'

/* ------------------------------------------------------------------ */
/*  Shared motion + constants                                          */
/* ------------------------------------------------------------------ */

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: (i: number) => ({
    opacity: 1, y: 0,
    transition: { delay: i * 0.06, duration: 0.45, ease: 'easeOut' as const },
  }),
}

const VARIABLES = [
  { key: 'temperature', label: 'Temperature', icon: <Thermometer size={14} />, color: '#f43f5e' },
  { key: 'salinity', label: 'Salinity', icon: <Waves size={14} />, color: '#06b6d4' },
  { key: 'oxygen', label: 'Oxygen', icon: <Dna size={14} />, color: '#10b981' },
  { key: 'chlorophyll', label: 'Chlorophyll', icon: <Dna size={14} />, color: '#22c55e' },
  { key: 'current_speed', label: 'Current', icon: <Radio size={14} />, color: '#8b8cf8' },
  { key: 'wave_height', label: 'Waves', icon: <Waves size={14} />, color: '#38bdf8' },
  { key: 'pressure', label: 'Pressure', icon: <Activity size={14} />, color: '#a78bfa' },
  { key: 'nutrients', label: 'Nutrients', icon: <Dna size={14} />, color: '#f59e0b' },
  { key: 'ph', label: 'pH', icon: <Droplets size={14} />, color: '#22d3ee' },
  { key: 'density', label: 'Density', icon: <BarChart3 size={14} />, color: '#64748b' },
]

const VERDICT_STYLE: Record<string, { color: string; bg: string }> = {
  LIKELY_SENSOR_ISSUE:     { color: '#f43f5e', bg: 'rgba(244,63,94,0.12)' },
  LIKELY_MODEL_ISSUE:      { color: '#f59e0b', bg: 'rgba(245,158,11,0.12)' },
  LIKELY_MISSING_PHENOMENON: { color: '#8b8cf8', bg: 'rgba(139,140,248,0.12)' },
  INSUFFICIENT_EVIDENCE:   { color: '#64748b', bg: 'rgba(100,116,139,0.12)' },
}

const DECISION_COLOR: Record<string, string> = {
  INVESTIGATE_ANOMALY: '#f43f5e',
  INCREASE_MONITORING: '#f59e0b',
  CONTINUE_MONITORING: '#10b981',
}

/* ------------------------------------------------------------------ */
/*  Main component                                                    */
/* ------------------------------------------------------------------ */

export default function Tide() {
  const navigate = useNavigate()
  /* ---- core state ---- */
  const [candidates, setCandidates] = useState<TideCandidate[]>([])
  const [selected, setSelected] = useState<TideCandidate | null>(null)
  const [variable, setVariable] = useState('temperature')
  const [depthM] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  /* ---- detail panels ---- */
  const [explanation, setExplanation] = useState<TideExplanation | null>(null)
  const [verdict, setVerdict] = useState<TideVerdict | null>(null)
  const [eventCtx, setEventCtx] = useState<TideEventContext | null>(null)
  const [detailBusy, setDetailBusy] = useState(false)

  /* ---- what-if simulation ---- */
  const [simInput, setSimInput] = useState('')
  const [simulation, setSimulation] = useState<VirtualObservationSimulation | null>(null)
  const [simBusy, setSimBusy] = useState(false)
  const [simError, setSimError] = useState<string | null>(null)

  /* ---- 1. Fetch ranked candidates on variable/depth change ---- */
  useEffect(() => {
    let alive = true
    setLoading(true)
    setError(null)
    fetchTideCandidates({ variable, depth_m: depthM })
      .then((d) => {
        if (!alive) return
        const list = (d?.data ?? []) as TideCandidate[]
        setCandidates(list)
        setSelected(list[0] ?? null)
      })
      .catch(() => {
        if (!alive) return
        setError('TIDE recommendation data is currently unavailable.')
        setCandidates([])
        setSelected(null)
      })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [variable, depthM])

  /* ---- 2. Fetch detail panels for the selected candidate ---- */
  const sel = selected
  useEffect(() => {
    if (!sel) {
      setExplanation(null); setVerdict(null); setEventCtx(null)
      setSimulation(null); setSimInput('')
      return
    }
    let alive = true
    setDetailBusy(true)
    Promise.all([
      fetchTideExplanation({ location_id: sel.location_id, variable: sel.variable, depth_m: sel.depth_m }).catch(() => null),
      fetchTideVerdict({ location_id: sel.location_id, variable: sel.variable, depth_m: sel.depth_m }).catch(() => null),
      fetchTideEventContext('event-0').catch(() => null),
    ])
      .then(([e, v, ev]) => {
        if (!alive) return
        setExplanation(e?.data ?? (e as unknown as TideExplanation) ?? null)
        setVerdict(v?.data ?? (v as unknown as TideVerdict) ?? null)
        setEventCtx(ev?.data ?? (ev as unknown as TideEventContext) ?? null)
      })
      .finally(() => { if (alive) setDetailBusy(false) })
    return () => { alive = false }
  }, [sel])

  /* ---- 3. What-if simulation ---- */
  const runWhatIf = async () => {
    if (!selected) return
    setSimBusy(true); setSimError(null)
    try {
      const d = await runVirtualObservation({
        location_id: selected.location_id,
        variable: selected.variable,
        depth_m: selected.depth_m,
        observation_type: 'VIRTUAL_SENSOR',
        value: simInput.trim() ? parseFloat(simInput.trim()) : undefined,
      })
      setSimulation(d?.data ?? (d as unknown as VirtualObservationSimulation) ?? null)
    } catch {
      setSimError('Could not run the simulation. This is a demonstration-only feature.')
    } finally { setSimBusy(false) }
  }

  /* ---- derived stats ---- */
  const topScore: TideCandidate | undefined = candidates[0]
  const totalCount = candidates.length
  const topLoc = topScore?.location ?? '—'
  const topScoreVal = topScore?.observation_value ?? 0
  const topUncertainty = topScore?.uncertainty ?? 0
  const topGap = topScore?.data_gap ?? 0
  const topEvidenceCount = topScore?.evidence?.length ?? 0
  const activeEvent = eventCtx?.event
  const verdictConf = verdict?.confidence ?? 0

  return (
    <div className="page tide-page">
      {/* ---- Header ---- */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" custom={0} className="page-header">
        <div>
          <h1 className="page-title text-gradient">TIDE Command Center</h1>
          <p className="page-subtitle">
            Phase 5 Interactive Frontend — explainable observation ranking using real
            backend TIDE-Loop data.
          </p>
        </div>
        <div className="tide-legend">
          <span className="legend-chip"><span className="legend-dot" style={{ background: '#22d3ee' }} /> Top candidate</span>
          <span className="legend-chip"><span className="legend-dot" style={{ background: '#f43f5e' }} /> HIGH priority</span>
          <span className="legend-chip"><span className="legend-dot" style={{ background: '#f59e0b' }} /> MEDIUM priority</span>
          <span className="legend-chip"><span className="legend-dot" style={{ background: '#10b981' }} /> LOW priority</span>
          <button className="tide-btn" onClick={() => navigate('/tide/replay')} title="Phase 6: step-by-step replay of the TIDE decision for a detected event">
            <History size={14} /> Decision Replay
          </button>
          <button className="tide-btn" onClick={() => navigate('/tide/validation')} title="Phase 8: honest validation status, baseline benchmarks and limitations">
            <ShieldCheck size={14} /> Validation Center
          </button>
        </div>
      </motion.div>

      {/* ---- Control bar ---- */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" custom={1} className="glass-card tide-controls">
        <span className="tide-controls-label"><Crosshair size={14} /> VARIABLE</span>
        <div className="tide-var-picker">
          {VARIABLES.map((v) => (
            <button
              key={v.key}
              className={`tide-var-pill ${variable === v.key ? 'tide-var-pill-on' : ''}`}
              onClick={() => setVariable(v.key)}
              style={variable === v.key ? { borderColor: v.color, color: v.color } : undefined}
            >
              {v.icon}
              <span>{v.label}</span>
            </button>
          ))}
        </div>
      </motion.div>

      {/* ---- Stats strip ---- */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" custom={2} className="stats-grid tide-stats">
        <div className="stat-card glass-card">
          <div className="stat-card-icon" style={{ borderColor: '#22d3ee', color: '#22d3ee' }}><Target size={18} /></div>
          <div className="stat-card-label">ACTIVE CANDIDATES</div>
          <div className="stat-card-value">{loading ? '…' : totalCount}</div>
          <div className="stat-card-sub">Ranked by observation value</div>
        </div>
        <div className="stat-card glass-card">
          <div className="stat-card-icon" style={{ borderColor: '#38bdf8', color: '#38bdf8' }}><MapPin size={18} /></div>
          <div className="stat-card-label">TOP RANK LOCATION</div>
          <div className="stat-card-value tide-mono-sm">{loading ? '…' : topLoc}</div>
          <div className="stat-card-sub">{loading ? '' : `Score ${topScoreVal.toFixed(4)}`}</div>
        </div>
        <div className="stat-card glass-card">
          <div className="stat-card-icon" style={{ borderColor: '#f59e0b', color: '#f59e0b' }}><ShieldAlert size={18} /></div>
          <div className="stat-card-label">TOP UNCERTAINTY</div>
          <div className="stat-card-value">{loading ? '…' : `${(topUncertainty * 100).toFixed(0)}%`}</div>
          <div className="stat-card-sub">{loading ? '' : `Data gap ${(topGap * 100).toFixed(0)}%`}</div>
        </div>
        <div className="stat-card glass-card">
          <div className="stat-card-icon" style={{ borderColor: '#8b5cf6', color: '#8b5cf6' }}><FileText size={18} /></div>
          <div className="stat-card-label">TOP EVIDENCE</div>
          <div className="stat-card-value">{loading ? '…' : topEvidenceCount}</div>
          <div className="stat-card-sub">Independent TIDE signals</div>
        </div>
        <div className="stat-card glass-card">
          <div className="stat-card-icon" style={{ borderColor: activeEvent ? '#f43f5e' : '#64748b', color: activeEvent ? '#f43f5e' : '#64748b' }}><Activity size={18} /></div>
          <div className="stat-card-label">ACTIVE EVENT</div>
          <div className="stat-card-value tide-mono-sm">{activeEvent ? (activeEvent.event_type ?? '').replace(/_/g, ' ') : 'None'}</div>
          <div className="stat-card-sub">{activeEvent ? `Location #${activeEvent.location_id ?? '—'}` : 'No mapped events in TIDE'}</div>
        </div>
      </motion.div>

      {/* ---- Error state ---- */}
      {error && (
        <motion.div variants={fadeUp} initial="hidden" animate="show" custom={3} className="glass-card tide-empty">
          <AlertTriangle size={32} color="#f43f5e" />
          <p>{error}</p>
          <button className="tide-btn" onClick={() => setVariable((v) => v)}>Retry</button>
        </motion.div>
      )}

      {/* ---- Loading state ---- */}
      {loading && !error && (
        <motion.div variants={fadeUp} initial="hidden" animate="show" custom={3} className="glass-card tide-empty">
          <Loader2 size={32} className="spin" color="#22d3ee" />
          <p>Loading TIDE candidates…</p>
        </motion.div>
      )}

      {/* ---- Empty state ---- */}
      {!loading && !error && candidates.length === 0 && (
        <motion.div variants={fadeUp} initial="hidden" animate="show" custom={3} className="glass-card tide-empty">
          <Search size={32} color="#64748b" />
          <p>No TIDE candidates available for {variable} at {depthM}m.</p>
          <p className="tide-empty-sub">Try a different variable or increase observation data coverage.</p>
        </motion.div>
      )}

      {/* ---- Main layout: Candidate list + detail panels ---- */}
      {!loading && !error && candidates.length > 0 && (
        <motion.div variants={fadeUp} initial="hidden" animate="show" custom={3} className="tide-layout">

          {/* ---- Left: candidate list ---- */}
          <div className="glass-card tide-sidebar">
            <div className="panel-header">
              <h3><Target size={15} /> Candidates</h3>
              <span className="panel-badge">{totalCount} ranked</span>
            </div>
            <div className="tide-candidate-list">
              {candidates.map((c, idx) => {
                const active = selected?.candidate_id === c.candidate_id
                const decColor = DECISION_COLOR[c.affected_decision] ?? '#64748b'
                return (
                  <button
                    key={c.candidate_id}
                    className={`tide-candidate ${active ? 'tide-candidate-active' : ''}`}
                    onClick={() => { setSelected(c); setSimulation(null); setSimInput('') }}
                  >
                    <span className="tide-cand-rank" style={{ color: idx === 0 ? '#22d3ee' : idx < 3 ? '#f59e0b' : '#64748b' }}>#{idx + 1}</span>
                    <div className="tide-cand-body">
                      <div className="tide-cand-loc">{c.location}</div>
                      <div className="tide-cand-meta">
                        <span>{c.variable.replace('_', ' ')}</span>
                        <span className="tide-status" style={{ color: decColor }}>{c.affected_decision.replace(/_/g, ' ')}</span>
                        <span className="tide-method">{c.observation_type.replace(/_/g, ' ')}</span>
                      </div>
                    </div>
                    <span className="tide-cand-score">{c.observation_value.toFixed(4)}</span>
                    {active && <ChevronRight size={14} className="tide-cand-chevron" />}
                  </button>
                )
              })}
            </div>
          </div>

          {/* ---- Right: detail panels ---- */}
          <div className="tide-details">
            {detailBusy && (
              <div className="glass-card tide-detail-card tide-empty">
                <Loader2 size={24} className="spin" color="#22d3ee" />
                <span>Loading detail panels…</span>
              </div>
            )}

            {/* Why This Location */}
            {selected && !detailBusy && (
              <div className="glass-card tide-detail-card">
                <div className="panel-header">
                  <h3><Search size={15} /> Why This Location</h3>
                  <span className="panel-badge">{selected.status.replace(/_/g, ' ')}</span>
                </div>
                <p className="tide-why-text">{selected.reason}</p>
                <div className="tide-why-evidence">
                  {selected.evidence.length > 0
                    ? selected.evidence.map((e) => (
                        <div key={e.evidence_id ?? e.type} className="tide-evidence-chip">
                          <span className="tide-ev-type">{e.type.replace(/_/g, ' ')}</span>
                          <span className="tide-ev-strength">strength {(e.strength * 100).toFixed(0)}%</span>
                        </div>
                      ))
                    : <span className="tide-muted">No standalone evidence signals were available.</span>}
                </div>
                {selected.limitations.length > 0 && (
                  <div className="tide-limitations">
                    <Info size={12} /> {selected.limitations[0]}
                  </div>
                )}
              </div>
            )}

            {/* Observation Value — formula breakdown (Phase 7) */}
            {selected && !detailBusy && (
              <div className="glass-card tide-detail-card">
                <div className="panel-header">
                  <h3><Target size={15} /> Observation Value — Formula</h3>
                  <span className="panel-badge">heuristic</span>
                </div>
                <div className="tide-formula" aria-label="Observation value formula">
                  <span className="tide-formula-term">Decision Impact</span>
                  <span className="tide-formula-op">×</span>
                  <span className="tide-formula-term">Uncertainty</span>
                  <span className="tide-formula-op">×</span>
                  <span className="tide-formula-term">Data Gap</span>
                  <span className="tide-formula-op">×</span>
                  <span className="tide-formula-term">Anomaly Persistence</span>
                  <span className="tide-formula-op">÷</span>
                  <span className="tide-formula-term">Observation Cost</span>
                </div>
                <div className="tide-formula-rows">
                  {[
                    { label: 'Decision Impact', value: selected.decision_impact },
                    { label: 'Uncertainty', value: selected.uncertainty },
                    { label: 'Data Gap', value: selected.data_gap },
                    { label: 'Anomaly Persistence', value: selected.anomaly_persistence },
                    { label: 'Observation Cost', value: selected.observation_cost },
                  ].map((f) => (
                    <div className="tide-formula-row" key={f.label}>
                      <span className="tide-formula-label">{f.label}</span>
                      <span className="tide-formula-bar"><i style={{ width: `${Math.min(100, Math.round(f.value * 100))}%` }} /></span>
                      <span className="tide-formula-val">{f.value.toFixed(3)}</span>
                    </div>
                  ))}
                </div>
                <div className="tide-formula-result">
                  <span>Observation Value</span>
                  <b>{selected.observation_value.toFixed(4)}</b>
                </div>
                <div className="tide-formula-result tide-formula-result-sub">
                  <span>Expected uncertainty reduction</span>
                  <b>{(selected.expected_uncertainty_reduction * 100).toFixed(0)}%</b>
                </div>
                <div className="tide-limitations">
                  <Info size={12} /> Observation Value is a decision-support heuristic, not a scientifically validated information-gain metric.
                </div>
              </div>
            )}

            {/* Confidence + Verdict */}
            {!detailBusy && (
              <div className="glass-card tide-detail-card">
                <div className="panel-header">
                  <h3><Shield size={15} /> Confidence & Verdict</h3>
                </div>
                {verdict ? (
                  <div className="tide-verdict-wrap">
                    <div className="tide-verdict-badge" style={{
                      color: VERDICT_STYLE[verdict.verdict]?.color ?? '#64748b',
                      background: VERDICT_STYLE[verdict.verdict]?.bg ?? 'rgba(100,116,139,0.1)',
                    }}>
                      {verdict.verdict.replace(/_/g, ' ')}
                    </div>
                    <p className="tide-verdict-summary">{verdict.summary}</p>
                    <div className="tide-verdict-meta">
                      <span><b>{(verdictConf * 100).toFixed(0)}%</b> confidence</span>
                      <span>{verdict.evidence.length} evidence signals</span>
                    </div>
                    {verdict.alternative_explanation && (
                      <p className="tide-alt-explain">Alternative: {verdict.alternative_explanation}</p>
                    )}
                    <div className="tide-verdict-evidence">
                      {verdict.evidence.slice(0, 4).map((e) => (
                        <div key={e.evidence_id ?? e.type} className="tide-ev-item">
                          <span className="tide-ev-source">{e.source_system ?? 'TIDE'}</span>
                          <span>{e.description}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="tide-muted"><Info size={13} /> Verdict data is not available for this location.</div>
                )}
              </div>
            )}

            {/* Event DNA */}
            {!detailBusy && eventCtx && (
              <div className="glass-card tide-detail-card">
                <div className="panel-header">
                  <h3><FileText size={15} /> Event DNA → TIDE</h3>
                  <span className="panel-badge">{eventCtx.event_id}</span>
                </div>
                <div className="tide-event-dna">
                  <div className="tide-dna-tags">
                    {(eventCtx.event_dna?.tags ?? []).length > 0
                      ? eventCtx.event_dna.tags.map((t) => <span key={t} className="tide-dna-chip">{t}</span>)
                      : <span className="tide-muted">No categorical DNA tags available.</span>}
                  </div>
                  {eventCtx.event && (
                    <div className="tide-event-summary">
                      <span><b>Type:</b> {(eventCtx.event.event_type ?? '—').replace(/_/g, ' ')}</span>
                      {eventCtx.event.model != null && <span><b>Model:</b> {eventCtx.event.model}</span>}
                      {eventCtx.event.observed != null && <span><b>Observed:</b> {eventCtx.event.observed}</span>}
                    </div>
                  )}
                  {eventCtx.message && <p className="tide-muted">{eventCtx.message}</p>}
                </div>
              </div>
            )}

            {/* Explanation */}
            {!detailBusy && explanation && (
              <div className="glass-card tide-detail-card">
                <div className="panel-header">
                  <h3><Info size={15} /> Explanation</h3>
                </div>
                <p className="tide-explain-summary">{explanation.explanation.summary}</p>
                <ul className="tide-explain-reasons">
                  {explanation.explanation.reasons.map((r, i) => <li key={i}>{r}</li>)}
                </ul>
                <p className="tide-explain-benefit">{explanation.explanation.expected_benefit}</p>
                <div className="tide-explain-evidence">
                  {explanation.explanation.evidence.slice(0, 4).map((e) => (
                    <div key={e.evidence_id ?? e.type} className="tide-ev-item">
                      <span className="tide-ev-source">{e.source_system ?? 'TIDE'}</span>
                      <span>{e.description}</span>
                    </div>
                  ))}
                </div>
                <div className="tide-decision-ctx">
                  <span>Affected decision: <b style={{ color: DECISION_COLOR[explanation.explanation.affected_decision] ?? '#22d3ee' }}>{explanation.explanation.affected_decision.replace(/_/g, ' ')}</b></span>
                </div>
              </div>
            )}

            {/* What-If Simulation */}
            {!detailBusy && selected && (
              <div className="glass-card tide-detail-card tide-whatif">
                <div className="panel-header">
                  <h3><RotateCcw size={15} /> What-If Simulation</h3>
                  <span className="panel-badge">SIMULATED</span>
                </div>
                <p className="tide-whatif-desc">
                  Run a deterministic what-if for <b>{selected.location}</b> ({selected.variable}).
                  The simulated reading is never written to the observation store.
                </p>
                <div className="tide-whatif-input">
                  <input
                    type="number"
                    value={simInput}
                    onChange={(e) => setSimInput(e.target.value)}
                    placeholder={`Optional: custom ${selected.variable} value`}
                  />
                  <button className="tide-btn" disabled={simBusy} onClick={runWhatIf}>
                    {simBusy ? <Loader2 size={14} className="spin" /> : <RotateCcw size={14} />}
                    {simBusy ? 'Simulating…' : 'Run What-If'}
                  </button>
                </div>
                {simError && <p className="tide-sim-error"><AlertTriangle size={13} /> {simError}</p>}
                {simulation && (
                  <div className="tide-sim-result">
                    <div className="tide-sim-note">{simulation.notes[0]}</div>
                    <div className="tide-sim-grid">
                      <div className="tide-sim-cell">
                        <span className="tide-sim-label">Uncertainty</span>
                        <span className="tide-sim-val">{(simulation.uncertainty_change.before * 100).toFixed(0)}% → {(simulation.uncertainty_change.after * 100).toFixed(0)}%</span>
                        <span className={`tide-sim-delta ${simulation.uncertainty_change.delta <= 0 ? 'down' : 'up'}`}>{simulation.uncertainty_change.delta > 0 ? '+' : ''}{(simulation.uncertainty_change.delta * 100).toFixed(1)}%</span>
                      </div>
                      <div className="tide-sim-cell">
                        <span className="tide-sim-label">Anomaly Risk</span>
                        <span className="tide-sim-val">{(simulation.risk_change.before * 100).toFixed(0)}% → {(simulation.risk_change.after * 100).toFixed(0)}%</span>
                        <span className={`tide-sim-delta ${simulation.risk_change.delta <= 0 ? 'down' : 'up'}`}>{simulation.risk_change.delta > 0 ? '+' : ''}{(simulation.risk_change.delta * 100).toFixed(1)}%</span>
                      </div>
                      <div className="tide-sim-cell">
                        <span className="tide-sim-label">Ranking</span>
                        <span className="tide-sim-val">#{simulation.before.ranking} → #{simulation.after.ranking}</span>
                        <span className={`tide-sim-delta ${simulation.after.ranking <= simulation.before.ranking ? 'down' : 'up'}`}>{simulation.after.ranking <= simulation.before.ranking ? 'Improved' : 'Worse'}</span>
                      </div>
                      <div className="tide-sim-cell">
                        <span className="tide-sim-label">Decision</span>
                        <span className="tide-sim-val">{simulation.before.decision.replace(/_/g, ' ')}</span>
                        <span className={`tide-sim-delta ${simulation.decision_changed ? 'up' : ''}`} style={{ color: simulation.decision_changed ? '#22d3ee' : '#64748b' }}>
                          {simulation.decision_changed ? 'CHANGED' : 'Unchanged'}
                        </span>
                      </div>
                    </div>
                    {simulation.simulated_observation.value != null && (
                      <div className="tide-sim-reading">
                        Simulated reading: <b>{simulation.simulated_observation.value} {selected.variable.replace(/_/g, ' ')}</b> · {simulation.simulated_observation.status}
                      </div>
                    )}
                    {simulation.supports_model_hypothesis != null && (
                      <div className="tide-sim-support">
                        Supports model hypothesis: <b>{simulation.supports_model_hypothesis ? 'Yes' : 'No'}</b>
                      </div>
                    )}
                    <button
                      className="tide-btn tide-replay-open"
                      onClick={() =>
                        navigate(
                          `/tide/replay?location_id=${encodeURIComponent(selected.location_id)}&variable=${selected.variable}&depth_m=${selected.depth_m}${simulation.simulated_observation.value != null ? `&value=${simulation.simulated_observation.value}` : ''}`
                        )
                      }
                      title="Open the Phase 6 Decision Replay using this simulated observation"
                    >
                      <History size={14} /> Open Decision Replay
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </motion.div>
      )}
    </div>
  )
}
