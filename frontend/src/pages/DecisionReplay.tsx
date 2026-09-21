import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  Play, Pause, SkipBack, SkipForward, RotateCcw, Activity, Crosshair,
  Camera, ShieldAlert, AlertTriangle, Info, Target, Dna, Loader2, Search,
  CheckCircle2, XCircle, Globe2, Database, BarChart3, FlaskConical,
  Scale, ChevronRight,
} from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceLine, Legend, CartesianGrid,
} from 'recharts'
import CesiumGlobe from '../components/3d/globe/CesiumGlobe'
import type { LayersState, ReplayGlobeMarker } from '../components/3d/globe/CesiumGlobe'
import type { GlobeLocation } from '../components/3d/globe/CesiumGlobe'
import { fetchLocations, fetchTideEventIndex, fetchDecisionReplay } from '../api/client'
import type { DecisionReplay, ReplayEventItem, ReplayState } from '../types/tide'
import './DecisionReplay.css'

/* ------------------------------------------------------------------ */
/*  Shared presentation constants                                       */
/* ------------------------------------------------------------------ */

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: (i: number) => ({
    opacity: 1, y: 0,
    transition: { delay: i * 0.06, duration: 0.45, ease: 'easeOut' as const },
  }),
}

const DECISION_COLOR: Record<string, string> = {
  INVESTIGATE_ANOMALY: '#f43f5e',
  INCREASE_MONITORING: '#f59e0b',
  CONTINUE_MONITORING: '#10b981',
}

const LOOP_META: Record<string, { icon: React.ComponentType<{ size?: number; color?: string }>; color: string }> = {
  MODEL: { icon: Database, color: '#22d3ee' },
  OBSERVATION: { icon: Camera, color: '#38bdf8' },
  DISAGREEMENT: { icon: GitIcon, color: '#f43f5e' },
  UNCERTAINTY: { icon: Activity, color: '#f59e0b' },
  NEXT_OBSERVATION: { icon: Crosshair, color: '#8b8cf8' },
  DECISION: { icon: Scale, color: '#fbbf24' },
  VALIDATION: { icon: CheckCircle2, color: '#34d399' },
}

function GitIcon({ size }: { size?: number }) {
  return <XCircle size={size ?? 15} />
}

const LAYER_DEFAULTS: LayersState = {
  labels: true,
  temperature: true,
  waves: false,
  currents: false,
  storm: false,
  uncertainty: false,
  priority: false,
  argo: false,
  realArgo: false,
  realSST: false,
  realChl: false,
  disagreement: false,
  anomalies: false,
  tide: false,
  isos: false,
  vectors: false,
  modelgrid: false,
  glider: false,
}

const pct = (v: number | string | null | undefined): string => {
  const n = typeof v === 'number' ? v : typeof v === 'string' ? Number(v) : null
  return n == null ? '—' : `${(n * 100).toFixed(0)}%`
}

const num = (v: number | null | undefined, d = 3): string =>
  v == null ? '—' : v.toFixed(d)

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */

export default function DecisionReplay() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const initial = {
    location_id: searchParams.get('location_id') ? Number(searchParams.get('location_id')) : undefined,
    variable: searchParams.get('variable') ?? undefined,
    depth_m: searchParams.get('depth_m') ? Number(searchParams.get('depth_m')) : 0,
    value: searchParams.get('value') ? Number(searchParams.get('value')) : undefined,
  }

  const [events, setEvents] = useState<ReplayEventItem[]>([])
  const [eventId, setEventId] = useState(searchParams.get('event') ?? '')
  const [replay, setReplay] = useState<DecisionReplay | null>(null)
  const [locations, setLocations] = useState<GlobeLocation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  /* ---- playback ---- */
  const [stepIdx, setStepIdx] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [flyTo, setFlyTo] = useState<{ locId: number; n: number } | null>(null)

  /* ---- 1. Load the playable event index + globe regions ---- */
  useEffect(() => {
    let alive = true
    fetchTideEventIndex()
      .then((d) => {
        if (!alive) return
        const list = (d?.data?.events ?? []) as ReplayEventItem[]
        setEvents(list)
        if (list.length > 0 && !searchParams.get('event')) setEventId(list[0].event_id)
      })
      .catch(() => { /* index is advisory only */ })
    fetchLocations()
      .then((d) => { if (alive) setLocations(d ?? []) })
      .catch(() => { /* globe falls back to built-in coasts */ })
    return () => { alive = false }
  }, [searchParams])

  /* ---- 2. Build the replay whenever the selected event changes ---- */
  useEffect(() => {
    if (!eventId) return
    let alive = true
    setLoading(true)
    setError(null)
    setPlaying(false)
    setStepIdx(0)
    fetchDecisionReplay({
      eventId,
      location_id: initial.location_id,
      variable: initial.variable,
      depth_m: initial.depth_m,
      value: initial.value,
    })
      .then((d) => {
        if (!alive) return
        setReplay(d?.data ?? (d as unknown as DecisionReplay) ?? null)
        if (d?.data?.location_id) {
          setFlyTo({ locId: d.data.location_id, n: 1 })
        }
      })
      .catch(() => {
        if (alive) setError('The Decision Replay could not be built for this event.')
        setReplay(null)
      })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [eventId, initial.location_id, initial.variable, initial.depth_m, initial.value])

  /* ---- 3. Playback clock ---- */
  useEffect(() => {
    if (!playing || !replay) return
    if (stepIdx >= replay.steps.length - 1) { setPlaying(false); return }
    const t = setTimeout(() => setStepIdx((i) => Math.min(replay.steps.length - 1, i + 1)), 2600)
    return () => clearTimeout(t)
  }, [playing, stepIdx, replay])

  /* ---- 4. Camera focus at the observation step ---- */
  useEffect(() => {
    const obs = replay?.steps.findIndex((s) => s.id === 'OBSERVATION') ?? -1
    if (replay && stepIdx === obs) {
      setFlyTo((p) => ({ locId: replay.location_id, n: (p?.n ?? 0) + 1 }))
    }
  }, [stepIdx, replay])

  /* ---- 5. Globe markers for the current step ---- */
  const stepIds = useMemo(() => replay?.steps.map((s) => s.id) ?? [], [replay])
  const recIdx = stepIds.indexOf('TIDE_RECOMMENDATION')
  const obsIdx = stepIds.indexOf('OBSERVATION')

  const replayMarkers: ReplayGlobeMarker[] = useMemo(() => {
    if (!replay) return []
    const loc = locations.find((l) => l.id === replay.location_id)
    if (!loc || loc.latitude == null || loc.longitude == null) return []
    const lat = loc.latitude
    const lon = loc.longitude
    const markers: ReplayGlobeMarker[] = [
      {
        id: 'replay-event',
        kind: 'event',
        lat,
        lon,
        label: `${replay.event.label ?? replay.event.event_type ?? 'EVENT'} · ${replay.location}`,
        visible: stepIdx >= 0,
        location_id: replay.location_id,
      },
      {
        id: 'replay-tide',
        kind: 'candidate',
        lat,
        lon,
        label: `TIDE #1 · ${replay.variable.replace(/_/g, ' ')}`,
        visible: recIdx >= 0 && stepIdx >= recIdx,
        location_id: replay.location_id,
      },
      {
        id: 'replay-obs',
        kind: 'observation',
        lat,
        lon,
        label: 'Sim. observation',
        visible: obsIdx >= 0 && stepIdx >= obsIdx,
        location_id: replay.location_id,
      },
    ]
    return markers
  }, [replay, locations, stepIdx, recIdx, obsIdx])

  const currentStep = replay?.steps[stepIdx] ?? null

  return (
    <div className="page replay-page">
      {/* ---- Header ---- */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" custom={0} className="page-header">
        <div>
          <h1 className="page-title text-gradient">TIDE Decision Replay</h1>
          <p className="page-subtitle">
            Phase 6 — read-only, two-mode replay of a detected ocean event:
            MODEL-ONLY vs TIDE-ASSISTED, step-by-step.
          </p>
        </div>
        <div className="replay-legend">
          <span className="legend-chip"><span className="legend-dot" style={{ background: '#a5f3fc' }} /> Event</span>
          <span className="legend-chip"><span className="legend-dot" style={{ background: '#22d3ee' }} /> TIDE candidate</span>
          <span className="legend-chip"><span className="legend-dot" style={{ background: '#fb7185' }} /> Simulated observation</span>
          <span className="legend-chip"><span className="legend-dot" style={{ background: '#34d399' }} /> Validation</span>
        </div>
      </motion.div>

      {/* ---- Event selector ---- */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" custom={1} className="glass-card replay-toolbar">
        <span className="replay-toolbar-label"><Activity size={14} /> REPLAY EVENT</span>
        <div className="replay-event-picker">
          {events.length === 0 && <span className="replay-toolbar-hint">No playable events loaded.</span>}
          {events.map((ev) => (
            <button
              key={ev.event_id}
              className={`replay-event-pill ${eventId === ev.event_id ? 'replay-event-pill-on' : ''}`}
              onClick={() => setEventId(ev.event_id)}
              title={`${ev.label} · ${ev.location}`}
            >
              <span>{ev.icon}</span>
              <span>{ev.label ?? ev.event_type?.replace(/_/g, ' ')}</span>
              <span className="replay-event-loc">{ev.location}</span>
            </button>
          ))}
        </div>
        {replay && (
          <span className="replay-var-chip">
            <Crosshair size={13} /> {replay.variable.replace(/_/g, ' ')} · {replay.depth_m}m · {eventId}
          </span>
        )}
      </motion.div>

      {/* ---- Error / loading / empty ---- */}
      {error && (
        <motion.div variants={fadeUp} initial="hidden" animate="show" custom={2} className="glass-card replay-empty">
          <AlertTriangle size={32} color="#f43f5e" />
          <p>{error}</p>
        </motion.div>
      )}

      {loading && !error && (
        <motion.div variants={fadeUp} initial="hidden" animate="show" custom={2} className="glass-card replay-empty">
          <Loader2 size={32} className="spin" color="#22d3ee" />
          <p>Building the replay from existing TIDE / Twin / Forensics inputs…</p>
        </motion.div>
      )}

      {!loading && !error && !replay && (
        <motion.div variants={fadeUp} initial="hidden" animate="show" custom={2} className="glass-card replay-empty">
          <Search size={32} color="#64748b" />
          <p>Select a playable event to begin the replay.</p>
        </motion.div>
      )}

      {/* ---- Main content ---- */}
      {!loading && !error && replay && (
        <>
          {/* TIDE Loop status strip */}
          <motion.div variants={fadeUp} initial="hidden" animate="show" custom={2} className="replay-loop">
            {replay.tide_loop.map((s) => {
              const meta = LOOP_META[s.key] ?? { icon: Activity, color: '#64748b' }
              const Icon = meta.icon
              return (
                <div
                  key={s.key}
                  className={`replay-loop-item ${s.reached ? 'replay-loop-on' : ''}`}
                  title={s.detail}
                  style={s.reached ? { borderColor: `${meta.color}66` } : undefined}
                >
                  <Icon size={14} color={s.reached ? meta.color : '#64748b'} />
                  <span className="replay-loop-label">{s.label}</span>
                  {s.reached ? <CheckCircle2 size={12} color={meta.color} /> : <XCircle size={12} color="#475569" />}
                </div>
              )
            })}
          </motion.div>

          {/* Globe + playback */}
          <motion.div variants={fadeUp} initial="hidden" animate="show" custom={3} className="replay-stage">
            <div className="replay-globe-wrap">
              <CesiumGlobe
                locations={locations}
                layers={LAYER_DEFAULTS}
                replayMarkers={replayMarkers}
                onRegionClick={(locId) => setFlyTo((p) => ({ locId, n: (p?.n ?? 0) + 1 }))}
                flyToTarget={flyTo}
              />
              <div className="replay-globe-note">
                <Info size={12} /> Markers reflect the current step · observations are SIMULATED — DEMONSTRATION ONLY
              </div>
            </div>

            <div className="glass-card replay-player">
              <div className="replay-player-head">
                <span className="replay-player-title">
                  <Target size={14} /> Step {stepIdx + 1} / {replay.steps.length}
                </span>
                <span className="replay-player-step">{currentStep?.label ?? ''}</span>
              </div>

              {/* step dots */}
              <div className="replay-step-dots">
                {replay.steps.map((s, i) => (
                  <button
                    key={s.id}
                    className={`replay-step-dot ${i === stepIdx ? 'replay-step-dot-on' : ''} ${i < stepIdx ? 'replay-step-dot-done' : ''}`}
                    onClick={() => { setStepIdx(i); setPlaying(false) }}
                    title={`${i + 1}. ${s.label}`}
                  />
                ))}
              </div>

              {/* transport */}
              <div className="replay-transport">
                <button className="replay-btn" onClick={() => setStepIdx(0)} disabled={stepIdx === 0} aria-label="Back to start">
                  <SkipBack size={16} />
                </button>
                <button className="replay-btn" onClick={() => setStepIdx((i) => Math.max(0, i - 1))} disabled={stepIdx === 0} aria-label="Previous step">
                  <RotateCcw size={15} />
                  <span>Prev</span>
                </button>
                <button
                  className="replay-btn replay-btn-play"
                  onClick={() => setPlaying((p) => !p)}
                  disabled={stepIdx >= replay.steps.length - 1 && !playing}
                  aria-label={playing ? 'Pause replay' : 'Play replay'}
                >
                  {playing ? <Pause size={18} /> : <Play size={18} />}
                  <span>{playing ? 'Pause' : 'Play'}</span>
                </button>
                <button className="replay-btn" onClick={() => setStepIdx((i) => Math.min(replay.steps.length - 1, i + 1))} disabled={stepIdx >= replay.steps.length - 1} aria-label="Next step">
                  <span>Next</span>
                  <SkipForward size={15} />
                </button>
                <button className="replay-btn" onClick={() => { setStepIdx(replay.steps.length - 1); setPlaying(false) }} disabled={stepIdx >= replay.steps.length - 1} aria-label="Jump to end">
                  <SkipForward size={16} />
                </button>
              </div>

              {currentStep && (
                <div className="replay-step-detail">
                  <p className="replay-step-desc">{currentStep.description}</p>
                  <div className="replay-step-sources">
                    {currentStep.sources.map((s) => <span key={s} className="replay-src">{s}</span>)}
                  </div>
                  <div className="replay-step-cols">
                    <ModeState title={replay.labels.model_only ?? 'MODEL-ONLY'} state={currentStep.model_only} tone="#22d3ee" />
                    <ModeState title={`${replay.labels.tide_assisted ?? 'TIDE-ASSISTED'}${currentStep.tide_assisted.observation_status ? ' · SIMULATED' : ''}`}
                      state={currentStep.tide_assisted} tone="#fb7185" />
                  </div>
                </div>
              )}
            </div>
          </motion.div>

          {/* Decision banner */}
          <motion.div variants={fadeUp} initial="hidden" animate="show" custom={4}>
            <DecisionBanner replay={replay} />
          </motion.div>

          {/* Comparison + mode summaries */}
          <motion.div variants={fadeUp} initial="hidden" animate="show" custom={4} className="replay-cmp-grid">
            <ModeCard
              title={replay.labels.model_only}
              summary={replay.model_only}
              tone="#22d3ee"
              observationLabel={replay.labels.observation}
            />
            <ModeCard
              title={replay.labels.tide_assisted}
              summary={replay.tide_assisted}
              tone="#fb7185"
              observationLabel={replay.labels.observation}
            />

            <div className="glass-card replay-card replay-compare">
              <div className="panel-header">
                <h3><BarChart3 size={15} /> Side-by-side comparison</h3>
                <span className="panel-badge">BOTH MODES</span>
              </div>
              <table className="replay-cmp-table">
                <thead>
                  <tr>
                    <th>Metric</th>
                    <th>Model-only</th>
                    <th>TIDE-assisted</th>
                    <th>Δ</th>
                  </tr>
                </thead>
                <tbody>
                  <CmpRow label="Uncertainty" m={replay.comparison.uncertainty} fmt={pct} />
                  <CmpRow label="Anomaly risk" m={replay.comparison.anomaly_risk} fmt={pct} />
                  <CmpRow label="Confidence" m={replay.comparison.confidence} fmt={pct} />
                  <CmpRow label="Decision" m={replay.comparison.decision} fmt={(v) => String(v ?? '—')} />
                  <CmpRow label="Detection time" m={replay.comparison.detection_time} fmt={(v) => (v == null ? '—' : `${v} h ago`)} />
                </tbody>
              </table>
              {!replay.comparison.detection_time.calculated && (
                <p className="replay-note">Detection-time difference is not calculated: a simulated observation cannot change the historical detection time.</p>
              )}
              <div className="replay-rules">
                <span className="replay-rules-title">Documented decision rules</span>
                {Object.entries(replay.rules ?? {}).map(([k, v]) => (
                  <div key={k} className="replay-rule">
                    <span className="tide-status" style={{ color: DECISION_COLOR[k] ?? '#64748b' }}>{k.replace(/_/g, ' ')}</span>
                    <span className="replay-rule-desc">{v}</span>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>

          {/* Uncertainty journey + validation + regret */}
          <motion.div variants={fadeUp} initial="hidden" animate="show" custom={5} className="replay-journey-grid">
            <div className="glass-card replay-card replay-unc-journey">
              <div className="panel-header">
                <h3><Activity size={15} /> Uncertainty journey</h3>
                <span className="panel-badge">PER STEP</span>
              </div>
              <div className="replay-chart">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={replay.uncertainty_journey} margin={{ top: 8, right: 14, bottom: 30, left: -18 }}>
                    <CartesianGrid stroke="rgba(148,163,184,0.08)" />
                    <XAxis
                      dataKey="label"
                      tick={{ fill: '#7dd3fc', fontSize: 9 }}
                      tickFormatter={(v: string) => v.replace(/\s/g, '\n')}
                      interval={0}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis domain={[0, 1]} tick={{ fill: '#7dd3fc', fontSize: 10 }} axisLine={false} tickLine={false} />
                    <Tooltip
                      contentStyle={{ background: '#0a1526', border: '1px solid #1e3a5f', borderRadius: 8, fontSize: 12 }}
                      labelStyle={{ color: '#e2f3ff' }}
                    />
                    <Legend />
                    <ReferenceLine y={replay.model_only?.uncertainty ?? undefined} stroke="#22d3ee" strokeDasharray="4 4" strokeOpacity={0.35} />
                    <Line type="monotone" dataKey="uncertainty_model_only" name="Model-only" stroke="#22d3ee" strokeWidth={2} strokeDasharray="6 4" dot={{ r: 3 }} />
                    <Line type="monotone" dataKey="uncertainty_tide_assisted" name="TIDE-assisted" stroke="#fb7185" strokeWidth={2.4} dot={{ r: 3 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div className="replay-journey-legend">
                <span><i style={{ background: '#22d3ee' }} /> MODEL-ONLY · no extra observation</span>
                <span><i style={{ background: '#fb7185' }} /> TIDE-ASSISTED · simulated observation applied</span>
              </div>
            </div>

            <div className="glass-card replay-card replay-validation">
              <div className="panel-header">
                <h3><Scale size={15} /> Validation</h3>
                <span className="panel-badge">{replay.validation.available ? 'COMPARED' : 'UNAVAILABLE'}</span>
              </div>
              {replay.validation.available ? (
                <div className="replay-val-body">
                  <p className="replay-val-msg">{replay.validation.message}</p>
                  <div className="replay-val-grid">
                    <ValBlock title="Model-only (real)" block={replay.validation.model_only} />
                    <ValBlock title="TIDE-assisted (simulated)" block={replay.validation.tide_assisted} />
                  </div>
                </div>
              ) : (
                <div className="replay-val-unavailable">
                  <AlertTriangle size={16} color="#f59e0b" />
                  <span>{replay.validation.message}</span>
                </div>
              )}
            </div>

            <div className="glass-card replay-card replay-regret">
              <div className="panel-header">
                <h3><FlaskConical size={15} /> Decision regret (demonstration)</h3>
                <span className="panel-badge">DEMO</span>
              </div>
              <div className="replay-regret-metric" style={{ '--regret': `${Math.round((replay.regret.value ?? 0) * 100)}%` } as React.CSSProperties}>
                <span className="replay-regret-ring">
                  <b>{((replay.regret.value ?? 0) * 100).toFixed(0)}</b>
                  <em>regret</em>
                </span>
                <span className="replay-regret-expl">{replay.regret.explanation}</span>
              </div>
              <p className="replay-regret-def">{replay.regret.definition}</p>
              <div className="replay-regret-caveat">{replay.regret.caveat}</div>
            </div>
          </motion.div>

          {/* Evidence journey + Event DNA */}
          <motion.div variants={fadeUp} initial="hidden" animate="show" custom={6} className="replay-ev-grid">
            <div className="glass-card replay-card">
              <div className="panel-header">
                <h3><Dna size={15} /> Evidence journey</h3>
                <span className="panel-badge">{replay.evidence_journey.length} SIGNALS</span>
              </div>
              <div className="replay-ev-list">
                {replay.evidence_journey.map((e, i) => {
                  const stepLabel = replay.steps.find((s) => s.id === e.step)?.label ?? e.step
                  return (
                    <div key={`${e.type}-${i}`} className="replay-ev-item">
                      <span className="replay-ev-marker" />
                      <div className="replay-ev-body">
                        <div className="replay-ev-meta">
                          <span className="replay-ev-type">{e.type.replace(/_/g, ' ')}</span>
                          {e.data_status && <span className="replay-status-chip"><b>{e.data_status}</b></span>}
                          <span className="replay-ev-step">{stepLabel}</span>
                        </div>
                        <p>{e.description}</p>
                        {e.source_system && <span className="replay-ev-source">{e.source_system}</span>}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>

            <div className="glass-card replay-card">
              <div className="panel-header">
                <h3><Dna size={15} /> Ocean Event DNA</h3>
                <span className="panel-badge">{replay.event_id}</span>
              </div>
              <div className="tide-dna-tags">
                {(replay.event_dna?.tags ?? []).length > 0
                  ? replay.event_dna.tags.map((t) => <span key={t} className="tide-dna-chip">{t}</span>)
                  : <span className="replay-muted">No categorical DNA tags available.</span>}
              </div>
              <p className="replay-dna-note">
                Event DNA provides contextual evidence for the TIDE observation recommendation. The
                fingerprint is generated by the existing Ocean Forensics engine and never changed by the replay.
              </p>
              <div className="replay-dna-flow">
                <span>EVENT</span><ChevronRight size={12} />
                <span>OCEAN DNA</span><ChevronRight size={12} />
                <span>TIDE RECOMMENDATION</span><ChevronRight size={12} />
                <span>OBSERVATION</span><ChevronRight size={12} />
                <span>DECISION</span><ChevronRight size={12} />
                <span>VALIDATION</span>
              </div>
            </div>
          </motion.div>

          {/* Notes + trust map */}
          <motion.div variants={fadeUp} initial="hidden" animate="show" custom={7} className="glass-card replay-card replay-notes">
            <div className="panel-header">
              <h3><Info size={15} /> Trust & limitations</h3>
              <span className="panel-badge">READ-ONLY</span>
            </div>
            <ul className="replay-notes-list">
              {replay.notes.map((n, i) => <li key={i}>{n}</li>)}
            </ul>
            <div className="replay-trust-map">
              {Object.entries(replay.data_status ?? {}).map(([k, v]) => (
                <span key={k} className="replay-trust-chip">
                  <span className="replay-trust-key">{k.replace(/_/g, ' ')}</span>
                  {v ? <span className="replay-status-chip"><b>{v}</b></span> : <span className="replay-trust-none">n/a</span>}
                </span>
              ))}
            </div>
            <div className="replay-action-row">
              <span className="replay-breadcrumb">
                <Globe2 size={13} /> This replay reuses the existing globe, event timeline, Forensics, Event DNA and TIDE engines — nothing is duplicated.
              </span>
              <button className="tide-btn" onClick={() => navigate('/tide')}>
                <Crosshair size={14} /> Open TIDE Command Center
              </button>
            </div>
          </motion.div>
        </>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Sub-components                                                     */
/* ------------------------------------------------------------------ */

function ModeState({ title, state, tone }: { title: string; state: ReplayState; tone: string }) {
  return (
    <div className="replay-mode-state">
      <div className="replay-mode-head">
        <span style={{ color: tone }} className="replay-mode-title">{title}</span>
        <span className="replay-mode-decision" style={{ color: DECISION_COLOR[state.decision] ?? '#64748b' }}>
          {state.decision.replace(/_/g, ' ')}
        </span>
      </div>
      <div className="replay-mode-grid">
        <span className="replay-mode-cell"><b>{pct(state.uncertainty)}</b> u</span>
        <span className="replay-mode-cell"><b>{pct(state.anomaly_risk)}</b> risk</span>
        <span className="replay-mode-cell"><b>{pct(state.confidence)}</b> conf</span>
        <span className="replay-mode-cell"><b>{state.evidence_count}</b> ev</span>
      </div>
      <div className="replay-mode-readings">
        <span>model <b>{num(state.model_value)}</b></span>
        {state.observed_value != null ? <span>observed <b>{num(state.observed_value)}</b> {state.observation_status ?? ''}</span> : <span>observed —</span>}
        {state.observation_status && <span className="replay-sim-chip">SIMULATED</span>}
      </div>
    </div>
  )
}

function DecisionBanner({ replay }: { replay: DecisionReplay }) {
  const d = replay.decision
  const changed = d.decision_changed
  return (
    <div className={`glass-card replay-card replay-decision ${changed ? 'replay-decision-changed' : ''}`}>
      <div className="panel-header">
        <h3><ShieldIcon /> Decision state</h3>
        <span
          className="replay-decision-badge"
          style={{ color: changed ? '#fb7185' : '#10b981', background: changed ? 'rgba(251,113,133,0.12)' : 'rgba(16,185,129,0.12)' }}
        >
          {d.decision_result.replace(/_/g, ' ')}
        </span>
      </div>
      <div className="replay-decision-body">
        <div className="replay-decision-transition">
          <span className="replay-dec-before" style={{ color: DECISION_COLOR[d.before] ?? '#64748b' }}>{d.before.replace(/_/g, ' ')}</span>
          <span className="replay-dec-arrow">{changed ? '→' : '·'}</span>
          <span className="replay-dec-after" style={{ color: DECISION_COLOR[d.after] ?? '#64748b' }}>{d.after.replace(/_/g, ' ')}</span>
        </div>
        <p className="replay-decision-expl">{d.explanation}</p>
        <ul className="replay-decision-why">
          {d.why.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      </div>
    </div>
  )
}

function ShieldIcon() {
  return <ShieldAlert size={15} />
}

function ModeCard({ title, summary, tone, observationLabel }: {
  title: string
  summary: DecisionReplay['model_only']
  tone: string
  observationLabel: string
}) {
  return (
    <div className="glass-card replay-card replay-mode-card">
      <div className="panel-header">
        <h3 style={{ color: tone }}>{title}</h3>
        <span className="panel-badge">{summary.observation_available ? 'OBSERVED' : 'NO EXTRA OBSERVATION'}</span>
      </div>
      <div className="stat-card replay-mode-stat">
        <div className="stat-card-label">DECISION</div>
        <div className="stat-card-value tide-mono-sm" style={{ color: DECISION_COLOR[summary.decision] ?? '#64748b' }}>
          {summary.decision.replace(/_/g, ' ')}
        </div>
      </div>
      <div className="replay-mode-summary">
        <span>Uncertainty <b>{pct(summary.uncertainty)}</b></span>
        <span>Anomaly risk <b>{pct(summary.anomaly_risk)}</b></span>
        <span>Confidence <b>{pct(summary.confidence)}</b></span>
        <span>Evidence <b>{summary.evidence_count}</b></span>
        <span>Detection <b>{summary.detection_time_h != null ? `${summary.detection_time_h} h ago` : '—'}</b></span>
      </div>
      {summary.observation_available && (
        <div className="replay-mode-obs">
          <Camera size={13} /> Observation applied: <b>{num(summary.observation_value)}</b>
          <span className="replay-sim-chip">{observationLabel.replace(' SIMULATED OBSERVATION - DEMONSTRATION ONLY', '').trim()}</span>
        </div>
      )}
    </div>
  )
}

function CmpRow({ label, m, fmt }: {
  label: string
  m: DecisionReplay['comparison']['uncertainty']
  fmt: (v: number | string | null) => string
}) {
  const delta = typeof m.delta === 'number' ? m.delta : null
  const changed = m.changed ?? null
  return (
    <tr>
      <td className="replay-cmp-label">{label}</td>
      <td>{fmt(m.model_only)}</td>
      <td>{fmt(m.tide_assisted)}</td>
      <td className="replay-cmp-delta">
        {changed != null ? (
          <span className={changed ? 'replay-cmp-changed' : 'replay-cmp-same'}>
            {changed ? 'CHANGED' : 'UNCHANGED'}
          </span>
        ) : delta != null ? (
          <span style={{ color: delta <= 0 ? '#34d399' : '#fbbf24' }}>{delta > 0 ? '+' : ''}{fmt(delta)}</span>
        ) : m.calculated ? (
          <span className="replay-cmp-same">≡</span>
        ) : (
          <span className="replay-cmp-na">n/a</span>
        )}
      </td>
    </tr>
  )
}

function ValBlock({ title, block }: { title: string; block: DecisionReplay['validation']['model_only'] }) {
  return (
    <div className="replay-val-block">
      <div className="replay-val-title">
        <span>{title}</span>
        {block.quality_status && <span className="replay-status-chip"><b>{block.quality_status}</b></span>}
        {block.simulated && <span className="replay-sim-chip">SIMULATED</span>}
      </div>
      <div className="replay-val-cells">
        <span>predicted <b>{num(block.predicted)}</b></span>
        <span>observed <b>{num(block.observed)}</b></span>
        <span>diff <b>{num(block.difference)}</b></span>
        <span>Δ% <b>{block.difference_pct != null ? `${block.difference_pct}%` : '—'}</b></span>
      </div>
    </div>
  )
}