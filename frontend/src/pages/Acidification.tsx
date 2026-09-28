import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import {
  Droplet, FlaskConical, Database, Download, AlertTriangle, Info, Layers,
  Gauge, Ship, Globe2, RefreshCw, Radio, TrendingDown, CheckCircle2, TestTube2,
} from 'lucide-react'
import {
  fetchAcidificationOverview,
  fetchAcidificationZones,
  fetchAcidificationSamples,
  fetchAcidificationSources,
  ingestAcidification,
} from '../api/client'
import { phColorCss, omegaColorCss, phSeverityLabel } from '../components/3d/globe/layerMath'
import { DataSourceBadge, StatusIndicator } from '../components/ocean/OceanUI'
import './Acidification.css'

/**
 * Ocean Acidification
 * ====================
 * The dedicated screen for ocean pH monitoring, backed entirely by measured
 * BGC-Argo in-situ pH profiles (`PH_IN_SITU_TOTAL`).
 *
 * Why this page exists separately from the Digital Twin: the globe can *show* a
 * pH layer, but it cannot answer "how acidified is it, where, and how do I
 * know?". This page is the evidence surface.
 *
 * Five presentation rules, because an acidification screen is exactly where it
 * is easiest to be quietly dishonest:
 *
 *  1. MEASURED pH AND DERIVED aragonite NEVER LOOK ALIKE.  pH is observed.
 *     Aragonite saturation is computed from measured pH plus co-located
 *     temperature and salinity via CO2SYS. Every aragonite figure on this page
 *     is tinted and marked, and a sample with no salinity shows "—" rather than
 *     a value. Nothing here is ever described as measured aragonite.
 *
 *  2. THE 1500 km REGION RADIUS IS A CAVEAT, NOT A FOOTNOTE.  The monitored
 *     regions are COASTAL, but BGC floats sample open ocean: the median stored
 *     cast sits ~1047 km from the nearest label. Attribution therefore uses a
 *     1500 km radius and every attributed row keeps its real
 *     `region_distance_km`, which is displayed on each hotspot. A "Lakshadweep
 *     Sea" hotspot is a basin-scale measurement, not a shore measurement, and
 *     the page says so.
 *
 *  3. TWO SPATIAL VIEWS, NOT ONE.  Hotspots are region-scoped; the /zones grid
 *     is region-independent. Both are shown, because a 0.5-degree cell is the
 *     only view that does not quietly fold a 1000 km offset into a coastal name.
 *
 *  4. GAPS STAY GAPS.  Unassigned samples are counted, not redistributed. A
 *     cell with no measurement is never drawn as pH 8.1.
 *
 *  5. ANCHORS ARE NAMED.  Acidified = pH < 8.00. Aragonite saturation = 1.0;
 *     operational shellfish stress = 2.0. The UI never relabels a threshold.
 */

const fadeUp = {
  hidden: { opacity: 0, y: 18 },
  show: { opacity: 0, y: 0, transition: { duration: 0.42, ease: 'easeOut' as const } },
}

/** Matches units.SEVERITY_ORDINALS / the stored severity_label values. */
const SEVERITY_COLOR: Record<string, string> = {
  NORMAL: '#00ffb3',
  LOW: '#38bdf8',
  MODERATE: '#ffb800',
  HIGH: '#ff7a45',
  CRITICAL: '#ff3366',
  Unknown: '#6e9cba',
}

const BAND_LABEL: Record<string, string> = {
  surface: 'Surface (0–30 m)',
  pycnocline: 'Pycnocline (30–200 m)',
  deep: 'Deep (>200 m)',
}

const BANDS = ['surface', 'pycnocline', 'deep'] as const
type Band = (typeof BANDS)[number]

/** pH to 3 decimals. A real pH measurement is never 0 or 1 significant figure. */
function phStr(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return value.toFixed(3)
}

/**
 * Aragonite to 2 decimals, with an explicit em dash when it is absent.
 *
 * The dash is meaningful: it means "not derived", because temperature or
 * salinity was unavailable. It must never be rendered as 0, and never as
 * "healthy".
 */
function omegaStr(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return value.toFixed(2)
}

function pct(part: number, total: number): string {
  if (!total) return '0%'
  return `${((part / total) * 100).toFixed(1)}%`
}

interface ZoneCell {
  latitude: number
  longitude: number
  n_samples: number
  n_floats: number
  n_with_omega: number
  mean_ph: number
  min_ph: number
  max_ph: number
  mean_omega: number | null
  min_omega: number | null
  worst_ordinal: number | null
  worst_label: string
  is_zone: boolean
  is_undersaturated: boolean
  depth_min: number
  depth_max: number
}

interface ZonesPayload {
  has_data: boolean
  grid_step_deg: number
  band: string | null
  zone_count: number
  undersaturated_count: number
  cells_with_data: number
  zones: ZoneCell[]
  threshold_note?: string
  reason?: string
}

interface HotspotStat {
  n_samples: number
  n_floats: number
  n_undersaturated: number
  n_with_derived_omega: number
  min_ph: number
  mean_ph: number
  min_omega_arag: number | null
  mean_omega_arag: number | null
  mean_distance_km: number | null
  temporal_span_days: number | null
  persistence: number | null
  depth_min: number
  depth_max: number
}

interface Hotspot {
  region: string
  region_id: number
  depth_layer: string
  severity: string
  severity_label: string
  severity_ordinal: number | null
  priority: number
  confidence: number
  trend: string
  action: string
  rationale: string
  recommendations: string[]
  is_hotspot: boolean
  latitude: number
  longitude: number
  latest_sample_at: string | null
  statistics: HotspotStat
}

interface Summary {
  n_samples: number
  min_ph: number | null
  mean_ph: number | null
  max_ph: number | null
  min_omega_arag: number | null
  mean_omega_arag: number | null
  n_acidic: number
  n_undersaturated: number
  n_floats: number
  aragonite_saturation_threshold: number
}

interface Coverage {
  has_data: boolean
  total_samples: number
  region_radius_km: number
  by_region: Record<string, number>
  by_source: Record<string, number>
  by_severity: Record<string, number>
  acidic_samples: number
  undersaturated_samples: number
  samples_with_derived_omega: number
  unassigned_samples: number
  regions_with_data: number
  regions_total: number
  regions_without_data: string[]
  measurement_discipline: string
  honesty_note: string
}

interface SampleRow {
  id: number
  latitude: number
  longitude: number
  sampled_at: string | null
  depth_m: number
  depth_band: string
  ph_total: number
  ph_free: number | null
  omega_arag: number | null
  /** SQLite returns the SQLAlchemy Boolean as 0/1, so this is not a real bool. */
  omega_arag_derived: boolean | 0 | 1
  dic_umol_kg: number | null
  pco2_uatm: number | null
  temperature_c: number | null
  salinity_psu: number | null
  severity_label: string
  is_acidic: boolean
  is_undersaturated: boolean
  region_id: number | null
  region_distance_km: number | null
  float_id: string | null
  cycle: number | null
  qc_flag: string
  source_file: string | null
  source_record_link: string | null
  organization: string | null
}

export default function Acidification() {
  const navigate = useNavigate()

  const [overview, setOverview] = useState<{
    status: string
    summary: Summary
    coverage: Coverage
    hotspots: { hotspots: Hotspot[]; zone_count: number; recommendations: { summary: string } }
    zones: { zone_count: number; cells_with_data: number }
  } | null>(null)
  const [band, setBand] = useState<Band>('deep')
  const [zones, setZones] = useState<ZonesPayload | null>(null)
  const [samples, setSamples] = useState<SampleRow[]>([])
  const [sources, setSources] = useState<{
    sources: { name: string; available: boolean; status: string; note?: string }[]
  } | null>(null)
  const [loading, setLoading] = useState(true)
  const [ingesting, setIngesting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastIngest, setLastIngest] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    const results = await Promise.allSettled([
        fetchAcidificationOverview(),
        fetchAcidificationZones({ band }),
        fetchAcidificationSamples({ limit: 300 }),
        fetchAcidificationSources(),
      ])
    const failures: string[] = []
    const [overviewResult, zonesResult, samplesResult, sourcesResult] = results

    if (overviewResult.status === 'fulfilled') setOverview(overviewResult.value)
    else failures.push('overview')

    if (zonesResult.status === 'fulfilled') setZones(zonesResult.value)
    else failures.push('depth-band grid')

    if (samplesResult.status === 'fulfilled') setSamples(samplesResult.value?.samples ?? [])
    else failures.push('sample table')

    if (sourcesResult.status === 'fulfilled') setSources(sourcesResult.value)
    else failures.push('source catalogue')

    if (failures.length) {
      setError(`Some acidification data could not be loaded (${failures.join(', ')}). Available sections remain displayed; refresh to retry.`)
    }
    setLoading(false)
  }, [band])

  useEffect(() => {
    void load()
  }, [load])

  const runIngest = async () => {
    setIngesting(true)
    setError(null)
    try {
      const res = await ingestAcidification(14)
      setLastIngest(
        `Ingested ${res?.persistence?.inserted ?? 0} new / ` +
          `${res?.persistence?.updated ?? 0} updated pH sample(s). ` +
          `${res?.normalisation?.records_rejected ?? 0} implausible reading(s) rejected.`,
      )
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ingest failed')
    } finally {
      setIngesting(false)
    }
  }

  const downloadCsv = () => {
    if (!samples.length) return
    const head = [
      'id', 'sampled_at', 'latitude', 'longitude', 'depth_m', 'depth_band',
      'ph_total', 'ph_free', 'omega_arag', 'omega_derived', 'dic_umol_kg',
      'pco2_uatm', 'temperature_c', 'salinity_psu', 'severity_label',
      'is_acidic', 'is_undersaturated', 'region_id', 'region_distance_km',
      'float_id', 'cycle', 'qc_flag', 'source_file', 'source_record_link',
    ]
    const rows = samples.map((s) =>
      [
        s.id, s.sampled_at ?? '', s.latitude, s.longitude, s.depth_m, s.depth_band,
        s.ph_total, s.ph_free ?? '', s.omega_arag ?? '', s.omega_arag_derived,
        s.dic_umol_kg ?? '', s.pco2_uatm ?? '', s.temperature_c ?? '',
        s.salinity_psu ?? '', s.severity_label, s.is_acidic, s.is_undersaturated,
        s.region_id ?? '', s.region_distance_km ?? '', s.float_id ?? '',
        s.cycle ?? '', s.qc_flag, s.source_file ?? '', s.source_record_link ?? '',
      ].map((v) => {
        const t = String(v)
        return /[",\n]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t
      }).join(','),
    )
    const blob = new Blob([[head.join(','), ...rows].join('\n')], {
      type: 'text/csv;charset=utf-8',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `acidification_ph_samples_${band}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const summary = overview?.summary
  const coverage = overview?.coverage
  const hotspots = overview?.hotspots?.hotspots ?? []
  const total = summary?.n_samples ?? samples.length

  // Worst measured pH: the headline is always the MEASURED quantity.
  const worst = useMemo(() => {
    if (!samples.length) return null
    return samples.reduce((acc, s) => (s.ph_total < acc.ph_total ? s : acc), samples[0])
  }, [samples])

  const severityMix = useMemo(() => {
    const mix = coverage?.by_severity ?? {}
    const order = ['CRITICAL', 'HIGH', 'MODERATE', 'LOW', 'NORMAL']
    return order
      .filter((k) => mix[k])
      .map((k) => ({ label: k, n: mix[k] }))
  }, [coverage])

  const derivedCoverage = useMemo(() => {
    const withOmega = samples.filter((s) => s.omega_arag != null).length
    return { withOmega, without: samples.length - withOmega }
  }, [samples])

  return (
    <div className="acid-page">
      {/* ---------- header ---------- */}
      <motion.div initial="hidden" animate="show" variants={fadeUp}>
        <div className="acid-page-head">
          <h1>
            Ocean Acidification
          </h1>
          <div className="acid-head-actions">
            <button className="acid-btn" onClick={() => void load()} disabled={loading}>
              <RefreshCw size={13} /> {loading ? 'Loading' : 'Refresh'}
            </button>
            <button
              className="acid-btn"
              onClick={runIngest}
              disabled={ingesting}
              title="Fetch real Argo BGC pH profiles and re-derive carbonate chemistry"
            >
              <Database size={13} /> {ingesting ? 'Ingesting…' : 'Ingest Argo pH'}
            </button>
            <button
              className="acid-btn acid-btn-ghost"
              onClick={downloadCsv}
              disabled={!samples.length}
            >
              <Download size={13} /> CSV
            </button>
            <button
              className="acid-btn acid-btn-ghost"
              onClick={() => navigate('/oceanvision')}
            >
              <Globe2 size={13} /> 3D Globe
            </button>
          </div>
        </div>

        {error && (
          <div className="acid-notice acid-crit" style={{ marginBottom: 'var(--sp-3)' }}>
            <AlertTriangle size={13} style={{ verticalAlign: -2, marginRight: 7 }} />
            {error}
          </div>
        )}
        {loading && !overview && (
          <div className="acid-notice" role="status" aria-live="polite" style={{ marginBottom: 'var(--sp-3)' }}>
            <Radio size={13} style={{ verticalAlign: -2, marginRight: 7 }} />
            Loading measured pH and acidification evidence…
          </div>
        )}
        {lastIngest && (
          <div className="acid-live" style={{ marginBottom: 'var(--sp-3)' }}>
            <CheckCircle2 size={15} className="acid-live-icon" />
            <span>{lastIngest}</span>
          </div>
        )}
      </motion.div>

      {/* ---------- live provenance ---------- */}
      {total > 0 && (
        <motion.div className="acid-live" initial="hidden" animate="show" variants={fadeUp}>
          <Radio size={15} className="acid-live-icon" />
          <div>
            <b>Live measured pH</b>
            <span>
              {total.toLocaleString()} real in-situ pH observations from {summary?.n_floats ?? 0}{' '}
              BGC-Argo float(s), pH in {phStr(summary?.min_ph)}–{phStr(summary?.max_ph)}.
              Values outside the 7.40–8.60 seawater plausibility window are rejected at
              ingest regardless of the sensor QC flag.
            </span>
          </div>
        </motion.div>
      )}

      {/* ---------- measured vs derived key ---------- */}
      {total > 0 && (
        <motion.div
          className="acid-derivation-key"
          initial="hidden"
          animate="show"
          variants={fadeUp}
        >
          <TestTube2 size={15} />
          <span>
            <b>pH is measured.</b> <b>Aragonite saturation is derived</b>, never observed:
            CO2SYS solves the carbonate system from measured pH plus co-located temperature
            and practical salinity, taking alkalinity from the salinity relationship
            (Li et al. 2016). Salinity comes from the co-located core Argo profile, because
            BGC files carry none of their own. Tinted figures below are derived
            estimates. {derivedCoverage.without.toLocaleString()} of{' '}
            {samples.length.toLocaleString()} listed samples have no aragonite because
            temperature or salinity was unavailable — those show{' '}
            <code>—</code>, not a value.
          </span>
        </motion.div>
      )}

      {/* ---------- no data ---------- */}
      {total === 0 && !loading && (
        <motion.div className="acid-empty" initial="hidden" animate="show" variants={fadeUp}>
          <AlertTriangle size={20} />
          <div>
            <b>No stored pH samples</b>
            <p>
              Nothing has been ingested yet, so there is nothing honest to plot. Run an
              ingest to fetch real Argo BGC in-situ pH profiles.
            </p>
            <button className="acid-btn" onClick={runIngest} disabled={ingesting}>
              <Database size={13} /> {ingesting ? 'Ingesting…' : 'Ingest Argo pH'}
            </button>
          </div>
        </motion.div>
      )}

      {total > 0 && (
        <>
          {/* ---------- KPI strip ---------- */}
          <motion.div
            className="acid-kpis"
            initial="hidden"
            animate="show"
            variants={fadeUp}
          >
            <div className="acid-kpi">
              <span className="acid-kpi-label">{summary ? 'Samples' : 'Samples loaded'}</span>
              <span className="acid-kpi-value">{total.toLocaleString()}</span>
              <em>measured pH levels</em>
            </div>
            <div className="acid-kpi">
              <span className="acid-kpi-label">Min pH</span>
              <span className="acid-kpi-value acid-crit">{phStr(summary?.min_ph)}</span>
              <em>lowest measured</em>
            </div>
            <div className="acid-kpi">
              <span className="acid-kpi-label">Mean pH</span>
              <span className="acid-kpi-value">{phStr(summary?.mean_ph)}</span>
              <em>all depths, all regions</em>
            </div>
            <div className="acid-kpi">
              <span className="acid-kpi-label">Acidified</span>
              <span className="acid-kpi-value acid-warn">{summary?.n_acidic ?? 0}</span>
              <em>pH &lt; 8.00 · {pct(summary?.n_acidic ?? 0, total)}</em>
            </div>
            <div className="acid-kpi acid-kpi-derived">
              <span className="acid-kpi-label">Min Ωarag</span>
              <span className="acid-kpi-value">{omegaStr(summary?.min_omega_arag)}</span>
              <em>derived · saturation = 1.0</em>
            </div>
            <div className="acid-kpi acid-kpi-derived">
              <span className="acid-kpi-label">Undersaturated</span>
              <span className="acid-kpi-value acid-crit">
                {summary?.n_undersaturated ?? 0}
              </span>
              <em>derived Ωarag &lt; 1.0 · {pct(summary?.n_undersaturated ?? 0, total)}</em>
            </div>
          </motion.div>

          {/* ---------- worst measurement ---------- */}
          {worst && (
            <motion.div className="acid-worst" initial="hidden" animate="show" variants={fadeUp}>
              <div className="acid-worst-top">
                <FlaskConical size={17} className="acid-crit" />
                <h2>{phStr(worst.ph_total)}</h2>
                <span className="acid-class-chip" style={{
                  borderColor: SEVERITY_COLOR[worst.severity_label] ?? '#6e9cba',
                  color: SEVERITY_COLOR[worst.severity_label] ?? '#6e9cba',
                }}>
                  {worst.severity_label}
                </span>
                <span className="acid-worst-cell">
                  lowest measured pH on record ·{' '}
                  {worst.depth_m.toFixed(0)} m ({BAND_LABEL[worst.depth_band] ?? worst.depth_band})
                  {' · '}
                  {worst.latitude.toFixed(2)}°, {worst.longitude.toFixed(2)}°
                  {worst.sampled_at ? ` · ${worst.sampled_at.slice(0, 10)}` : ''}
                </span>
                <span className="acid-worst-value">
                  {omegaStr(worst.omega_arag)}
                  <em>Ωarag derived</em>
                </span>
              </div>
              <p className="acid-worst-body">
                Float <b>{worst.float_id ?? 'unknown'}</b> cycle {worst.cycle ?? '—'}, QC flag{' '}
                <b>{worst.qc_flag}</b>
                {worst.salinity_psu != null && worst.temperature_c != null ? (
                  <>
                    , with co-located <b>{worst.temperature_c.toFixed(1)} °C</b> and{' '}
                    <b>{worst.salinity_psu.toFixed(2)} PSU</b> from the co-located core profile
                  </>
                ) : (
                  <>, with no co-located temperature/salinity so no aragonite was derived</>
                )}
                .{' '}
                {worst.is_undersaturated
                  ? 'At this saturation, aragonite is undersaturated and calcifying organisms cannot build or maintain shell.'
                  : 'Aragonite is still supersaturated here, so shell formation remains possible, though margin is reduced.'}
              </p>
            </motion.div>
          )}

          {/* ---------- two spatial views ---------- */}
          <div className="acid-cols">
            {/* ---- zones grid: region-independent ---- */}
            <motion.section className="acid-panel" initial="hidden" animate="show" variants={fadeUp}>
              <div className="acid-panel-head">
                <Layers size={15} />
                <b>Measured pH on a 0.5° grid</b>
                <span className="acid-dim">
                  {zones?.cells_with_data ?? 0} cell(s) with data
                </span>
                <div className="acid-band-tabs">
                  {BANDS.map((b) => (
                    <button
                      key={b}
                      className={`acid-band ${band === b ? 'acid-band-on' : ''}`}
                      onClick={() => setBand(b)}
                    >
                      {b}
                    </button>
                  ))}
                </div>
              </div>

              {!zones?.zones?.length ? (
                <div className="acid-absent">
                  <Info size={14} />
                  <span>
                    No measured pH in the <b>{BAND_LABEL[band] ?? band}</b> band yet. The
                    cell stays empty rather than being filled with a guessed value.
                  </span>
                </div>
              ) : (
                <div className="acid-zone-list">
                  {zones.zones.map((c) => (
                    <div
                      key={`${c.latitude},${c.longitude}`}
                      className={`acid-zone-row ${
                        c.is_undersaturated ? 'acid-zone-under' : c.is_zone ? 'acid-zone-low' : ''
                      }`}
                    >
                      <span className="acid-zone-pos">
                        {c.latitude.toFixed(2)}°, {c.longitude.toFixed(2)}°
                      </span>
                      <span
                        className="acid-sev-dot"
                        style={{ background: SEVERITY_COLOR[c.worst_label] ?? '#6e9cba' }}
                      />
                      <span className="acid-zone-label" style={{
                        color: SEVERITY_COLOR[c.worst_label] ?? '#6e9cba',
                      }}>
                        {c.worst_label}
                      </span>
                      <span className="acid-zone-stat">
                        <b style={{ color: phColorCss(c.min_ph) }}>{phStr(c.min_ph)}</b>
                        <em>min pH</em>
                      </span>
                      <span className="acid-zone-stat">
                        <b>{phStr(c.mean_ph)}</b>
                        <em>mean pH</em>
                      </span>
                      <span className="acid-zone-stat">
                        <b style={{ color: c.min_omega != null ? '#c084fc' : undefined }}>
                          {omegaStr(c.min_omega)}
                        </b>
                        <em className={c.n_with_omega === 0 ? 'acid-derived-mark' : undefined}>
                          min Ωarag{c.n_with_omega === 0 ? ' (none derived)' : ''}
                        </em>
                      </span>
                      <span className="acid-zone-n">{c.n_samples} obs</span>
                      <span className="acid-zone-track">
                        <i style={{
                          width: `${Math.min(100, (c.n_samples / 200) * 100)}%`,
                          background: phColorCss(c.mean_ph),
                        }} />
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {zones?.threshold_note && (
                <p className="acid-note">
                  <b>Grid definition.</b> {zones.threshold_note}
                </p>
              )}
            </motion.section>

            {/* ---- hotspots + severity mix ---- */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-3)' }}>
              <motion.section className="acid-panel" initial="hidden" animate="show" variants={fadeUp}>
                <div className="acid-panel-head">
                  <AlertTriangle size={15} />
                  <b>Acidification stress zones</b>
                  <span className="acid-dim">{hotspots.length} detected</span>
                </div>

                {coverage?.region_radius_km != null && (
                  <div className="acid-absent">
                    <Info size={14} />
                    <span>
                      These are <b>coastal</b> regions, but BGC floats sample open ocean.
                      Attribution uses a <b>{coverage.region_radius_km.toLocaleString()} km</b>{' '}
                      radius, and each row below shows its true distance from the label.
                      Read them as basin-scale, not shore-scale.
                    </span>
                  </div>
                )}

                {hotspots.length === 0 ? (
                  <div className="acid-absent">
                    <Info size={14} />
                    <span>No region met the stress criteria.</span>
                  </div>
                ) : (
                  <div className="acid-hot-list">
                    {hotspots.map((h) => (
                      <div
                        key={`${h.region_id}-${h.depth_layer}`}
                        className="acid-hot-row"
                      >
                        <span className="acid-hot-pos">#{h.region_id}</span>
                        <span
                          className="acid-sev-dot"
                          style={{ background: SEVERITY_COLOR[h.severity] ?? '#6e9cba' }}
                        />
                        <span className="acid-hot-region">
                          <b>{h.region}</b>
                          <em>
                            {BAND_LABEL[h.depth_layer] ?? h.depth_layer}
                            {h.statistics.mean_distance_km != null &&
                              ` · ${h.statistics.mean_distance_km.toFixed(0)} km offshore`}
                          </em>
                        </span>
                        <span className="acid-hot-class">
                          <b style={{ color: SEVERITY_COLOR[h.severity] ?? '#6e9cba' }}>
                            {h.severity}
                          </b>
                          <em>{h.trend.replace(/_/g, ' ')}</em>
                        </span>
                        <span className="acid-hot-stat">
                          <b style={{ color: phColorCss(h.statistics.min_ph) }}>
                            {phStr(h.statistics.min_ph)}
                          </b>
                          <em>min pH</em>
                        </span>
                        <span className="acid-hot-stat">
                          <b style={{ color: h.statistics.min_omega_arag != null ? '#c084fc' : undefined }}>
                            {omegaStr(h.statistics.min_omega_arag)}
                          </b>
                          <em className={h.statistics.n_with_derived_omega === 0 ? 'acid-derived-mark' : undefined}>
                            min Ωarag
                            {h.statistics.n_with_derived_omega === 0 ? ' n/a' : ''}
                          </em>
                        </span>
                        <span className="acid-hot-n">{h.statistics.n_samples}</span>
                        <span className="acid-hot-track">
                          <i style={{
                            width: `${Math.min(100, h.priority)}%`,
                            background: SEVERITY_COLOR[h.severity] ?? '#6e9cba',
                          }} />
                        </span>
                        <span className="acid-hot-prio">{h.priority.toFixed(1)}</span>
                      </div>
                    ))}
                  </div>
                )}

                {overview?.hotspots?.recommendations?.summary && (
                  <p className="acid-note">
                    <b>{overview.hotspots.recommendations.summary}</b>
                  </p>
                )}
              </motion.section>

              <motion.section className="acid-panel" initial="hidden" animate="show" variants={fadeUp}>
                <div className="acid-panel-head">
                  <Gauge size={15} />
                  <b>Severity mix</b>
                </div>
                <div className="acid-sev-list">
                  {severityMix.map(({ label, n }) => (
                    <div key={label} className="acid-sev-row">
                      <span className="acid-sev-name">
                        <span
                          className="acid-sev-swatch"
                          style={{ background: SEVERITY_COLOR[label] }}
                        />
                        {label}
                      </span>
                      <span className="acid-sev-track">
                        <i style={{
                          width: `${(n / total) * 100}%`,
                          background: SEVERITY_COLOR[label],
                        }} />
                      </span>
                      <b>{n.toLocaleString()}</b>
                      <span className="acid-sev-pct">{pct(n, total)}</span>
                    </div>
                  ))}
                </div>

                <div className="acid-anchors">
                  <h4><Info size={12} /> Named anchors</h4>
                  <ul>
                    <li><b>Acidified</b>: pH &lt; 8.00, the conventional reduction threshold vs pre-industrial open ocean.</li>
                    <li><b>CRITICAL</b>: pH &lt; 7.75 · <b>HIGH</b>: 7.75–7.90 · <b>MODERATE</b>: 7.90–8.00 · <b>LOW</b>: 8.00–8.05 · <b>NORMAL</b>: ≥ 8.05.</li>
                    <li><b>Aragonite saturation</b> = 1.0; <b>operational shellfish stress</b> = 2.0. Derived, not measured.</li>
                    <li><b>Plausible pH window</b> 7.40–8.60; outside it a reading is discarded, whatever its QC flag.</li>
                  </ul>
                </div>
              </motion.section>
            </div>
          </div>

          {/* ---------- recommendations ---------- */}
          {hotspots.filter((h) => h.recommendations?.length).length > 0 && (
            <motion.section className="acid-panel" initial="hidden" animate="show" variants={fadeUp}>
              <div className="acid-panel-head">
                <Ship size={15} />
                <b>Recommended actions</b>
                <span className="acid-dim">per stress zone</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-3)' }}>
                {hotspots
                  .filter((h) => h.recommendations?.length)
                  .slice(0, 4)
                  .map((h) => (
                    <div key={`rec-${h.region_id}-${h.depth_layer}`}>
                      <div className="acid-hot-region" style={{ marginBottom: 6 }}>
                        <b>
                          {h.region} · {BAND_LABEL[h.depth_layer] ?? h.depth_layer}
                        </b>
                        <em>
                          action: {h.action.replace(/_/g, ' ').toLowerCase()} · confidence{' '}
                          {h.confidence.toFixed(0)}%
                        </em>
                      </div>
                      {h.recommendations.map((r, i) => (
                        <p className="acid-reco" key={i}>
                          {r}
                        </p>
                      ))}
                    </div>
                  ))}
              </div>
            </motion.section>
          )}

          {/* ---------- samples table ---------- */}
          <motion.section className="acid-panel" initial="hidden" animate="show" variants={fadeUp}>
            <div className="acid-panel-head">
              <Droplet size={15} />
              <b>Measured pH samples</b>
              <span className="acid-dim">
                showing {samples.length.toLocaleString()} of {total.toLocaleString()}
              </span>
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table className="acid-table">
                <thead>
                  <tr>
                    <th>Sampled</th>
                    <th>Position</th>
                    <th>Depth</th>
                    <th>pH (measured)</th>
                    <th>Ωarag (derived)</th>
                    <th>DIC (derived)</th>
                    <th>pCO₂ (derived)</th>
                    <th>T / S</th>
                    <th>Class</th>
                    <th>Float</th>
                    <th>Region</th>
                    <th>QC</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {samples.map((s) => (
                    <tr key={s.id}>
                      <td>{s.sampled_at ? s.sampled_at.slice(0, 10) : '—'}</td>
                      <td className="acid-num">
                        {s.latitude.toFixed(2)}°, {s.longitude.toFixed(2)}°
                      </td>
                      <td className="acid-num">{s.depth_m.toFixed(0)} m</td>
                      <td className="acid-num" style={{ color: phColorCss(s.ph_total) }}>
                        {phStr(s.ph_total)}
                      </td>
                      <td className="acid-omega-cell">{omegaStr(s.omega_arag)}</td>
                      <td className="acid-num">
                        {s.dic_umol_kg != null ? s.dic_umol_kg.toFixed(0) : '—'}
                      </td>
                      <td className="acid-num">
                        {s.pco2_uatm != null ? s.pco2_uatm.toFixed(0) : '—'}
                      </td>
                      <td className="acid-num">
                        {s.temperature_c != null ? `${s.temperature_c.toFixed(1)}°C` : '—'}
                        {' / '}
                        {s.salinity_psu != null ? s.salinity_psu.toFixed(2) : '—'}
                      </td>
                      <td>
                        <span
                          className="acid-class-chip"
                          style={{
                            borderColor: SEVERITY_COLOR[s.severity_label] ?? '#6e9cba',
                            color: SEVERITY_COLOR[s.severity_label] ?? '#6e9cba',
                          }}
                        >
                          {s.severity_label}
                        </span>
                      </td>
                      <td className="acid-num">{s.float_id ?? '—'}</td>
                      <td className="acid-num">
                        {s.region_id != null ? `#${s.region_id}` : 'unassigned'}
                        {s.region_distance_km != null &&
                          ` (${s.region_distance_km.toFixed(0)} km)`}
                      </td>
                      <td className="acid-num">{s.qc_flag}</td>
                      <td className="acid-file">
                        {s.source_record_link ? (
                          <a
                            href={s.source_record_link}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {s.source_file ?? 'profile'}
                          </a>
                        ) : (
                          (s.source_file ?? '—')
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </motion.section>

          {/* ---------- coverage honesty + sources ---------- */}
          <div className="acid-cols">
            <motion.section className="acid-panel" initial="hidden" animate="show" variants={fadeUp}>
              <div className="acid-panel-head">
                <Layers size={15} />
                <b>Regional coverage</b>
                <span className="acid-dim">
                  {coverage?.regions_with_data ?? 0} of {coverage?.regions_total ?? 0} regions
                </span>
              </div>
              {coverage?.honesty_note && (
                <p className="acid-note">
                  <b>Read this before trusting a region.</b> {coverage.honesty_note}
                </p>
              )}
              <div className="acid-anchors">
                <h4><Info size={12} /> Attribution accounting</h4>
                <ul>
                  <li>
                    <b>{(coverage?.total_samples ?? 0) - (coverage?.unassigned_samples ?? 0)}</b>{' '}
                    of {(coverage?.total_samples ?? 0).toLocaleString()} samples attributed
                    to a monitored region.
                  </li>
                  <li>
                    <b>{coverage?.unassigned_samples ?? 0}</b> left unassigned. These are
                    counted, never redistributed into a neighbouring label.
                  </li>
                  <li>
                    <b>{coverage?.regions_without_data?.length ?? 0} of {coverage?.regions_total ?? 0}</b>{' '}
                    monitored regions have no measurement at all
                    {coverage?.regions_without_data?.length
                      ? ` (${coverage.regions_without_data.join(', ')})`
                      : ''}
                    . That is absent evidence, not evidence of healthy conditions.
                  </li>
                  <li>
                    <b>{coverage?.samples_with_derived_omega ?? 0}</b> of{' '}
                    {(coverage?.total_samples ?? 0).toLocaleString()} samples carry a derived
                    aragonite value; the rest derive nothing because temperature or
                    salinity was unavailable.
                  </li>
                </ul>
              </div>
              {coverage?.measurement_discipline && (
                <p className="acid-note">
                  <b>How the derived numbers were obtained.</b> {coverage.measurement_discipline}
                </p>
              )}
            </motion.section>

            <motion.section className="acid-panel" initial="hidden" animate="show" variants={fadeUp}>
              <div className="acid-panel-head">
                <Database size={15} />
                <b>Sources</b>
              </div>
              <div className="acid-src-list">
                {(sources?.sources ?? []).map((s) => (
                  <div
                    key={s.name}
                    className={`acid-src-row ${s.available ? '' : 'acid-src-off'}`}
                  >
                    <span className="acid-src-name">
                      <span
                        className="acid-src-dot"
                        style={{ background: s.available ? 'var(--ok)' : 'var(--accent-warm)' }}
                      />
                      <b>{s.name}</b>
                    </span>
                    <span className="acid-src-status">{s.status}</span>
                    <span className="acid-src-meta">{s.available ? 'available' : 'unavailable'}</span>
                  </div>
                ))}
              </div>
            </motion.section>
          </div>
        </>
      )}

      {/* ---------- limitations ---------- */}
      <motion.section className="acid-limits" initial="hidden" animate="show" variants={fadeUp}>
        <div className="acid-panel-head">
          <AlertTriangle size={15} />
          <b>What this screen does not tell you</b>
        </div>
        <ul>
          <li>
            <b>Aragonite is never measured here.</b> It is solved from measured pH plus
            co-located temperature and salinity, with alkalinity estimated from salinity
            (Li et al. 2016). Shell-building risk is therefore a modelled consequence, not
            an observation, and coastal conditions are not directly sampled at all.
          </li>
          <li>
            <b>Coastal acidification is the real risk, and it is not measured here.</b>{' '}
            BGC floats sample open ocean. The {coverage?.region_radius_km?.toLocaleString() ?? '1500'} km
            attribution radius is wide enough to reach the nearest coastal label only
            because these casts are basin-scale, and the true offset is shown on every
            hotspot.
          </li>
          <li>
            <b>Only {summary?.n_floats ?? 0} float(s) contribute.</b> pH is a BGC-Argo
            parameter, not a core one, so coverage is far sparser than temperature or
            oxygen. A region with no row is unmeasured, not safe.
          </li>
          <li>
            <b>Secondary corroboration is absent.</b> SOCAT, NOAA NCEI OAP/GLODAP and
            Copernicus all require registration or portal-mediated access, so no independent
            surface-pCO₂ cross-check is applied to these derived values.
          </li>
          <li>
            <b>Trend confidence is bounded by record length.</b> A "declining" label is a
            fitted slope over the stored window, and is withheld when the signal does not
            clear the module's significance and persistence rules.
          </li>
        </ul>
        <div className="acid-limits-actions">
          <button className="acid-btn" onClick={runIngest} disabled={ingesting}>
            <Database size={13} /> {ingesting ? 'Ingesting…' : 'Ingest Argo pH'}
          </button>
          <button className="acid-btn acid-btn-ghost" onClick={() => void load()}>
            <RefreshCw size={13} /> Refresh
          </button>
          <button className="acid-btn acid-btn-ghost" onClick={() => navigate('/oceanvision')}>
            <Globe2 size={13} /> View on 3D globe
          </button>
        </div>
      </motion.section>

      {/* Colorbar key for the globe ramp, so the page and globe agree. */}
      <motion.div className="acid-panel" initial="hidden" animate="show" variants={fadeUp}>
        <div className="acid-panel-head">
          <TrendingDown size={15} />
          <b>Colour keys</b>
          <span className="acid-dim">same ramps the 3D globe uses</span>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--sp-4)' }}>
          {[7.6, 7.75, 7.9, 8.0, 8.05, 8.2].map((v) => (
            <div key={v} style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
              <span
                className="acid-sev-swatch"
                style={{ background: phColorCss(v), width: 22, height: 12, borderRadius: 3 }}
              />
              <span className="acid-num" style={{ fontSize: 'var(--fs-xs)' }}>
                pH {v.toFixed(2)}
              </span>
              <span className="acid-dim" style={{ fontSize: 'var(--fs-xs)' }}>
                {phSeverityLabel(v) ?? '—'}
              </span>
            </div>
          ))}
          {[0.6, 1.0, 1.5, 2.0, 3.0].map((v) => (
            <div key={`w${v}`} style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
              <span
                className="acid-sev-swatch"
                style={{ background: omegaColorCss(v), width: 22, height: 12, borderRadius: 3 }}
              />
              <span style={{ fontSize: 'var(--fs-xs)' }} className="acid-num">
                Ωarag {v.toFixed(1)}
              </span>
              <span className="acid-derived-mark">derived</span>
            </div>
          ))}
        </div>
      </motion.div>

      <DataSourceBadge label="Argo BGC in-situ pH · open" />
      <StatusIndicator tone="ok">MEASURED pH</StatusIndicator>
    </div>
  )
}
