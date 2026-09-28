import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import {
  Activity, AlertTriangle, Database, Droplets, GitCompare, Layers, Navigation, Orbit,
  Radar, Route, Satellite, Crosshair,
} from 'lucide-react'
import {
  fetchAnomalies,
  fetchChlorLatest,
  fetchDataSources,
  fetchDeoxygenationOverview,
  fetchErsstLatest,
  fetchGliderDeployments,
  fetchModelGridSummary,
  fetchModelGridVectors,
  fetchRealArgoFloats,
  fetchSituation,
  fetchTwinDisagreement,
  fetchUncertainty,
} from '../api/client'
import ColorScaleBar from '../components/3d/globe/ColorScaleBar'
import { inIndiaBox, domainFrom, TEMP_DEFAULT_DOMAIN, CHL_LEGACY_DOMAIN } from '../components/3d/globe/layerMath'
import type { ScaleMode } from '../components/3d/globe/layerMath'
import type {
  AnomalyPoint, ChlorLayer, DisagreementPoint, ErsstLayer,
  GliderDeployment, RealArgoFloat,
} from '../components/3d/globe/CesiumGlobe'
import './DataLayers.css'

interface AgSit {
  split: {
    normal_regions_pct: number
    watch_regions_pct: number
    high_risk_regions_pct: number
  }
  active_events: number
  observation_coverage_pct: number
  model_trust: number
  summary: string
}

interface HotspotRow {
  region_id: number
  region: string
  depth_layer: string
  latitude: number
  longitude: number
  priority: number
  severity: string
  unit: string
  medium_display: string
  trend: string
  confidence: number
  statistics: {
    n_samples: number
    n_hypoxic: number
    n_dead_zone: number
    min_do_mg_l?: number
    mean_do_mg_l?: number
    max_do_mg_l?: number
  }
}

interface ModelField {
  available: boolean
  variable: string
  unit: string
  source: string
  reason?: string | null
  levels?: { depth_m: number }[]
}

interface SourceRow {
  id: string
  name: string
  kind: string
  status: string
  status_detail?: string
  variables?: string[]
  coverage_pct?: number
  last_update?: string
  note?: string
}

function unwrap<T>(d: unknown): T {
  if (d && typeof d === 'object' && 'data' in d) return (d as { data: T }).data
  return d as T
}

function arrayOrEmpty<T>(value: unknown): T[] {
  return Array.isArray(value) ? value as T[] : []
}

function Card({
  title, icon, count, children,
}: { title: string; icon: ReactNode; count?: string; children: ReactNode }) {
  return (
    <div className="glass-card dl-card">
      <div className="dl-card-header">
        <div className="dl-card-title">
          {icon}
          <h3>{title}</h3>
        </div>
        {count && <span className="dl-count">{count}</span>}
      </div>
      <div className="dl-card-body">{children}</div>
    </div>
  )
}

function Loading({ busy, empty, label }: { busy: boolean; empty: string; label: string }) {
  if (busy) return <div className="dl-hint">Loading {label}…</div>
  return <div className="dl-hint dl-hint-empty">{empty}</div>
}

function Section({
  title, icon, children,
}: { title: string; icon: ReactNode; children: ReactNode }) {
  return (
    <section className="dl-section">
      <div className="dl-section-head">
        {icon}
        <h2>{title}</h2>
        <span className="dl-section-rule" />
      </div>
      <div className="dl-grid">{children}</div>
    </section>
  )
}

function Scroll({ children }: { children: ReactNode }) {
  return <div className="dl-scroll">{children}</div>
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: 'ok' | 'warn' | 'off' }) {
  return (
    <div className={`dl-stat${tone ? ` ${tone}` : ''}`}>
      <span>{label}</span>
      <b>{value}</b>
    </div>
  )
}

const SEV_CLASS: Record<string, string> = {
  high: 'crit', critical: 'crit', moderate: 'warn',
  warning: 'warn', medium: 'warn', low: 'ok', normal: 'ok',
}

export default function DataLayers() {
  const [ersstData, setErsstData] = useState<ErsstLayer | null>(null)
  const [ersstLoading, setErsstLoading] = useState(true)
  const [chlorData, setChlorData] = useState<ChlorLayer | null>(null)
  const [chlorLoading, setChlorLoading] = useState(true)
  const [floats, setFloats] = useState<RealArgoFloat[]>([])
  const [floatsLoading, setFloatsLoading] = useState(true)
  const [gliders, setGliders] = useState<GliderDeployment[]>([])
  const [glidersLoading, setGlidersLoading] = useState(true)
  const [gridFields, setGridFields] = useState<Record<string, ModelField> | null>(null)
  const [gridLoading, setGridLoading] = useState(true)
  const [vectors, setVectors] = useState<{ available: boolean; cells?: unknown[]; reason?: string } | null>(null)
  const [vectorsLoading, setVectorsLoading] = useState(true)
  const [disagreement, setDisagreement] = useState<DisagreementPoint[]>([])
  const [disLoading, setDisLoading] = useState(true)
  const [anomalies, setAnomalies] = useState<AnomalyPoint[]>([])
  const [anLoading, setAnLoading] = useState(true)
  const [uncRegions, setUncRegions] = useState<Record<string, unknown>[]>([])
  const [uncLoading, setUncLoading] = useState(true)
  const [sit, setSit] = useState<AgSit | null>(null)
  const [sitLoading, setSitLoading] = useState(true)
  const [sources, setSources] = useState<SourceRow[]>([])
  const [srcLoading, setSrcLoading] = useState(true)
  const [hotspots, setHotspots] = useState<HotspotRow[]>([])
  const [oxyLoading, setOxyLoading] = useState(true)
  const [sstScale, setSstScale] = useState<ScaleMode>('linear')
  const [chlScale, setChlScale] = useState<ScaleMode>('log')

  const sstDomain = useMemo(
    () => domainFrom(ersstData?.samples?.map((s) => s.sst) ?? []) ?? TEMP_DEFAULT_DOMAIN,
    [ersstData],
  )

  const chlDomain = useMemo(
    () => domainFrom(
      chlorData?.available ? (chlorData.samples ?? []).map((s) => s.chlor_a) : [],
    ) ?? CHL_LEGACY_DOMAIN,
    [chlorData],
  )

  useEffect(() => {
    fetchErsstLatest()
      .then((d: Partial<ErsstLayer>) => {
        const samples = Array.isArray(d?.samples) ? d.samples : []
        setErsstData({
          available: d?.available !== false && Array.isArray(d?.samples),
          error: d?.error,
          time: d?.time ?? 'Unavailable',
          months: d?.months ?? [],
          resolution_deg: d?.resolution_deg ?? 0,
          source: d?.source ?? 'NOAA ERSST v5',
          rows: d?.rows ?? samples.length,
          stats: d?.stats ?? null,
          samples,
        })
      })
      .catch(() => setErsstData(null))
      .finally(() => setErsstLoading(false))

    fetchChlorLatest()
      .then((d: Partial<ChlorLayer>) => {
        const samples = Array.isArray(d?.samples) ? d.samples : []
        setChlorData({
          available: d?.available === true && Array.isArray(d?.samples),
          error: d?.error,
          time: d?.time ?? 'Unavailable',
          months: d?.months ?? [],
          resolution_deg: d?.resolution_deg ?? 0,
          source: d?.source ?? 'NOAA CoastWatch VIIRS',
          rows: d?.rows ?? samples.length,
          stats: d?.stats ?? null,
          samples,
        })
      })
      .catch(() => setChlorData(null))
      .finally(() => setChlorLoading(false))

    fetchRealArgoFloats()
      .then((d) => setFloats(arrayOrEmpty<RealArgoFloat>(d?.floats)))
      .catch(() => setFloats([]))
      .finally(() => setFloatsLoading(false))

    fetchGliderDeployments()
      .then((d) => setGliders(arrayOrEmpty<GliderDeployment>(d?.deployments)))
      .catch(() => setGliders([]))
      .finally(() => setGlidersLoading(false))

    fetchModelGridSummary()
      .then((d) => setGridFields(d.available_fields ?? null))
      .catch(() => setGridFields(null))
      .finally(() => setGridLoading(false))

    fetchModelGridVectors(0)
      .then((d) => setVectors(d))
      .catch(() => setVectors(null))
      .finally(() => setVectorsLoading(false))

    fetchTwinDisagreement('temperature')
      .then((d) => setDisagreement(arrayOrEmpty<DisagreementPoint>(d?.points)))
      .catch(() => setDisagreement([]))
      .finally(() => setDisLoading(false))

    fetchAnomalies({ sort: 'severity' })
      .then((d) => setAnomalies(arrayOrEmpty<AnomalyPoint>(d?.anomalies)))
      .catch(() => setAnomalies([]))
      .finally(() => setAnLoading(false))

    fetchUncertainty()
      .then((d) => setUncRegions(arrayOrEmpty<Record<string, unknown>>(d?.regions)))
      .catch(() => setUncRegions([]))
      .finally(() => setUncLoading(false))

    fetchSituation()
      .then((d) => setSit(unwrap<AgSit>(d)))
      .catch(() => setSit(null))
      .finally(() => setSitLoading(false))

    fetchDataSources()
      .then((d) => setSources(arrayOrEmpty<SourceRow>(d?.sources)))
      .catch(() => setSources([]))
      .finally(() => setSrcLoading(false))

    fetchDeoxygenationOverview()
      .then((d) => setHotspots(arrayOrEmpty<HotspotRow>(d?.hotspots?.hotspots)))
      .catch(() => setHotspots([]))
      .finally(() => setOxyLoading(false))
  }, [])

  const indiaErsst = useMemo(
    () => (ersstData?.available ? (ersstData.samples ?? []).filter((s) => inIndiaBox(s.latitude, s.longitude)).length : 0),
    [ersstData],
  )

  const indiaChl = useMemo(
    () => (chlorData?.available ? (chlorData.samples ?? []).filter((s) => inIndiaBox(s.latitude, s.longitude)).length : 0),
    [chlorData],
  )

  const onlineSources = useMemo(
    () => sources.filter((s) => s.status === 'online').length,
    [sources],
  )

  const gridAvailable = useMemo(
    () => (gridFields ? Object.values(gridFields).filter((f) => f.available).length : 0),
    [gridFields],
  )

  const gridTotal = useMemo(
    () => (gridFields ? Object.keys(gridFields).length : 0),
    [gridFields],
  )

  return (
    <div className="page data-layers-page animate-in">
      <header className="dl-header">
        <div className="dl-header-text">
          <h1>Data Layers Dashboard</h1>
          <p>
            Coverage, provenance and availability for every real data layer in the
            system. This page loads its own payloads, so it is independent of which
            layers happen to be switched on in the Digital Twin globe.
          </p>
        </div>
      </header>

      <div className="dl-summary">
        <Stat label="Sources online" value={`${onlineSources}/${sources.length || '–'}`} tone={onlineSources > 0 ? 'ok' : 'off'} />
        <Stat label="Model fields" value={`${gridAvailable}/${gridTotal || '–'}`} tone={gridAvailable > 0 ? 'ok' : 'off'} />
        <Stat label="SST cells" value={ersstData?.available ? ersstData.rows.toLocaleString() : '–'} />
        <Stat label="Floats + gliders" value={`${floats.length + gliders.length}`} />
        <Stat label="Hotspots" value={`${hotspots.length}`} tone={hotspots.length > 0 ? 'warn' : undefined} />
        <Stat label="Active events" value={sit ? String(sit.active_events) : '–'} />
        <Stat label="Obs coverage" value={sit ? `${sit.observation_coverage_pct}%` : '–'} />
        <Stat label="Ranked anomalies" value={`${anomalies.length}`} tone={anomalies.length > 0 ? 'warn' : undefined} />
      </div>

      <div className="dl-sections">
        <Section title="Observed Grids" icon={<Satellite size={15} />}>
        <Card title="Real SST (NOAA ERSST v5)" icon={<Satellite size={16} />} count={ersstData?.available ? ersstData.time : undefined}>
          {ersstLoading ? (
            <div className="dl-hint">Loading the real ERSST grid…</div>
          ) : !ersstData ? (
            <div className="dl-hint dl-hint-empty">ERSST endpoint unavailable.</div>
          ) : !ersstData.available ? (
            <div className="dl-pending">
              <b>No ERSST grid is available.</b>
              <p>The current database has no ingested NOAA ERSST cells. This layer will appear when a real grid is available.</p>
            </div>
          ) : (
            <>
              <div className="dl-chips">
                <span className="dl-chip"><i />GRID <b>{ersstData.resolution_deg}°</b></span>
                <span className="dl-chip"><i />CELLS <b>{ersstData.rows}</b></span>
                <span className="dl-chip"><i />INDIA-BOX <b>{indiaErsst}</b></span>
              </div>
              {ersstData.stats?.min != null && ersstData.stats.max != null && (
                <div className="dl-range">
                  <span>RANGE <b>{ersstData.stats.min.toFixed(1)}°</b> → <b>{ersstData.stats.max.toFixed(1)}°C</b></span>
                  <span>MONTHS <b>{ersstData.months.length}</b></span>
                </div>
              )}
              <ColorScaleBar
                label="ERSST v5 SST"
                unit="°C"
                domain={sstDomain}
                mode={sstScale}
                onModeChange={setSstScale}
                value={null}
              />
              <p className="dl-note">{ersstData.source}</p>
            </>
          )}
        </Card>

        <Card title="Satellite Chl (VIIRS)" icon={<Orbit size={16} />} count={chlorData?.available ? chlorData.time : undefined}>
          {chlorLoading ? (
            <div className="dl-hint">Loading the real satellite Chl grid…</div>
          ) : !chlorData?.available ? (
            <div className="dl-pending">
              <b>No satellite Chl data on this machine yet.</b>
              <p>The real grid is NOAA CoastWatch Geo-Polar Blended VIIRS-Himawari ocean colour. Fetch and ingest it on a networked host:</p>
              <code>python -m scripts.fetch_chlor</code>
              <code>python -m scripts.ingest_netcdf backend/data/chl_monthly_2021-09.nc --reingest</code>
              <p className="dl-note">Until then no ocean colour is shown — the pipeline never fabricates satellite values.</p>
            </div>
          ) : (
            <>
              <div className="dl-chips">
                <span className="dl-chip"><i />GRID <b>{chlorData.resolution_deg}°</b></span>
                <span className="dl-chip"><i />CELLS <b>{chlorData.rows}</b></span>
                <span className="dl-chip"><i />INDIA-BOX <b>{indiaChl}</b></span>
              </div>
              {chlorData.stats?.min != null && chlorData.stats.max != null && (
                <div className="dl-range">
                  <span>RANGE <b>{chlorData.stats.min.toFixed(3)}</b> → <b>{chlorData.stats.max.toFixed(3)} mg/m³</b></span>
                </div>
              )}
              <ColorScaleBar
                label="Satellite Chl-a"
                unit="mg/m³"
                domain={chlDomain}
                mode={chlScale}
                onModeChange={setChlScale}
                value={null}
                stops={['#1d4ed8', '#16a34a', '#eab308']}
              />
              <p className="dl-note">{chlorData.source}</p>
            </>
          )}
        </Card>
        </Section>

        <Section title="In-Situ Platforms" icon={<Navigation size={15} />}>
        <Card title="Real Argo Floats" icon={<Navigation size={16} />} count={`${floats.length} FLOAT${floats.length === 1 ? '' : 'S'}`}>
          <Loading busy={floatsLoading} empty="No real Argo floats available." label="Argo floats" />
          {!floatsLoading && <Scroll>
            {floats.map((f) => (
            <div className="dl-item" key={f.float_id}>
              <div className="dl-item-top">
                <b>{f.float_id}</b>
                <span className="dl-meta">{f.latest_time?.split('T')[0]}</span>
              </div>
              <div className="dl-item-meta">
                {f.latitude != null && f.longitude != null && (
                  <span>{f.latitude.toFixed(2)}°, {f.longitude.toFixed(2)}°</span>
                )}
                {f.depth_max_m != null && (
                  <span>{f.depth_min_m?.toFixed(0)}–{f.depth_max_m.toFixed(0)} m</span>
                )}
                <span>{f.levels} levels</span>
              </div>
            </div>
          ))}
          </Scroll>}
        </Card>

        <Card title="Glider Fleet" icon={<Route size={16} />} count={`${gliders.length} DEPLOY${gliders.length === 1 ? '' : 'S'}`}>
          <Loading busy={glidersLoading} empty="No glider deployments ingested." label="glider deployments" />
          {!glidersLoading && <Scroll>
            {gliders.map((g) => (
              <div className="dl-item" key={g.deployment_id}>
                <div className="dl-item-top">
                  <b>{g.deployment_id}</b>
                  <span className="dl-meta">{g.samples} samples</span>
                </div>
                <div className="dl-item-meta">
                  {g.time_start && <span>{g.time_start.split('T')[0]}</span>}
                  {g.depth_max_m != null && (
                    <span>{g.depth_min_m?.toFixed(0)}–{g.depth_max_m.toFixed(0)} m</span>
                  )}
                  {g.bgc_samples?.dissolved_oxygen != null && (
                    <span>DO {g.bgc_samples.dissolved_oxygen.toFixed(2)}</span>
                  )}
                </div>
              </div>
            ))}
          </Scroll>}
        </Card>
        </Section>

        <Section title="Model & Forcing" icon={<Layers size={15} />}>
        <Card title="Ocean Model Grid" icon={<Layers size={16} />} count={gridLoading ? undefined : `${gridAvailable}/${gridTotal || 0}`}>
          <Loading busy={gridLoading} empty="Model-grid summary unavailable." label="model grid" />
          {!gridLoading && gridFields && Object.keys(gridFields).length === 0 && (
            <div className="dl-hint dl-hint-empty">No model-grid fields reported.</div>
          )}
          {!gridLoading && gridFields && <Scroll>
            {Object.entries(gridFields).map(([key, f]) => (
            <div className="dl-row" key={key}>
              <div className="dl-row-main">
                <b>{f.variable}</b>
                <span className={`dl-badge ${f.available ? 'ok' : 'off'}`}>
                  {f.available ? 'available' : 'no data'}
                </span>
              </div>
              <div className="dl-item-meta">
                <span>{f.unit}</span>
                {f.levels && <span>{f.levels.length} depth levels</span>}
              </div>
              {!f.available && f.reason && <p className="dl-reason">{f.reason}</p>}
            </div>
          ))}
          </Scroll>}
        </Card>

        <Card title="Current Velocity Vectors" icon={<Droplets size={16} />} count={vectors?.available ? `${vectors.cells?.length ?? 0} CELLS` : undefined}>
          <Loading busy={vectorsLoading} empty="Current vectors unavailable." label="current vectors" />
          {!vectorsLoading && vectors?.available && (
            <div className="dl-hint">Surface velocity vectors are ready to draw on the globe.</div>
          )}
          {!vectorsLoading && !vectors?.available && vectors?.reason && (
            <p className="dl-reason">{vectors.reason}</p>
          )}
        </Card>
        </Section>

        <Section title="Validation & Intelligence" icon={<GitCompare size={15} />}>
        <Card title="Model vs Reality" icon={<GitCompare size={16} />} count={`${disagreement.length} REGIONS`}>
          <Loading busy={disLoading} empty="No disagreement data." label="disagreement" />
          {!disLoading && <Scroll>
            {disagreement.map((d, i) => (
            <div className="dl-item" key={`${d.location_id}-${i}`}>
              <div className="dl-item-top">
                <b>{d.location}</b>
                <span className={`sev ${SEV_CLASS[d.severity?.toLowerCase()] ?? ''}`}>{d.severity}</span>
              </div>
              <div className="dl-item-meta">
                <span>{d.variable}</span>
                {d.model != null && d.observed != null && (
                  <span>{d.model.toFixed(2)} vs {d.observed.toFixed(2)}</span>
                )}
                {d.percent_difference != null && <span>{d.percent_difference.toFixed(1)}%</span>}
              </div>
            </div>
          ))}
          </Scroll>}
        </Card>

        <Card title="Anomaly Intelligence" icon={<Radar size={16} />} count={`${anomalies.length} RANKED`}>
          <Loading busy={anLoading} empty="No ranked anomalies." label="anomalies" />
          {!anLoading && <Scroll>
            {anomalies.map((a, i) => (
            <div className="dl-item" key={`${a.location_id}-${a.variable}-${i}`}>
              <div className="dl-item-top">
                <b>{a.location}</b>
                <span className={`sev ${SEV_CLASS[a.severity?.toLowerCase()] ?? ''}`}>{a.severity}</span>
              </div>
              <div className="dl-item-meta">
                <span>{a.label}</span>
                {a.model != null && a.observed != null && (
                  <span>{a.model.toFixed(2)} → {a.observed.toFixed(2)} {a.unit}</span>
                )}
                <span>conf {a.confidence}</span>
              </div>
            </div>
          ))}
          </Scroll>}
        </Card>

        <Card title="Hypoxic Zones" icon={<AlertTriangle size={16} />} count={`${hotspots.length} HOTSPOTS`}>
          <Loading busy={oxyLoading} empty="No hypoxic hotspots detected." label="oxygen hotspots" />
          {!oxyLoading && <Scroll>
            {hotspots.map((h, i) => (
            <div className="dl-item" key={`${h.region_id}-${h.depth_layer}-${i}`}>
              <div className="dl-item-top">
                <b>{h.region}</b>
                {h.severity && (
                  <span className={`sev ${SEV_CLASS[h.severity.toLowerCase()] ?? ''}`}>{h.severity}</span>
                )}
              </div>
              <div className="dl-item-meta">
                {h.statistics.mean_do_mg_l != null && (
                  <span>mean DO {h.statistics.mean_do_mg_l.toFixed(2)} {h.unit}</span>
                )}
                {h.statistics.min_do_mg_l != null && (
                  <span>min {h.statistics.min_do_mg_l.toFixed(2)}</span>
                )}
                {h.statistics.n_hypoxic > 0 && <span>{h.statistics.n_hypoxic} hypoxic</span>}
                <span>{h.latitude.toFixed(1)}°, {h.longitude.toFixed(1)}°</span>
                <span>priority {h.priority}</span>
                <span>conf {h.confidence}</span>
              </div>
              <div className="dl-item-meta">
                <span>{h.medium_display}</span>
                <span>trend: {h.trend.replace(/_/g, ' ')}</span>
              </div>
            </div>
          ))}
          </Scroll>}
        </Card>
        </Section>

        <Section title="Coverage & Provenance" icon={<Database size={15} />}>
        <Card title="Uncertainty & Coverage" icon={<Crosshair size={16} />} count={`${uncRegions.length} REGIONS`}>
          <Loading busy={uncLoading} empty="No uncertainty data." label="uncertainty" />
          {!uncLoading && <Scroll>
            {uncRegions.map((r, i) => {
              const row = r as Record<string, string | number | undefined>
              return (
                <div className="dl-row" key={i}>
                  <div className="dl-row-main">
                    <b>{String(row.location ?? `Region ${i + 1}`)}</b>
                  </div>
                  <div className="dl-item-meta">
                    {row.uncertainty != null && <span>gap {String(row.uncertainty)}%</span>}
                    {row.coverage_pct != null && <span>cov {String(row.coverage_pct)}%</span>}
                  </div>
                </div>
              )
            })}
          </Scroll>}
        </Card>

        <Card title="Data Provenance" icon={<Database size={16} />} count={`${onlineSources}/${sources.length} ONLINE`}>
          <Loading busy={srcLoading} empty="No data sources reported." label="sources" />
          {!srcLoading && <Scroll>
            {sources.map((s) => (
              <div className="dl-item" key={s.id}>
                <div className="dl-item-top">
                  <b>{s.name}</b>
                  <span className={`dl-badge ${s.status === 'online' ? 'ok' : 'off'}`}>{s.status}</span>
                </div>
                <div className="dl-item-meta">
                  {s.kind && <span>{s.kind}</span>}
                  {s.coverage_pct != null && <span>cov {s.coverage_pct}%</span>}
                  {s.last_update && <span>{s.last_update.split('T')[0]}</span>}
                </div>
                {s.status !== 'online' && s.note && <p className="dl-reason">{s.note}</p>}
              </div>
            ))}
          </Scroll>}
        </Card>

        <Card title="Situation Overview" icon={<Activity size={16} />} count={sit ? `${sit.active_events} ACTIVE` : undefined}>
          <Loading busy={sitLoading} empty="Situation unavailable." label="situation" />
          {!sitLoading && sit && (
            <>
              <div className="dl-kpis">
                <div className="dl-kpi"><span>Active events</span><b>{sit.active_events}</b></div>
                <div className="dl-kpi"><span>Obs coverage</span><b>{sit.observation_coverage_pct}%</b></div>
                <div className="dl-kpi"><span>Model trust</span><b>{sit.model_trust}%</b></div>
                <div className="dl-kpi"><span>High risk</span><b>{sit.split.high_risk_regions_pct}%</b></div>
                <div className="dl-kpi"><span>Watch</span><b>{sit.split.watch_regions_pct}%</b></div>
                <div className="dl-kpi"><span>Normal</span><b>{sit.split.normal_regions_pct}%</b></div>
              </div>
              <p className="dl-note">{sit.summary}</p>
            </>
          )}
        </Card>
        </Section>
      </div>
    </div>
  )
}
