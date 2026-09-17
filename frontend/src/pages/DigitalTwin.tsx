import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { useSearchParams } from 'react-router-dom'
import {
  Thermometer, Waves, Droplets, Tag, Globe2, Crosshair, Layers, Tornado, Clock,
  Play, Pause, Repeat, Target, Navigation, GitCompare, AlertTriangle, Activity,
  Database, ShieldCheck, Gauge, ChevronRight, Radar, Route, ScanLine, X, Loader2,
} from 'lucide-react'
import CesiumGlobe from '../components/3d/globe/CesiumGlobe'
import type { GlobeLocation, SeriesRegion, StormTrackData, ArgoFloat, DisagreementPoint, AnomalyPoint, TransectData, TideGlobeMarker } from '../components/3d/globe/CesiumGlobe'
import TransectHUD from '../components/transect/TransectHUD'
import {
  fetchLocations, fetchObservations, fetchStormTrack, fetchSafetyTimeseries, fetchUncertainty,
  fetchRecommendations, fetchArgo, fetchTwinCompare, fetchTwinExplain, fetchTwinProfile,
  fetchTwinDisagreement, fetchAnomalies, fetchSituation, fetchDataSources, fetchTransect,
  fetchTideCandidates,
} from '../api/client'
import './DigitalTwin.css'

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: 'easeOut' as const } },
}

type ReplayMode = 'temp' | 'model' | 'difference'

const VARIABLES = [
  { key: 'temperature', label: 'Sea Temperature', unit: '°C', short: 'Temp' },
  { key: 'wave_height', label: 'Wave Height', unit: 'm', short: 'Waves' },
  { key: 'salinity', label: 'Salinity', unit: 'PSU', short: 'Salt' },
  { key: 'current_speed', label: 'Current Speed', unit: 'm/s', short: 'Curr' },
]

const SEV_COLOR: Record<string, string> = {
  low: '#10b981',
  known: '#10b981',
  'no data': '#64748b',
  unknown: '#64748b',
  no_data: '#64748b',
  moderate: '#f59e0b',
  high: '#f43f5e',
  unavailable: '#64748b',
}

const STATUS_LABEL: Record<string, string> = {
  live: 'LIVE',
  recent: 'RECENT',
  cached: 'CACHED',
  demo: 'DEMO',
  derived: 'DERIVED',
  unavailable: 'UNAVAILABLE',
}

interface ComparePayload {
  location_id: number
  location: string
  latitude: number | null
  longitude: number | null
  variable: string
  label: string
  unit: string
  depth_m: number
  model: number | null
  observed: number | null
  difference: number | null
  percent_difference: number | null
  status: string
  severity: string
  band: string
  confidence: number
  confidence_level: string
  confidence_factors: { factor: string; pct: number; weight: number; note: string }[]
  confidence_reasons: string[]
  observation_source: string | null
  observation_time: string | null
  data_status: string
}

interface ExplainPayload {
  what: string
  explanation: string
  cause: string
  evidence: string[]
  confidence: number
  status: string
  data_status: string
}

/** Rolling baseline + deviation for a point index (mirrors the globe layer). */
function baselineAt(reg: SeriesRegion, idx: number) {
  const temps = reg.points
    .slice(Math.max(0, idx - 12), idx)
    .map((p) => p.temperature)
    .filter((t): t is number => t != null)
  if (temps.length === 0) return null
  return temps.reduce((a, b) => a + b, 0) / temps.length
}

export default function DigitalTwin() {
  const [searchParams] = useSearchParams()
  const [locations, setLocations] = useState<GlobeLocation[]>([])
  const [loading, setLoading] = useState(true)
  const [activeLoc, setActiveLoc] = useState<GlobeLocation | null>(null)
  const [variable, setVariable] = useState('temperature')
  const [layers, setLayers] = useState({
    temperature: true,
    waves: true,
    currents: true,
    labels: true,
    storm: false,
    uncertainty: false,
    priority: false,
    argo: false,
    disagreement: true,
    anomalies: true,
    tide: false,
  })
  const [storm, setStorm] = useState<StormTrackData | null>(null)
  const [series, setSeries] = useState<SeriesRegion[]>([])
  const [uncertainties, setUncertainties] = useState<Record<number, number>>({})
  const [priorities, setPriorities] = useState<Record<number, number>>({})
  const [argoFloats, setArgoFloats] = useState<ArgoFloat[]>([])
  const [cursor, setCursor] = useState<number>(0)
  const [playing, setPlaying] = useState(false)
  const [replayMode, setReplayMode] = useState<ReplayMode>('temp')

  // --- Ocean Digital Twin intelligence state ---
  const [disagreement, setDisagreement] = useState<DisagreementPoint[]>([])
  const [anomalyRows, setAnomalyRows] = useState<AnomalyPoint[]>([])
  const [tideCandidates, setTideCandidates] = useState<TideGlobeMarker[]>([])
  const [compare, setCompare] = useState<ComparePayload | null>(null)
  const [explainData, setExplainData] = useState<ExplainPayload | null>(null)
  const [profileData, setProfileData] = useState<ProfilePayload | null>(null)
  const [situation, setSituation] = useState<Situation | null>(null)
  const [sources, setSources] = useState<Record<string, unknown>[]>([])
  const [flyToTarget, setFlyToTarget] = useState<{ locId: number; n: number } | null>(null)

  // --- 3D vertical transect curtain state ---
  const [transectData, setTransectData] = useState<TransectData | null>(null)
  const [transectActive, setTransectActive] = useState(false)
  const [transectPicks, setTransectPicks] = useState<{ lat: number; lon: number }[]>([])
  const [transectBusy, setTransectBusy] = useState(false)
  const [transectError, setTransectError] = useState<string | null>(null)
  const [transectDepth, setTransectDepth] = useState(2000)

  const handleTransectPick = (pt: { lat: number; lon: number }) => {
    if (transectBusy) return
    const next = [...transectPicks, pt]
    setTransectPicks(next)
    if (next.length >= 2) {
      setTransectActive(false)
      setTransectBusy(true)
      setTransectError(null)
      const [a, b] = next
      fetchTransect({
        lat1: a.lat, lon1: a.lon,
        lat2: b.lat, lon2: b.lon,
        variable, depth_max: transectDepth, n_samples: 48,
      })
        .then((data: TransectData) => {
          if (data && data.samples && data.samples.length > 1) {
            setTransectData(data)
          } else {
            setTransectError(data?.error || 'Transect returned no data')
          }
        })
        .catch(() => setTransectError('Transect request failed'))
        .finally(() => {
          setTransectBusy(false)
          setTransectPicks([])
        })
    }
  }

  const clearTransect = () => {
    setTransectData(null)
    setTransectPicks([])
    setTransectError(null)
    setTransectActive(false)
  }

  useEffect(() => {
    fetchLocations()
      .then(async (data: GlobeLocation[]) => {
        const withData = await Promise.all(
          data.map(async (loc) => {
            try {
              const obs = await fetchObservations(loc.id, 1)
              const last = obs[0]
              return {
                ...loc,
                temperature: last?.sea_surface_temperature ?? null,
                wave_height: last?.wave_height ?? null,
              }
            } catch {
              return loc
            }
          }),
        )
        setLocations(withData)
        const focusId = Number(searchParams.get('focus') || 0)
        const target = withData.find((l) => l.id === focusId) ?? withData[0] ?? null
        setActiveLoc(target)
        if (focusId && target) {
          setFlyToTarget((p) => ({ locId: target.id, n: (p?.n ?? 0) + 1 }))
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false))

    fetchStormTrack()
      .then((d: StormTrackData) => setStorm(d))
      .catch(() => {})
    fetchSafetyTimeseries()
      .then((d) => {
        const regions: SeriesRegion[] = d.regions ?? []
        setSeries(regions)
        setCursor(0)
      })
      .catch(() => {})

    fetchUncertainty()
      .then((d) => {
        const map: Record<number, number> = {}
        for (const r of d.regions ?? []) {
          if (r.location_id != null && r.uncertainty != null) map[r.location_id] = r.uncertainty
        }
        setUncertainties(map)
      })
      .catch(() => {})
    fetchRecommendations(0)
      .then((d) => {
        const map: Record<number, number> = {}
        for (const r of d.recommendations ?? []) {
          if (r.location_id != null && r.obs_need != null) map[r.location_id] = r.obs_need
        }
        setPriorities(map)
      })
      .catch(() => {})

    fetchArgo()
      .then((d) => setArgoFloats(d.floats ?? []))
      .catch(() => {})

    // Ocean Digital Twin intelligence payloads.
    fetchSituation().then((d) => setSituation(d as Situation)).catch(() => {})
    fetchDataSources()
      .then((d) => setSources(d.sources ?? []))
      .catch(() => {})
    fetchAnomalies({ sort: 'severity' })
      .then((d) => setAnomalyRows(d.anomalies ?? []))
      .catch(() => {})
    fetchTideCandidates({ variable })
      .then((d) => {
        const list = (d as { data?: TideGlobeMarker[] }).data ?? []
        setTideCandidates(list.map((c, i) => ({ ...c, rank: i + 1 })))
      })
      .catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Deep-link from the Anomaly Intelligence page: ?focus=<id>&var=<variable>
  const focusId = Number(searchParams.get('focus') || 0)
  useEffect(() => {
    const v = searchParams.get('var')
    if (v && VARIABLES.some((x) => x.key === v)) setVariable(v)
  }, [searchParams])
  useEffect(() => {
    if (!focusId || !locations.length) return
    const t = locations.find((l) => l.id === focusId)
    if (t) {
      setActiveLoc(t)
      setFlyToTarget((p) => ({ locId: t.id, n: (p?.n ?? 0) + 1 }))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusId, locations])

  // Recolor the disagreement globe layer when the variable changes.
  useEffect(() => {
    fetchTwinDisagreement(variable)
      .then((d) => setDisagreement(d.points ?? []))
      .catch(() => {})
  }, [variable])

  // Per-region intelligence: compare + explanation + depth profile.
  useEffect(() => {
    if (!activeLoc) return
    let alive = true
    Promise.all([
      fetchTwinCompare(activeLoc.id, variable),
      fetchTwinExplain(activeLoc.id, variable),
      fetchTwinProfile(activeLoc.id, variable).catch(() => null),
    ])
      .then(([c, x, p]) => {
        if (!alive) return
        setCompare(c as ComparePayload)
        setExplainData(x as ExplainPayload)
        setProfileData(p as ProfilePayload | null)
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [activeLoc, variable])

  // Timeline auto-play
  const maxCursor = series.length > 0 ? series[0].points.length - 1 : 0
  useEffect(() => {
    if (!playing || maxCursor <= 0) return
    const id = setInterval(() => setCursor((c) => (c + 1) % (maxCursor + 1)), 240)
    return () => clearInterval(id)
  }, [playing, maxCursor])

  const toggleLayer = (key: keyof typeof layers) => {
    setLayers((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  const LAYER_PANEL = [
    { key: 'labels' as const, icon: <Tag size={16} />, name: 'Region Labels', desc: 'Floating labels on the globe' },
    { key: 'temperature' as const, icon: <Thermometer size={16} />, name: 'Sea Temperature', desc: 'Heat signature layer' },
    { key: 'waves' as const, icon: <Waves size={16} />, name: 'Wave Height', desc: 'Wave energy layer' },
    { key: 'currents' as const, icon: <Droplets size={16} />, name: 'Ocean Currents', desc: 'Flow field layer' },
    { key: 'storm' as const, icon: <Tornado size={16} />, name: 'Storm Track', desc: 'Simulated cyclone path + eye' },
    { key: 'disagreement' as const, icon: <GitCompare size={16} />, name: 'Model vs Reality', desc: 'Agreement patches (observation vs model)' },
    { key: 'anomalies' as const, icon: <Radar size={16} />, name: 'Anomaly Beacons', desc: 'Ranked model-vs-observation anomalies' },
    { key: 'uncertainty' as const, icon: <Crosshair size={16} />, name: 'Data Uncertainty', desc: 'Confidence-gap rings per region' },
    { key: 'priority' as const, icon: <Target size={16} />, name: 'Sampling Priority', desc: 'Pulse where observation is needed' },
    { key: 'argo' as const, icon: <Navigation size={16} />, name: 'Argo Floats', desc: 'Simulated float trajectories + T/S profiles' },
    { key: 'tide' as const, icon: <Radar size={16} />, name: 'TIDE Decisions', desc: 'Ranked observation recommendation markers' },
  ]

  const activeVar = VARIABLES.find((v) => v.key === variable) ?? VARIABLES[0]
  const cursorTime = series[0]?.points[cursor]?.time
  const cursorLabel = cursorTime
    ? new Date(cursorTime).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    : '—'

  // Event replay readout: strongest model-vs-reality gap at the current hour.
  const replayEvent = useMemo(() => {
    if (series.length === 0 || series[0].points.length === 0) return null
    let best: { loc: string; dev: number; cur: number } | null = null
    for (const reg of series) {
      const idx = Math.min(cursor, reg.points.length - 1)
      const cur = reg.points[idx]?.temperature
      if (cur == null) continue
      const base = baselineAt(reg, idx)
      if (base == null) continue
      const dev = cur - base
      if (!best || Math.abs(dev) > Math.abs(best.dev)) best = { loc: reg.location, dev, cur }
    }
    if (!best) return null
    const aDev = Math.abs(best.dev)
    const grade = aDev >= 0.8 ? 'SIGNIFICANT EVENT' : aDev >= 0.4 ? 'NOTABLE' : 'WITHIN BASELINE'
    const kind = best.dev > 0 ? 'heating' : best.dev < 0 ? 'cooling' : 'neutral'
    return { cur: best.cur, dev: best.dev, grade, kind, loc: best.loc.replace(' Coast', '') }
  }, [series, cursor])

  const replayLabel = replayMode === 'temp' ? 'OBSERVED' : replayMode === 'model' ? 'MODEL' : 'DIFFERENCE'

  const diff = compare?.difference ?? null
  const pct = compare?.percent_difference ?? null
  const sev = compare?.severity ?? 'unknown'
  const dataStatus = compare?.data_status ?? 'unavailable'
  const conf = compare?.confidence ?? 0
  const confReasons = compare?.confidence_reasons ?? []
  const confFactors = compare?.confidence_factors ?? []

  const handleRegionClick = (locId: number) => {
    const loc = locations.find((l) => l.id === locId)
    if (!loc) return
    setActiveLoc(loc)
    setFlyToTarget((p) => ({ locId, n: (p?.n ?? 0) + 1 }))
  }

  const focusAnomaly = (a: AnomalyPoint) => {
    if (a.variable !== variable) setVariable(a.variable)
    const loc = locations.find((l) => l.id === a.location_id)
    if (loc) {
      setActiveLoc(loc)
      setFlyToTarget((p) => ({ locId: a.location_id, n: (p?.n ?? 0) + 1 }))
    }
  }

  return (
    <div className="page digital-twin animate-in">
      <div className="page-header twin-header">
        <div>
          <h1 className="page-title title-glow">
            3D Ocean <span className="text-gradient">Digital Twin</span>
          </h1>
          <p className="page-subtitle">
            Model-vs-observation intelligence on a live 3D globe — transparent confidence, ranked anomalies,
            explainable events.
          </p>
        </div>
        <div className="twin-count glass-card">
          <Crosshair size={16} />
          <span>{loading ? '…' : locations.length} MONITORED</span>
        </div>
      </div>

      {/* Decision situation strip */}
      <motion.div variants={fadeUp} initial="hidden" animate="show" className="twin-situation">
        <SituationStrip situation={situation} />
      </motion.div>

      <motion.div variants={fadeUp} initial="hidden" animate="show" className="twin-layout">
        {/* Globe */}
        <div className="twin-globe-wrap">
          <CesiumGlobe
            locations={locations}
            layers={layers}
            storm={storm}
            series={series}
            timeCursor={series.length > 0 ? cursor : null}
            timeColor={replayMode}
            uncertainties={uncertainties}
            priorities={priorities}
            argoFloats={argoFloats}
            disagreement={disagreement}
            anomalies={anomalyRows.filter((a) => a.severity !== 'low').slice(0, 8)}
            tideCandidates={tideCandidates}
            onRegionClick={handleRegionClick}
            flyToTarget={flyToTarget}
            transect={transectData}
            transectActive={transectActive}
            onTransectPick={handleTransectPick}
          />
          {transectData && <TransectHUD data={transectData} />}
        </div>

        {/* Control + intelligence panel */}
        <div className="twin-controls">
          {/* Variable selector */}
          <div className="glass-card control-card">
            <div className="control-title">
              <Gauge size={16} />
              <span>Compare Variable</span>
            </div>
            <div className="var-picker">
              {VARIABLES.map((v) => (
                <button
                  key={v.key}
                  className={`var-pill ${variable === v.key ? 'var-pill-on' : ''}`}
                  onClick={() => setVariable(v.key)}
                  title={v.label}
                >
                  {v.short}
                </button>
              ))}
            </div>
          </div>

          <div className="glass-card control-card">
            <div className="control-title">
              <Layers size={16} />
              <span>Data Layers</span>
            </div>
            <div className="control-list">
              {LAYER_PANEL.map(({ key, icon, name, desc }) => (
                <button
                  key={key}
                  className={`layer-toggle ${layers[key] ? 'layer-toggle-on' : ''}`}
                  onClick={() => toggleLayer(key)}
                >
                  <span className="toggle-icon">{icon}</span>
                  <span className="toggle-text">
                    <span className="toggle-name">{name}</span>
                    <span className="toggle-desc">{desc}</span>
                  </span>
                  <span className={`toggle-switch ${layers[key] ? 'toggle-switch-on' : ''}`}>
                    <span className="toggle-knob" />
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Event replay — 4D model-vs-reality scrubber */}
          <div className="glass-card control-card">
            <div className="control-title">
              <Clock size={16} />
              <span>Event Replay</span>
              <span className={`live-dot ${playing ? '' : 'live-dot-off'}`} />
            </div>

            <div className="replay-modes">
              {(['temp', 'model', 'difference'] as ReplayMode[]).map((m) => (
                <button
                  key={m}
                  className={`replay-mode ${replayMode === m ? 'replay-mode-on' : ''}`}
                  onClick={() => { setReplayMode(m); setPlaying(false) }}
                >
                  {m === 'temp' ? 'Observed' : m === 'model' ? 'Model' : 'Difference'}
                </button>
              ))}
            </div>

            {series.length > 0 ? (
              <>
                <div className="scrubber-label">
                  <span>{cursorLabel}</span>
                  <span className={`scrubber-badge ${replayMode === 'difference' ? 'scrubber-badge-dev' : ''}`}>
                    {replayLabel} · {cursor <= series[0].points.length - 1 - 24 ? 'OBSERVED' : 'AI PROJECTED'}
                  </span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={maxCursor}
                  value={cursor}
                  onChange={(e) => {
                    setCursor(Number(e.target.value))
                    setPlaying(false)
                  }}
                  className="scrubber"
                />
                <div className="scrubber-marks">
                  <span>H-48</span>
                  <span>Now</span>
                  <span>H+24</span>
                </div>

                {replayEvent && replayMode === 'difference' && (
                  <div className={`replay-event ${replayEvent.grade === 'SIGNIFICANT EVENT' ? 'replay-event-hot' : ''}`}>
                    <Repeat size={13} />
                    <span>
                      <b>{replayEvent.dev > 0 ? '+' : '−'}{Math.abs(replayEvent.dev).toFixed(1)}°C</b>
                      {' '}<b style={{ color: '#7dd3fc' }}>{replayEvent.grade}</b>
                      {' '}<span className="replay-event-meta">({replayEvent.kind === 'neutral' ? 'stable' : replayEvent.kind} · {replayEvent.cur}°C real · {replayEvent.loc})</span>
                    </span>
                  </div>
                )}
                {replayEvent && replayMode !== 'difference' && (
                  <div className="replay-event">
                    <Repeat size={13} />
                    <span><b>{replayMode === 'temp' ? replayEvent.cur : (replayEvent.cur - replayEvent.dev).toFixed(1)}°C</b> at {replayEvent.loc}</span>
                  </div>
                )}

                <button
                  className="btn-primary scrubber-play"
                  onClick={() => setPlaying((p) => !p)}
                  disabled={maxCursor <= 0}
                >
                  {playing ? <Pause size={14} /> : <Play size={14} />}
                  {playing ? 'Pause' : 'Play forecast'}
                </button>
              </>
            ) : (
              <div className="hint">Timeline loading…</div>
            )}
          </div>

          {/* Model vs Reality comparison */}
          <div className="glass-card control-card">
            <div className="control-title">
              <GitCompare size={16} />
              <span>Model vs Reality</span>
              {dataStatus && (
                <span className={`status-badge status-${dataStatus}`}>{STATUS_LABEL[dataStatus] ?? dataStatus.toUpperCase()}</span>
              )}
            </div>

            {compare && typeof diff === 'number' ? (
              <>
                <div className="cmp-grid">
                  <div className="cmp-cell">
                    <span className="cmp-kicker">MODEL</span>
                    <span className="cmp-value">{compare.model}{activeVar.unit}</span>
                  </div>
                  <div className="cmp-delta">
                    <span className={`cmp-sign ${diff > 0 ? 'cmp-sign-plus' : diff < 0 ? 'cmp-sign-minus' : ''}`}>
                      {diff > 0 ? '+' : ''}{diff.toFixed(2)}{activeVar.unit}
                    </span>
                    <span className="cmp-pct">{pct != null ? `${pct.toFixed(1)}%` : '—'}</span>
                  </div>
                  <div className="cmp-cell cmp-cell-obs">
                    <span className="cmp-kicker">OBSERVED</span>
                    <span className="cmp-value">{compare.observed}{activeVar.unit}</span>
                  </div>
                </div>
                {activeVar.key !== 'temperature' && (
                  <p className="hint">Sea temperature uses the real satellite-derived surface feed; other variables show status when data is unavailable.</p>
                )}
                <div className="cmp-status-row">
                  <span className="sev-chip" style={{ color: SEV_COLOR[sev], borderColor: SEV_COLOR[sev] }}>
                    {sev.toUpperCase()} DISAGREEMENT
                  </span>
                  <span className="cmp-label">{activeVar.label}</span>
                </div>

                {/* Confidence bar */}
                <div className="conf-block">
                  <div className="conf-head">
                    <ShieldCheck size={14} />
                    <span>Comparison confidence</span>
                    <b>{conf}%</b>
                  </div>
                  <div className="conf-track">
                    <div className="conf-fill" style={{ width: `${conf}%` }} />
                  </div>
                  <div className="conf-reasons">
                    {confReasons.slice(0, 3).map((r) => (
                      <div key={r} className="conf-reason">• {r}</div>
                    ))}
                  </div>
                </div>

                {/* Factor breakdown */}
                {confFactors.length > 0 && (
                  <div className="factor-list">
                    {confFactors.map((f) => (
                      <div key={f.factor} className="factor-row">
                        <span className="factor-name">{f.factor}<em>{f.note}</em></span>
                        <div className="factor-track"><div className="factor-fill" style={{ width: `${f.pct}%` }} /></div>
                      </div>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <div className="hint">Select a region on the globe to load the comparison.</div>
            )}
          </div>

          {/* 3D Vertical Transect curtain */}
          <div className="glass-card control-card">
            <div className="control-title">
              <Route size={16} />
              <span>3D Vertical Transect</span>
              {transectData && (
                <button className="icon-btn-clear" onClick={clearTransect} title="Clear transect">
                  <X size={14} />
                </button>
              )}
            </div>
            <p className="hint">
              Click two points on the ocean (A → B) to render a subsurface vertical
              curtain down to <b>{transectDepth}m</b> with the thermocline layer and
              any Argo floats inside a 50 km buffer.
            </p>

            <div className="transect-depth-row">
              <span className="cmp-kicker">MAX DEPTH</span>
              <input
                type="range"
                min={500}
                max={2000}
                step={250}
                value={transectDepth}
                disabled={transectActive || transectBusy}
                onChange={(e) => setTransectDepth(Number(e.target.value))}
                className="scrubber"
              />
              <span className="transect-depth-val">{transectDepth} m</span>
            </div>

            {!transectActive && !transectData && (
              <button
                className="btn-primary scrubber-play"
                onClick={() => { setTransectError(null); setTransectPicks([]); setTransectActive(true) }}
              >
                <ScanLine size={14} />
                {transectPicks.length === 0 ? 'Pick transect on the globe' : `Point ${transectPicks.length} picked · click point B`}
              </button>
            )}

            {transectActive && (
              <div className="transect-status">
                <Loader2 size={13} className="spin" />
                <span>
                  {transectPicks.length === 0
                    ? <b>Click point A</b>
                    : <b>Click point B</b>}
                </span>
                <span>— the globe is translucent; click anywhere on the ocean</span>
                <button className="link-btn" onClick={() => setTransectActive(false)}>Cancel</button>
              </div>
            )}

            {transectBusy && (
              <div className="transect-status">
                <Loader2 size={13} className="spin" />
                <span>Interpolating the 3D field along your transect…</span>
              </div>
            )}

            {transectError && <p className="transect-error">{transectError}</p>}

            {transectData && (
              <div className="transect-meta">
                <span>{transectData.a.lat.toFixed(2)}°, {transectData.a.lon.toFixed(2)}°</span>
                <span className="transect-meta-arrow">→</span>
                <span>{transectData.b.lat.toFixed(2)}°, {transectData.b.lon.toFixed(2)}°</span>
                <span className="transect-meta-dist">{transectData.distance_km.toFixed(0)} km</span>
                <span className="transect-meta-argos">{transectData.argos.length} Argo float{transectData.argos.length === 1 ? '' : 's'} in buffer</span>
              </div>
            )}
          </div>

          {/* AI explanation */}
          {explainData && (
            <div className="glass-card control-card">
              <div className="control-title">
                <Activity size={16} />
                <span>Why is this happening?</span>
              </div>
              <div className="explain-block">
                <p className="explain-what">{explainData.what}</p>
                <p className="explain-text">{explainData.explanation}</p>
                <div className="explain-cause">
                  <b>Cause</b>
                  <span>{explainData.cause}</span>
                </div>
              </div>
            </div>
          )}

          {/* Depth profile */}
          {profileData && (profileData.rows?.length ?? 0) > 0 && (
            <div className="glass-card control-card">
              <div className="control-title">
                <Waves size={16} />
                <span>Depth Profile — {activeVar.label}</span>
              </div>
              <DepthProfileChart data={profileData as ProfilePayload} />
            </div>
          )}

          {/* Region focus */}
          {activeLoc && (
            <div className="glass-card control-card">
              <div className="control-title">
                <Globe2 size={16} />
                <span>Region Focus</span>
              </div>
              <div className="focus-region">
                <div className="focus-name">{activeLoc.name}</div>
                <div className="focus-meta">
                  <span>{activeLoc.region_type}</span>
                  <span>{activeLoc.country}</span>
                </div>
                <div className="focus-coords">
                  {activeLoc.latitude?.toFixed(2)}°N, {activeLoc.longitude?.toFixed(2)}°E
                </div>
              </div>
            </div>
          )}

          {/* Anomaly podium */}
          <div className="glass-card control-card">
            <div className="control-title">
              <AlertTriangle size={16} />
              <span>Anomaly Intelligence</span>
              <span className="podium-count">{anomalyRows.length} RANKED</span>
            </div>
            {anomalyRows.length > 0 ? (
              <div className="podium-list">
                {anomalyRows.slice(0, 5).map((a) => (
                  <button key={`${a.location_id}-${a.variable}`} className="podium-row" onClick={() => focusAnomaly(a)}>
                    <span className={`podium-sev sev-${a.severity}`} />
                    <span className="podium-txt">
                      <b>{a.location}</b>
                      <em>{a.label} · {a.observed} {a.unit} vs {a.model} {a.unit}</em>
                    </span>
                    <span className="podium-right">
                      <span className="podium-diff" style={{ color: SEV_COLOR[a.severity] }}>
                        {a.difference != null ? `${a.difference > 0 ? '+' : ''}${a.difference.toFixed(1)}` : '—'} {a.unit}
                      </span>
                      <span className="podium-conf">{a.confidence}%</span>
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <div className="hint">No anomalies above threshold in available data.</div>
            )}
          </div>

          {/* Data sources */}
          <div className="glass-card control-card">
            <div className="control-title">
              <Database size={16} />
              <span>Data Provenance</span>
            </div>
            <div className="src-list">
              {sources.map((s) => {
                const st = (s.status ?? '') as string
                return (
                  <div key={s.id as string} className="src-row">
                    <span className={`src-dot src-${st}`} />
                    <span className="src-txt">
                      <b>{s.name as string}</b>
                      <em>{s.note as string}</em>
                    </span>
                    <span className="src-meta">
                      <span className="src-status">{st.toUpperCase().replace('_', ' ')}</span>
                      {(s.coverage_pct as number) != null && <span className="src-cov">{(s.coverage_pct as number).toFixed(0)}%</span>}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  )
}

/* ------------------------------------------------------------------ */

interface Situation {
  split: { normal_regions_pct: number; watch_regions_pct: number; high_risk_regions_pct: number }
  active_events: number
  high_disagreements: number
  observation_coverage_pct: number
  model_trust: number
  summary: string
}

function SituationStrip({ situation }: { situation: Situation | null }) {
  const s = situation
  if (!s) {
    return (
      <div className="glass-card sit-card">
        <div className="hint">Loading ocean situation…</div>
      </div>
    )
  }
  const stats = [
    { label: 'Normal', value: s.split.normal_regions_pct, color: '#10b981' },
    { label: 'Watch', value: s.split.watch_regions_pct, color: '#f59e0b' },
    { label: 'High Risk', value: s.split.high_risk_regions_pct, color: '#f43f5e' },
  ]
  return (
    <div className="glass-card sit-card">
      <div className="sit-title">
        <Activity size={15} />
        <b>Ocean Situation</b>
        <span className="sit-summary">{s.summary}</span>
      </div>
      {stats.map((st) => (
        <div key={st.label} className="sit-stat">
          <span className="sit-label">{st.label}</span>
          <div className="sit-track"><div className="sit-fill" style={{ width: `${st.value}%`, background: st.color }} /></div>
          <span className="sit-value" style={{ color: st.color }}>{st.value}%</span>
        </div>
      ))}
      <div className="sit-badges">
        <span className="sit-badge">⚡ {s.active_events} active events</span>
        <span className="sit-badge">⟲ {s.high_disagreements} high disagreements</span>
        <span className="sit-badge">◉ {s.observation_coverage_pct}% observed</span>
        <span className="sit-badge">🛡 {s.model_trust}% model trust</span>
        <ChevronRight size={14} className="sit-chevron" />
      </div>
    </div>
  )
}

interface ProfileRow {
  depth_m: number
  model: number
  observed: number
  difference: number
  data_status: string
}

interface ProfilePayload {
  rows: ProfileRow[]
  unit: string
  label: string
  surface_data_status: string
  model_note?: string
  observation_note?: string
}

/** Tiny SVG line chart: model (cyan) vs observed (amber) down the water column. */
function DepthProfileChart({ data }: { data: ProfilePayload }) {
  const { rows } = data
  if (!rows || rows.length < 2) return null
  const W = 280
  const H = 120
  const pad = 8
  const depths = rows.map((r) => r.depth_m)
  const vals = rows.flatMap((r) => [r.model, r.observed]).filter((v) => v != null)
  const maxD = Math.max(...depths)
  const vMin = Math.min(...vals)
  const vMax = Math.max(...vals)
  const span = Math.max(1e-6, vMax - vMin)
  const x = (d: number) => pad + (d / (maxD || 1)) * (W - pad * 2)
  const y = (v: number) => H - pad - ((v - vMin) / span) * (H - pad * 2)
  const line = (key: 'model' | 'observed') =>
    rows.map((r, i) => `${i === 0 ? 'M' : 'L'}${x(r.depth_m).toFixed(1)},${y(r[key]).toFixed(1)}`).join(' ')
  return (
    <div className="profile-block">
      <svg viewBox={`0 0 ${W} ${H}`} className="profile-svg">
        {[0, 50, 100].map((g) => (
          <line key={g} x1={pad} x2={W - pad} y1={(g / 100) * (H - pad * 2) + pad} y2={(g / 100) * (H - pad * 2) + pad}
            className="profile-gridline" />
        ))}
        <path d={line('observed')} fill="none" stroke="#f59e0b" strokeWidth="2.2" />
        <path d={line('model')} fill="none" stroke="#22d3ee" strokeWidth="2" strokeDasharray="4 3" />
        {rows.map((r) => (
          <circle key={r.depth_m} cx={x(r.depth_m)} cy={y(r.observed)} r="2.6" fill="#f59e0b" />
        ))}
      </svg>
      <div className="profile-legend">
        <span><i className="leg-legged" /> Observed {data.surface_data_status === 'derived' ? '(surface real, below derived)' : ''}</span>
        <span><i className="leg-model" /> Model</span>
      </div>
      <div className="profile-hint">{data.observation_note}</div>
    </div>
  )
}