/**
 * IntelligenceWorkspace — Phase 7 unified "Integrated Ocean Intelligence
 * Experience". A single front-door that fuses the EXISTING engines:
 *
 *   01 OBSERVE   02 DETECT   03 INVESTIGATE   04 UNDERSTAND   05 PRIORITIZE
 *   06 OBSERVE NEXT   07 SIMULATE   08 DECIDE   09 VALIDATE   + EXPLAIN (Copilot)
 *
 * Nothing is recomputed: it reads the real Digital Twin, validation, forensics,
 * TIDE and replay endpoints. Missing data is shown as DATA UNAVAILABLE.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Loader2, Search, Dna, Crosshair, RotateCcw, History, FileCheck, Info } from 'lucide-react'
import {
  fetchLocations,
  fetchCoverage,
  fetchHealthScore,
  fetchValidationSituation,
  fetchTideCandidates,
  fetchTideExplanation,
  fetchTideVerdict,
  fetchTideEventContext,
  fetchTideEventIndex,
} from '../../api/client'
import type {
  TideCandidate, TideEvidence, TideExplanation, TideVerdict, TideEventContext, ReplayEventItem,
} from '../../types/tide'
import WorkflowHeader from './WorkflowHeader'
import IntelligenceBrief, { type BriefTile, type BriefAction } from './IntelligenceBrief'
import IntelligenceGraph from './IntelligenceGraph'
import EvidenceDrawer from './EvidenceDrawer'
import SystemHealth, { type HealthProbe } from './SystemHealth'
import UncertaintyGauge, { type GaugeItem } from './UncertaintyGauge'
import DataQualityIndicator from './DataQualityIndicator'
import { TrustLegend } from './TrustBadge'
import './workspace.css'

interface Location {
  id: number
  name: string
  region_type: string
  country: string
}

interface CoverageRow {
  location_id: number
  location: string
  coverage_pct?: number
  gap_score?: number
  uncertainty?: number
  priority?: number
  tier?: string
  recency_h?: number
}

interface SituationRow {
  location_id: number
  location: string
  status: string
  temperature_anomaly: string
  wave_state: string
  observation_confidence: number
  model_trust: number
  disagreement: boolean
  headline: string
}

interface HealthRow {
  location_id: number
  location: string
  score: number
  label: string
}

const asArray = <T,>(value: unknown): T[] => (Array.isArray(value) ? (value as T[]) : [])
const env = (body: unknown) => (body as { data?: unknown } | null)?.data ?? body

export default function IntelligenceWorkspace() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const [locations, setLocations] = useState<Location[]>([])
  const [locationId, setLocationId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)

  const [coverage, setCoverage] = useState<CoverageRow[] | null>(null)
  const [situation, setSituation] = useState<SituationRow[] | null>(null)
  const [health, setHealth] = useState<HealthRow[] | null>(null)
  const [candidates, setCandidates] = useState<TideCandidate[]>([])
  const [explanation, setExplanation] = useState<TideExplanation | null>(null)
  const [verdict, setVerdict] = useState<TideVerdict | null>(null)
  const [eventCtx, setEventCtx] = useState<TideEventContext | null>(null)
  const [eventIndex, setEventIndex] = useState<ReplayEventItem[]>([])
  const [errors, setErrors] = useState<Record<string, boolean>>({})
  const [evidenceOpen, setEvidenceOpen] = useState(false)

  // URL-driven context persistence (?location_id=…) — no new global store.
  useEffect(() => {
    let alive = true
    fetchLocations()
      .then((locs: Location[]) => {
        if (!alive) return
        setLocations(locs)
        const fromUrl = Number(searchParams.get('location_id'))
        const valid = locs.find((l) => l.id === fromUrl)
        setLocationId(valid ? valid.id : (locs[0]?.id ?? null))
      })
      .catch(() => alive && setErrors((e) => ({ ...e, locations: true })))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const selectLocation = useCallback(
    (id: number) => {
      setLocationId(id)
      const params = new URLSearchParams(searchParams)
      params.set('location_id', String(id))
      setSearchParams(params, { replace: true })
    },
    [searchParams, setSearchParams],
  )

  useEffect(() => {
    if (locationId == null) return
    let alive = true
    setLoading(true)
    const fail = (key: string, value: boolean) =>
      alive && setErrors((e) => ({ ...e, [key]: value }))

    Promise.all([
      fetchCoverage().catch(() => { fail('coverage', true); return null }),
      fetchValidationSituation().catch(() => { fail('situation', true); return null }),
      fetchHealthScore(locationId).catch(() => { fail('health', true); return null }),
      fetchTideCandidates({ variable: 'temperature', depth_m: 0 }).catch(() => { fail('candidates', true); return null }),
      fetchTideExplanation({ location_id: locationId, variable: 'temperature', depth_m: 0 }).catch(() => null),
      fetchTideVerdict({ location_id: locationId, variable: 'temperature', depth_m: 0 }).catch(() => null),
      fetchTideEventContext('event-0').catch(() => null),
      fetchTideEventIndex().catch(() => null),
    ]).then(([cov, sit, hea, cand, exp, ver, evc, idx]) => {
      if (!alive) return
      setCoverage(cov ? asArray<CoverageRow>(env(cov) ?? cov) : [])
      const sitRows = (env(sit) as { regions?: SituationRow[] } | null)?.regions
      setSituation(sitRows ?? asArray<SituationRow>(env(sit)))
      setHealth(hea ? asArray<HealthRow>(env(hea) ?? hea) : [])
      setCandidates(asArray<TideCandidate>(env(cand)))
      setExplanation(exp ? ((env(exp) as TideExplanation) ?? null) : null)
      setVerdict(ver ? ((env(ver) as TideVerdict) ?? null) : null)
      setEventCtx(evc ? ((env(evc) as TideEventContext) ?? null) : null)
      const events = (env(idx) as { events?: ReplayEventItem[] } | null)?.events
      setEventIndex(asArray<ReplayEventItem>(events ?? env(idx)))
      setLoading(false)
    }).catch(() => alive && setLoading(false))

    return () => { alive = false }
  }, [locationId])

  const location = useMemo(() => locations.find((l) => l.id === locationId) ?? null, [locations, locationId])
  const covRow = useMemo(() => coverage?.find((c) => c.location_id === locationId) ?? null, [coverage, locationId])
  const sitRow = useMemo(() => situation?.find((s) => s.location_id === locationId) ?? null, [situation, locationId])
  const healthRow = useMemo(() => health?.find((h) => h.location_id === locationId) ?? health?.[0] ?? null, [health, locationId])
  const topCandidate = useMemo(
    () => candidates.find((c) => c.location_id === locationId) ?? candidates[0] ?? null,
    [candidates, locationId],
  )

  const evidence = useMemo<TideEvidence[]>(() => {
    const out: TideEvidence[] = []
    if (topCandidate?.evidence) out.push(...topCandidate.evidence)
    if (explanation?.explanation?.evidence) out.push(...explanation.explanation.evidence)
    if (verdict?.evidence) out.push(...verdict.evidence)
    if (eventCtx?.evidence) out.push(...eventCtx.evidence)
    return out
  }, [topCandidate, explanation, verdict, eventCtx])

  const backendDown = !loading && !!errors.locations && locations.length === 0

  // ----- System health probes (derived from real responses) -----
  const probes: HealthProbe[] = [
    {
      key: 'twin', label: 'Digital Twin',
      state: coverage == null || errors.coverage ? 'unavailable' : coverage.length > 0 ? 'available' : 'limited',
      detail: coverage == null ? 'coverage endpoint unreachable' : `${coverage.length} regions in coverage map`,
    },
    {
      key: 'validation', label: 'Model Validation',
      state: situation == null || errors.situation ? 'unavailable' : situation.length > 0 ? 'available' : 'limited',
      detail: situation == null ? 'situation endpoint unreachable' : `${situation.length} situation rows`,
    },
    {
      key: 'forensics', label: 'Forensics',
      state: errors.candidates ? 'unavailable' : candidates.length > 0 ? 'available' : 'limited',
      detail: candidates.length > 0 ? 'event/TIDE inputs present' : 'no ranked candidates in current data',
    },
    {
      key: 'replay', label: 'Decision Replay',
      state: eventIndex.length > 0 ? 'available' : 'limited',
      detail: eventIndex.length > 0 ? `${eventIndex.length} playable event(s)` : 'no threshold-crossing event maps into TIDE',
    },
  ]

  // ----- Brief tiles (real payloads or DATA UNAVAILABLE) -----
  const tiles: BriefTile[] = [
    {
      key: 'what', label: 'WHAT',
      value: sitRow?.headline ?? (situation ? 'No situation row for this coast' : 'DATA UNAVAILABLE'),
      tone: sitRow?.status === 'danger' ? 'bad' : sitRow?.disagreement ? 'warn' : 'good',
    },
    {
      key: 'where', label: 'WHERE',
      value: location?.name ?? (topCandidate?.location ?? 'DATA UNAVAILABLE'),
      hint: location?.region_type,
    },
    {
      key: 'when', label: 'WHEN',
      value: covRow?.recency_h != null ? `latest obs ${Math.round(covRow.recency_h)} h ago` : 'DATA UNAVAILABLE',
    },
    {
      key: 'changed', label: 'WHAT CHANGED',
      value: sitRow ? `temp anomaly ${sitRow.temperature_anomaly} · waves ${sitRow.wave_state}` : 'DATA UNAVAILABLE',
      tone: sitRow?.temperature_anomaly === 'HIGH' ? 'bad' : sitRow?.temperature_anomaly === 'MODERATE' ? 'warn' : 'good',
    },
    {
      key: 'confidence', label: 'CONFIDENCE',
      value: sitRow ? `obs ${sitRow.observation_confidence}% · model ${sitRow.model_trust}%` : 'DATA UNAVAILABLE',
      tone: sitRow && sitRow.observation_confidence >= 70 ? 'good' : 'warn',
    },
    {
      key: 'disagrees', label: 'DISAGREES',
      value: sitRow == null ? 'DATA UNAVAILABLE' : sitRow.disagreement ? 'model ↔ reality flagged' : 'model tracks reality',
      tone: sitRow?.disagreement ? 'bad' : 'good',
    },
    {
      key: 'matters', label: 'WHY IT MATTERS',
      value: covRow?.tier ? `${covRow.tier} priority${healthRow ? ` · health ${Math.round(healthRow.score)}/100 (${healthRow.label})` : ''}` : healthRow ? `health ${Math.round(healthRow.score)}/100 (${healthRow.label})` : 'DATA UNAVAILABLE',
      tone: covRow?.tier === 'CRITICAL' || covRow?.tier === 'HIGH' ? 'bad' : 'good',
    },
    {
      key: 'observe', label: 'OBSERVE NEXT',
      value: topCandidate ? `${topCandidate.location} · ${topCandidate.variable.replace(/_/g, ' ')} (value ${topCandidate.observation_value.toFixed(4)})` : 'DATA UNAVAILABLE',
      hint: topCandidate ? topCandidate.affected_decision.replace(/_/g, ' ') : undefined,
      tone: topCandidate ? 'warn' : 'muted',
    },
    {
      key: 'evidence', label: 'EVIDENCE',
      value: `${evidence.length} record(s)`,
      hint: topCandidate ? `top: ${topCandidate.observation_type.replace(/_/g, ' ')}` : undefined,
    },
    {
      key: 'whatif', label: 'WHAT IF',
      value: topCandidate ? 'Virtual observation available' : 'no candidate to simulate',
      tone: topCandidate ? 'good' : 'muted',
    },
    {
      key: 'validation', label: 'HOW VALIDATED',
      value: eventIndex.length > 0 ? `${eventIndex.length} replayable event(s)` : 'no event to validate yet',
      tone: eventIndex.length > 0 ? 'good' : 'muted',
    },
  ]

  const actions: BriefAction[] = [
    { key: 'forensics', label: 'OPEN FORENSICS', to: '/forensics', icon: Search },
    { key: 'dna', label: 'VIEW EVENT DNA', to: '/tide', icon: Dna },
    { key: 'tide', label: 'OPEN TIDE', to: `/tide?location_id=${locationId ?? ''}&variable=temperature`, icon: Crosshair },
    { key: 'whatif', label: 'WHAT IF WE MEASURE HERE?', to: `/tide?location_id=${locationId ?? ''}&variable=temperature`, icon: RotateCcw },
    { key: 'replay', label: 'REPLAY DECISION', to: `/tide/replay?location_id=${locationId ?? ''}&variable=temperature&depth_m=0`, icon: History },
    { key: 'validate', label: 'VIEW VALIDATION', to: `/validate?location_id=${locationId ?? ''}`, icon: FileCheck },
    { key: 'evidence', label: 'EVIDENCE', to: '', evidence: true, icon: Info },
  ]

  const gaugeItems: GaugeItem[] = [
    { label: 'Uncertainty', value: topCandidate?.uncertainty ?? null, color: '#22d3ee', hint: 'How unsure the system is' },
    { label: 'Confidence', value: topCandidate?.confidence ?? null, color: '#10b981', hint: 'How sure the system is' },
    { label: 'Obs. value', value: topCandidate?.observation_value ?? null, color: '#8b8cf8', hint: 'Decision-support heuristic, not information gain' },
    { label: 'Decision impact', value: topCandidate?.decision_impact ?? null, color: '#f59e0b', hint: 'How much a decision could change' },
  ]

  const noLiveSignal = !loading && candidates.length === 0 && eventIndex.length === 0 && evidence.length === 0

  return (
    <div className="intel-workspace">
      <WorkflowHeader />

      <div className="ws-section">
        <div className="ws-section-head">
          <h3>Active Coast</h3>
          <label style={{ marginLeft: 'auto', fontSize: 11, color: '#9fb4d4' }}>
            Focus{' '}
            <select
              value={locationId ?? ''}
              onChange={(e) => selectLocation(Number(e.target.value))}
              aria-label="Focus coast"
              style={{ marginLeft: 6, background: '#0f2039', color: '#e8f1fc', border: '1px solid rgba(150,182,230,0.28)', borderRadius: 8, padding: '3px 8px' }}
            >
              {locations.map((l) => (
                <option key={l.id} value={l.id}>{l.name}</option>
              ))}
            </select>
          </label>
        </div>
        <TrustLegend />
      </div>

      {backendDown && (
        <div className="ws-banner">
          <Info size={15} style={{ flex: '0 0 auto', marginTop: 1 }} />
          <span>
            The intelligence engines are unreachable right now. Every value below will read <b>DATA UNAVAILABLE</b> rather
            than show a fabricated figure. Start the backend and sync observations to populate the workspace.
          </span>
        </div>
      )}

      {noLiveSignal && !backendDown && (
        <div className="ws-banner">
          <Info size={15} style={{ flex: '0 0 auto', marginTop: 1 }} />
          <span>
            No threshold-crossing events or TIDE candidates are present in the current data. This is an honest reading of a
            calm ocean, not a failure — the workspace will light up as soon as the engines have real signals.
          </span>
        </div>
      )}

      <IntelligenceBrief
        locationName={location?.name ?? (topCandidate?.location ?? '')}
        tiles={tiles}
        actions={actions}
        overallStatus={sitRow?.disagreement ? 'MODEL_DERIVED' : null}
        onNavigate={navigate}
        onOpenEvidence={() => setEvidenceOpen(true)}
      />

      <div className="ws-section">
        <div className="ws-section-head">
          <h3>Confidence & Value</h3>
          <span className="ws-kicker">concepts kept distinct</span>
        </div>
        <div className="glass-card" style={{ padding: '12px 14px' }}>
          {loading ? (
            <div className="ws-loading"><Loader2 size={15} className="spin" /> Loading meters…</div>
          ) : (
            <UncertaintyGauge items={gaugeItems} />
          )}
        </div>
      </div>

      <div className="ws-section">
        <div className="ws-section-head">
          <h3>Data Quality</h3>
          <span className="ws-kicker">{location?.name ?? 'network'}</span>
        </div>
        <div className="glass-card" style={{ padding: '12px 14px' }}>
          <DataQualityIndicator
            coverage={covRow?.coverage_pct ?? null}
            confidence={sitRow?.observation_confidence ?? null}
            location={location?.name}
          />
        </div>
      </div>

      <div className="ws-section">
        <div className="ws-section-head">
          <h3>Event → TIDE → Decision</h3>
          <span className="ws-kicker">reused DNA chain</span>
        </div>
        <div className="glass-card" style={{ padding: '12px 14px' }}>
          <IntelligenceGraph
            eventType={(eventCtx?.event?.event_type as string) ?? null}
            eventLocation={(eventCtx?.event?.location as string) ?? null}
            eventConfidence={(eventCtx?.event?.confidence as number) ?? null}
            candidate={topCandidate}
            decision={topCandidate ? { affected_decision: topCandidate.affected_decision, decision_impact: topCandidate.decision_impact, replayable: eventIndex.length > 0 } : null}
          />
        </div>
      </div>

      <div className="ws-section">
        <div className="ws-section-head">
          <h3>System Health</h3>
          <span className="ws-kicker">derived from live responses</span>
        </div>
        <SystemHealth probes={probes} backendDown={backendDown} />
      </div>

      <EvidenceDrawer
        evidence={evidence}
        open={evidenceOpen}
        onOpen={() => setEvidenceOpen(true)}
        onClose={() => setEvidenceOpen(false)}
      />
    </div>
  )
}