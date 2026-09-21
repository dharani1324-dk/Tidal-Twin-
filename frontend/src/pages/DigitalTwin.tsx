import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { useSearchParams } from 'react-router-dom'
import {
  Thermometer, Waves, Droplets, Tag, Globe2, Crosshair, Layers, Tornado, Clock,
  Play, Pause, Repeat, Target, Navigation, GitCompare, AlertTriangle, Activity,
  Database, ShieldCheck, Gauge, ChevronRight, Radar, Route, ScanLine, X, Loader2,
  Satellite, Orbit,
} from 'lucide-react'
import CesiumGlobe from '../components/3d/globe/CesiumGlobe'
import ColorScaleBar from '../components/3d/globe/ColorScaleBar'
import { inIndiaBox, nearestCell, domainFrom, isoLevelsFor, TEMP_DEFAULT_DOMAIN, SAL_DEFAULT_DOMAIN, CHL_LEGACY_DOMAIN } from '../components/3d/globe/layerMath'
import type { ScaleDomain, ScaleMode } from '../components/3d/globe/layerMath'
import type { GlobeLocation, SeriesRegion, StormTrackData, ArgoFloat, RealArgoFloat, ErsstLayer, ChlorLayer, DisagreementPoint, AnomalyPoint, TransectData, TideGlobeMarker, LayerKey, CurrentVector, ModelSlice, GliderDeployment, GliderSample, GliderTrack } from '../components/3d/globe/CesiumGlobe'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine } from 'recharts'
import TransectHUD from '../components/transect/TransectHUD'
import {
  fetchLocations, fetchObservations, fetchStormTrack, fetchSafetyTimeseries, fetchUncertainty,
  fetchRecommendations, fetchArgo, fetchRealArgoFloats, fetchArgoFloatProfile, fetchErsstLatest,
  fetchChlorLatest, fetchModelGridVectors, fetchModelGridSummary, fetchModelGridSlice,
  fetchGliderDeployments, fetchGliderSamples, fetchGliderBgc,
  fetchTwinCompare, fetchTwinExplain, fetchTwinProfile,
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
    realArgo: true,
    realSST: true,
    realChl: true,
    disagreement: true,
    anomalies: true,
    tide: false,
    isos: true,
    vectors: true,
    modelgrid: true,
    glider: false,
  })
  const [storm, setStorm] = useState<StormTrackData | null>(null)
  const [series, setSeries] = useState<SeriesRegion[]>([])
  const [uncertainties, setUncertainties] = useState<Record<number, number>>({})
  const [priorities, setPriorities] = useState<Record<number, number>>({})
  const [argoFloats, setArgoFloats] = useState<ArgoFloat[]>([])
  const [realArgoFloats, setRealArgoFloats] = useState<RealArgoFloat[]>([])
  const [ersstData, setErsstData] = useState<ErsstLayer | null>(null)
  const [chlorData, setChlorData] = useState<ChlorLayer | null>(null)
  const [sstScale, setSstScale] = useState<ScaleMode>('linear')
  const [chlScale, setChlScale] = useState<ScaleMode>('log')
  const [activeArgo, setActiveArgo] = useState<RealArgoFloat | null>(null)
  const [argoProfile, setArgoProfile] = useState<ArgoProfilePayload | null>(null)
  const [argoProfileBusy, setArgoProfileBusy] = useState(false)
  const [argoProfileError, setArgoProfileError] = useState<string | null>(null)
  const [cursor, setCursor] = useState<number>(0)
  const [playing, setPlaying] = useState(false)
  const [replayMode, setReplayMode] = useState<ReplayMode>('temp')

  // --- Globe visual style (features #12 layer opacity + #13 exaggeration) ---
  const [opacity, setOpacity] = useState<Partial<Record<LayerKey, number>>>({
    realSST: 1,
    realChl: 1,
    temperature: 1,
    waves: 1,
    currents: 1,
    realArgo: 1,
    isos: 1,
    vectors: 1,
    modelgrid: 1,
    glider: 1,
  })
  const [exaggeration, setExaggeration] = useState(1)

  // --- True current-velocity vectors (feature #14, real model-grid u/v) ---
  const [currentVectors, setCurrentVectors] = useState<CurrentVector[] | null>(null)
  const [vectorStatus, setVectorStatus] = useState<'loading' | 'ready' | 'nodata'>('loading')

  // --- Horizontal depth slices of the real model field (feature #7) ---
  const [gridVar, setGridVar] = useState<'temperature' | 'salinity'>('temperature')
  const [gridDepth, setGridDepth] = useState<number>(0)
  const [gridDepths, setGridDepths] = useState<number[]>([])
  const [gridSlice, setGridSlice] = useState<ModelSlice | null>(null)
  const [gridStatus, setGridStatus] = useState<'loading' | 'ready' | 'nodata'>('loading')
  const [gridScale, setGridScale] = useState<ScaleMode>('linear')

  // --- Real glider fleet + tracks (feature #16) ---
  const [gliderDeployments, setGliderDeployments] = useState<GliderDeployment[]>([])
  const [gliderTracks, setGliderTracks] = useState<GliderTrack[]>([])
  const [gliderStatus, setGliderStatus] = useState<'loading' | 'ready' | 'nodata'>('loading')
  const [gliderProfile, setGliderProfile] = useState<GliderProfileData | null>(null)
  const [gliderProfileBusy, setGliderProfileBusy] = useState(false)
  const [gliderProfileError, setGliderProfileError] = useState<string | null>(null)

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

    fetchRealArgoFloats()
      .then((d) => {
        const list: RealArgoFloat[] = d.floats ?? []
        setRealArgoFloats(list)
        if (list.length > 0) setActiveArgo(list[0])
      })
      .catch(() => {})

    fetchErsstLatest()
      .then((d: ErsstLayer) => setErsstData(d))
      .catch(() => {})

    fetchChlorLatest()
      .then((d: ChlorLayer) => setChlorData(d))
      .catch(() => {})

    // Feature #14: true u/v current vectors from the real ocean-model grid.
    fetchModelGridVectors(0)
      .then((d) => {
        if (d && d.available) {
          setCurrentVectors((d.cells ?? []).map((c: { latitude: number; longitude: number; u: number; v: number; speed?: number }) => (
            { latitude: c.latitude, longitude: c.longitude, u: c.u, v: c.v, speed: c.speed }
          )))
          setVectorStatus('ready')
        } else {
          setCurrentVectors(null)
          setVectorStatus('nodata')
        }
      })
      .catch(() => {
        setCurrentVectors(null)
        setVectorStatus('nodata')
      })

    // Feature #7: real depth levels available per model variable. The slice
    // itself is fetched by a dedicated effect whenever the selection changes.
    fetchModelGridSummary()
      .then((d) => {
        const fields = d.available_fields ?? {}
        const t = fields.temperature
        const s = fields.salinity
        const chosen: 'temperature' | 'salinity' | null = s?.available ? 'salinity' : t?.available ? 'temperature' : null
        const src = s?.available ? s : t
        const depths: number[] = (src?.levels ?? []).map((l: { depth_m: number }) => l.depth_m)
        if (!chosen || depths.length === 0) {
          setGridStatus('nodata')
          return
        }
        setGridVar(chosen)
        setGridDepths(depths)
        setGridDepth(depths[0])
      })
      .catch(() => setGridStatus('nodata'))

    // Feature #16: real glider deployments (tracks are fetched on layer open).
    fetchGliderDeployments()
      .then((d) => {
        const list: GliderDeployment[] = d.deployments ?? []
        setGliderDeployments(list)
        setGliderStatus(list.length > 0 ? 'ready' : 'nodata')
      })
      .catch(() => setGliderStatus('nodata'))

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

  // Fetch the selected variable+depth slice whenever the choice changes (feature #7).
  useEffect(() => {
    if (gridDepths.length === 0) return
    setGridStatus('loading')
    fetchModelGridSlice(gridVar, gridDepth)
      .then((sl: ModelSlice) => {
        setGridSlice(sl)
        setGridStatus(sl.available ? 'ready' : 'nodata')
      })
      .catch(() => {
        setGridSlice(null)
        setGridStatus('nodata')
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gridVar, gridDepth, gridDepths])

  // Fetch each deployment's real sample track when the glider layer turns on
  // (and only then — the tracks are the heaviest payload on the page).
  useEffect(() => {
    if (!layers.glider || gliderDeployments.length === 0) return
    const missing = gliderDeployments.filter(
      (d) => !gliderTracks.some((t) => t.deploymentId === d.deployment_id),
    )
    if (missing.length === 0) return
    for (const d of missing) {
      fetchGliderSamples(d.deployment_id)
        .then((resp) => {
          setGliderTracks((prev) => {
            if (prev.some((t) => t.deploymentId === d.deployment_id)) return prev
            return [...prev, { deploymentId: d.deployment_id, instrument: resp.instrument ?? null, samples: resp.samples ?? [] }]
          })
        })
        .catch(() => {})
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layers.glider, gliderDeployments])

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
    { key: 'realArgo' as const, icon: <Navigation size={16} />, name: 'Real Argo Floats', desc: 'Indian-Ocean in-situ floats · click for depth profile' },
    { key: 'realSST' as const, icon: <Satellite size={16} />, name: 'Real SST (ERSST)', desc: 'NOAA ERSST v5 · 2° grid · real measurements' },
    { key: 'realChl' as const, icon: <Orbit size={16} />, name: 'Satellite Chl (VIIRS)', desc: 'NOAA CoastWatch VIIRS·Himawari · 5 km · ocean colour' },
    { key: 'isos' as const, icon: <ScanLine size={16} />, name: 'SST Isolines', desc: 'Marching-squares isotherms of the real ERSST field' },
    { key: 'vectors' as const, icon: <Navigation size={16} />, name: 'Current Vectors', desc: 'True u/v arrows of the real model current field' },
    { key: 'modelgrid' as const, icon: <Layers size={16} />, name: 'Model Depth Slice', desc: 'One real model grid layer at the selected depth' },
    { key: 'glider' as const, icon: <Route size={16} />, name: 'Real Gliders', desc: 'Underwater-glider transects · click for depth profile' },
    { key: 'tide' as const, icon: <Radar size={16} />, name: 'TIDE Decisions', desc: 'Ranked observation recommendation markers' },
  ]

  // Feature #12: per-layer sliders in the Visual Style card, in display order.
  const OPACITY_ROWS: { key: LayerKey; label: string }[] = [
    { key: 'realSST', label: 'Real SST (ERSST)' },
    { key: 'realChl', label: 'Satellite Chl (VIIRS)' },
    { key: 'temperature', label: 'Sea Temperature' },
    { key: 'waves', label: 'Wave Height' },
    { key: 'currents', label: 'Ocean Currents' },
    { key: 'realArgo', label: 'Real Argo Floats' },
    { key: 'isos', label: 'SST Isolines' },
    { key: 'vectors', label: 'Current Vectors' },
    { key: 'modelgrid', label: 'Model Depth Slice' },
    { key: 'glider', label: 'Real Gliders' },
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

  const handleArgoFloatClick = (floatId: string) => {
    const flt = realArgoFloats.find((f) => f.float_id === floatId)
    if (flt) setActiveArgo(flt)
    setArgoProfile(null)
    setArgoProfileError(null)
    setArgoProfileBusy(true)
    fetchArgoFloatProfile(floatId)
      .then((p) => setArgoProfile(p as ArgoProfilePayload))
      .catch(() => setArgoProfileError('Argo profile request failed'))
      .finally(() => setArgoProfileBusy(false))
  }

  // Feature #16/#18: clicking a glider track opens its real sample profile.
  const handleGliderClick = (deploymentId: string) => {
    setGliderProfile(null)
    setGliderProfileError(null)
    setGliderProfileBusy(true)
    fetchGliderSamples(deploymentId)
      .then((d) => {
        // Also pull the real BGC traces (feature #17); merged in lockstep.
        setGliderProfile({
          deploymentId,
          instrument: d.instrument ?? null,
          samples: d.samples ?? [],
        })
        fetchGliderBgc(deploymentId)
          .then((b) => {
            setGliderProfile((prev) => (prev && prev.deploymentId === deploymentId
              ? { ...prev, bgc: { fields: b.fields ?? {}, samples: b.samples ?? [] } }
              : prev))
          })
          .catch(() => {})
      })
      .catch(() => setGliderProfileError('Glider sample request failed'))
      .finally(() => setGliderProfileBusy(false))
  }

  // Nearest real NOAA ERSST cell to the active region (Δ ≤ 3.5°, else unavailable).
  const realSstAtRegion = useMemo(() => {
    const samples = ersstData?.samples ?? []
    if (samples.length === 0 || !activeLoc?.latitude || !activeLoc.longitude) return null
    const hit = nearestCell(activeLoc.latitude, activeLoc.longitude, samples, 3.5)
    return hit ? { sst: hit.cell.sst, dist: hit.dist, lon: hit.cell.longitude, lat: hit.cell.latitude } : null
  }, [ersstData, activeLoc])

  // Nearest real satellite Chl-a cell to the active region (Δ ≤ 0.2°, else unavailable).
  const realChlorAtRegion = useMemo(() => {
    const samples = chlorData?.available ? (chlorData.samples ?? []) : []
    if (samples.length === 0 || !activeLoc?.latitude || !activeLoc.longitude) return null
    const hit = nearestCell(activeLoc.latitude, activeLoc.longitude, samples, 0.2)
    return hit ? { chl: hit.cell.chlor_a, dist: hit.dist, lon: hit.cell.longitude, lat: hit.cell.latitude } : null
  }, [chlorData, activeLoc])

  // --- Dynamic colour scales: data-driven min/max over the real grid cells ---
  const sstDomain: ScaleDomain = useMemo(() => {
    const s = ersstData?.stats
    const d = s && s.min !== null && s.max !== null ? domainFrom([s.min, s.max]) : null
    return d ?? TEMP_DEFAULT_DOMAIN
  }, [ersstData])

  const chlDomain: ScaleDomain = useMemo(() => {
    const s = chlorData?.stats
    const d = s && s.min !== null && s.max !== null ? domainFrom([s.min, s.max]) : null
    return d ?? CHL_LEGACY_DOMAIN
  }, [chlorData])

  // Feature #7: live domain over the selected depth-slice cells (+ fallback window).
  const gridDomain: ScaleDomain = useMemo(() => {
    const cells = gridSlice?.available ? (gridSlice.cells ?? []) : []
    const d = domainFrom(cells.map((c) => c.value))
    if (d) return d
    return gridVar === 'salinity' ? SAL_DEFAULT_DOMAIN : TEMP_DEFAULT_DOMAIN
  }, [gridSlice, gridVar])

  // Nearest real model cell to the active region at the selected depth (Δ ≤ 0.5°).
  const gridAtRegion = useMemo(() => {
    const cells = gridSlice?.available ? (gridSlice.cells ?? []) : []
    if (cells.length === 0 || !activeLoc?.latitude || !activeLoc.longitude) return null
    const hit = nearestCell(activeLoc.latitude, activeLoc.longitude, cells, 0.5)
    return hit ? { value: hit.cell.value, dist: hit.dist, lon: hit.cell.longitude, lat: hit.cell.latitude } : null
  }, [gridSlice, activeLoc])

  // Isosurface contour levels for the real ERSST field (feature #11).
  const isoLevels = useMemo(() => {
    const s = ersstData?.stats
    if (!s || s.min == null || s.max == null) return null
    return isoLevelsFor({ min: s.min, max: s.max }, 6)
  }, [ersstData])

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
            realArgoFloats={realArgoFloats}
            ersst={ersstData}
            chlor={chlorData}
            scaleModes={{ sst: sstScale, chl: chlScale, modelgrid: gridScale }}
            disagreement={disagreement}
            anomalies={anomalyRows.filter((a) => a.severity !== 'low').slice(0, 8)}
            tideCandidates={tideCandidates}
            opacity={opacity}
            exaggeration={exaggeration}
            isolevels={layers.isos ? isoLevels : null}
            currentVectors={layers.vectors ? currentVectors : null}
            modelSlice={layers.modelgrid ? gridSlice : null}
            gliderTracks={layers.glider ? gliderTracks : []}
            onGliderClick={handleGliderClick}
            onRegionClick={handleRegionClick}
            onArgoFloatClick={handleArgoFloatClick}
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

          {/* Visual style — per-layer opacity (feature #12) + exaggeration (#13) */}
          <div className="glass-card control-card">
            <div className="control-title">
              <Gauge size={16} />
              <span>Visual Style</span>
            </div>

            <div className="style-block">
              <div className="style-kicker">LAYER OPACITY</div>
              {OPACITY_ROWS.map(({ key, label }) => (
                <div key={key} className="opacity-row">
                  <span className="opacity-label">{label}</span>
                  <input
                    type="range"
                    min={0.1}
                    max={1}
                    step={0.05}
                    value={opacity[key] ?? 1}
                    onChange={(e) => setOpacity((p) => ({ ...p, [key]: Number(e.target.value) }))}
                    className="scrubber"
                    aria-label={`${label} opacity`}
                  />
                  <span className="opacity-value">{Math.round((opacity[key] ?? 1) * 100)}%</span>
                </div>
              ))}

              <div className="style-kicker">VERTICAL EXAGGERATION</div>
              <div className="opacity-row">
                <span className="opacity-label">Terrain / ocean relief</span>
                <input
                  type="range"
                  min={1}
                  max={8}
                  step={0.5}
                  value={exaggeration}
                  onChange={(e) => setExaggeration(Number(e.target.value))}
                  className="scrubber"
                  aria-label="Vertical exaggeration"
                />
                <span className="opacity-value">×{exaggeration.toFixed(1)}</span>
              </div>
            </div>
          </div>

          {/* Feature #14 — True current velocity vectors (real model-grid u/v) */}
          <div className="glass-card control-card">
            <div className="control-title">
              <Navigation size={16} />
              <span>Current Velocity Vectors</span>
              <span className="podium-count">
                {vectorStatus === 'ready' ? `${currentVectors?.length ?? 0} CELLS` : 'REAL U/V'}
              </span>
            </div>

            {vectorStatus === 'loading' ? (
              <div className="hint">Loading the real model-grid vectors…</div>
            ) : vectorStatus === 'ready' && currentVectors && currentVectors.length > 0 ? (
              <>
                <p className="argo-note">
                  True eastward (u) and northward (v) components of the real ocean-model surface
                  current — one arrow per grid cell of the latest model month. The globe draws the
                  strongest 600 cells; the field is never interpolated or guessed.
                </p>
                <div className="argo-chips">
                  <span className="argo-chip argo-chip-surface"><i /> VECTORS <b>{currentVectors.length}</b></span>
                  <span className="argo-chip argo-chip-mld"><i /> SURFACE <b>0 m</b></span>
                  <span className="argo-chip argo-chip-mld">
                    <i /> MAX <b>{Math.max(...currentVectors.map((v) => v.speed ?? 0)).toFixed(2)} m/s</b>
                  </span>
                </div>
              </>
            ) : (
              <div className="chl-pending">
                <b>No real u/v grid on this machine yet.</b>
                <p>
                  These arrows come from the true current field of the ocean-model 3D grid. Fetch and ingest
                  it on a networked host:
                </p>
                <code>python -m scripts.fetch_model --month 2021-09</code>
                <code>python -m scripts.ingest_netcdf backend/data/model/hycom_3d_2021-09.nc --reingest</code>
                <p className="argo-note">
                  Until then no arrows are drawn — the pipeline never fabricates current directions.
                </p>
              </div>
            )}
          </div>

          {/* Feature #16/#17 — Real glider fleet (transects + BGC-capable payloads) */}
          <div className="glass-card control-card">
            <div className="control-title">
              <Route size={16} />
              <span>Glider Fleet</span>
              <span className="podium-count">
                {gliderStatus === 'ready' ? `${gliderDeployments.length} DEPLOYMENTS` : 'REAL IN-SITU'}
              </span>
            </div>

            {gliderStatus === 'loading' ? (
              <div className="hint">Loading the real glider fleet…</div>
            ) : gliderStatus === 'nodata' || gliderDeployments.length === 0 ? (
              <div className="chl-pending">
                <b>No real glider deployments on this machine yet.</b>
                <p>
                  Glider transects come from real underwater-glider deployments (GliderDAC). Fetch and
                  ingest them on a networked host:
                </p>
                <code>python -m scripts.fetch_glider --yesterday</code>
                <code>python -m scripts.ingest_glider backend/data/glider/session/netCDF</code>
                <p className="argo-note">
                  Until then no transects are drawn — the twin never fabricates glider paths.
                </p>
              </div>
            ) : (
              <>
                <div className="glider-list">
                  {gliderDeployments.map((d) => {
                    const bgc = d.bgc_samples ?? {}
                    const anyBgc = Object.values(bgc).some((n) => (n ?? 0) > 0)
                    return (
                      <button
                        key={d.deployment_id}
                        className="glider-row"
                        onClick={() => handleGliderClick(d.deployment_id)}
                        title={`Click to open ${d.deployment_id} sample profile`}
                      >
                        <span className="glider-id">{d.deployment_id}</span>
                        <span className="glider-chips">
                          <span className="glider-chip"><i /> {d.samples} samples</span>
                          <span className="glider-chip"><i /> {d.depth_min_m ?? '?'}–{d.depth_max_m ?? '?'} m</span>
                          <span className="glider-chip"><i /> {d.time_start?.slice(0, 10) ?? '—'} → {d.time_end?.slice(0, 10) ?? '—'}</span>
                          {anyBgc && <span className="glider-chip glider-chip-bgc"><i /> BGC</span>}
                        </span>
                      </button>
                    )
                  })}
                </div>

                <p className="argo-note">
                  Real glider deployments (GliderDAC): each row is one instrument run with its true
                  sample extent. Clicking a row (or its track on the globe) opens the measured
                  temperature/salinity/depth profile. <b>BGC</b> marks deployments whose payload
                  carried bio-optical sensors (oxygen / chlorophyll / nitrate).
                </p>

                {gliderProfileBusy ? (
                  <div className="hint">Loading {gliderProfile?.deploymentId ?? 'glider'} samples…</div>
                ) : gliderProfileError ? (
                  <div className="redo-chip">{gliderProfileError}</div>
                ) : gliderProfile ? (
                  <GliderProfileChart profile={gliderProfile} />
                ) : null}
              </>
            )}
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

          {/* Real Argo floats — click a marker on the globe or a row below */}
          <div className="glass-card control-card">
            <div className="control-title">
              <Activity size={16} />
              <span>Argo Depth Profile</span>
              <span className="podium-count">{realArgoFloats.length} FLOAT{realArgoFloats.length === 1 ? '' : 'S'}</span>
            </div>

            {realArgoFloats.length === 0 ? (
              <div className="hint">Real Argo profiles are not loaded yet.</div>
            ) : (
              <>
                <div className="argo-list">
                  {realArgoFloats.map((f) => (
                    <button
                      key={f.float_id}
                      className={`argo-row ${activeArgo?.float_id === f.float_id ? 'argo-row-on' : ''}`}
                      onClick={() => handleArgoFloatClick(f.float_id)}
                    >
                      <span className="argo-pin" />
                      <span className="argo-txt">
                        <b>Float {f.float_id}</b>
                        <em>{argoArea(f.longitude)} · {f.levels} levels · max {fmtDepth(f.depth_max_m)}</em>
                      </span>
                      <span className="argo-go">{activeArgo?.float_id === f.float_id ? 'OPEN' : '›'}</span>
                    </button>
                  ))}
                </div>

                {activeArgo && (
                  <div className="argo-meta">
                    <span className="argo-meta-item">Lat {activeArgo.latitude?.toFixed(2)}°N · Lon {activeArgo.longitude?.toFixed(2)}°E</span>
                    <span className="argo-meta-item">Profile {fmtDate(activeArgo.latest_time)} UTC</span>
                    <span className="argo-meta-item argo-offshore">OFFSHORE · real in-situ data (data-argo.ifremer.fr)</span>
                  </div>
                )}

                {argoProfileBusy && (
                  <div className="transect-status">
                    <Loader2 size={13} className="spin" />
                    <span>Loading vertical profile…</span>
                  </div>
                )}

                {argoProfileError && <p className="transect-error">{argoProfileError}</p>}

                {!argoProfileBusy && argoProfile && <ArgoProfileChart data={argoProfile} />}
              </>
            )}
          </div>

          {/* Real NOAA ERSST v5 sea-surface-temperature grid */}
          <div className="glass-card control-card">
            <div className="control-title">
              <Satellite size={16} />
              <span>Real SST (NOAA ERSST v5)</span>
              {ersstData && (
                <span className="podium-count">{ersstData.time}</span>
              )}
            </div>

            {!ersstData ? (
              <div className="hint">Loading the real ERSST grid…</div>
            ) : (
              <>
                <div className="argo-chips">
                  <span className="argo-chip argo-chip-surface"><i /> GRID <b>{ersstData.resolution_deg}°</b></span>
                  <span className="argo-chip argo-chip-mld"><i /> CELLS <b>{ersstData.rows}</b></span>
                  <span className="argo-chip argo-chip-mld"><i /> INDIA-BOX <b>{ersstData.samples.filter((s) => inIndiaBox(s.latitude, s.longitude)).length}</b></span>
                </div>

                <div className="ersst-readout">
                  <span className="ersst-kicker">REAL SST AT ACTIVE REGION</span>
                  {realSstAtRegion ? (
                    <span className="ersst-value">
                      <b>{realSstAtRegion.sst.toFixed(1)} °C</b>
                      <em>cell {realSstAtRegion.lat.toFixed(1)}°,{realSstAtRegion.lon.toFixed(1)}° · Δ {realSstAtRegion.dist.toFixed(1)}°</em>
                    </span>
                  ) : (
                    <span className="ersst-value ersst-na">
                      <b>Data unavailable</b>
                      <em>no real ERSST cell within 3.5° of this location</em>
                    </span>
                  )}
                </div>

                <p className="argo-note">
                  NOAA ERSST v5 is a 2° × 2° monthly gridded analysis built from in-situ ship and buoy
                  observations (ICOADS). It is a historical archive — the newest month is{' '}
                  <b>{ersstData.time}</b> — not a live feed and not a satellite product. Colored dots on the
                  globe are the real cells, exactly as ingested (blank where the source had no cell).
                </p>

                <ColorScaleBar
                  label="ERSST v5 SST"
                  unit="°C"
                  domain={sstDomain}
                  mode={sstScale}
                  onModeChange={setSstScale}
                  value={realSstAtRegion?.sst ?? null}
                />
              </>
            )}
          </div>

          {/* Real satellite ocean-colour (NOAA CoastWatch VIIRS-Himawari) */}
          <div className="glass-card control-card">
            <div className="control-title">
              <Orbit size={16} />
              <span>Satellite Chl (VIIRS)</span>
              {chlorData?.available && (
                <span className="podium-count">{chlorData.time}</span>
              )}
            </div>

            {!chlorData ? (
              <div className="hint">Loading the real satellite Chl grid…</div>
            ) : !chlorData.available ? (
              <div className="chl-pending">
                <b>No satellite Chl data on this machine yet.</b>
                <p>
                  The real grid is NOAA CoastWatch Geo-Polar Blended VIIRS-Himawari ocean colour.
                  Fetch and ingest it on a networked host:
                </p>
                <code>python -m scripts.fetch_chlor</code>
                <code>python -m scripts.ingest_netcdf backend/data/chl_monthly_2021-09.nc --reingest</code>
                <p className="argo-note">
                  Until then no ocean colour is shown — the pipeline never fabricates satellite values.
                </p>
              </div>
            ) : (
              <>
                <div className="argo-chips">
                  <span className="argo-chip argo-chip-mld"><i /> GRID <b>{chlorData.resolution_deg}°</b></span>
                  <span className="argo-chip argo-chip-mld"><i /> CELLS <b>{chlorData.rows}</b></span>
                  <span className="argo-chip argo-chip-surface"><i /> INDIA-BOX <b>{chlorData.samples.filter((s) => inIndiaBox(s.latitude, s.longitude)).length}</b></span>
                </div>

                <div className="ersst-readout chl-readout">
                  <span className="ersst-kicker">REAL CHL-A AT ACTIVE REGION</span>
                  {realChlorAtRegion ? (
                    <span className="ersst-value">
                      <b>{realChlorAtRegion.chl.toFixed(2)} mg/m³</b>
                      <em>cell {realChlorAtRegion.lat.toFixed(2)}°,{realChlorAtRegion.lon.toFixed(2)}° · Δ {realChlorAtRegion.dist.toFixed(2)}°</em>
                    </span>
                  ) : (
                    <span className="ersst-value ersst-na">
                      <b>Data unavailable</b>
                      <em>no satellite Chl cell within 0.2° of this location</em>
                    </span>
                  )}
                </div>

                <p className="argo-note">
                  Real satellite ocean colour: NOAA CoastWatch Geo-Polar Blended VIIRS-Himawari-NPP
                  Chlorophyll-a (5 km), composited to a monthly mean over the Indian region by{' '}
                  <b>scripts.fetch_chlor</b>. The newest month is <b>{chlorData.time}</b> — an
                  archive, not a live feed. Dots on the globe are the real cells, exactly as ingested
                  (blank where the source had no retrieval).
                </p>

                <ColorScaleBar
                  label="Satellite Chl-a"
                  unit="mg/m³"
                  domain={chlDomain}
                  mode={chlScale}
                  onModeChange={setChlScale}
                  value={realChlorAtRegion?.chl ?? null}
                  stops={['#1d4ed8', '#16a34a', '#eab308']}
                />
              </>
            )}
          </div>

          {/* Feature #7 — Ocean-Model horizontal depth slices (real 3D grid) */}
          <div className="glass-card control-card">
            <div className="control-title">
              <Layers size={16} />
              <span>Model Depth Slices</span>
              <span className="podium-count">
                {gridStatus === 'ready' && gridSlice?.available ? gridSlice.month : '3D GRID'}
              </span>
            </div>

            {gridStatus === 'loading' ? (
              <div className="hint">Loading the real model slice…</div>
            ) : gridStatus === 'nodata' || !gridSlice?.available ? (
              <div className="chl-pending">
                <b>No real ocean-model grid on this machine yet.</b>
                <p>
                  Depth slices come from the true 3D fields of the ocean model (temperature /
                  salinity / current speed by depth level). Fetch and ingest them on a networked host:
                </p>
                <code>python -m scripts.fetch_model --month 2021-09</code>
                <code>python -m scripts.ingest_netcdf backend/data/model/hycom_3d_2021-09.nc --reingest</code>
                <p className="argo-note">
                  Until then no slice is drawn — the twin never fabricates a sub-surface field.
                </p>
              </div>
            ) : (
              <>
                <div className="slice-controls">
                  <div className="slice-field">
                    <span className="slice-kicker">VARIABLE</span>
                    <div className="slice-selects">
                      <button
                        className={`slice-pill ${gridVar === 'temperature' ? 'on' : ''}`}
                        onClick={() => setGridVar('temperature')}
                      >
                        Temperature
                      </button>
                      <button
                        className={`slice-pill ${gridVar === 'salinity' ? 'on' : ''}`}
                        onClick={() => setGridVar('salinity')}
                      >
                        Salinity
                      </button>
                    </div>
                  </div>
                  <div className="slice-field">
                    <span className="slice-kicker">DEPTH LEVEL</span>
                    <select
                      className="slice-select"
                      value={gridDepth}
                      onChange={(e) => setGridDepth(Number(e.target.value))}
                      aria-label="Model depth level"
                    >
                      {gridDepths.map((d) => (
                        <option key={d} value={d}>
                          {d === 0 ? 'Surface (0 m)' : `${d} m`}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="argo-chips">
                  <span className="argo-chip argo-chip-mld"><i /> MONTH <b>{gridSlice.month}</b></span>
                  <span className="argo-chip argo-chip-mld"><i /> DEPTH <b>{gridSlice.depth_m === 0 ? '0 m' : `${gridSlice.depth_m} m`}</b></span>
                  <span className="argo-chip argo-chip-surface"><i /> CELLS <b>{gridSlice.rows}</b></span>
                </div>

                <div className="ersst-readout chl-readout">
                  <span className="ersst-kicker">
                    MODEL {gridVar === 'salinity' ? 'SALINITY' : 'TEMP'} AT ACTIVE REGION
                  </span>
                  {gridAtRegion ? (
                    <span className="ersst-value">
                      <b>{gridAtRegion.value.toFixed(gridVar === 'salinity' ? 2 : 1)} {gridSlice.unit}</b>
                      <em>cell {gridAtRegion.lat.toFixed(2)}°,{gridAtRegion.lon.toFixed(2)}° · Δ {gridAtRegion.dist.toFixed(2)}°</em>
                    </span>
                  ) : (
                    <span className="ersst-value ersst-na">
                      <b>Data unavailable</b>
                      <em>no real model cell within 0.5° of this location at {gridSlice.depth_m === 0 ? 'the surface' : `${gridSlice.depth_m} m`}</em>
                    </span>
                  )}
                </div>

                <p className="argo-note">
                  One true horizontal slice of the real ocean-model 3D grid — {gridSlice.source}. The
                  latest month is <b>{gridSlice.month}</b>. Dots on the globe are the real cells at{' '}
                  {gridSlice.depth_m === 0 ? 'the surface' : `${gridSlice.depth_m} m`}, exactly as
                  ingested (blank where the source had no cell at that depth level).
                </p>

                <ColorScaleBar
                  label={gridVar === 'salinity' ? 'Model Salinity' : 'Model Temperature'}
                  unit={gridVar === 'salinity' ? 'PSU' : '°C'}
                  domain={gridDomain}
                  mode={gridScale}
                  onModeChange={setGridScale}
                  value={gridAtRegion?.value ?? null}
                  stops={gridVar === 'salinity' ? ['#1e40af', '#22d3ee'] : undefined}
                />
              </>
            )}
          </div>

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

/* ---------- Real glider deployment profile (feature #16/#18) ---------- */

interface GliderBgcSample {
  time: string
  depth_m: number
  dissolved_oxygen: number | null
  chlorophyll: number | null
  nitrate: number | null
}

interface GliderProfileData {
  deploymentId: string
  instrument?: string | null
  samples: GliderSample[]
  bgc?: { fields: Record<string, boolean>; samples: GliderBgcSample[] } | null
}

function GliderProfileChart({ profile }: { profile: GliderProfileData }) {
  const rows = (profile.samples ?? []).slice().sort((a, b) => a.depth_m - b.depth_m)
  if (rows.length === 0) {
    return <div className="hint">{profile.deploymentId} has no samples.</div>
  }
  const tempRows = rows.filter((r) => r.temperature != null)
  const saltRows = rows.filter((r) => r.salinity != null)
  const tipStyle = { background: '#0a1526', border: '1px solid rgba(34,211,238,0.35)', borderRadius: 8, fontSize: 11 }
  const axis = (tick: { value: number }) => `${tick.value} m`

  return (
    <div className="argo-charts">
      {profile.instrument && (
        <div className="argo-chips">
          <span className="argo-chip argo-chip-mld"><i /> INSTRUMENT <b>{profile.instrument}</b></span>
          <span className="argo-chip argo-chip-mld"><i /> SAMPLES <b>{rows.length}</b></span>
          <span className="argo-chip argo-chip-surface"><i /> DEPTH <b>{rows[0].depth_m.toFixed(0)}–{rows[rows.length - 1].depth_m.toFixed(0)} m</b></span>
        </div>
      )}
      <div className="argo-chart-block">
        <div className="argo-chart-label">TEMPERATURE (°C) · REAL GLIDER</div>
        <ResponsiveContainer width="100%" height={130}>
          <LineChart data={tempRows} margin={{ top: 4, right: 24, left: -10, bottom: 0 }}>
            <CartesianGrid stroke="rgba(120,190,255,0.12)" />
            <XAxis dataKey="temperature" type="number" domain={['auto', 'auto']} stroke="rgba(148,163,184,0.5)" tick={{ fill: '#94a3b8', fontSize: 9 }} tickFormatter={(v: number) => `${v}°`} />
            <YAxis dataKey="depth_m" type="number" reversed domain={[0, 'dataMax']} tickFormatter={axis} width={44} stroke="rgba(148,163,184,0.5)" tick={{ fill: '#94a3b8', fontSize: 9 }} />
            <Tooltip contentStyle={tipStyle} labelFormatter={(v) => `Temperature ${String(v)} °C`} formatter={(value) => [`${String(value)} m`, 'Depth']} />
            <Line dataKey="depth_m" name="Depth" stroke="#22d3ee" strokeWidth={2} dot={{ r: 1.4, fill: '#22d3ee' }} connectNulls={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
        {tempRows.length === 0 && <div className="hint">Temperature unavailable for this deployment.</div>}
      </div>
      <div className="argo-chart-block">
        <div className="argo-chart-label">SALINITY (PSU) · REAL GLIDER</div>
        <ResponsiveContainer width="100%" height={130}>
          <LineChart data={saltRows} margin={{ top: 4, right: 24, left: -10, bottom: 0 }}>
            <CartesianGrid stroke="rgba(120,190,255,0.12)" />
            <XAxis dataKey="salinity" type="number" domain={['auto', 'auto']} stroke="rgba(148,163,184,0.5)" tick={{ fill: '#94a3b8', fontSize: 9 }} tickFormatter={(v: number) => `${v}`} />
            <YAxis dataKey="depth_m" type="number" reversed domain={[0, 'dataMax']} tickFormatter={axis} width={44} stroke="rgba(148,163,184,0.5)" tick={{ fill: '#94a3b8', fontSize: 9 }} />
            <Tooltip contentStyle={tipStyle} labelFormatter={(v) => `Salinity ${String(v)} PSU`} formatter={(value) => [`${String(value)} m`, 'Depth']} />
            <Line dataKey="depth_m" name="Depth" stroke="#a78bfa" strokeWidth={2} dot={{ r: 1.4, fill: '#a78bfa' }} connectNulls={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
        {saltRows.length === 0 && <div className="hint">Salinity unavailable for this deployment.</div>}
      </div>

      {/* Feature #17 — real BGC traces (oxygen / chlorophyll / nitrate) */}
      {profile.bgc &&
        (() => {
          const b = profile.bgc
          const bgcCharts: (
            | { key: 'dissolved_oxygen'; label: string; color: string }
            | { key: 'chlorophyll'; label: string; color: string }
            | { key: 'nitrate'; label: string; color: string }
          )[] = [
            { key: 'dissolved_oxygen', label: 'DISSOLVED OXYGEN (mol m⁻³) · REAL', color: '#34d399' },
            { key: 'chlorophyll', label: 'CHLOROPHYLL (mg m⁻³) · REAL', color: '#eab308' },
            { key: 'nitrate', label: 'NITRATE (mmol m⁻³) · REAL', color: '#a78bfa' },
          ]
          const present = bgcCharts.filter((c) => b.fields[c.key] && b.samples.some((s) => s[c.key] != null))

          if (present.length === 0) {
            return <div className="hint">This deployment carried no BGC sensors (oxygen / chlorophyll / nitrate).</div>
          }
          return (
            <>
              {present.map((c) => {
                const rows = b.samples
                  .filter((s) => s[c.key] != null)
                  .map((s) => ({ depth_m: s.depth_m, value: s[c.key] as number }))
                return (
                  <div key={c.key} className="argo-chart-block">
                    <div className="argo-chart-label">{c.label}</div>
                    <ResponsiveContainer width="100%" height={110}>
                      <LineChart data={rows} margin={{ top: 4, right: 24, left: -10, bottom: 0 }}>
                        <CartesianGrid stroke="rgba(120,190,255,0.12)" />
                        <XAxis dataKey="value" type="number" domain={['auto', 'auto']} stroke="rgba(148,163,184,0.5)" tick={{ fill: '#94a3b8', fontSize: 9 }} />
                        <YAxis dataKey="depth_m" type="number" reversed domain={[0, 'dataMax']} tickFormatter={axis} width={44} stroke="rgba(148,163,184,0.5)" tick={{ fill: '#94a3b8', fontSize: 9 }} />
                        <Tooltip contentStyle={tipStyle} labelFormatter={(v) => `${c.key.replace('_', ' ').toUpperCase()} ${String(v)}`} formatter={(value) => [`${String(value)} m`, 'Depth']} />
                        <Line dataKey="depth_m" name="Depth" stroke={c.color} strokeWidth={2} dot={{ r: 1.4, fill: c.color }} connectNulls={false} isAnimationActive={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )
              })}
            </>
          )
        })()}

      <p className="argo-note">
        Real measurements from deployment <b>{profile.deploymentId}</b>, ordered by depth. Values are
        exactly as ingested — gaps mean the sensor or sample was absent in the source file.
      </p>
    </div>
  )
}

/* ---------- Real Argo float depth profile (feature: click marker → chart) ---------- */

interface ArgoProfileLevel {
  depth_m: number
  temperature: number | null
  salinity: number | null
  pressure: number | null
}

interface ArgoProfilePayload {
  float_id: string
  time: string
  latitude: number | null
  longitude: number | null
  levels: ArgoProfileLevel[]
}

const argoArea = (lon: number | null): string =>
  lon == null ? 'Indian Ocean (offshore)' : lon < 80 ? 'Arabian Sea (offshore)' : 'Bay of Bengal (offshore)'

const fmtDepth = (d: number | null): string => (d == null ? '—' : `${Math.round(d)} m`)
const fmtDate = (t: string): string => {
  const d = new Date(t)
  if (Number.isNaN(d.getTime())) return t
  return d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

interface MldSummary {
  surfaceTemp: number | null
  surfaceDepthM: number | null
  mldM: number | null
  maxDepthM: number
}

/** Mixed-layer depth: first depth where temperature is ≥ 0.2 °C cooler than
 *  the shallowest sampled level (standard ΔT = 0.2 °C criterion). */
function computeMld(levels: ArgoProfileLevel[]): MldSummary {
  const withTemp = levels
    .filter((l) => l.temperature != null)
    .sort((a, b) => a.depth_m - b.depth_m)
  const maxDepthM = withTemp.length > 0 ? withTemp[withTemp.length - 1].depth_m : 0
  if (withTemp.length === 0) return { surfaceTemp: null, surfaceDepthM: null, mldM: null, maxDepthM }
  const ref = withTemp[0]
  const threshold = ref.temperature! - 0.2
  const hit = withTemp.find((l) => l.temperature! <= threshold)
  return { surfaceTemp: ref.temperature!, surfaceDepthM: ref.depth_m, mldM: hit ? hit.depth_m : null, maxDepthM }
}

/** Real Argo temperature + salinity vs depth, drawn with recharts.
 *  Depth runs up the (inverted) vertical axis so the surface is on top. */
function ArgoProfileChart({ data }: { data: ArgoProfilePayload }) {
  const levels = data.levels ?? []
  if (levels.length === 0) return <div className="hint">This float has no profile levels.</div>
  const tempRows = levels.filter((l) => l.temperature != null)
  const saltRows = levels.filter((l) => l.salinity != null)
  const hasTemp = tempRows.length > 0
  const hasSalt = saltRows.length > 0
  const s = computeMld(levels)
  const surfaceUnsampled = s.surfaceDepthM != null && s.surfaceDepthM > 2

  const axis = (tick: { value: number }) => `${tick.value} m`
  const tipStyle = { background: '#0a1526', border: '1px solid rgba(34,211,238,0.35)', borderRadius: 8, fontSize: 11 }

  return (
    <div className="argo-charts">
      {s.surfaceTemp != null && (
        <div className="argo-chips">
          <span
            className="argo-chip argo-chip-surface"
            title={
              surfaceUnsampled
                ? `Shallowest sample at ${s.surfaceDepthM!.toFixed(0)} m — the surface above it was not sampled by this float`
                : 'Temperature at the surface (shallowest sampled level)'
            }
          >
            <i /> SURFACE <b>{s.surfaceTemp.toFixed(1)} °C</b>
            {surfaceUnsampled && <em>ref @ {s.surfaceDepthM!.toFixed(0)} m</em>}
          </span>
          <span
            className={`argo-chip argo-chip-mld ${s.mldM == null ? 'argo-chip-na' : ''}`}
            title="Mixed-layer depth: first depth where temperature is ≥ 0.2 °C cooler than the shallowest sample"
          >
            <i /> MLD {s.mldM != null ? <b>{Math.round(s.mldM)} m</b> : <b>below {Math.round(s.maxDepthM)} m</b>}
            <em>ΔT 0.2 °C</em>
          </span>
        </div>
      )}

      <div className="argo-chart-block">
        <div className="argo-chart-label">TEMPERATURE (°C) · REAL</div>
        <ResponsiveContainer width="100%" height={130}>
          <LineChart data={tempRows} margin={{ top: 4, right: 24, left: -10, bottom: 0 }}>
            <CartesianGrid stroke="rgba(120,190,255,0.12)" />
            <XAxis dataKey="temperature" type="number" domain={['auto', 'auto']} stroke="rgba(148,163,184,0.5)" tick={{ fill: '#94a3b8', fontSize: 9 }} tickFormatter={(v: number) => `${v}°`} />
            <YAxis dataKey="depth_m" type="number" reversed domain={[0, 'dataMax']} tickFormatter={axis} width={44} stroke="rgba(148,163,184,0.5)" tick={{ fill: '#94a3b8', fontSize: 9 }} />
            <Tooltip
              contentStyle={tipStyle}
              labelFormatter={(v) => `Temperature ${String(v)} °C`}
              formatter={(value) => [`${String(value)} m`, 'Depth']}
            />
            <Line dataKey="depth_m" name="Depth" stroke="#22d3ee" strokeWidth={2} dot={{ r: 1.6, fill: '#22d3ee' }} connectNulls={false} isAnimationActive={false} />
            {s.mldM != null && (
              <ReferenceLine
                y={s.mldM}
                stroke="#f472b6"
                strokeDasharray="4 3"
                strokeWidth={1.5}
                label={{ value: 'MLD', fill: '#f472b6', fontSize: 9, position: 'insideRight' }}
              />
            )}
          </LineChart>
        </ResponsiveContainer>
        {!hasTemp && <div className="hint">Temperature unavailable for this float.</div>}
      </div>

      <div className="argo-chart-block">
        <div className="argo-chart-label">SALINITY (PSU) · REAL</div>
        <ResponsiveContainer width="100%" height={130}>
          <LineChart data={saltRows} margin={{ top: 4, right: 16, left: -10, bottom: 0 }}>
            <CartesianGrid stroke="rgba(120,190,255,0.12)" />
            <XAxis dataKey="salinity" type="number" domain={['auto', 'auto']} stroke="rgba(148,163,184,0.5)" tick={{ fill: '#94a3b8', fontSize: 9 }} tickFormatter={(v: number) => `${v}`} />
            <YAxis dataKey="depth_m" type="number" reversed domain={[0, 'dataMax']} tickFormatter={axis} width={44} stroke="rgba(148,163,184,0.5)" tick={{ fill: '#94a3b8', fontSize: 9 }} />
            <Tooltip
              contentStyle={tipStyle}
              labelFormatter={(v) => `Salinity ${String(v)} PSU`}
              formatter={(value) => [`${String(value)} m`, 'Depth']}
            />
            <Line dataKey="depth_m" name="Depth" stroke="#f59e0b" strokeWidth={2} dot={{ r: 1.6, fill: '#f59e0b' }} connectNulls={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
        {!hasSalt && <div className="hint">Salinity unavailable for this float.</div>}
      </div>

      <div className="argo-note">
        Depth axis is inverted — the surface (0 m) is at the top. The pink MLD line marks the first level at least
        0.2 °C cooler than the shallowest sample (if that float did not sample to 0 m, the note is shown on the chip).
        Where the source file had no value, the curve is blank (data unavailable) rather than guessed.
      </div>
    </div>
  )
}