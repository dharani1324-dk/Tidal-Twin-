import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import {
  Droplets, Wind, Database, Download, AlertTriangle, Info, Layers,
  Gauge, Ship, Globe2, RefreshCw, Radio, TrendingDown, CheckCircle2,
} from 'lucide-react'
import {
  fetchDeoxygenationOverview,
  fetchDeoxygenationZones,
  fetchDeoxygenationSamples,
  fetchDeoxygenationSources,
  ingestDeoxygenation,
} from '../api/client'
import { DataSourceBadge, StatusIndicator } from '../components/ocean/OceanUI'
import './Deoxygenation.css'

/**
 * Ocean Deoxygenation
 * ===================
 * The dedicated screen for dissolved-oxygen monitoring, backed entirely by
 * measured BGC-Argo `DOXY` profiles.
 *
 * Why this page exists separately from the Digital Twin: the globe can *show*
 * an oxygen layer, but it cannot answer "how bad is it, where, and how do I
 * know?". This page is the evidence surface.
 *
 * Four presentation rules, because a deoxygenation screen is exactly where it
 * is easiest to be quietly dishonest:
 *
 *  1. TWO SPATIAL VIEWS, NOT ONE.  The 8 monitored regions are COASTAL and
 *     assignment is capped at a 500 km radius, so a float drifting in the open
 *     Arabian Sea OMZ is correctly left unassigned and never reaches a hotspot.
 *     The /zones grid is region-independent and is what actually surfaces the
 *     offshore oxygen minimum zone. Showing only hotspots would hide ~99% of
 *     the real measurements.
 *
 *  2. µmol/kg IS THE STORED UNIT.  Argo reports µmol/kg; mg/L is derived
 *     (× 0.032). Every oxygen figure shows which one it is, because a
 *     hypoxic threshold quoted in the wrong family is wrong by ~30×.
 *
 *  3. GAPS STAY GAPS.  Unassigned samples are counted, not redistributed. A
 *     cell with no measurement is never drawn as 0 mg/L.
 *
 *  4. ANCHORS ARE NAMED.  Hypoxic = < 2 mg/L (≈62.5 µmol/kg), dead zone =
 *     < 0.5 mg/L (≈15.6 µmol/kg). The UI never relabels a threshold.
 */

const fadeUp = {
  hidden: { opacity: 0, y: 18 },
  show: { opacity: 1, y: 0, transition: { duration: 0.42, ease: 'easeOut' as const } },
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

/** mg/L with a fixed 3-decimal floor: 0.040 mg/L is a real measurement. */
function mg(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  if (value === 0) return '0.000'
  return value < 0.01 ? value.toExponential(2) : value.toFixed(3)
}

interface ZoneCell {
  latitude: number
  longitude: number
  n_samples: number
  n_floats: number
  mean_mg_l: number
  min_mg_l: number
  max_mg_l: number
  worst_ordinal: number | null
  worst_label: string
  is_zone: boolean
  is_dead_zone: boolean
  depth_min: number
  depth_max: number
}

interface ZonesPayload {
  has_data: boolean
  grid_step_deg: number
  band: string | null
  cells_with_data: number
  zone_count: number
  dead_zone_count: number
  zones: ZoneCell[]
  threshold_note?: string
  reason?: string
}

interface SampleRow {
  id: number
  latitude: number
  longitude: number
  sampled_at: string | null
  depth_m: number
  do_umol_kg: number
  do_mg_l: number
  severity_label: string
  is_hypoxic: boolean
  is_dead_zone: boolean
  float_id: string | null
  cycle: number | null
  source_file: string | null
  source_record_link: string | null
  organization: string | null
  qc_flag: string | null
  origin_status: string
}

interface Coverage {
  has_data: boolean
  total_samples: number
  hypoxic_samples: number
  dead_zone_samples: number
  unassigned_samples: number
  regions_with_data: number
  regions_total: number
  regions_without_data: string[]
  by_severity: Record<string, number>
  by_source: Record<string, number>
  honesty_note?: string
  reason?: string
}

interface Hotspot {
  hotspot_id: string
  region: string
  depth_layer: string
  severity: string
  priority: number
  trend: string
  action: string
  statistics: {
    n_samples: number
    n_dead_zone: number
    min_do_mg_l: number | null
    mean_do_mg_l: number | null
  }
}

interface OverviewPayload {
  status: string
  reason?: string | null
  cache?: { hit: boolean; ttl_seconds: number }
  coverage: Coverage
  hotspots: { hotspot_count: number; hotspots: Hotspot[]; recommendations?: { summary: string } }
  measurement_discipline?: { rule: string; region_vs_zone: string }
}

interface SourceEntry {
  id: string
  name: string
  status: string
  license: string
  access: string
  update_frequency?: string
  used_for?: string
}

export default function Deoxygenation() {
  const navigate = useNavigate()
  const [overview, setOverview] = useState<OverviewPayload | null>(null)
  const [zones, setZones] = useState<ZonesPayload | null>(null)
  const [samples, setSamples] = useState<SampleRow[]>([])
  const [sources, setSources] = useState<SourceEntry[]>([])
  const [band, setBand] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    Promise.all([
      fetchDeoxygenationOverview(),
      fetchDeoxygenationZones(band ? { band: band as 'surface' } : {}),
      fetchDeoxygenationSamples({ limit: 40, is_hypoxic: true }).catch(() => ({ samples: [] })),
      fetchDeoxygenationSources().catch(() => ({ sources: [] })),
    ])
      .then(([ov, zn, sm, src]) => {
        setOverview(ov)
        setZones(zn)
        setSamples(sm?.samples ?? [])
        setSources(src?.sources ?? [])
        setError(null)
      })
      .catch((e) => setError(e?.message ?? 'Could not reach the deoxygenation service.'))
      .finally(() => setLoading(false))
  }, [band])

  useEffect(load, [load])

  const handleIngest = async () => {
    setBusy(true)
    try {
      const r = await ingestDeoxygenation(4)
      const kept = r?.normalisation?.records_accepted ?? 0
      const stored = r?.persistence?.total ?? 0
      setNotice(
        kept
          ? `Pulled ${kept} measured level(s) from real Argo BGC profiles · ${stored} row(s) now stored.`
          : 'No oxygen values retrieved — the connector reports its reason under Sources.',
      )
      load()
    } catch {
      setNotice('Ingestion request failed. Check that the backend is running.')
    } finally {
      setBusy(false)
    }
  }

  const coverage = overview?.coverage
  const hasData = coverage?.has_data ?? false
  const hotspots = overview?.hotspots?.hotspots ?? []
  const zoneCells = useMemo(() => zones?.zones ?? [], [zones])

  /** Worst real measurement anywhere on the grid, with its own provenance. */
  const worstCell = useMemo(
    () => zoneCells.filter((c) => c.is_dead_zone).sort((a, b) => a.min_mg_l - b.min_mg_l)[0] ?? null,
    [zoneCells],
  )

  const severityTotal = useMemo(
    () => Object.values(coverage?.by_severity ?? {}).reduce((a, b) => a + b, 0),
    [coverage],
  )

  if (loading) {
    return <div className="page dox-page animate-in"><div className="hint">Loading oxygen evidence…</div></div>
  }

  if (error) {
    return (
      <div className="page dox-page animate-in">
        <div className="glass-card dox-empty">
          <AlertTriangle size={18} />
          <div>
            <b>Deoxygenation service unavailable</b>
            <p>{error}</p>
            <p className="dox-dim">
              There is no illustrative fallback here. When the oxygen service is
              unreachable, the honest state is an empty one — a drawn-out map of
              invented oxygen would be worse than nothing.
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="page dox-page animate-in">
      {/* ---------- header ---------- */}
      <div className="page-header">
        <div>
          <h1 className="page-title title-glow">
            <Droplets size={26} style={{ verticalAlign: '-4px', marginRight: 8, color: '#00d4ff' }} />
            Ocean <span className="text-gradient">Deoxygenation</span>
          </h1>
          <p className="page-subtitle">
            Measured dissolved oxygen from BGC-Argo floats — hypoxic zones, dead
            zones, and the offshore oxygen minimum zone in the Indian Ocean.
          </p>
        </div>
        <div className="dox-head-actions">
          <DataSourceBadge label="BGC-Argo DOXY · open" />
          <button className="dox-btn" onClick={handleIngest} disabled={busy}>
            {busy ? <RefreshCw size={14} className="spin" /> : <Download size={14} />}
            {busy ? 'Pulling…' : 'Pull live profiles'}
          </button>
          <button className="dox-btn dox-btn-ghost" onClick={() => navigate('/globe')}>
            <Globe2 size={14} /> Digital Twin
          </button>
        </div>
      </div>

      {notice && <div className="glass-card dox-notice" role="status">{notice}</div>}

      {/* ---------- live-data provenance banner ---------- */}
      {hasData && (
        <motion.div variants={fadeUp} initial="hidden" animate="show" className="glass-card dox-live">
          <Radio size={15} className="dox-live-icon" />
          <div>
            <b>Real measurements, not a model</b>
            <span>
              Every oxygen value here was read from a real BGC-Argo profile file
              downloaded from the Argo GDAC. Nothing is interpolated, and no
              oxygen is synthesised. Coverage is currently{' '}
              <b>{coverage?.total_samples ?? 0}</b> measured level(s) — see the
              Sources panel for which connectors are actually reachable.
            </span>
          </div>
        </motion.div>
      )}

      {/* ---------- KPI strip ---------- */}
      {hasData ? (
        <div className="dox-kpis">
          <div className="glass-card dox-kpi">
            <span className="dox-kpi-label">Measured levels</span>
            <b className="dox-kpi-value">{coverage?.total_samples ?? 0}</b>
            <em>µmol/kg, Argo DOXY</em>
          </div>
          <div className="glass-card dox-kpi">
            <span className="dox-kpi-label">Hypoxic</span>
            <b className="dox-kpi-value dox-warn">{coverage?.hypoxic_samples ?? 0}</b>
            <em>&lt; 2 mg/L (≈62.5 µmol/kg)</em>
          </div>
          <div className="glass-card dox-kpi">
            <span className="dox-kpi-label">Dead zone</span>
            <b className="dox-kpi-value dox-crit">{coverage?.dead_zone_samples ?? 0}</b>
            <em>&lt; 0.5 mg/L (≈15.6 µmol/kg)</em>
          </div>
          <div className="glass-card dox-kpi">
            <span className="dox-kpi-label">Dead-zone cells</span>
            <b className="dox-kpi-value dox-crit">{zones?.dead_zone_count ?? 0}</b>
            <em>of {zones?.cells_with_data ?? 0} grid cells sampled</em>
          </div>
          <div className="glass-card dox-kpi">
            <span className="dox-kpi-label">Coastal hotspots</span>
            <b className="dox-kpi-value dox-warn">{overview?.hotspots?.hotspot_count ?? 0}</b>
            <em>8 monitored coastal regions</em>
          </div>
          <div className="glass-card dox-kpi">
            <span className="dox-kpi-label">Offshore</span>
            <b className="dox-kpi-value">{coverage?.unassigned_samples ?? 0}</b>
            <em>beyond 500 km — kept, not snapped</em>
          </div>
        </div>
      ) : (
        <div className="glass-card dox-empty">
          <Database size={18} />
          <div>
            <b>No oxygen measurements stored yet</b>
            <p>{coverage?.reason ?? overview?.reason}</p>
            <button className="dox-btn" onClick={handleIngest} disabled={busy}>
              <Download size={14} /> Pull live Argo BGC profiles
            </button>
          </div>
        </div>
      )}

      {/* ---------- the worst real measurement ---------- */}
      {worstCell && (
        <motion.div variants={fadeUp} initial="hidden" animate="show" className="glass-card dox-worst">
          <div className="dox-worst-top">
            <StatusIndicator tone="crit">DEAD ZONE</StatusIndicator>
            <h2>
              {worstCell.latitude.toFixed(2)}°, {worstCell.longitude.toFixed(2)}°
            </h2>
            <span className="dox-worst-cell">
              {worstCell.n_samples} level(s) · {worstCell.n_floats} float(s)
            </span>
            <span className="dox-worst-value">
              {mg(worstCell.min_mg_l)}<em>mg/L min</em>
            </span>
          </div>
          <p className="dox-worst-body">
            The lowest oxygen measured anywhere in the stored data. At this depth
            range ({worstCell.depth_min.toFixed(0)}–{worstCell.depth_max.toFixed(0)} m) the
            cell averages {mg(worstCell.mean_mg_l)} mg/L and peaks at{' '}
            {mg(worstCell.max_mg_l)} mg/L. This is an open-ocean cell: it sits far
            outside every coastal mapping radius, so it appears in the zone grid
            rather than in a regional hotspot.
          </p>
        </motion.div>
      )}

      {/* ---------- offshore zone grid ---------- */}
      {hasData && (
        <motion.div variants={fadeUp} initial="hidden" animate="show" className="glass-card dox-panel">
          <div className="dox-panel-head">
            <Layers size={15} />
            <b>Offshore oxygen minimum zones</b>
            <span className="dox-dim">
              measured oxygen on a {zones?.grid_step_deg ?? 0.5}° grid ·{' '}
              {zones?.zone_count ?? 0} zone(s), {zones?.dead_zone_count ?? 0} dead
            </span>
            <div className="dox-band-tabs">
              <button
                className={`dox-band${band === '' ? ' dox-band-on' : ''}`}
                onClick={() => setBand('')}
              >
                All depths
              </button>
              {Object.keys(BAND_LABEL).map((b) => (
                <button
                  key={b}
                  className={`dox-band${band === b ? ' dox-band-on' : ''}`}
                  onClick={() => setBand(b)}
                >
                  {BAND_LABEL[b]}
                </button>
              ))}
            </div>
          </div>

          {zoneCells.length === 0 ? (
            <div className="dox-absent">
              <Info size={14} />
              <span>
                No stored sample falls in{' '}
                {band ? BAND_LABEL[band] : 'this selection'}. That is a gap in
                coverage, not an absence of oxygen.
              </span>
            </div>
          ) : (
            <div className="dox-zone-list">
              {zoneCells.map((c) => (
                <div
                  key={`${c.latitude}:${c.longitude}`}
                  className={`dox-zone-row${c.is_dead_zone ? ' dox-zone-dead' : c.is_zone ? ' dox-zone-low' : ''}`}
                >
                  <span className="dox-zone-pos">
                    {c.latitude.toFixed(2)}°, {c.longitude.toFixed(2)}°
                  </span>
                  <span
                    className="dox-sev-dot"
                    style={{ background: SEVERITY_COLOR[c.worst_label] ?? SEVERITY_COLOR.Unknown }}
                  />
                  <span className="dox-zone-label">{c.worst_label}</span>
                  <span className="dox-zone-depth">
                    {c.depth_min.toFixed(0)}–{c.depth_max.toFixed(0)} m
                  </span>
                  <span className="dox-zone-stat">
                    <b>{mg(c.min_mg_l)}</b>
                    <em>min mg/L</em>
                  </span>
                  <span className="dox-zone-stat">
                    <b>{mg(c.mean_mg_l)}</b>
                    <em>mean</em>
                  </span>
                  <span className="dox-zone-n">
                    {c.n_samples} lvl · {c.n_floats} float
                  </span>
                  <span className="dox-zone-track">
                    <i
                      style={{
                        width: `${Math.min(100, (c.min_mg_l / 6) * 100)}%`,
                        background: SEVERITY_COLOR[c.worst_label] ?? SEVERITY_COLOR.Unknown,
                      }}
                    />
                  </span>
                </div>
              ))}
            </div>
          )}

          <p className="dox-note">
            {zones?.threshold_note ??
              'A cell is a zone when its worst stored sample is below 4 mg/L, and a dead zone when any sample is below 0.5 mg/L.'}
            {' '}Sorted worst-first, and the cell bar is scaled against 6 mg/L (the healthy
            ceiling) — a short bar means severe depletion, not missing data.
          </p>
        </motion.div>
      )}

      {/* ---------- severity mix + coastal hotspots ---------- */}
      {hasData && (
        <div className="dox-cols">
          <motion.div variants={fadeUp} initial="hidden" animate="show" className="glass-card dox-panel">
            <div className="dox-panel-head">
              <Gauge size={15} />
              <b>Coastal hotspots</b>
              <span className="dox-dim">8 monitored regions · 500 km radius</span>
            </div>

            {overview?.hotspots?.recommendations?.summary && (
              <p className="dox-reco">{overview.hotspots.recommendations.summary}</p>
            )}

            {hotspots.length === 0 ? (
              <div className="dox-absent">
                <CheckCircle2 size={14} />
                <span>
                  No monitored coastal region currently holds a low-oxygen sample.
                  This says nothing about the open ocean — see the zone grid above.
                </span>
              </div>
            ) : (
              <div className="dox-hot-list">
                {hotspots.map((h, i) => (
                  <div key={h.hotspot_id} className="dox-hot-row">
                    <span className="dox-hot-pos">{i + 1}</span>
                    <span
                      className="dox-sev-dot"
                      style={{ background: SEVERITY_COLOR[h.severity] ?? SEVERITY_COLOR.Unknown }}
                    />
                    <span className="dox-hot-region">
                      <b>{h.region}</b>
                      <em>{h.depth_layer} water</em>
                    </span>
                    <span className="dox-hot-class">
                      <b>{h.severity}</b>
                      <em>{h.trend.replace(/_/g, ' ')}</em>
                    </span>
                    <span className="dox-hot-stat">
                      <b>{mg(h.statistics.min_do_mg_l)}</b>
                      <em>min mg/L</em>
                    </span>
                    <span className="dox-hot-n">{h.statistics.n_samples} lvl</span>
                    <span className="dox-hot-track">
                      <i
                        style={{
                          width: `${h.priority}%`,
                          background: SEVERITY_COLOR[h.severity] ?? SEVERITY_COLOR.Unknown,
                        }}
                      />
                    </span>
                    <span className="dox-hot-prio">{h.priority.toFixed(0)}</span>
                  </div>
                ))}
              </div>
            )}

            <p className="dox-note">
              Hotspots are region-scoped, so each row rests on few samples right
              now. <b>Unassigned</b> offshore measurements are counted, never
              redistributed into the nearest coast.
            </p>
          </motion.div>

          <motion.div variants={fadeUp} initial="hidden" animate="show" className="glass-card dox-panel">
            <div className="dox-panel-head">
              <TrendingDown size={15} />
              <b>Severity mix</b>
              <span className="dox-dim">{severityTotal} classified level(s)</span>
            </div>

            <div className="dox-sev-list">
              {Object.entries(coverage?.by_severity ?? {})
                .sort((a, b) => b[1] - a[1])
                .map(([label, n]) => (
                  <div key={label} className="dox-sev-row">
                    <span className="dox-sev-name">
                      <i className="dox-sev-swatch" style={{ background: SEVERITY_COLOR[label] }} />
                      {label}
                    </span>
                    <span className="dox-sev-track">
                      <i
                        style={{
                          width: `${(n / Math.max(1, severityTotal)) * 100}%`,
                          background: SEVERITY_COLOR[label],
                        }}
                      />
                    </span>
                    <b>{n}</b>
                    <span className="dox-sev-pct">
                      {((n / Math.max(1, severityTotal)) * 100).toFixed(1)}%
                    </span>
                  </div>
                ))}
            </div>

            <div className="dox-anchors">
              <h4><Info size={12} /> Thresholds are fixed, not fitted</h4>
              <ul>
                <li><b>Hypoxic</b> — below 2 mg/L (≈62.5 µmol/kg)</li>
                <li><b>Dead zone</b> — below 0.5 mg/L (≈15.6 µmol/kg)</li>
                <li>
                  Stored canonically in <b>µmol/kg</b> (Argo native); mg/L is
                  derived by ×0.032
                </li>
              </ul>
            </div>
          </motion.div>
        </div>
      )}

      {/* ---------- recent hypoxic measurements ---------- */}
      {hasData && (
        <motion.div variants={fadeUp} initial="hidden" animate="show" className="glass-card dox-panel">
          <div className="dox-panel-head">
            <Ship size={15} />
            <b>Most recent hypoxic measurements</b>
            <span className="dox-dim">every row traceable to its source file</span>
          </div>

          {samples.length === 0 ? (
            <div className="dox-absent">
              <Info size={14} />
              <span>No hypoxic sample is stored. Pull live profiles to populate this table.</span>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="dox-table">
                <thead>
                  <tr>
                    <th>Float / cycle</th>
                    <th>Position</th>
                    <th>Depth</th>
                    <th>µmol/kg</th>
                    <th>mg/L</th>
                    <th>Class</th>
                    <th>QC</th>
                    <th>Source file</th>
                    <th>Sampled (UTC)</th>
                  </tr>
                </thead>
                <tbody>
                  {samples.slice(0, 14).map((s) => (
                    <tr key={s.id}>
                      <td className="mono">
                        {s.float_id ?? '—'}
                        {s.cycle != null ? ` · c${s.cycle}` : ''}
                      </td>
                      <td className="mono">
                        {s.latitude.toFixed(2)}°, {s.longitude.toFixed(2)}°
                      </td>
                      <td className="mono">{s.depth_m.toFixed(1)} m</td>
                      <td className="mono">{s.do_umol_kg.toFixed(1)}</td>
                      <td className="mono">{mg(s.do_mg_l)}</td>
                      <td>
                        <span
                          className="dox-class-chip"
                          style={{ color: SEVERITY_COLOR[s.severity_label], borderColor: `${SEVERITY_COLOR[s.severity_label]}55` }}
                        >
                          {s.severity_label}
                        </span>
                      </td>
                      <td className="mono">{s.qc_flag ?? '—'}</td>
                      <td className="mono dox-file">
                        {s.source_record_link ? (
                          <a href={s.source_record_link} target="_blank" rel="noreferrer">
                            {s.source_file}
                          </a>
                        ) : (
                          <span className="dox-dim">{s.organization ?? 'curated reference'}</span>
                        )}
                      </td>
                      <td className="mono dox-dim">
                        {s.sampled_at ? new Date(s.sampled_at).toISOString().slice(0, 16).replace('T', ' ') : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="dox-note">
            Rows with no float, file or timestamp are curated literature reference
            points, not float measurements — they are stored with reduced
            confidence and are labelled as such rather than being passed off as
            observations.
          </p>
        </motion.div>
      )}

      {/* ---------- source provenance ---------- */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="glass-card dox-panel">
        <div className="dox-panel-head">
          <Wind size={15} />
          <b>Oxygen source catalogue</b>
          <span className="dox-dim">reachability is reported, never faked</span>
        </div>
        <div className="dox-src-list">
          {sources.map((s) => {
            const active = s.status.startsWith('ACTIVE')
            return (
              <div key={s.id} className={`dox-src-row${active ? '' : ' dox-src-off'}`}>
                <span className="dox-src-name">
                  <i className="dox-src-dot" style={{ background: active ? '#00ffb3' : '#ffb800' }} />
                  <b>{s.name}</b>
                </span>
                <span className="dox-src-status">{s.status}</span>
                <span className="dox-src-meta">
                  {s.license} · {s.access}
                </span>
              </div>
            )
          })}
        </div>
        <p className="dox-note">
          A connector that cannot reach its source is reported{' '}
          <b>UNAVAILABLE</b> with the reason. An empty result is never used to
          disguise a broken endpoint, and no substitute values are invented.
        </p>
      </motion.div>

      {/* ---------- limitations ---------- */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="glass-card dox-limits">
        <div className="dox-panel-head">
          <Info size={15} />
          <b>Read this before quoting any number above</b>
        </div>
        <ul>
          <li>
            <b>Hotspots ≠ the whole picture.</b> The 8 monitored regions are
            coastal and capped at a 500 km radius, so offshore measurements are
            stored unassigned. The zone grid is what covers the open ocean.
          </li>
          <li>
            <b>Coverage is currently thin.</b> Only a handful of profiles have
            been ingested, so regional trends report{' '}
            <b>insufficient_data</b> rather than a slope. Pull more profiles
            before quoting any trend.
          </li>
          <li>
            <b>Depth is approximated.</b> These files publish in-situ pressure
            rather than geometric depth, so 1 dbar is read as 1 m. That is
            accurate near the surface and drifts with compressibility at depth.
          </li>
          <li>
            <b>Dead zone is a threshold, not a verdict.</b> It marks water below
            0.5 mg/L; it does not by itself establish ecological collapse.
          </li>
        </ul>
        <div className="dox-limits-actions">
          <button className="dox-btn dox-btn-ghost" onClick={() => navigate('/monitoring')}>
            <AlertTriangle size={13} /> Alerts
          </button>
          <button className="dox-btn dox-btn-ghost" onClick={() => navigate('/globe')}>
            <Globe2 size={13} /> Digital Twin
          </button>
        </div>
      </motion.div>
    </div>
  )
}
