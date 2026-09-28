import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import {
  Droplets, AlertTriangle, Download, ArrowUpRight, Database, Clock,
  Gauge, TrendingUp, Layers, Info, Ship,
} from 'lucide-react'
import {
  fetchMicroplasticsOverview,
  fetchMicroplasticTimeline,
  fetchAlerts,
  ingestMicroplastics,
  refreshMicroplasticAlerts,
} from '../api/client'
import { DataSourceBadge, StatusIndicator } from '../components/ocean/OceanUI'
import './MicroplasticsDashboard.css'

/**
 * Microplastics Dashboard
 * =======================
 * The scannable summary screen. The workspace page at /microplastics is where
 * you interrogate a single region; this is where you decide which region
 * deserves attention at all.
 *
 * The same two presentation rules apply as on the workspace page, because a
 * dashboard is exactly where it is easiest to break them:
 *
 *  1. NO BLENDED CONCENTRATION.  Sample *counts* are summed here (counting
 *     samples is safe - it is an inventory, not a measurement), but no mean,
 *     peak or severity is ever aggregated across media. Those stay per medium
 *     with their own unit attached. A single "plastics risk" tile would be the
 *     easiest thing to draw and the most dishonest.
 *
 *  2. GAPS AND STALE DATA LOOK LIKE GAPS AND STALE DATA.  The archival-vintage
 *     banner is not hidden just because this is a summary screen, and regions
 *     with no published sample are named as gaps rather than shown as zero.
 */

const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { duration: 0.45, ease: 'easeOut' as const } },
}

/** 4 significant digits: source values span 0.0005 to 30000. */
function fmt(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  if (value === 0) return '0'
  if (Math.abs(value) >= 10000) return value.toExponential(2)
  const text = value.toPrecision(4)
  return text.includes('.') ? text.replace(/0+$/, '').replace(/\.$/, '') : text
}

/**
 * Render the `**bold**` spans the backend's summary text uses.
 * Assistant.tsx has a fuller markdown-ish renderer, but it is file-local and
 * styles through Assistant.css, so reusing it here would couple this page to
 * another page's stylesheet. This is the bold-only subset actually needed.
 */
function withBold(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**')
      ? <strong key={i}>{part.slice(2, -2)}</strong>
      : <span key={i}>{part}</span>,
  )
}

const SEVERITY_COLOR: Record<string, string> = {
  critical: '#ff3366',
  high: '#f43f5e',
  medium: '#f59e0b',
  low: '#10b981',
  info: '#38bdf8',
  unknown: '#64748b',
}

/** Distinct colour per medium so a stacked count never implies one series. */
const MEDIUM_COLOR: Record<string, string> = {
  water: '#00d4ff',
  sediment: '#ffb800',
  beach: '#00ffb3',
  beach_nurdle: '#8b8cf8',
  unknown: '#3f6784',
}

const MEDIUM_LABEL: Record<string, string> = {
  water: 'Water column',
  sediment: 'Sediment',
  beach: 'Beach',
  beach_nurdle: 'Nurdle patrol',
  unknown: 'Unknown',
}

interface Hotspot {
  hotspot_id: string
  region_id: number
  region: string
  medium: string
  medium_display: string
  unit: string
  is_hotspot: boolean
  severity: string
  published_class: string | null
  latest_published_class: string | null
  action: string
  priority: number
  statistics: { n_samples: number; median: number | null; max: number | null }
  latest_sample_at: string | null
  confidence: number
  basis: string[]
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
      is_live_feed: boolean
    }
  }
  hotspots: {
    hotspot_count: number
    groups_evaluated: number
    weights: Record<string, number>
    hotspots: Hotspot[]
    recommendations: { summary: string; action_count: number }
  }
  surfaces: Record<string, { has_data: boolean; gap_cells?: number; nodes: unknown[]; coverage_ratio?: number; unit?: string | null }>
}

interface TimelineBucket {
  year: number
  region: string
  medium: string
  unit: string
  n_samples: number
  max: number | null
  worst_ordinal: number | null
}

interface MpAlert {
  id: number
  alert_type: string
  severity: string
  location_name: string
  status: string
  description?: string
  created_at: string
}

export default function MicroplasticsDashboard() {
  const navigate = useNavigate()
  const [data, setData] = useState<Overview | null>(null)
  const [buckets, setBuckets] = useState<TimelineBucket[]>([])
  const [alerts, setAlerts] = useState<MpAlert[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    Promise.all([
      fetchMicroplasticsOverview(),
      fetchMicroplasticTimeline().catch(() => ({ buckets: [] })),
      fetchAlerts('active').catch(() => []),
    ])
      .then(([ov, tl, al]) => {
        setData(ov)
        setBuckets(tl?.buckets ?? [])
        const rows: MpAlert[] = Array.isArray(al) ? al : (al?.alerts ?? [])
        // The monitoring schema does not expose `source`, but microplastic
        // alerts are namespaced by alert_type, so that is the filter key.
        setAlerts(rows.filter((a) => String(a.alert_type).startsWith('microplastic_hotspot')))
        setError(null)
      })
      .catch((e) => setError(e?.message ?? 'Could not reach the microplastics service.'))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const handleIngest = async () => {
    setBusy(true)
    try {
      const summary = await ingestMicroplastics()
      const kept = summary?.normalisation?.records_accepted ?? 0
      setNotice(kept ? `Ingested ${kept} published sample(s).` : 'No samples retrieved — see the connector reason in the workspace.')
      load()
    } catch {
      setNotice('Ingestion request failed.')
    } finally {
      setBusy(false)
    }
  }

  const handleAlerts = async () => {
    setBusy(true)
    try {
      const r = await refreshMicroplasticAlerts()
      setNotice(`${r.created} new alert(s), ${r.refreshed} refreshed.`)
      load()
    } catch {
      setNotice('Could not raise alerts.')
    } finally {
      setBusy(false)
    }
  }

  const ranking = useMemo(
    () => (data?.hotspots?.hotspots ?? []).slice().sort((a, b) => b.priority - a.priority),
    [data],
  )

  /** Samples per year, split by medium. Counts are additive; values are not. */
  const byYear = useMemo(() => {
    const map = new Map<number, { total: number; media: Record<string, number> }>()
    for (const b of buckets) {
      const entry = map.get(b.year) ?? { total: 0, media: {} }
      entry.total += b.n_samples
      entry.media[b.medium] = (entry.media[b.medium] ?? 0) + b.n_samples
      map.set(b.year, entry)
    }
    return [...map.entries()].sort((a, b) => a[0] - b[0])
  }, [buckets])

  const yearMax = Math.max(1, ...byYear.map(([, v]) => v.total))

  if (loading) {
    return <div className="page mpd-page animate-in"><div className="hint">Loading dashboard…</div></div>
  }

  if (error) {
    return (
      <div className="page mpd-page animate-in">
        <div className="glass-card mpd-empty">
          <AlertTriangle size={18} />
          <div>
            <b>Microplastics service unavailable</b>
            <p>{error}</p>
            <p className="mpd-dim">
              This dashboard has no illustrative fallback. When the service is
              unreachable, the honest state is an empty one.
            </p>
          </div>
        </div>
      </div>
    )
  }

  const coverage = data?.coverage
  const hasData = coverage?.has_data
  const vintage = coverage?.data_vintage
  const worst = ranking[0]
  const gaps = (data?.surfaces?.['water_column']?.gap_cells ?? 0)

  return (
    <div className="page mpd-page animate-in">
      {/* ---------- header ---------- */}
      <div className="page-header">
        <div>
          <h1 className="page-title title-glow">
            Microplastics <span className="text-gradient">Dashboard</span>
          </h1>
          <p className="page-subtitle">
            Situation summary for open-source microplastic observations across
            the monitored coastal regions.
          </p>
        </div>
        <div className="mpd-head-actions">
          <DataSourceBadge label="NOAA NCEI + curated literature · open" />
          <button className="mpd-btn" onClick={() => navigate('/microplastics')}>
            Open workspace <ArrowUpRight size={14} />
          </button>
        </div>
      </div>

      {notice && <div className="glass-card mpd-notice" role="status">{notice}</div>}

      {/* ---------- vintage: kept on the summary screen on purpose ---------- */}
      {hasData && (
        <motion.div variants={fadeUp} initial="hidden" animate="show" className="glass-card mpd-vintage">
          <Clock size={15} />
          <div>
            <b>Archival record — not a live feed</b>
            <span>
              Samples span <b>{vintage?.oldest?.slice(0, 10)}</b> → <b>{vintage?.latest?.slice(0, 10)}</b>
              {vintage?.span_years ? ` (${vintage.span_years} years)` : ''}. Priority means
              "most recent evidence available", never "measured this week".
            </span>
          </div>
        </motion.div>
      )}

      {/* ---------- KPI strip ---------- */}
      {hasData ? (
        <div className="mpd-kpis">
          <div className="glass-card mpd-kpi">
            <span className="mpd-kpi-label">Real samples</span>
            <b className="mpd-kpi-value">{coverage?.total_samples ?? 0}</b>
            <em>published observations, all REAL origin</em>
          </div>
          <div className="glass-card mpd-kpi">
            <span className="mpd-kpi-label">Hotspots</span>
            <b className="mpd-kpi-value mpd-warn">{data?.hotspots?.hotspot_count ?? 0}</b>
            <em>of {data?.hotspots?.groups_evaluated ?? 0} region/medium groups</em>
          </div>
          <div className="glass-card mpd-kpi">
            <span className="mpd-kpi-label">Regions covered</span>
            <b className="mpd-kpi-value">
              {coverage?.regions_with_data ?? 0}<i>/{coverage?.regions_total ?? 0}</i>
            </b>
            <em>{(coverage?.regions_without_data ?? []).length} named as gaps</em>
          </div>
          <div className="glass-card mpd-kpi">
            <span className="mpd-kpi-label">Active alerts</span>
            <b className="mpd-kpi-value mpd-crit">{alerts.length}</b>
            <em>raised into Monitoring &amp; Alerts</em>
          </div>
          <div className="glass-card mpd-kpi">
            <span className="mpd-kpi-label">Unmapped</span>
            <b className="mpd-kpi-value">{coverage?.unassigned_samples ?? 0}</b>
            <em>beyond the mapping radius, not snapped</em>
          </div>
          <div className="glass-card mpd-kpi">
            <span className="mpd-kpi-label">Surface gaps</span>
            <b className="mpd-kpi-value mpd-warn">{gaps}</b>
            <em>water-column cells with no sample in range</em>
          </div>
        </div>
      ) : (
        <div className="glass-card mpd-empty">
          <Database size={18} />
          <div>
            <b>No microplastic samples stored yet</b>
            <p>{coverage?.honesty_note ?? data?.reason}</p>
            <button className="mpd-btn" onClick={handleIngest} disabled={busy}>
              <Download size={14} /> Ingest the source collections
            </button>
          </div>
        </div>
      )}

      {/* ---------- top recommendation ---------- */}
      {hasData && worst && (
        <motion.div variants={fadeUp} initial="hidden" animate="show" className="glass-card mpd-headline">
          <div className="mpd-headline-top">
            <StatusIndicator tone={worst.severity === 'critical' ? 'crit' : 'warn'}>
              {worst.severity.toUpperCase()}
            </StatusIndicator>
            <h2>{worst.region}</h2>
            <span className="mpd-medium-chip">{worst.medium_display}</span>
            <span className="mpd-priority">{worst.priority.toFixed(0)}<em>/100</em></span>
          </div>
          <p className="mpd-headline-action">
            {withBold(data?.hotspots?.recommendations?.summary ?? '')}
          </p>
          <div className="mpd-headline-actions">
            <button className="mpd-btn" onClick={() => navigate('/microplastics')}>
              Investigate <ArrowUpRight size={13} />
            </button>
            <button className="mpd-btn mpd-btn-ghost" onClick={handleAlerts} disabled={busy}>
              <AlertTriangle size={13} /> Raise alerts
            </button>
            <button className="mpd-btn mpd-btn-ghost" onClick={handleIngest} disabled={busy}>
              <Download size={13} /> Ingest latest
            </button>
          </div>
        </motion.div>
      )}

      {/* ---------- two columns: ranking + coverage ---------- */}
      {hasData && (
        <div className="mpd-cols">
          <motion.div variants={fadeUp} initial="hidden" animate="show" className="glass-card mpd-panel">
            <div className="mpd-panel-head">
              <Gauge size={15} />
              <b>Hotspot ranking</b>
              <span className="mpd-dim">
                severity 55% · evidence 10% · recency 15% · trust 20%
              </span>
            </div>

            {ranking.length === 0 ? (
              <div className="hint">No region/medium group reaches the source's “Medium” class.</div>
            ) : (
              <div className="mpd-rank-list">
                {ranking.map((h, i) => (
                  <button
                    key={h.hotspot_id}
                    className={`mpd-rank-row${h.is_hotspot ? '' : ' mpd-rank-row--below'}`}
                    onClick={() => navigate('/microplastics')}
                  >
                    <span className="mpd-rank-pos">{i + 1}</span>
                    <span className="mpd-sev-dot" style={{ background: SEVERITY_COLOR[h.severity] }} />
                    <span className="mpd-rank-region">
                      <b>{h.region}</b>
                      <em>{h.medium_display}</em>
                    </span>
                    <span className="mpd-rank-class">
                      <b>{h.published_class ?? '—'}</b>
                      <em>{h.unit}</em>
                    </span>
                    <span className="mpd-rank-value">
                      <b>{fmt(h.statistics.max)}</b>
                      <em>peak</em>
                    </span>
                    <span className="mpd-rank-bar">
                      <i style={{ width: `${h.priority}%`, background: SEVERITY_COLOR[h.severity] }} />
                    </span>
                    <span className="mpd-rank-prio">{h.priority.toFixed(0)}</span>
                  </button>
                ))}
              </div>
            )}

            <p className="mpd-note">
              Each row is one region <em>and</em> one medium. Rows are never
              combined, because their units are not comparable.
            </p>
          </motion.div>

          <motion.div variants={fadeUp} initial="hidden" animate="show" className="glass-card mpd-panel">
            <div className="mpd-panel-head">
              <Layers size={15} />
              <b>Samples by medium</b>
              <span className="mpd-dim">inventory counts</span>
            </div>

            <div className="mpd-medium-list">
              {Object.entries(coverage?.by_medium ?? {}).map(([medium, count]) => {
                const pct = ((count as number) / Math.max(1, coverage?.total_samples ?? 1)) * 100
                return (
                  <div key={medium} className="mpd-medium-row">
                    <span className="mpd-medium-name">
                      <i className="mpd-medium-swatch" style={{ background: MEDIUM_COLOR[medium] ?? '#3f6784' }} />
                      {MEDIUM_LABEL[medium] ?? medium}
                    </span>
                    <span className="mpd-medium-track">
                      <i style={{ width: `${pct}%`, background: MEDIUM_COLOR[medium] ?? '#3f6784' }} />
                    </span>
                    <b>{count as number}</b>
                  </div>
                )
              })}
            </div>

            <div className="mpd-gaps">
              <h4><AlertTriangle size={12} /> Regions with no published sample</h4>
              {(coverage?.regions_without_data ?? []).length === 0 ? (
                <p className="mpd-dim">Every monitored region has at least one sample.</p>
              ) : (
                <ul>
                  {(coverage?.regions_without_data ?? []).map((r) => <li key={r}>{r}</li>)}
                </ul>
              )}
              <p className="mpd-note">
                These are gaps, not zeros. No value is estimated for them.
              </p>
            </div>
          </motion.div>
        </div>
      )}

      {/* ---------- survey-year histogram ---------- */}
      {byYear.length > 0 && (
        <motion.div variants={fadeUp} initial="hidden" animate="show" className="glass-card mpd-panel">
          <div className="mpd-panel-head">
            <TrendingUp size={15} />
            <b>Published samples per survey year</b>
            <span className="mpd-dim">
              counts are additive; concentrations are not
            </span>
          </div>

          <div className="mpd-bars">
            {byYear.map(([year, entry]) => (
              <div key={year} className="mpd-bar-col" title={
                Object.entries(entry.media)
                  .map(([m, n]) => `${MEDIUM_LABEL[m] ?? m}: ${n}`)
                  .join(' · ')
              }>
                <span className="mpd-bar-value">{entry.total}</span>
                <span className="mpd-bar-stack" style={{ height: `${(entry.total / yearMax) * 100}%` }}>
                  {Object.entries(entry.media).map(([m, n]) => (
                    <i
                      key={m}
                      style={{
                        flexGrow: n,
                        background: MEDIUM_COLOR[m] ?? '#3f6784',
                      }}
                    />
                  ))}
                </span>
                <span className="mpd-bar-year">{year}</span>
              </div>
            ))}
          </div>
          <p className="mpd-note">
            Only {byYear.length} survey year(s) have any published sample. Absence of a
            bar is absence of data, not absence of plastic.
          </p>
        </motion.div>
      )}

      {/* ---------- alerts ---------- */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="glass-card mpd-panel">
        <div className="mpd-panel-head">
          <AlertTriangle size={15} />
          <b>Microplastic alerts</b>
          <span className="mpd-dim">source = microplastics</span>
          <button className="mpd-btn mpd-btn-xs" onClick={() => navigate('/monitoring')}>
            Monitoring <ArrowUpRight size={12} />
          </button>
        </div>

        {alerts.length === 0 ? (
          <div className="mpd-absent">
            <Info size={14} />
            <span>
              No microplastic alerts are active. Raise alerts to publish eligible
              hotspots into the platform alert store.
            </span>
          </div>
        ) : (
          <div className="mpd-alert-list">
            {alerts.map((a) => (
              <div key={a.id} className="mpd-alert">
                <span className="mpd-sev-dot" style={{ background: SEVERITY_COLOR[a.severity] }} />
                <b>{a.location_name}</b>
                <span className="mpd-medium-chip">
                  {a.alert_type.replace('microplastic_hotspot_', '').replace(/_/g, ' ')}
                </span>
                <span className="mpd-alert-sev" style={{ color: SEVERITY_COLOR[a.severity] }}>
                  {a.severity.toUpperCase()}
                </span>
              </div>
            ))}
          </div>
        )}
      </motion.div>

      {/* ---------- limitation strip ---------- */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="glass-card mpd-limits">
        <div className="mpd-panel-head">
          <Info size={15} />
          <b>Read this before quoting any number above</b>
        </div>
        <ul>
          <li>
            Concentrations are never pooled across media. <b>pieces/m3</b>,{' '}
            <b>pieces/kg dw</b> and <b>pieces/10 min</b> measure different things
            under different sampling effort.
          </li>
          <li>
            The NOAA NCEI collection is an archive, not a live feed. Nothing here
            describes present-day conditions.
          </li>
          <li>
            Interpolated surface cells are estimates; cells with no sample in range are
            reported as gaps and never filled with zero.
          </li>
          <li>
            Drift is refused when no real current forcing exists, and downgraded when
            the forcing fails a credibility check.
          </li>
        </ul>
        <div className="mpd-limits-actions">
          <button className="mpd-btn mpd-btn-ghost" onClick={() => navigate('/microplastics')}>
            <Droplets size={13} /> Full workspace
          </button>
          <button className="mpd-btn mpd-btn-ghost" onClick={() => navigate('/globe')}>
            <Ship size={13} /> Digital Twin
          </button>
        </div>
      </motion.div>
    </div>
  )
}
