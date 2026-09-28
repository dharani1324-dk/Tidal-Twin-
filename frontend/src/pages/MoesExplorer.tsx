import { useEffect, useMemo, useState } from 'react'
import { ArrowUpRight, Database, ExternalLink, RefreshCw, Search, Waves } from 'lucide-react'
import { useNavigate, useParams } from 'react-router-dom'
import { fetchMoesArgoGrid, fetchMoesBiodiversity, fetchMoesBuoys, fetchMoesDatasetMetadata, fetchMoesDatasets, fetchMoesFeature, fetchMoesHydrodynamicForecast, fetchMoesRegistry, fetchMoesWaveForecast } from '../api/client'
import './MoesExplorer.css'

const FEATURES = [
  { id: 'temperature', label: 'Ocean Temperature', icon: '🌡️', page: '/globe', query: 'temperature', note: 'Sea surface and in-situ profile data; source timestamps shown per product.' },
  { id: 'waves', label: 'Wave Intelligence', icon: '🌊', page: '/monitoring', query: 'wave', note: 'Wave products and forecasts where the source catalog exposes them.' },
  { id: 'currents', label: 'Ocean Currents', icon: '↗', page: '/data-layers', query: 'current', note: 'Current products from the live catalog and existing current layers.' },
  { id: 'salinity', label: 'Salinity', icon: '💧', page: '/globe', query: 'salinity', note: 'Argo salinity profiles and catalogued gridded products.' },
  { id: 'sea-level', label: 'Sea Level', icon: '〰', page: '/coastal', query: 'sea level', note: 'Sea-level related products, when publicly catalogued.' },
  { id: 'wind', label: 'Wind & Atmospheric Forcing', icon: '💨', page: '/monitoring', query: 'wind', note: 'Ocean wind and atmospheric forcing products.' },
  { id: 'chlorophyll', label: 'Chlorophyll', icon: '🟢', page: '/oceanvision', query: 'chlorophyll', note: 'Ocean-colour products; satellite analysis freshness varies by dataset.' },
  { id: 'biodiversity', label: 'Marine Biodiversity', icon: '🐠', page: '/microplastics', query: 'biodiversity', note: 'Marine ecosystem records when present; biodiversity endpoints are not assumed.' },
  { id: 'profiles', label: 'Ocean Depth Profiles', icon: '↕', page: '/globe', query: 'argo', note: 'Argo temperature and salinity profiles; observation time and depth are retained.' },
  { id: 'forecast', label: 'Ocean Forecast', icon: '⏱', page: '/monitoring', query: 'forecast', note: 'Forecast products are model output and are kept distinct from measurements.' },
  { id: 'coastal-change', label: 'Coastal Change', icon: '🏝', page: '/coastal', query: 'coast', note: 'Coastal products and monitoring workspace.' },
  { id: 'events', label: 'Ocean Events', icon: '⚡', page: '/anomalies', query: '', note: 'Events are detected from connected observation and model data.' },
  { id: 'model-observation', label: 'Model vs Observation', icon: '⇄', page: '/validate', query: '', note: 'Compares data with provenance; no model product is labelled as a sensor reading.' },
  { id: 'disagreement', label: 'Data Disagreement', icon: '⚖', page: '/forensics', query: '', note: 'Inspect mismatch, coverage, and evidence limitations.' },
  { id: 'confidence', label: 'Confidence Engine', icon: '◉', page: '/intelligence', query: '', note: 'Confidence follows available evidence, spatial coverage, and freshness.' },
  { id: 'fusion', label: 'Multi-Source Fusion', icon: '✣', page: '/data-layers', query: '', note: 'Explore connected data layers without blending away source identity.' },
  { id: 'ocean-health', label: 'Ocean Health', icon: '♡', page: '/classic', query: '', note: 'Health indicators remain tied to their source data and caveats.' },
  { id: 'data-explorer', label: 'MoES Data Explorer', icon: '▦', page: '/moes', query: '', note: 'Search the live INCOIS ERDDAP metadata catalog.' },
  { id: 'polar', label: 'Polar Ocean', icon: '❄', page: '/moes', query: 'polar', note: 'Search the catalog; polar coverage is shown only when a matching dataset is listed.' },
  { id: 'provenance', label: 'Data Provenance', icon: 'ⓘ', page: '/data-layers', query: '', note: 'Inspect provider, product, timestamps, and source links.' },
]

type Source = { id: string; name: string; url: string; official_url?: string; status: string; live: boolean; protocol?: string; dataset?: string | null; category?: string; variable?: string | null; units?: string | null; temporal_resolution?: string | null; coverage?: string | null; spatial_resolution?: string | null; last_updated?: string | null; checked_at?: string | null; endpoint?: string | null; attribution?: string | null; license?: string | null; cached?: boolean; error?: string | null }
type Dataset = { id: string; name: string; institution: string; protocol: string; temporal_start?: string | null; temporal_end?: string | null; observation_age_days?: number | null; temporal_resolution_seconds?: number | null; description: string; url: string; status?: string; spatial_resolution?: { latitude_deg?: number | null; longitude_deg?: number | null }; coverage?: { south?: number | null; north?: number | null; west?: number | null; east?: number | null } }
type DatasetMetadata = { available: boolean; variables?: { name: string; attributes: Record<string, string> }[]; license?: string; error?: string }
type FeatureEvidence = { available: boolean; feature_id: string; feature: string; status: string; data_status: string; live_endpoint: boolean; live_measurements: boolean; forecast_available?: boolean; forecast_freshness?: string; forecast_age_hours?: number; forecast_file?: string; forecast_run?: string; forecast_source_url?: string; checked_at?: string; sources: string[]; dataset_count: number; datasets: Dataset[]; notes: string[] }

function DatasetDisclosure({ id }: { id: string }) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [metadata, setMetadata] = useState<DatasetMetadata | null>(null)
  const load = async () => {
    if (open) { setOpen(false); return }
    setOpen(true)
    if (metadata) return
    setLoading(true)
    try { setMetadata(await fetchMoesDatasetMetadata(id)) }
    catch (e) { setMetadata({ available: false, error: e instanceof Error ? e.message : 'Metadata unavailable.' }) }
    finally { setLoading(false) }
  }
  return <div className="moes-variable-disclosure"><button onClick={() => void load()}>{loading ? 'Loading metadata…' : open ? 'Hide metadata' : 'Show variables, units & license'}</button>{open && <div className="moes-variable-metadata">{loading ? 'Fetching official dataset metadata…' : metadata?.available ? <>{metadata.variables?.map((v) => <span key={v.name}><b>{v.name}</b> {v.attributes.long_name ?? ''} · {v.attributes.units ?? 'units not listed'}</span>)}<p>License: {metadata.license ?? 'Not provided in metadata.'}</p></> : metadata?.error}</div>}</div>
}
type ArgoGrid = { available: boolean; status: string; freshness?: string; age_days?: number; source?: string; dataset?: string; variable?: string; unit?: string; time?: string; depth_m?: number; coverage?: { south: number; north: number; west: number; east: number }; resolution_deg?: number; cells?: { latitude: number; longitude: number; value: number }[]; records?: { latitude: number; longitude: number; value: number | string | null }[]; record_count?: number; cell_count?: number; source_url?: string; error?: string }
type Occurrences = { available: boolean; status: string; provider?: string; total_node_records?: number; returned?: number; record_count?: number; records?: { record_id?: string; value?: string | null; observed_at?: string | null; latitude: number; longitude: number; depth_m?: number | null; attributes?: { basis_of_record?: string | null }; source_url?: string }[]; source_url?: string; error?: string }
type BuoyDirectory = { available: boolean; status: string; checked_at?: string; station_count?: number; stations?: { station_id?: string; buoy_id?: string; type?: string; status?: string; latitude: number; longitude: number; deployed_at?: string; retrieved_at?: string; data_period?: string; record_available?: boolean }[]; data_status_note?: string; source_url?: string; error?: string }
type ForecastRecord = { variable: string; value: number; units?: string; observed_at?: string; latitude?: number; longitude?: number; attributes?: Record<string, string | null> }
type PointForecast = { available: boolean; status: string; freshness?: string; age_hours?: number; provider?: string; dataset?: string; model_run?: string; valid_at?: string; variable?: string; forecast_times?: string[]; forecast_window_hours?: number; record_count?: number; records?: ForecastRecord[]; requested_position?: { latitude: number; longitude: number }; source_url?: string; error?: string }

export function MoesFeatureGrid() {
  const navigate = useNavigate()
  return <section className="moes-feature-section">
    <div className="moes-section-heading"><div><span className="moes-eyebrow">MINISTRY OF EARTH SCIENCES · SOURCE-AWARE WORKSPACES</span><h2>MoES Ocean Intelligence</h2><p>Open a focused workspace. Live status is checked against the connected source catalog.</p></div><button className="moes-open-explorer" onClick={() => navigate('/moes')}><Database size={15}/> Data Explorer <ArrowUpRight size={14}/></button></div>
    <div className="moes-feature-grid">{FEATURES.map((f) => <button className="moes-feature-card" key={f.id} onClick={() => navigate(`/moes/${f.id}`)}><span className="moes-feature-icon" aria-hidden="true">{f.icon}</span><span className="moes-feature-label">{f.label}</span><ArrowUpRight size={14}/></button>)}</div>
  </section>
}

export default function MoesExplorer() {
  const { feature: featureId } = useParams()
  const navigate = useNavigate()
  const feature = FEATURES.find((f) => f.id === featureId)
  const [sources, setSources] = useState<Source[]>([])
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [catalogStatus, setCatalogStatus] = useState('CHECKING')
  const [checkedAt, setCheckedAt] = useState('')
  const [query, setQuery] = useState(feature?.query ?? '')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [grid, setGrid] = useState<ArgoGrid | null>(null)
  const [gridLoading, setGridLoading] = useState(false)
  const [occurrences, setOccurrences] = useState<Occurrences | null>(null)
  const [occurrencesLoading, setOccurrencesLoading] = useState(false)
  const [buoyDirectory, setBuoyDirectory] = useState<BuoyDirectory | null>(null)
  const [buoyLoading, setBuoyLoading] = useState(false)
  const [featureEvidence, setFeatureEvidence] = useState<FeatureEvidence | null>(null)
  const [featureEvidenceLoading, setFeatureEvidenceLoading] = useState(false)
  const [forecast, setForecast] = useState<PointForecast | null>(null)
  const [forecastLoading, setForecastLoading] = useState(false)
  const [forecastProduct, setForecastProduct] = useState<'currents' | 'temperature' | 'salinity' | 'sea-level'>('currents')
  const [waveVariable, setWaveVariable] = useState('HS')
  const [forecastValidAt, setForecastValidAt] = useState('')
  const [forecastLatitude, setForecastLatitude] = useState('10')
  const [forecastLongitude, setForecastLongitude] = useState('80')
  const [forecastRefresh, setForecastRefresh] = useState(0)

  useEffect(() => { setQuery(feature?.query ?? '') }, [feature?.id])
  useEffect(() => {
    if (!feature) { setFeatureEvidence(null); return }
    let active = true
    setFeatureEvidenceLoading(true)
    fetchMoesFeature(feature.id)
      .then((data) => { if (active) setFeatureEvidence(data) })
      .catch((e: unknown) => { if (active) setFeatureEvidence({ available: false, feature_id: feature.id, feature: feature.label, status: 'TEMPORARILY_UNAVAILABLE', data_status: 'TEMPORARILY_UNAVAILABLE', live_endpoint: false, live_measurements: false, sources: [], dataset_count: 0, datasets: [], notes: [e instanceof Error ? e.message : 'Could not resolve source availability.'] }) })
      .finally(() => { if (active) setFeatureEvidenceLoading(false) })
    return () => { active = false }
  }, [feature?.id, refresh])
  useEffect(() => {
    const id = feature?.id
    const isWave = id === 'waves' || id === 'wind'
    const isHydrodynamic = id === 'currents' || id === 'temperature' || id === 'salinity' || id === 'sea-level' || id === 'forecast'
    if (!isWave && !isHydrodynamic) { setForecast(null); return }
    const latitude = Number(forecastLatitude)
    const longitude = Number(forecastLongitude)
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return
    let active = true
    setForecastLoading(true)
    const request = isWave
      ? fetchMoesWaveForecast(latitude, longitude, id === 'wind' ? 'WIND' : waveVariable, forecastValidAt || undefined)
      : fetchMoesHydrodynamicForecast(id === 'forecast' ? forecastProduct : id as 'currents' | 'temperature' | 'salinity' | 'sea-level', latitude, longitude)
    request.then((data) => {
      if (!active) return
      setForecast(data)
      if (isWave && !forecastValidAt && data.valid_at) setForecastValidAt(data.valid_at)
    }).catch((e: unknown) => {
      if (active) setForecast({ available: false, status: 'TEMPORARILY_UNAVAILABLE', error: e instanceof Error ? e.message : 'Could not fetch the INCOIS forecast.' })
    }).finally(() => { if (active) setForecastLoading(false) })
    return () => { active = false }
  }, [feature?.id, forecastLatitude, forecastLongitude, forecastProduct, waveVariable, forecastValidAt, forecastRefresh])
  useEffect(() => {
    let active = true
    setLoading(true); setError('')
    Promise.all([fetchMoesRegistry(), fetchMoesDatasets(query)])
      .then(([registry, catalog]) => {
        if (!active) return
        setSources(registry.sources ?? []); setDatasets(catalog.datasets ?? [])
        setCatalogStatus(catalog.status ?? registry.catalog_status ?? 'UNKNOWN')
        setCheckedAt(catalog.checked_at ?? registry.checked_at ?? '')
        if (catalog.error) setError(catalog.error)
      })
      .catch((e: unknown) => { if (active) { setError(e instanceof Error ? e.message : 'Could not reach the data service.'); setCatalogStatus('TEMPORARILY_UNAVAILABLE') } })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [query, refresh])

  useEffect(() => {
    if (feature?.id !== 'temperature' && feature?.id !== 'salinity') { setGrid(null); return }
    let active = true
    setGridLoading(true)
    fetchMoesArgoGrid(feature.id === 'temperature' ? 'TEMP' : 'SAL')
      .then((data) => { if (active) setGrid(data) })
      .catch((e: unknown) => { if (active) setGrid({ available: false, status: 'TEMPORARILY_UNAVAILABLE', error: e instanceof Error ? e.message : 'Could not fetch INCOIS grid.' }) })
      .finally(() => { if (active) setGridLoading(false) })
    return () => { active = false }
  }, [feature?.id, refresh])

  useEffect(() => {
    if (feature?.id !== 'waves' && feature?.id !== 'currents') { setBuoyDirectory(null); return }
    let active = true
    setBuoyLoading(true)
    fetchMoesBuoys()
      .then((data) => { if (active) setBuoyDirectory(data) })
      .catch((e: unknown) => { if (active) setBuoyDirectory({ available: false, status: 'TEMPORARILY_UNAVAILABLE', error: e instanceof Error ? e.message : 'Could not fetch NIOT stations.' }) })
      .finally(() => { if (active) setBuoyLoading(false) })
    return () => { active = false }
  }, [feature?.id, refresh])

  useEffect(() => {
    if (feature?.id !== 'biodiversity') { setOccurrences(null); return }
    let active = true
    setOccurrencesLoading(true)
    fetchMoesBiodiversity()
      .then((data) => { if (active) setOccurrences(data) })
      .catch((e: unknown) => { if (active) setOccurrences({ available: false, status: 'TEMPORARILY_UNAVAILABLE', error: e instanceof Error ? e.message : 'Could not fetch IndOBIS records.' }) })
      .finally(() => { if (active) setOccurrencesLoading(false) })
    return () => { active = false }
  }, [feature?.id, refresh])

  const matchingFeature = useMemo(() => feature ?? null, [feature])
  const incois = sources.find((s) => s.id === 'INCOIS')
  const gridCells = grid?.cells ?? grid?.records?.flatMap((record) => typeof record.value === 'number' ? [{ latitude: record.latitude, longitude: record.longitude, value: record.value }] : [])
  const gridValues = gridCells?.map((cell) => cell.value) ?? []
  const gridMin = gridValues.length ? Math.min(...gridValues) : 0
  const gridMax = gridValues.length ? Math.max(...gridValues) : 1
  return <main className="moes-page">
    <header className="moes-page-header"><div><span className="moes-eyebrow">OCEANVERSE AI · UNIFIED SOURCE LAYER</span><h1>{matchingFeature?.label ?? 'MoES Ocean Intelligence'}</h1><p>{matchingFeature?.note ?? 'Discover publicly accessible MoES ocean and earth-system datasets. Catalog metadata refreshes from INCOIS ERDDAP; other institutions link to their official portals until machine-readable services are confirmed.'}</p></div><div className={`moes-live-pill ${catalogStatus === 'LIVE' ? 'is-live' : ''}`}><span/>CATALOG CHECK · {catalogStatus.replaceAll('_', ' ')}</div></header>
    {matchingFeature && <section className="moes-detail-actions"><div><b>Connected workspace</b><span>Use the existing TidalTwin analysis workspace for this feature.</span></div><button onClick={() => navigate(matchingFeature.page)}>Open workspace <ArrowUpRight size={15}/></button><button className="moes-back" onClick={() => navigate('/moes')}>All MoES features</button></section>}
    {matchingFeature && <section className="moes-feature-evidence"><div className="moes-section-heading"><div><span className="moes-eyebrow">SOURCE CHECK · {featureEvidence?.sources?.join(' / ') || 'CHECKING'}</span><h2>Connected evidence</h2><p>Endpoint status and measurement availability are reported separately.</p></div><div className={`moes-live-pill ${featureEvidence?.live_endpoint ? 'is-live' : ''}`}><span/>{featureEvidenceLoading ? 'CHECKING' : (featureEvidence?.data_status ?? 'UNKNOWN').replaceAll('_', ' ')}</div></div>
      {featureEvidenceLoading && <div className="moes-empty">Resolving source availability for this feature…</div>}
      {!featureEvidenceLoading && featureEvidence && <><div className="moes-grid-meta"><span><small>REQUEST STATUS</small><b>{featureEvidence.status.replaceAll('_', ' ')}</b></span><span><small>PUBLIC DATA MATCHES</small><b>{featureEvidence.dataset_count}</b></span><span><small>LIVE MEASUREMENTS</small><b>{featureEvidence.live_measurements ? 'Yes' : 'No current feed verified'}</b></span><span><small>FORECAST FRESHNESS</small><b>{featureEvidence.forecast_freshness ?? 'No forecast file'}</b></span><span><small>FORECAST RUN AGE</small><b>{featureEvidence.forecast_age_hours == null ? 'Not applicable' : `${featureEvidence.forecast_age_hours} hours`}</b></span><span><small>CHECKED</small><b>{featureEvidence.checked_at ? new Date(featureEvidence.checked_at).toLocaleTimeString() : 'Not available'}</b></span></div>
        {featureEvidence.forecast_file && <p className="moes-evidence-note"><b>Forecast product:</b> {featureEvidence.forecast_file} · run {featureEvidence.forecast_run ? new Date(featureEvidence.forecast_run).toLocaleString() : 'time not listed'} · <a href={featureEvidence.forecast_source_url} target="_blank" rel="noreferrer">official product <ExternalLink size={11}/></a></p>}
        {featureEvidence.notes.map((note, i) => <p className="moes-evidence-note" key={i}>{note}</p>)}
        <div className="moes-feature-source-links">{sources.filter((source) => featureEvidence.sources.includes(source.id)).map((source) => <a key={source.id} href={source.official_url ?? source.url} target="_blank" rel="noreferrer">{source.id} official source <ExternalLink size={11}/></a>)}</div>
        {featureEvidence.datasets.length > 0 && <div className="moes-evidence-datasets">{featureEvidence.datasets.slice(0, 8).map((d) => <article key={d.id}><div><b>{d.name || d.id}</b><span>{d.institution} · {d.protocol} · source time age: {d.observation_age_days == null ? 'not listed' : `${d.observation_age_days} days`}</span></div><a href={d.url} target="_blank" rel="noreferrer">Source metadata <ExternalLink size={12}/></a></article>)}</div>}
        {featureEvidence.dataset_count === 0 && <p className="moes-evidence-note">No matching public machine-readable dataset is connected for this feature. The institution registry below links to official portals.</p>}
      </>}
    </section>}
    <section className="moes-source-strip"><div className="moes-source-main"><Waves size={17}/><div><b>{incois?.name ?? 'INCOIS'}</b><span>{incois?.dataset ?? 'Public ERDDAP dataset catalog'} · {incois?.protocol ?? 'ERDDAP'}</span></div></div><div className="moes-source-state"><b>{incois?.status?.replaceAll('_', ' ') ?? catalogStatus}</b><span>{checkedAt ? `Catalog checked ${new Date(checkedAt).toLocaleString()}` : 'Waiting for source check'}</span></div><button className="moes-refresh" onClick={() => setRefresh((n) => n + 1)} aria-label="Refresh live source catalog" disabled={loading}><RefreshCw size={15}/></button></section>
    {['waves', 'wind', 'currents', 'temperature', 'salinity', 'sea-level', 'forecast'].includes(feature?.id ?? '') && <section className="moes-live-grid moes-forecast-panel"><div className="moes-section-heading"><div><span className="moes-eyebrow">INCOIS · OPERATIONAL FORECAST · THREDDS</span><h2>{feature?.id === 'waves' ? 'Wave forecast' : feature?.id === 'wind' ? 'Wind forecast' : 'Ocean forecast'}</h2><p>Choose a point and inspect model output at its source valid times.</p></div><div className={`moes-live-pill ${forecast?.status === 'LIVE' ? 'is-live' : ''}`}><span/>{forecastLoading ? 'FETCHING' : (forecast?.status ?? 'CHECKING').replaceAll('_', ' ')}</div></div>
      <div className="moes-forecast-controls"><label>Latitude<input type="number" min="-60" max="31" step="0.1" value={forecastLatitude} onChange={(e) => setForecastLatitude(e.target.value)}/></label><label>Longitude<input type="number" min="20" max="120" step="0.1" value={forecastLongitude} onChange={(e) => setForecastLongitude(e.target.value)}/></label>
        {(feature?.id === 'waves' || feature?.id === 'wind') && feature.id !== 'wind' && <label>Wave variable<select value={waveVariable} onChange={(e) => { setWaveVariable(e.target.value); setForecastValidAt('') }}><option value="HS">Significant wave height</option><option value="PWP">Peak wave period</option><option value="T02">Mean wave period</option><option value="DIR">Mean wave direction</option><option value="PWD">Principal wave direction</option><option value="SPR">Directional spread</option><option value="STP">Wave steepness</option></select></label>}
        {feature?.id === 'forecast' && <label>Forecast variable<select value={forecastProduct} onChange={(e) => setForecastProduct(e.target.value as typeof forecastProduct)}><option value="currents">Ocean currents</option><option value="temperature">Temperature</option><option value="salinity">Salinity</option><option value="sea-level">Sea level</option></select></label>}
        {(feature?.id === 'waves' || feature?.id === 'wind') && forecast?.forecast_times && <label>Valid time<select value={forecastValidAt || forecast.valid_at || ''} onChange={(e) => setForecastValidAt(e.target.value)}>{forecast.forecast_times.map((time) => <option key={time} value={time}>{new Date(time).toLocaleString()}</option>)}</select></label>}
        <button onClick={() => setForecastRefresh((n) => n + 1)} disabled={forecastLoading}>Load forecast</button>
      </div>
      {forecastLoading && <div className="moes-empty">Requesting the latest official INCOIS forecast sample…</div>}
      {!forecastLoading && forecast?.available && <><div className="moes-grid-meta"><span><small>PROVIDER</small><b>{forecast.provider}</b></span><span><small>MODEL RUN</small><b>{forecast.model_run ? new Date(forecast.model_run).toLocaleString() : 'Not listed'}</b></span><span><small>RUN AGE</small><b>{forecast.age_hours == null ? 'Not listed' : `${forecast.age_hours.toFixed(1)} hours`}</b></span><span><small>VALID RECORDS</small><b>{forecast.record_count}</b></span><span><small>POSITION</small><b>{forecast.requested_position?.latitude}°, {forecast.requested_position?.longitude}°</b></span></div><div className="moes-forecast-values">{forecast.records?.map((record, i) => <article key={`${record.observed_at}-${i}`}><small>{record.observed_at ? new Date(record.observed_at).toLocaleString() : 'Valid time not listed'}</small><b>{record.variable.replaceAll('_', ' ')}: {record.value.toFixed(3)} {record.units}</b>{record.attributes?.eastward_velocity_m_s && <span>U {Number(record.attributes.eastward_velocity_m_s).toFixed(3)} m/s · V {Number(record.attributes.northward_velocity_m_s).toFixed(3)} m/s · toward {Number(record.attributes.direction_towards_deg).toFixed(1)}°</span>}</article>)}</div><p className="moes-grid-disclaimer">Forecast model output; this is not a buoy or in-situ observation. Valid time and model run time are shown separately. <a href={forecast.source_url} target="_blank" rel="noreferrer">INCOIS source <ExternalLink size={11}/></a></p></>}
      {!forecastLoading && forecast && !forecast.available && <div className="moes-empty">Forecast unavailable: {forecast.error ?? forecast.status}</div>}
    </section>}
    {(matchingFeature?.id === 'temperature' || matchingFeature?.id === 'salinity') && <section className="moes-live-grid"><div className="moes-section-heading"><div><span className="moes-eyebrow">INCOIS · GRIDDAP SUBSET</span><h2>{matchingFeature.label} analysis grid</h2><p>1° gridded Argo analysis · nearest surface level · Indian Ocean region</p></div><div className={`moes-live-pill ${grid?.status === 'LIVE' ? 'is-live' : ''}`}><span/>{gridLoading ? 'FETCHING' : (grid?.status ?? 'UNAVAILABLE').replaceAll('_', ' ')}</div></div>
      {gridLoading && <div className="moes-empty">Fetching the latest available gridded analysis from INCOIS…</div>}
      {!gridLoading && grid?.available && gridCells && grid.coverage && <><div className="moes-grid-meta"><span><small>SOURCE TIME</small><b>{grid.time ? new Date(grid.time).toLocaleString() : 'Not listed'}</b></span><span><small>FRESHNESS</small><b>{grid.freshness} · {grid.age_days} days old</b></span><span><small>DEPTH LEVEL</small><b>{grid.depth_m} m</b></span><span><small>CELLS</small><b>{grid.record_count?.toLocaleString() ?? grid.cell_count?.toLocaleString()}</b></span><span><small>VALUE RANGE</small><b>{gridMin.toFixed(1)}–{gridMax.toFixed(1)} {grid.unit}</b></span></div><div className="moes-grid-plot"><div className="moes-grid-axis-y"><span>{grid.coverage.north}°N</span><span>{grid.coverage.south}°</span></div><svg viewBox="0 0 800 420" role="img" aria-label={`${matchingFeature.label} analysis grid spatial coverage`}>{gridCells.map((cell, i) => { const ratio = (cell.value - gridMin) / (gridMax - gridMin || 1); const x = ((cell.longitude - grid.coverage!.west) / (grid.coverage!.east - grid.coverage!.west)) * 800; const y = ((grid.coverage!.north - cell.latitude) / (grid.coverage!.north - grid.coverage!.south)) * 420; return <rect key={`${cell.latitude}-${cell.longitude}-${i}`} x={x - 3.5} y={y - 3.5} width="7" height="7" rx="1.5" fill={`hsl(${205 - ratio * 175} 82% ${58 - ratio * 12}%)`}><title>{cell.latitude.toFixed(1)}°, {cell.longitude.toFixed(1)}° · {cell.value.toFixed(2)} {grid.unit}</title></rect> })}</svg><div className="moes-grid-axis-x"><span>{grid.coverage.west}°E</span><span>{grid.coverage.east}°E</span></div></div><p className="moes-grid-disclaimer">This is an INCOIS 10-day variational analysis of Argo data. It is not a real-time sensor feed; the displayed source time and age describe the underlying analysis. <a href={grid.source_url} target="_blank" rel="noreferrer">Dataset details <ExternalLink size={11}/></a></p></>}
      {!gridLoading && grid && !grid.available && <div className="moes-empty">INCOIS grid unavailable: {grid.error ?? grid.status}</div>}
    </section>}
    {matchingFeature?.id === 'biodiversity' && <section className="moes-live-grid"><div className="moes-section-heading"><div><span className="moes-eyebrow">CMLRE · INDOBIS · OBIS API V3</span><h2>Published marine species occurrences</h2><p>Verified IndOBIS node records · historical event dates retained per record</p></div><div className={`moes-live-pill ${occurrences?.available ? 'is-live' : ''}`}><span/>{occurrencesLoading ? 'FETCHING' : (occurrences?.status ?? 'UNAVAILABLE').replaceAll('_', ' ')}</div></div>
      {occurrencesLoading && <div className="moes-empty">Fetching public CMLRE / IndOBIS occurrence records…</div>}
      {!occurrencesLoading && occurrences?.available && <><div className="moes-grid-meta"><span><small>NODE RECORDS</small><b>{occurrences.total_node_records?.toLocaleString()}</b></span><span><small>RETURNED HERE</small><b>{occurrences.record_count?.toLocaleString() ?? occurrences.returned}</b></span><span><small>PROVIDER</small><b>CMLRE / IndOBIS</b></span><span><small>DATA TYPE</small><b>Species occurrence</b></span><span><small>LIVE ABUNDANCE</small><b>No · dated records</b></span></div><div className="moes-occurrence-list">{occurrences.records?.slice(0, 60).map((r, i) => <article key={r.record_id ?? i}><span className="moes-occurrence-dot">✦</span><div><a href={r.source_url ?? occurrences.source_url} target="_blank" rel="noreferrer">{r.value ?? 'Unidentified species'} <ExternalLink size={11}/></a><small>{r.observed_at ?? 'Date not provided'} · {r.latitude.toFixed(3)}°, {r.longitude.toFixed(3)}° · {r.attributes?.basis_of_record ?? 'Record type not provided'}</small></div></article>)}</div><p className="moes-grid-disclaimer">CMLRE confirms IndOBIS occurrence records are published to OBIS. Record dates vary and may be historical; these are not live animal tracks or abundance estimates. <a href="https://indobis.in/" target="_blank" rel="noreferrer">IndOBIS <ExternalLink size={11}/></a></p></>}
      {!occurrencesLoading && occurrences && !occurrences.available && <div className="moes-empty">IndOBIS unavailable: {occurrences.error ?? occurrences.status}</div>}
    </section>}
    {(matchingFeature?.id === 'waves' || matchingFeature?.id === 'currents') && <section className="moes-live-grid"><div className="moes-section-heading"><div><span className="moes-eyebrow">NIOT · OCEAN OBSERVATION SYSTEMS</span><h2>Met-ocean buoy network</h2><p>Live station directory and source-reported coverage periods; sensor time series are not exposed by this endpoint.</p></div><div className={`moes-live-pill ${buoyDirectory?.available ? 'is-live' : ''}`}><span/>{buoyLoading ? 'FETCHING' : (buoyDirectory?.status ?? 'UNAVAILABLE').replaceAll('_', ' ')}</div></div>
      {buoyLoading && <div className="moes-empty">Fetching NIOT buoy deployment metadata…</div>}
      {!buoyLoading && buoyDirectory?.available && <><div className="moes-grid-meta"><span><small>STATIONS IN REGION</small><b>{buoyDirectory.station_count}</b></span><span><small>PROVIDER</small><b>NIOT OOS</b></span><span><small>STATUS</small><b>Directory request succeeded</b></span><span><small>MEASUREMENTS</small><b>Not exposed here</b></span><span><small>CHECKED</small><b>{buoyDirectory.checked_at ? new Date(buoyDirectory.checked_at).toLocaleTimeString() : '—'}</b></span></div><div className="moes-occurrence-list">{buoyDirectory.stations?.map((s) => <article key={s.station_id}><span className="moes-occurrence-dot">◉</span><div><a href={buoyDirectory.source_url} target="_blank" rel="noreferrer">{s.station_id} · {s.type ?? 'Buoy'} <ExternalLink size={11}/></a><small>{s.latitude.toFixed(3)}°, {s.longitude.toFixed(3)}° · Data period: {s.data_period ?? 'Not listed'} · Deployed: {s.deployed_at ?? 'Not listed'}</small></div></article>)}</div><p className="moes-grid-disclaimer">The station API lists deployment metadata and the historical period for which data are available. No buoy measurements or current sea conditions are inferred from those date ranges. <a href={buoyDirectory.source_url} target="_blank" rel="noreferrer">NIOT buoy network <ExternalLink size={11}/></a></p></>}
      {!buoyLoading && buoyDirectory && !buoyDirectory.available && <div className="moes-empty">NIOT buoy catalog unavailable: {buoyDirectory.error ?? buoyDirectory.status}</div>}
    </section>}
    {matchingFeature?.id === 'data-explorer' || !matchingFeature ? <>
      <section className="moes-registry"><div className="moes-section-heading"><div><span className="moes-eyebrow">SOURCE REGISTRY</span><h2>MoES institutions</h2></div></div><div className="moes-source-grid">{sources.map((s) => <article className="moes-source-card" key={s.id}><div className="moes-source-card-head"><b>{s.id}</b><span className={s.live ? 'source-status-live' : ''}>{s.status.replaceAll('_', ' ')}</span></div><p>{s.name}</p><small><b>Dataset:</b> {s.dataset ?? 'No machine-readable dataset connected'}</small><small><b>Category:</b> {s.category ?? 'Not listed'}</small><small><b>Protocol:</b> {s.protocol ?? 'Official portal'}</small><small><b>Variables / units:</b> {s.variable ?? 'Not listed'} · {s.units ?? 'Not listed'}</small><small><b>Spatial coverage / resolution:</b> {s.coverage ?? 'Not listed'} · {s.spatial_resolution ?? 'Not listed'}</small><small><b>Update cadence:</b> {s.temporal_resolution ?? 'Not listed by source'}</small>{s.attribution && <small><b>Attribution:</b> {s.attribution}</small>}{s.license && <small><b>License:</b> {s.license}</small>}{s.error && <small className="moes-source-error">{s.error}</small>}{s.checked_at && <small>{s.cached ? 'Last check (cached)' : 'Last source check'} {new Date(s.checked_at).toLocaleString()}</small>}<a href={s.official_url ?? s.url} target="_blank" rel="noreferrer">Official source <ExternalLink size={12}/></a></article>)}</div></section>
      {!matchingFeature && <MoesFeatureGrid/>}
    </> : null}
    <section className="moes-catalog"><div className="moes-section-heading"><div><span className="moes-eyebrow">LIVE DATASET METADATA</span><h2>{matchingFeature ? `${matchingFeature.label} datasets` : 'INCOIS ERDDAP catalog'}</h2><p>{loading ? 'Fetching current catalog metadata…' : `${datasets.length} matching public dataset${datasets.length === 1 ? '' : 's'} in this response`}</p></div><label className="moes-search"><Search size={15}/><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search datasets or variables" aria-label="Search datasets"/></label></div>
      {error && <div className="moes-error">Catalog unavailable: {error}. Official source: <a href={incois?.url ?? 'https://erddap.incois.gov.in/erddap'} target="_blank" rel="noreferrer">INCOIS ERDDAP</a></div>}
      {!loading && datasets.length === 0 && <div className="moes-empty">No matching public datasets were returned. This is not evidence that the variable is absent from all MoES services.</div>}
      <div className="moes-dataset-list">{datasets.map((d) => <article className="moes-dataset-row" key={d.id}><div className="moes-dataset-icon"><Database size={16}/></div><div className="moes-dataset-info"><a href={d.url} target="_blank" rel="noreferrer">{d.name || d.id} <ExternalLink size={12}/></a><span>{d.id} · {d.institution} · {d.protocol} · {d.status ?? 'CATALOGED'}</span><p>{d.description}</p><DatasetDisclosure id={d.id}/></div><div className="moes-dataset-time"><small>TEMPORAL COVERAGE</small><b>{d.temporal_start ? new Date(d.temporal_start).toLocaleDateString() : 'Not listed'} – {d.temporal_end ? new Date(d.temporal_end).toLocaleDateString() : 'Latest not listed'}</b><small>LATEST SOURCE TIME AGE</small><b>{d.observation_age_days == null ? 'Not listed' : `${d.observation_age_days} days`}</b><small>SPATIAL COVERAGE</small><b>{d.coverage?.south ?? '—'} to {d.coverage?.north ?? '—'}° lat · {d.coverage?.west ?? '—'} to {d.coverage?.east ?? '—'}° lon</b><small>SPATIAL RESOLUTION</small><b>{d.spatial_resolution?.latitude_deg ?? '—'}° × {d.spatial_resolution?.longitude_deg ?? '—'}°</b><small>SOURCE TIME STEP</small><b>{d.temporal_resolution_seconds == null ? 'Not listed' : `${d.temporal_resolution_seconds} sec`}</b></div></article>)}</div>
      <footer className="moes-attribution">Catalog metadata provided by INCOIS ERDDAP. Metadata freshness is shown separately from measurement freshness; open each dataset for variables, units, coverage, and data use terms. Forecasts and analyses are not in-situ observations.</footer>
    </section>
  </main>
}
