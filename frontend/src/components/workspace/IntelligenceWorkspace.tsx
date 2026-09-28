import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Database, Info, Loader2, Search, ShieldCheck } from 'lucide-react'
import {
  fetchAnomalies,
  fetchCoverage,
  fetchHealthScore,
  fetchLocations,
  fetchValidationSituation,
} from '../../api/client'
import WorkflowHeader from './WorkflowHeader'
import IntelligenceBrief, { type BriefTile } from './IntelligenceBrief'
import SystemHealth, { type HealthProbe } from './SystemHealth'
import UncertaintyGauge, { type GaugeItem } from './UncertaintyGauge'
import DataQualityIndicator from './DataQualityIndicator'
import { TrustLegend } from './TrustBadge'
import './workspace.css'

interface Location { id: number; name: string; region_type: string; country: string }
interface CoverageRow {
  location_id: number; location: string; coverage_pct?: number; gap_score?: number
  uncertainty?: number; priority?: number; tier?: string; recency_h?: number
}
interface SituationRow {
  location_id: number; location: string; status: string; temperature_anomaly: string
  wave_state: string; observation_confidence: number; model_trust: number
  disagreement: boolean; headline: string
}
interface HealthRow { location_id: number; location: string; score: number; label: string }
interface AnomalyResponse { anomalies?: unknown[]; events?: unknown[] }

const asArray = <T,>(value: unknown): T[] => Array.isArray(value) ? value as T[] : []
const unwrap = (body: unknown) => (body as { data?: unknown } | null)?.data ?? body

export default function IntelligenceWorkspace() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const [locations, setLocations] = useState<Location[]>([])
  const [locationId, setLocationId] = useState<number | null>(null)
  const [coverage, setCoverage] = useState<CoverageRow[]>([])
  const [situations, setSituations] = useState<SituationRow[]>([])
  const [health, setHealth] = useState<HealthRow[]>([])
  const [anomalyCount, setAnomalyCount] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [errors, setErrors] = useState<Record<string, boolean>>({})

  useEffect(() => {
    let alive = true
    fetchLocations().then((rows: Location[]) => {
      if (!alive) return
      setLocations(rows)
      const fromUrl = Number(searchParams.get('location_id'))
      setLocationId(rows.find((row) => row.id === fromUrl)?.id ?? rows[0]?.id ?? null)
    }).catch(() => alive && setErrors((old) => ({ ...old, locations: true })))
    return () => { alive = false }
  }, [])

  useEffect(() => {
    if (locationId == null) return
    let alive = true
    setLoading(true)
    const results = Promise.allSettled([
      fetchCoverage(), fetchValidationSituation(), fetchHealthScore(locationId), fetchAnomalies({ sort: 'severity' }),
    ])
    results.then(([cov, sit, score, anomalies]) => {
      if (!alive) return
      const nextErrors: Record<string, boolean> = {}
      if (cov.status === 'fulfilled') setCoverage(asArray<CoverageRow>(unwrap(cov.value)))
      else { setCoverage([]); nextErrors.coverage = true }
      if (sit.status === 'fulfilled') {
        const raw = unwrap(sit.value) as { regions?: SituationRow[] } | SituationRow[] | null
        setSituations(Array.isArray(raw) ? raw : asArray<SituationRow>(raw?.regions))
      } else { setSituations([]); nextErrors.situation = true }
      if (score.status === 'fulfilled') setHealth(asArray<HealthRow>(unwrap(score.value)))
      else { setHealth([]); nextErrors.health = true }
      if (anomalies.status === 'fulfilled') {
        const data = unwrap(anomalies.value) as AnomalyResponse | unknown[] | null
        const rows = Array.isArray(data) ? data : data?.anomalies ?? data?.events ?? []
        setAnomalyCount(rows.length)
      } else { setAnomalyCount(null); nextErrors.anomalies = true }
      setErrors(nextErrors)
      setLoading(false)
    })
    return () => { alive = false }
  }, [locationId])

  const location = useMemo(() => locations.find((row) => row.id === locationId) ?? null, [locations, locationId])
  const coverageRow = coverage.find((row) => row.location_id === locationId) ?? null
  const situation = situations.find((row) => row.location_id === locationId) ?? null
  const healthRow = health.find((row) => row.location_id === locationId) ?? health[0] ?? null
  const backendDown = !loading && !!errors.locations && locations.length === 0

  const selectLocation = (id: number) => {
    setLocationId(id)
    const params = new URLSearchParams(searchParams)
    params.set('location_id', String(id))
    setSearchParams(params, { replace: true })
  }

  const tiles: BriefTile[] = [
    { key: 'situation', label: 'CURRENT SITUATION', value: situation?.headline ?? (loading ? 'Loading' : 'No situation record'), tone: situation?.disagreement ? 'warn' : 'good' },
    { key: 'coverage', label: 'OBSERVATION COVERAGE', value: coverageRow?.coverage_pct != null ? `${Math.round(coverageRow.coverage_pct)}%` : 'Unavailable', hint: coverageRow?.tier ? `${coverageRow.tier} coverage tier` : undefined },
    { key: 'recency', label: 'LATEST OBSERVATION', value: coverageRow?.recency_h != null ? `${Math.round(coverageRow.recency_h)} h ago` : 'Unavailable' },
    { key: 'temperature', label: 'TEMPERATURE ANOMALY', value: situation?.temperature_anomaly ?? 'Unavailable', tone: situation?.temperature_anomaly === 'HIGH' ? 'bad' : 'muted' },
    { key: 'waves', label: 'WAVE STATE', value: situation?.wave_state ?? 'Unavailable' },
    { key: 'confidence', label: 'OBSERVATION CONFIDENCE', value: situation ? `${Math.round(situation.observation_confidence)}%` : 'Unavailable' },
    { key: 'model-trust', label: 'MODEL TRUST', value: situation ? `${Math.round(situation.model_trust)}%` : 'Unavailable' },
    { key: 'health', label: 'COASTAL HEALTH', value: healthRow ? `${Math.round(healthRow.score)}/100 · ${healthRow.label}` : 'Unavailable' },
    { key: 'events', label: 'DETECTED ANOMALIES', value: anomalyCount == null ? 'Unavailable' : String(anomalyCount), tone: anomalyCount ? 'warn' : 'muted' },
  ]

  const probes: HealthProbe[] = [
    { key: 'twin', label: 'Digital Twin', state: errors.coverage ? 'unavailable' : coverage.length ? 'available' : 'limited', detail: errors.coverage ? 'coverage endpoint unreachable' : `${coverage.length} coverage regions` },
    { key: 'validation', label: 'Model Validation', state: errors.situation ? 'unavailable' : situations.length ? 'available' : 'limited', detail: errors.situation ? 'validation endpoint unreachable' : `${situations.length} coastal situation records` },
    { key: 'health', label: 'Coastal Health', state: errors.health ? 'unavailable' : health.length ? 'available' : 'limited', detail: errors.health ? 'health endpoint unreachable' : `${health.length} health records` },
    { key: 'anomalies', label: 'Anomaly Detection', state: errors.anomalies ? 'unavailable' : anomalyCount ? 'available' : 'limited', detail: errors.anomalies ? 'anomaly endpoint unreachable' : `${anomalyCount ?? 0} detected anomalies` },
  ]

  const gaugeItems: GaugeItem[] = [
    { label: 'Coverage', value: coverageRow?.coverage_pct ?? null, color: '#22d3ee', hint: 'Available observation coverage' },
    { label: 'Confidence', value: situation?.observation_confidence ?? null, color: '#10b981', hint: 'Observation confidence' },
    { label: 'Model trust', value: situation?.model_trust ?? null, color: '#8b8cf8', hint: 'Model trust score' },
    { label: 'Coastal health', value: healthRow?.score ?? null, color: '#f59e0b', hint: 'Coastal health index' },
  ]

  return (
    <div className="intel-workspace">
      <WorkflowHeader />
      <div className="ws-section">
        <div className="ws-section-head">
          <h3>Active Coast</h3>
          <label style={{ marginLeft: 'auto', fontSize: 11, color: '#9fb4d4' }}>
            Focus{' '}
            <select value={locationId ?? ''} onChange={(event) => selectLocation(Number(event.target.value))} aria-label="Focus coast">
              {locations.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
            </select>
          </label>
        </div>
        <TrustLegend />
      </div>
      {backendDown && <div className="ws-banner"><Info size={15} /> Coastal data services are unreachable. Values are shown as unavailable until the backend responds.</div>}
      {!loading && anomalyCount === 0 && !backendDown && <div className="ws-banner"><Info size={15} /> No anomalies are currently detected in the available data.</div>}
      <IntelligenceBrief locationName={location?.name ?? ''} tiles={tiles} actions={[
        { key: 'forensics', label: 'OPEN FORENSICS', to: '/forensics', icon: Search },
        { key: 'validation', label: 'MODEL VALIDATION', to: '/validate', icon: ShieldCheck },
        { key: 'layers', label: 'REVIEW DATA LAYERS', to: '/data-layers', icon: Database },
      ]} overallStatus={situation?.disagreement ? 'MODEL_DERIVED' : null} onNavigate={navigate} onOpenEvidence={() => {}} />
      <div className="ws-section">
        <div className="ws-section-head"><h3>Coverage & Confidence</h3><span className="ws-kicker">derived from available records</span></div>
        <div className="glass-card" style={{ padding: '12px 14px' }}>
          {loading ? <div className="ws-loading"><Loader2 size={15} className="spin" /> Loading metrics…</div> : <UncertaintyGauge items={gaugeItems} />}
        </div>
      </div>
      <div className="ws-section">
        <div className="ws-section-head"><h3>Data Quality</h3><span className="ws-kicker">{location?.name ?? 'network'}</span></div>
        <div className="glass-card" style={{ padding: '12px 14px' }}>
          <DataQualityIndicator coverage={coverageRow?.coverage_pct ?? null} confidence={situation?.observation_confidence ?? null} location={location?.name} />
        </div>
      </div>
      <div className="ws-section">
        <div className="ws-section-head"><h3>System Health</h3><span className="ws-kicker">coastal data services</span></div>
        <SystemHealth probes={probes} backendDown={backendDown} />
      </div>
    </div>
  )
}
