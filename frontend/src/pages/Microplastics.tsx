import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import {
  Waves, Anchor, Database, AlertTriangle, Download, Ship, Info,
  Layers, Clock, FileText, ExternalLink, TrendingUp, Gauge,
} from 'lucide-react'
import {
  fetchMicroplasticsOverview,
  fetchMicroplasticTimeline,
  ingestMicroplastics,
  projectMicroplasticDrift,
  refreshMicroplasticAlerts,
} from '../api/client'
import {
  DataSourceBadge, DataLabel, SectionHeader, RiskBar, StatusIndicator,
} from '../components/ocean/OceanUI'
import './Microplastics.css'

/**
 * Microplastics Intelligence
 * ==========================
 * Detection, regional mapping, hotspot ranking and drift projection from
 * open-source data only (NOAA NCEI in-situ collection; NASA satellite signal
 * when a NASA Earthdata token is configured).
 *
 * Two presentation rules this page exists to uphold:
 *
 *  1. MEDIUM IS NEVER BLENDED.  Water-column samples are measured in
 *     pieces/m3, sediment in pieces/kg dry weight, nurdle patrols in
 *     pieces/10 min.  The colour ramp is therefore built per medium, and each
 *     medium carries its own unit label everywhere it appears.  There is no
 *     single "microplastics score" in this UI because one cannot exist.
 *
 *  2. GAPS LOOK LIKE GAPS.  Grid cells with no sample in range are drawn as
 *     nothing, and the count of them is printed next to the picture.  A
 *     zero-concentration area and an unsampled area never look the same.
 */

/**
 * Format a concentration without implying false precision.
 * Source values range over many orders of magnitude (0.0005 to 30000), so a
 * fixed decimal count is wrong at both ends; 4 significant digits is readable
 * everywhere and never adds digits the measurement does not have.
 */
function fmt(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  if (value === 0) return '0'
  const abs = Math.abs(value)
  if (abs >= 10000) return value.toExponential(2)
  const text = value.toPrecision(4)
  return text.includes('.') ? text.replace(/0+$/, '').replace(/\.$/, '') : text
}

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: 'easeOut' as const } },
}

const LAYERS = [
  { key: 'water_column', medium: 'water', label: 'Water column', unitHint: 'pieces/m³' },
  { key: 'sediment_dry_weight', medium: 'sediment', label: 'Ocean sediment', unitHint: 'pieces/kg dw' },
  { key: 'beach', medium: 'beach', label: 'Beach', unitHint: 'beach ladder' },
  { key: 'beach_nurdle', medium: 'beach_nurdle', label: 'Nurdle patrol', unitHint: 'pieces/10 min' },
] as const

/** Severity ramp, consistent with the platform's anomaly-severity convention. */
const SEVERITY_COLOR: Record<string, string> = {
  critical: '#ff3366',
  high: '#f43f5e',
  medium: '#f59e0b',
  low: '#10b981',
  info: '#38bdf8',
  unknown: '#64748b',
}

interface Hotspot {
  hotspot_id: string
  region_id: number
  region: string
  medium: string
  medium_display: string
  unit: string
  unit_family: string
  unit_family_description?: string
  is_hotspot: boolean
  severity: string
  severity_label: string | null
  published_class: string | null
  latest_published_class: string | null
  severity_basis: string
  action: string
  action_rationale: string
  priority: number
  priority_components: Record<string, number> & { weights?: Record<string, number> }
  statistics: { n_samples: number; median: number | null; max: number | null; mean: number | null }
  latest_sample_at: string | null
  worst_sample_at: string | null
  confidence: number
  basis: string[]
}

interface DriftResult {
  status: 'OK' | 'NO_FORCING' | 'ERROR'
  region?: string
  reason?: string
  duration_h?: number
  confidence?: string
  confidence_note?: string
  checked_sources?: string[]
  limitations?: string[]
  forcing_quality?: { credible: boolean; warnings: string[] }
  forcing?: {
    origin: string; origin_status: string; speed_kmh?: number;
    direction_deg?: number; observed_at?: string | null;
    n_vessels?: number | null; n_observations?: number | null;
  }
  end_point?: { cumulative_km: number; spread_km: number }
}

interface Overview {
  status: string
  reason?: string
  coverage: {
    has_data: boolean
    total_samples: number
    by_medium: Record<string, number>
    by_unit_family: Record<string, number>
    regions_with_data: number
    regions_total: number
    regions_without_data: string[]
    unassigned_samples: number
    honesty_note: string
    data_vintage?: {
      latest: string | null
      oldest: string | null
      span_years: number | null
      basis: string
      is_live_feed: boolean
    }
  }
  hotspots: {
    hotspot_count: number
    groups_evaluated: number
    weights: Record<string, number>
    threshold_note: string
    data_vintage: { latest: string | null; oldest: string | null; is_live_feed: boolean; basis: string }
    hotspots: Hotspot[]
    recommendations: { summary: string; action_count: number; actions: any[] }
  }
  surfaces: Record<string, {
    has_data: boolean
    reason?: string
    nodes: { latitude: number; longitude: number; value: number; n_sources: number; nearest_km: number; is_estimate: boolean; confidence?: number }[]
    gap_cells?: number
    cells_evaluated?: number
    coverage_ratio?: number
    unit?: string | null
    unit_family?: string
    medium?: string
    sample_count?: number
    method?: string
    honesty_note?: string
  }>
  measurement_discipline: { rule: string; families: Record<string, string> }
  sources: { key: string; name: string; licence: string; homepage: string; requires_credentials: boolean; access: string }[]
}

export default function Microplastics() {
  const navigate = useNavigate()
  const [data, setData] = useState<Overview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [layer, setLayer] = useState<string>('water_column')

  const [years, setYears] = useState<number[]>([])
  const [activeYear, setActiveYear] = useState<number | null>(null)

  const [drift, setDrift] = useState<DriftResult | null>(null)
  const [driftHours, setDriftHours] = useState(72)
  const [driftBusy, setDriftBusy] = useState(false)

  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    fetchMicroplasticsOverview()
      .then((d) => {
        setData(d)
        setError(null)
      })
      .catch((e) => setError(e?.message ?? 'Could not reach the microplastics service.'))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  useEffect(() => {
    let alive = true
    fetchMicroplasticTimeline()
      .then((t) => {
        if (!alive) return
        const ys: number[] = t?.years ?? []
        setYears(ys)
        if (ys.length) setActiveYear(ys[ys.length - 1])
      })
      .catch(() => {})
    return () => { alive = false }
  }, [])

  const surface = data?.surfaces?.[layer]
  const coverage = data?.coverage
  const vintage = data?.hotspots?.data_vintage

  /** Year-filtered hotspots, so scrubbing actually changes what is shown. */
  const visibleHotspots = useMemo(() => {
    const all = data?.hotspots?.hotspots ?? []
    if (activeYear == null) return all
    return all.filter((h) => {
      const stamp = h.worst_sample_at || h.latest_sample_at
      return stamp ? new Date(stamp).getUTCFullYear() <= activeYear : true
    })
  }, [data, activeYear])

  const handleIngest = async () => {
    setBusy(true)
    setNotice(null)
    try {
      const summary = await ingestMicroplastics()
      const kept = summary?.normalisation?.records_accepted ?? 0
      const connectors = summary?.connectors ?? []
      const failed = connectors.filter((c: any) => c.status !== 'OK')
      setNotice(
        kept
          ? `Ingested ${kept} published sample(s).`
          : `No samples retrieved. ${failed.map((c: any) => `${c.source}: ${c.reason}`).join(' ')}`,
      )
      load()
    } catch {
      setNotice('Ingestion request failed. The connector may be unreachable.')
    } finally {
      setBusy(false)
    }
  }

  const handleAlerts = async () => {
    setBusy(true)
    try {
      const r = await refreshMicroplasticAlerts()
      setNotice(
        `${r.created} new alert(s) raised, ${r.refreshed} refreshed. They appear in Monitoring & Alerts.`,
      )
    } catch {
      setNotice('Could not raise alerts.')
    } finally {
      setBusy(false)
    }
  }

  const handleDrift = async (regionId: number) => {
    setDriftBusy(true)
    try {
      setDrift(await projectMicroplasticDrift({ region_id: regionId, duration_h: driftHours }))
    } catch {
      setDrift({ status: 'ERROR', reason: 'Drift request failed.' })
    } finally {
      setDriftBusy(false)
    }
  }

  // ---- render helpers ----------------------------------------------------
  const scatter = (() => {
    if (!surface?.has_data || !surface.nodes.length) return null
    const lats = surface.nodes.map((n) => n.latitude)
    const lons = surface.nodes.map((n) => n.longitude)
    const latMin = Math.min(...lats), latMax = Math.max(...lats)
    const lonMin = Math.min(...lons), lonMax = Math.max(...lons)
    const spanLat = Math.max(0.5, latMax - latMin)
    const spanLon = Math.max(0.5, lonMax - lonMin)
    const values = surface.nodes.map((n) => n.value).filter((v) => v != null)
    const sorted = [...values].sort((a, b) => a - b)
    // Per-medium normalisation: comparing across media is invalid, so each
    // ramp is scaled against its own distribution only.
    const p95 = sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.95))] || 1
    return { latMin, latMax, lonMin, lonMax, spanLat, spanLon, p95 }
  })()

  const toX = (lon: number) => ((lon - (scatter?.lonMin ?? 0)) / (scatter?.spanLon ?? 1)) * 100
  const toY = (lat: number) => 100 - ((lat - (scatter?.latMin ?? 0)) / (scatter?.spanLat ?? 1)) * 100
  const rampColor = (v: number) => {
    const t = Math.max(0, Math.min(1, v / (scatter?.p95 || 1)))
    // low (teal) -> medium (amber) -> high (rose)
    if (t < 0.5) {
      const k = t / 0.5
      return `rgb(${Math.round(0 + 245 * k)}, ${Math.round(255 - 100 * k)}, ${Math.round(179 - 70 * k)})`
    }
    const k = (t - 0.5) / 0.5
    return `rgb(${Math.round(245 + 9 * k)}, ${Math.round(155 - 92 * k)}, ${Math.round(109 - 15 * k)})`
  }

  if (loading) {
    return (
      <div className="page mp-page animate-in">
        <div className="hint">Loading the microplastics workspace…</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="page mp-page animate-in">
        <div className="glass-card mp-empty">
          <AlertTriangle size={18} />
          <div>
            <b>Microplastics service unavailable</b>
            <p>{error}</p>
            <p className="mp-dim">
              This page never falls back to illustrative numbers. When the service
              is unreachable, the honest state is an empty one.
            </p>
          </div>
        </div>
      </div>
    )
  }

  const hasData = coverage?.has_data

  return (
    <div className="page mp-page animate-in">
      {/* ---------- Header ---------- */}
      <div className="page-header">
        <div>
          <h1 className="page-title title-glow">
            Microplastics <span className="text-gradient">Intelligence</span>
          </h1>
          <p className="page-subtitle">
            Open-source microplastic observations mapped onto the monitored coastal
            regions, ranked into hotspots and fed into the decision engine as a new
            anomaly category. No hardware, no proprietary feed, no invented values.
          </p>
        </div>
        <div className="mp-head-actions">
          <DataSourceBadge label="NOAA NCEI + curated literature · open" />
          <button className="mp-btn" onClick={handleIngest} disabled={busy}>
            <Download size={14} /> Ingest latest
          </button>
          <button className="mp-btn mp-btn-ghost" onClick={handleAlerts} disabled={busy}>
            <AlertTriangle size={14} /> Raise alerts
          </button>
        </div>
      </div>

      {notice && <div className="glass-card mp-notice" role="status">{notice}</div>}

      {/* ---------- Data vintage warning: non-negotiable ---------- */}
      {hasData && (
        <motion.div variants={fadeUp} initial="hidden" animate="show" className="glass-card mp-vintage">
          <Clock size={16} />
          <div>
            <b>Archival record — not a live feed</b>
            <p>
              The newest published sample is{' '}
              <b>{vintage?.latest ? vintage.latest.slice(0, 10) : '—'}</b>
              {vintage?.oldest ? <> and the oldest is <b>{vintage.oldest.slice(0, 10)}</b></> : null}
              {coverage?.data_vintage?.span_years ? <> (span {coverage.data_vintage.span_years} years)</> : null}.
              Hotspot recency is ranked <em>against the collection itself</em>, not against today, so
              "priority" means "most recent evidence available", never "measured this week".
            </p>
          </div>
        </motion.div>
      )}

      {!hasData && (
        <motion.div variants={fadeUp} initial="hidden" animate="show" className="glass-card mp-empty">
          <Database size={18} />
          <div>
            <b>No microplastic samples stored yet</b>
            <p>{coverage?.honesty_note ?? data?.reason}</p>
            <p className="mp-dim">
              Nothing is drawn until real samples exist. Use <em>Ingest latest</em> to
              pull the NOAA collection and the curated literature file.
            </p>
          </div>
        </motion.div>
      )}

      {/* ---------- KPIs ---------- */}
      {hasData && (
        <div className="mp-kpi-row">
          <div className="glass-card mp-kpi">
            <DataLabel
              label="REAL SAMPLES"
              value={String(coverage?.total_samples ?? 0)}
              source="NOAA NCEI + published literature"
            />
          </div>
          <div className="glass-card mp-kpi">
            <DataLabel
              label="HOTSPOTS"
              value={String(data?.hotspots?.hotspot_count ?? 0)}
              source={`of ${data?.hotspots?.groups_evaluated ?? 0} region/medium groups`}
            />
          </div>
          <div className="glass-card mp-kpi">
            <DataLabel
              label="REGIONS COVERED"
              value={`${coverage?.regions_with_data ?? 0}/${coverage?.regions_total ?? 0}`}
              source="regions with at least one sample"
            />
          </div>
          <div className="glass-card mp-kpi">
            <DataLabel
              label="UNMAPPED"
              value={String(coverage?.unassigned_samples ?? 0)}
              source="beyond mapping radius, kept unassigned"
            />
          </div>
        </div>
      )}

      {/* ---------- Measurement discipline ---------- */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="glass-card mp-discipline">
        <div className="mp-disc-head">
          <Gauge size={15} />
          <b>Measurement discipline</b>
          <span className="mp-dim">Why there is no single “microplastics score” here</span>
        </div>
        <p className="mp-disc-rule">{data?.measurement_discipline?.rule}</p>
        <div className="mp-families">
          {Object.entries(coverage?.by_unit_family ?? {}).map(([family, count]) => (
            <div key={family} className="mp-family">
              <div className="mp-family-top">
                <code>{family}</code>
                <b>{count}</b>
              </div>
              <p>{data?.measurement_discipline?.families?.[family]}</p>
            </div>
          ))}
        </div>
      </motion.div>

      {/* ---------- Layer selector + surface ---------- */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="glass-card mp-layer-card">
        <SectionHeader
          eyebrow="SPATIAL LAYER"
          title="Concentration surface"
          sub="Inverse-distance-weighted estimates from real samples. Interpolated cells are shaded; unsampled cells are left blank and counted."
          right={
            <div className="mp-layer-toggle" role="group" aria-label="Choose a measurement medium">
              {LAYERS.map((l) => (
                <button
                  key={l.key}
                  className={`mp-layer-btn${layer === l.key ? ' on' : ''}`}
                  onClick={() => setLayer(l.key)}
                  title={`${l.label} (${l.unitHint})`}
                >
                  <Layers size={12} />
                  {l.label}
                </button>
              ))}
            </div>
          }
        />

        {!surface?.has_data ? (
          <div className="mp-absent">
            <Info size={15} />
            <span>{surface?.reason ?? 'No samples for this medium.'}</span>
          </div>
        ) : (
          <div className="mp-surface-wrap">
            <div className="mp-map" role="img" aria-label={`Interpolated ${surface.unit} surface`}>
              {scatter && surface.nodes.map((n, i) => (
                <span
                  key={i}
                  className="mp-node"
                  style={{
                    left: `${toX(n.longitude)}%`,
                    top: `${toY(n.latitude)}%`,
                    background: rampColor(n.value),
                    opacity: n.is_estimate ? 0.42 + 0.5 * ((n.confidence ?? 50) / 100) : 1,
                    transform: `translate(-50%,-50%) scale(${n.is_estimate ? 1 : 1.9})`,
                  }}
                  title={`${fmt(n.value)} ${surface.unit} · ${n.n_sources} source(s) · nearest ${n.nearest_km} km${n.is_estimate ? ' · interpolated' : ' · measured'}`}
                />
              ))}
            </div>
            <div className="mp-surface-meta">
              <div className="mp-meta-row">
                <span>Unit</span><b>{surface.unit}</b>
                <span className="mp-dim">family {surface.unit_family}</span>
              </div>
              <div className="mp-meta-row">
                <span>Real samples</span><b>{surface.sample_count}</b>
              </div>
              <div className="mp-meta-row">
                <span>Interpolated cells</span><b>{surface.nodes.length}</b>
              </div>
              <div className="mp-meta-row">
                <span>Unsampled cells</span><b className="mp-gap">{surface.gap_cells}</b>
              </div>
              <RiskBar
                pct={(surface.coverage_ratio ?? 0) * 100}
                label="Cell coverage"
                heat
              />
              <p className="mp-note">{surface.honesty_note}</p>
              <p className="mp-note mp-dim">{surface.method}</p>
            </div>
          </div>
        )}
      </motion.div>

      {/* ---------- Timeline scrubber ---------- */}
      {years.length > 0 && (
        <motion.div variants={fadeUp} initial="hidden" animate="show" className="glass-card mp-timeline">
          <div className="mp-tl-head">
            <Clock size={15} />
            <b>Survey year</b>
            <span className="mp-dim">
              Buckets are yearly because the source publishes discrete surveys, not a continuous series.
            </span>
          </div>
          <div className="mp-tl-track">
            {years.map((y) => (
              <button
                key={y}
                className={`mp-tl-year${activeYear === y ? ' on' : ''}`}
                onClick={() => setActiveYear(y)}
              >
                {y}
              </button>
            ))}
            <button className={`mp-tl-year${activeYear == null ? ' on' : ''}`} onClick={() => setActiveYear(null)}>
              ALL
            </button>
          </div>
          <p className="mp-note mp-dim">
            Showing hotspots whose strongest sample is dated {activeYear ?? 'any year'} or earlier.
          </p>
        </motion.div>
      )}

      {/* ---------- Hotspots ---------- */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="glass-card mp-hotspots">
        <SectionHeader
          eyebrow="DECISION INPUT"
          title="Microplastic hotspots"
          sub={data?.hotspots?.threshold_note}
          right={
            <div className="mp-weights">
              {Object.entries(data?.hotspots?.weights ?? {}).map(([k, v]) => (
                <span key={k} className="mp-weight">
                  <em>{k}</em><b>{Math.round((v as number) * 100)}%</b>
                </span>
              ))}
            </div>
          }
        />

        {visibleHotspots.length === 0 ? (
          <div className="hint">
            No region/medium group reaches the source's “Medium” class in this slice.
            That is sparse evidence, not a clean ocean.
          </div>
        ) : (
          <div className="mp-hotspot-list">
            {visibleHotspots.map((h) => (
              <div key={h.hotspot_id} className={`mp-hotspot${h.is_hotspot ? '' : ' mp-hotspot--below'}`}>
                <div className="mp-hotspot-head">
                  <span className="mp-sev-dot" style={{ background: SEVERITY_COLOR[h.severity] }} />
                  <b>{h.region}</b>
                  <span className="mp-medium-chip">{h.medium_display}</span>
                  <span className="mp-sev-label" style={{ color: SEVERITY_COLOR[h.severity] }}>
                    {h.severity.toUpperCase()}
                  </span>
                  {!h.is_hotspot && <span className="mp-dim mp-below-tag">below hotspot threshold</span>}
                  <span className="mp-priority">
                    <TrendingUp size={12} /> {h.priority.toFixed(0)}<em>/100</em>
                  </span>
                </div>

                <div className="mp-hotspot-grid">
                  <div className="mp-cell">
                    <span>Published class (worst)</span>
                    <b>{h.published_class ?? '—'}</b>
                    <em className="mp-dim">{h.severity_basis}</em>
                  </div>
                  <div className="mp-cell">
                    <span>Latest sample class</span>
                    <b>{h.latest_published_class ?? '—'}</b>
                    <em className="mp-dim">{h.latest_sample_at?.slice(0, 10) ?? 'undated'}</em>
                  </div>
                  <div className="mp-cell">
                    <span>Peak / median</span>
                    <b>{h.statistics.max == null && h.statistics.median == null
                      ? '—'
                      : `${fmt(h.statistics.max)} · ${fmt(h.statistics.median)}`}</b>
                    <em className="mp-dim">{h.unit}</em>
                  </div>
                  <div className="mp-cell">
                    <span>Samples</span>
                    <b>{h.statistics.n_samples}</b>
                    <em className="mp-dim">confidence {h.confidence}%</em>
                  </div>
                </div>

                <RiskBar pct={h.priority} label="Priority" value={`${h.priority.toFixed(0)}/100`} heat />

                {h.basis.length > 0 && (
                  <ul className="mp-basis">
                    {h.basis.map((b, i) => <li key={i}>{b}</li>)}
                  </ul>
                )}

                <div className="mp-hotspot-foot">
                  <span className={`mp-action mp-action--${h.action.toLowerCase()}`}>
                    {h.action.replace(/_/g, ' ')}
                  </span>
                  <span className="mp-dim">{h.action_rationale}</span>
                  <button className="mp-btn mp-btn-xs" disabled={driftBusy} onClick={() => handleDrift(h.region_id)}>
                    <Ship size={12} /> Project drift
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </motion.div>

      {/* ---------- Drift ---------- */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="glass-card mp-drift">
        <SectionHeader
          eyebrow="STRETCH GOAL"
          title="Drift projection"
          sub="Surface Lagrangian advection from real current forcing, with a sqrt-time diffusive spread."
          right={
            <label className="mp-hours">
              <span>Horizon <b>{driftHours}h</b></span>
              <input
                type="range" min={24} max={72} step={12}
                value={driftHours}
                onChange={(e) => setDriftHours(Number(e.target.value))}
              />
            </label>
          }
        />

        {!drift && (
          <div className="mp-absent">
            <Info size={15} />
            <span>Pick a region above and press <em>Project drift</em>.</span>
          </div>
        )}

        {drift?.status === 'NO_FORCING' && (
          <div className="mp-noforce">
            <AlertTriangle size={16} />
            <div>
              <b>No drift projection produced</b>
              <p>{drift.reason}</p>
              <p className="mp-dim">
                Sources checked: {drift.checked_sources?.join(', ')}
              </p>
              <p className="mp-dim">
                A corridor is only drawn when real forcing exists. Still water and
                unmeasured water are not the same thing, so they must not look the same.
              </p>
            </div>
          </div>
        )}

        {drift?.status === 'OK' && drift.forcing && (
          <div className="mp-drift-body">
            <div className="mp-drift-stats">
              <DataLabel
                label="FORCING"
                value={`${drift.forcing.speed_kmh?.toFixed(2) ?? '—'}`}
                unit="km/h"
                source={`${drift.forcing.origin} · ${drift.forcing.origin_status}`}
              />
              <DataLabel
                label="BEARING"
                value={`${drift.forcing.direction_deg?.toFixed(0) ?? '—'}`}
                unit="°"
                source="observed current direction"
              />
              <DataLabel
                label="DISPLACEMENT"
                value={`${drift.end_point?.cumulative_km?.toFixed(1) ?? '—'}`}
                unit="km"
                source={`over ${drift.duration_h}h`}
              />
              <DataLabel
                label="SPREAD"
                value={`${drift.end_point?.spread_km?.toFixed(1) ?? '—'}`}
                unit="km"
                source="sqrt-time diffusion"
              />
            </div>
            <div className="mp-drift-notes">
              <StatusIndicator tone={drift.forcing_quality?.credible ? 'warn' : 'crit'}>
                CONFIDENCE {drift.confidence}
              </StatusIndicator>
              <p className="mp-note">{drift.confidence_note}</p>
              {drift.forcing_quality && !drift.forcing_quality.credible && (
                <div className="mp-quality-fail">
                  <b>Forcing failed {drift.forcing_quality.warnings.length} credibility check(s)</b>
                  <ul className="mp-basis">
                    {drift.forcing_quality.warnings.map((w, i) => <li key={i}>{w}</li>)}
                  </ul>
                </div>
              )}
              <ul className="mp-basis">
                {(drift.limitations ?? [])
                  .filter((l) => !(drift.forcing_quality?.warnings ?? []).includes(l))
                  .map((l, i) => <li key={i}>{l}</li>)}
              </ul>
            </div>
          </div>
        )}
      </motion.div>

      {/* ---------- Coverage & gaps ---------- */}
      {hasData && (
        <motion.div variants={fadeUp} initial="hidden" animate="show" className="glass-card mp-coverage">
          <SectionHeader
            eyebrow="EVIDENCE REPORT"
            title="Coverage and gaps"
            sub={coverage?.honesty_note}
          />
          <div className="mp-cov-grid">
            <div className="mp-cov-col">
              <h4>Sampled media</h4>
              {Object.entries(coverage?.by_medium ?? {}).map(([m, n]) => (
                <div key={m} className="mp-cov-row">
                  <span>{m.replace(/_/g, ' ')}</span><b>{n}</b>
                </div>
              ))}
            </div>
            <div className="mp-cov-col">
              <h4 className="mp-gap-title">Regions with no published sample</h4>
              <ul className="mp-gap-list">
                {(coverage?.regions_without_data ?? []).map((r) => <li key={r}>{r}</li>)}
              </ul>
              <p className="mp-note mp-dim">
                These are displayed as gaps. They are not assigned an estimated value.
              </p>
            </div>
          </div>
        </motion.div>
      )}

      {/* ---------- Sources ---------- */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="glass-card mp-sources">
        <SectionHeader eyebrow="PROVENANCE" title="Data sources" />
        <div className="mp-src-grid">
          {(data?.sources ?? []).map((s) => (
            <div key={s.key} className="mp-src">
              <div className="mp-src-top">
                <b>{s.name}</b>
                {s.requires_credentials
                  ? <StatusIndicator tone="off">TOKEN REQUIRED</StatusIndicator>
                  : <StatusIndicator tone="ok">OPEN</StatusIndicator>}
              </div>
              <p className="mp-dim">{s.access}</p>
              <p className="mp-licence"><FileText size={11} /> {s.licence}</p>
              <a className="mp-link" href={s.homepage} target="_blank" rel="noreferrer">
                {s.homepage} <ExternalLink size={11} />
              </a>
            </div>
          ))}
        </div>
      </motion.div>

      {/* ---------- Cross-links ---------- */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="glass-card mp-crosslinks">
        <span><Gauge size={14} /> <button className="mp-link-btn" onClick={() => navigate('/microplastics/dashboard')}>Back to the dashboard</button></span>
        <span><Waves size={14} /> <button className="mp-link-btn" onClick={() => navigate('/globe')}>Open the Digital Twin globe</button></span>
        <span><Anchor size={14} /> <button className="mp-link-btn" onClick={() => navigate('/coastal')}>Coastal Intelligence</button></span>
        <span><AlertTriangle size={14} /> <button className="mp-link-btn" onClick={() => navigate('/monitoring')}>Monitoring &amp; Alerts</button></span>
      </motion.div>
    </div>
  )
}
