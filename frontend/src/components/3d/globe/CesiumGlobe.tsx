import { useEffect, useRef } from 'react'
import 'cesium/Build/Cesium/Widgets/widgets.css'
import './CesiumGlobe.css'
import type { TideCandidate } from '../../../types/tide'
import {
  arrowFor,
  buildLatLonField,
  chlorColorCssFrom,
  depthColorCss,
  domainFrom,
  isoLines,
  salColorCssFrom,
  tempColorCssFrom,
  tempColorCss,
  type ScaleMode,
  type CurrentVectorCell,
} from './layerMath'

/**
 * CesiumGlobe
 * =============
 * The 3D ocean digital twin rendered with Cesium (real satellite imagery,
 * true coastlines, terrain-aware markers). All data layers live here:
 *   - labels      : floating region name tags
 *   - temperature : translucent heat patches colored by real SST
 *   - waves       : expanding ripple rings around each coast
 *   - currents    : glowing flow arcs + dots streaming along ocean orbits
 *   - storm       : simulated cyclone path, confidence cone + moving eye
 *
 * An optional time-cursor (driven by the globe timeline scrubber) recolors
 * the temperature patches from a merged observation+forecast series.
 *
 * Cesium is loaded dynamically so its base URL / runtime workers can be
 * configured before the module evaluates.
 */

export interface GlobeLocation {
  id: number
  name: string
  country?: string
  region_type?: string
  latitude: number | null
  longitude: number | null
  temperature?: number | null
  wave_height?: number | null
}

export type LayerKey =
  | 'labels'
  | 'temperature'
  | 'waves'
  | 'currents'
  | 'storm'
  | 'uncertainty'
  | 'priority'
  | 'argo'
  | 'realArgo'
  | 'realSST'
  | 'realChl'
  | 'disagreement'
  | 'anomalies'
  | 'tide'
  | 'isos'
  | 'vectors'
  | 'modelgrid'
  | 'glider'
export type LayersState = Record<LayerKey, boolean>

/** One merged observation/forecast point used by the time scrubber. */
export interface TimedPoint {
  time: string
  temperature: number | null
  wave: number | null
  forecast?: boolean
}

/** Per-coast merged timeline (from /api/v1/safety/timeseries). */
export interface SeriesRegion {
  location_id: number
  location: string
  points: TimedPoint[]
}

/** Simulated cyclone track (from /api/v1/safety/storm). */
export interface StormTrackData {
  id?: string
  name?: string
  headline?: string
  points: { hour?: number; time?: string; lat: number; lon: number; wind_kmh?: number; radius_km?: number }[]
}

/** Argo float trajectory point (from /api/v1/apex/argo). */
export interface ArgoPoint {
  lat: number
  lon: number
  depth_m: number
  timestamp: string
  temperature: number
  salinity: number
}

export interface ArgoFloat {
  float_id: string
  label: string
  location_id: number
  location: string
  points: ArgoPoint[]
}

/** Real Argo float, latest known position (from /api/v1/argo/floats). */
export interface RealArgoFloat {
  float_id: string
  latest_time: string
  latitude: number | null
  longitude: number | null
  depth_min_m: number | null
  depth_max_m: number | null
  levels: number
}

/** One real NOAA ERSST v5 grid cell (from /api/v1/ersst/latest). */
export interface ErsstSample {
  latitude: number
  longitude: number
  sst: number
}

/** Real-grid value summary (min/max range drives a dynamic colour scale). */
export interface GridStats {
  min: number | null
  max: number | null
  count: number
}

/** The latest real ERSST month grid + coverage summary. */
export interface ErsstLayer {
  time: string
  months: string[]
  resolution_deg: number
  source: string
  rows: number
  stats?: GridStats | null
  samples: ErsstSample[]
}

/** One true current velocity vector (from /api/v1/modelgrid/vectors). */
export interface CurrentVector extends CurrentVectorCell {
  speed?: number
}

/** One cell of a horizontal model-grid depth slice. */
export interface ModelSliceCell {
  latitude: number
  longitude: number
  value: number
}

/**
 * One horizontal depth slice of the latest real ocean-model month (feature #7).
 * Honest: `available:false` (with `reason`) until the real grid / that depth
 * level exists; the globe paints nothing in that case.
 */
export interface ModelSlice {
  available: boolean
  variable: string
  month: string
  unit: string
  source: string
  depth_m: number
  depths: number[]
  rows: number
  reason?: string | null
  cells: ModelSliceCell[]
}

/** One real glider deployment (headline extent + BGC sensor presence). */
export interface GliderDeployment {
  deployment_id: string
  samples: number
  time_start?: string | null
  time_end?: string | null
  depth_min_m?: number | null
  depth_max_m?: number | null
  lat_min?: number | null
  lat_max?: number | null
  lon_min?: number | null
  lon_max?: number | null
  bgc_samples?: { dissolved_oxygen?: number; chlorophyll?: number; nitrate?: number }
}

/** One real glider measurement along the deployment trajectory. */
export interface GliderSample {
  time: string
  latitude: number
  longitude: number
  depth_m: number
  temperature: number | null
  salinity: number | null
  pressure: number | null
}

/** A tracked deployment: its real sample positions, in time order. */
export interface GliderTrack {
  deploymentId: string
  instrument?: string | null
  samples: GliderSample[]
}

/** One real satellite Chlorophyll-a grid cell (from /api/v1/chlor/latest). */
export interface ChlorSample {
  latitude: number
  longitude: number
  chlor_a: number
}

/** The latest real satellite Chl month grid + coverage summary. */
export interface ChlorLayer {
  time: string
  months: string[]
  resolution_deg: number
  source: string
  rows: number
  stats?: GridStats | null
  available?: boolean
  error?: string
  samples: ChlorSample[]
}

/** Per-region model-vs-observation disagreement (from /api/v1/twin/disagreement). */
export interface DisagreementPoint {
  location_id: number
  location: string
  latitude: number | null
  longitude: number | null
  variable: string
  model: number | null
  observed: number | null
  difference: number | null
  percent_difference: number | null
  status: string
  severity: string
  band: string
  confidence: number | null
  confidence_level?: string
  data_status: string
}

/** Ranked anomaly marker (from /api/v1/twin/anomalies). */
export interface AnomalyPoint {
  location_id: number
  location: string
  latitude: number | null
  longitude: number | null
  variable: string
  label: string
  unit: string
  model: number | null
  observed: number | null
  difference: number | null
  severity: string
  confidence: number
  score: number
  data_status?: string
}

/** TIDE observation candidate marker (from /api/v1/tide/candidates). */
export interface TideGlobeMarker extends TideCandidate {
  /** Display rank within the current candidate list (1 = top priority). */
  rank?: number
}

/** Phase 6 — Decision Replay marker on the shared globe. */
export interface ReplayGlobeMarker {
  id: string
  lat: number
  lon: number
  label: string
  /** event = detected ocean event location · candidate = TIDE next observation ·
   *  observation = simulated observation location (SIMULATED). */
  kind: 'event' | 'candidate' | 'observation'
  /** Show only while the replay is on (or past) the relevant step. */
  visible: boolean
  /** sprite sub-label, e.g. the TIDE rank number. */
  sub?: string
  /** Real location id so clicking the marker focuses that region on the replay. */
  location_id?: number
}

/** One vertical column of the 3D transect curtain (from /api/v1/twin/transect). */
export interface TransectSample {
  lat: number
  lon: number
  distance_km: number
  surface_temp: number | null
  surface_data_status: string
  surface_coverage: string
  surface_hint: string
  thermocline: {
    mixed_layer_depth: number | null
    thermocline_depth: number
    strength_c_per_m: number | null
    isotherm_20_c: number | null
  }
  values: (number | null)[]
}

/** Argo profiler float intersecting the transect buffer (in-situ vs model). */
export interface TransectArgo {
  float_id: string
  label: string
  location: string
  latitude: number
  longitude: number
  distance_km: number
  max_depth_m: number
  in_situ: { depths: number[]; temperature: (number | null)[]; salinity: (number | null)[] }
  model: { depths: number[]; temperature: (number | null)[]; salinity: (number | null)[] }
  difference_temperature: (number | null)[]
  data_status: string
  source: string
}

/** Full 3D vertical transect 'curtain' payload. */
export interface TransectData {
  a: { lat: number; lon: number }
  b: { lat: number; lon: number }
  distance_km: number
  variable: string
  label: string
  unit: string
  depth_max_m: number
  depths: number[]
  samples: TransectSample[]
  surface_series: (number | null)[]
  argos: TransectArgo[]
  thermocline_polyline: { lat: number; lon: number; depth_m: number }[]
  notes?: Record<string, string>
  /** Present when the transect is invalid (points too close, etc.). */
  error?: string
}

type CesiumModule = typeof import('cesium')
type Viz = InstanceType<CesiumModule['Viewer']>
type VizEntity = InstanceType<CesiumModule['Entity']>
/** Cesium wraps raw booleans into ConstantProperty at runtime; TS types lag it. */
type Showable = { show: boolean }

/**
 * Built-in fallback coasts, so the globe is always "marked" even if the
 * backend API hasn't loaded yet. Mirrors the seed data.
 */
const FALLBACK_LOCATIONS: GlobeLocation[] = [
  { id: 1, name: 'Arabian Sea (Mumbai Coast)', latitude: 18.9, longitude: 72.0, temperature: 28.6, wave_height: 1.4 },
  { id: 2, name: 'Bay of Bengal (Chennai Coast)', latitude: 13.0, longitude: 80.3, temperature: 29.2, wave_height: 1.1 },
  { id: 3, name: 'Gulf of Mannar', latitude: 9.0, longitude: 78.5, temperature: 29.5, wave_height: 0.8 },
  { id: 4, name: 'Kerala Coast (Kochi)', latitude: 9.9, longitude: 76.3, temperature: 28.8, wave_height: 1.2 },
  { id: 5, name: 'Goa Coast (Panaji)', latitude: 15.5, longitude: 73.8, temperature: 28.5, wave_height: 1.3 },
  { id: 6, name: 'Andaman Sea', latitude: 11.5, longitude: 92.5, temperature: 29.8, wave_height: 1.0 },
  { id: 7, name: 'Lakshadweep Sea', latitude: 10.5, longitude: 72.5, temperature: 29.0, wave_height: 1.1 },
  { id: 8, name: 'Odisha Coast (Puri)', latitude: 19.8, longitude: 85.8, temperature: 28.2, wave_height: 1.5 },
]

let cesiumPromise: Promise<CesiumModule> | null = null
function loadCesium(): Promise<CesiumModule> {
  if (!cesiumPromise) {
    ;(globalThis as Record<string, unknown>).CESIUM_BASE_URL = '/cesium/'
    cesiumPromise = import('cesium')
  }
  return cesiumPromise
}

/* ------------------ shared sprite textures ------------------ */

let beaconUrl: string | null = null
/** Target beacon: white core + cyan ring + glow. */
function getBeaconUrl() {
  if (beaconUrl) return beaconUrl
  const size = 128
  const c = document.createElement('canvas')
  c.width = c.height = size
  const ctx = c.getContext('2d')!
  const cx = size / 2
  const g = ctx.createRadialGradient(cx, cx, 0, cx, cx, 56)
  g.addColorStop(0, 'rgba(255,255,255,1)')
  g.addColorStop(0.22, 'rgba(103,232,249,0.95)')
  g.addColorStop(0.5, 'rgba(34,211,238,0.35)')
  g.addColorStop(1, 'rgba(34,211,238,0)')
  ctx.fillStyle = g
  ctx.beginPath(); ctx.arc(cx, cx, 56, 0, Math.PI * 2); ctx.fill()
  ctx.strokeStyle = 'rgba(103,232,249,0.95)'
  ctx.lineWidth = 5
  ctx.beginPath(); ctx.arc(cx, cx, 50, 0, Math.PI * 2); ctx.stroke()
  ctx.strokeStyle = 'rgba(255,255,255,0.75)'
  ctx.lineWidth = 2
  ctx.beginPath(); ctx.arc(cx, cx, 38, 0, Math.PI * 2); ctx.stroke()
  ctx.fillStyle = '#ffffff'
  ctx.beginPath(); ctx.arc(cx, cx, 6, 0, Math.PI * 2); ctx.fill()
  beaconUrl = c.toDataURL()
  return beaconUrl
}

let dotUrl: string | null = null
/** Soft glowing dot for current streams. */
function getDotUrl() {
  if (dotUrl) return dotUrl
  const size = 64
  const c = document.createElement('canvas')
  c.width = c.height = size
  const ctx = c.getContext('2d')!
  const cx = size / 2
  const g = ctx.createRadialGradient(cx, cx, 0, cx, cx, cx)
  g.addColorStop(0, 'rgba(255,255,255,1)')
  g.addColorStop(0.4, 'rgba(165,243,252,0.9)')
  g.addColorStop(1, 'rgba(165,243,252,0)')
  ctx.fillStyle = g
  ctx.beginPath(); ctx.arc(cx, cx, cx, 0, Math.PI * 2); ctx.fill()
  dotUrl = c.toDataURL()
  return dotUrl
}

let stormEyeUrl: string | null = null
/** Cyclone eye: amber core with a red tracking ring. */
function getStormEyeUrl() {
  if (stormEyeUrl) return stormEyeUrl
  const size = 128
  const c = document.createElement('canvas')
  c.width = c.height = size
  const ctx = c.getContext('2d')!
  const cx = size / 2
  const g = ctx.createRadialGradient(cx, cx, 0, cx, cx, 56)
  g.addColorStop(0, 'rgba(255,255,255,1)')
  g.addColorStop(0.25, 'rgba(251,191,36,0.95)')
  g.addColorStop(0.6, 'rgba(244,114,182,0.45)')
  g.addColorStop(1, 'rgba(244,114,182,0)')
  ctx.fillStyle = g
  ctx.beginPath(); ctx.arc(cx, cx, 56, 0, Math.PI * 2); ctx.fill()
  ctx.strokeStyle = 'rgba(251,191,36,0.95)'
  ctx.lineWidth = 5
  ctx.beginPath(); ctx.arc(cx, cx, 48, 0, Math.PI * 2); ctx.stroke()
  ctx.strokeStyle = 'rgba(244,114,182,0.8)'
  ctx.lineWidth = 2
  ctx.beginPath(); ctx.arc(cx, cx, 38, 0, Math.PI * 2); ctx.stroke()
  ctx.fillStyle = '#ffffff'
  ctx.beginPath(); ctx.arc(cx, cx, 8, 0, Math.PI * 2); ctx.fill()
  stormEyeUrl = c.toDataURL()
  return stormEyeUrl
}

/** Deviation palette: cool (reality below model) -> neutral -> warm (above). */
function deviationColor(Cesium: CesiumModule, dev: number) {
  const cool = Cesium.Color.fromCssColorString('#22d3ee')
  const neutral = Cesium.Color.fromCssColorString('#a7b6c8')
  const warm = Cesium.Color.fromCssColorString('#f43f5e')
  const span = 2.0
  const c = Cesium.Math.clamp(dev, -span, span)
  if (c < 0) return Cesium.Color.lerp(neutral, cool, -c / span, new Cesium.Color())
  return Cesium.Color.lerp(neutral, warm, c / span, new Cesium.Color())
}

/** Disagreement band palette used by the model-vs-observation globe layer. */
function bandColor(Cesium: CesiumModule, band: string | undefined) {
  switch (band) {
    case 'red':
      return Cesium.Color.fromCssColorString('#f43f5e')
    case 'orange':
      return Cesium.Color.fromCssColorString('#f97316')
    case 'yellow':
      return Cesium.Color.fromCssColorString('#eab308')
    case 'green':
      return Cesium.Color.fromCssColorString('#10b981')
    case 'no data':
    case 'unknown':
      return Cesium.Color.fromCssColorString('#64748b')
    default:
      return Cesium.Color.fromCssColorString('#22d3ee')
  }
}

let anomalySpriteCache: Record<string, string> = {}

function getAnomalySprite(severity: string) {
  const key = severity || 'medium'
  if (anomalySpriteCache[key]) return anomalySpriteCache[key]
  const size = 96
  const c = document.createElement('canvas')
  c.width = c.height = size
  const ctx = c.getContext('2d')!
  const cx = size / 2
  const color =
    key === 'high' ? '#f43f5e' : key === 'medium' ? '#f59e0b' : key === 'low' ? '#22d3ee' : '#64748b'
  // Filled diamond beacon with a softly pulsing ring.
  const g = ctx.createRadialGradient(cx, cx, 0, cx, cx, 46)
  g.addColorStop(0, 'rgba(255,255,255,0.95)')
  g.addColorStop(0.25, color + 'cc')
  g.addColorStop(1, color + '00')
  ctx.fillStyle = g
  ctx.beginPath()
  ctx.arc(cx, cx, 46, 0, Math.PI * 2)
  ctx.fill()
  ctx.save()
  ctx.translate(cx, cx)
  ctx.rotate(Math.PI / 4)
  ctx.fillStyle = color
  ctx.shadowColor = color
  ctx.shadowBlur = 14
  ctx.fillRect(-12, -12, 24, 24)
  ctx.restore()
  ctx.fillStyle = '#ffffff'
  ctx.beginPath()
  ctx.arc(cx, cx, 5, 0, Math.PI * 2)
  ctx.fill()
  anomalySpriteCache[key] = c.toDataURL()
  return anomalySpriteCache[key]
}

let tideSpriteUrl: string | null = null
/** TIDE decision marker: turquoise diamond + soft cyan halo + white core. */
function getTideSprite() {
  if (tideSpriteUrl) return tideSpriteUrl
  const size = 96
  const c = document.createElement('canvas')
  c.width = c.height = size
  const ctx = c.getContext('2d')!
  const cx = size / 2
  const tint = '#22d3ee'
  const g = ctx.createRadialGradient(cx, cx, 0, cx, cx, 46)
  g.addColorStop(0, 'rgba(255,255,255,0.95)')
  g.addColorStop(0.28, tint + 'cc')
  g.addColorStop(1, tint + '00')
  ctx.fillStyle = g
  ctx.beginPath()
  ctx.arc(cx, cx, 46, 0, Math.PI * 2)
  ctx.fill()
  // Diamond "decision" marker.
  ctx.save()
  ctx.translate(cx, cx)
  ctx.rotate(Math.PI / 4)
  ctx.fillStyle = tint
  ctx.shadowColor = tint
  ctx.shadowBlur = 12
  ctx.fillRect(-13, -13, 26, 26)
  ctx.restore()
  // Target cross on top.
  ctx.strokeStyle = 'rgba(165,243,252,0.9)'
  ctx.lineWidth = 3
  ctx.beginPath()
  ctx.moveTo(cx, cx - 26)
  ctx.lineTo(cx, cx + 26)
  ctx.moveTo(cx - 26, cx)
  ctx.lineTo(cx + 26, cx)
  ctx.stroke()
  ctx.fillStyle = '#ffffff'
  ctx.beginPath()
  ctx.arc(cx, cx, 5, 0, Math.PI * 2)
  ctx.fill()
  tideSpriteUrl = c.toDataURL()
  return tideSpriteUrl
}

let obsSpriteUrl: string | null = null
/** Phase 6 — simulated observation marker: rose diamond + soft halo + white core. */
function getObsSprite() {
  if (obsSpriteUrl) return obsSpriteUrl
  const size = 96
  const c = document.createElement('canvas')
  c.width = c.height = size
  const ctx = c.getContext('2d')!
  const cx = size / 2
  const tint = '#fb7185'
  const g = ctx.createRadialGradient(cx, cx, 0, cx, cx, 46)
  g.addColorStop(0, 'rgba(255,255,255,0.95)')
  g.addColorStop(0.28, tint + 'cc')
  g.addColorStop(1, tint + '00')
  ctx.fillStyle = g
  ctx.beginPath()
  ctx.arc(cx, cx, 46, 0, Math.PI * 2)
  ctx.fill()
  // Diamond "observation" marker.
  ctx.save()
  ctx.translate(cx, cx)
  ctx.rotate(Math.PI / 4)
  ctx.fillStyle = tint
  ctx.shadowColor = tint
  ctx.shadowBlur = 12
  ctx.fillRect(-13, -13, 26, 26)
  ctx.restore()
  // Inner ring (distinct from the TIDE cross).
  ctx.strokeStyle = 'rgba(254,205,211,0.9)'
  ctx.lineWidth = 3
  ctx.beginPath()
  ctx.arc(cx, cx, 18, 0, Math.PI * 2)
  ctx.stroke()
  ctx.fillStyle = '#ffffff'
  ctx.beginPath()
  ctx.arc(cx, cx, 5, 0, Math.PI * 2)
  ctx.fill()
  obsSpriteUrl = c.toDataURL()
  return obsSpriteUrl
}

/** Rolling 12h baseline of a region's merged timeline up to (excluding) idx. */
function rollingBaseline(reg: SeriesRegion, idx: number): number | null {
  const windowPoints = reg.points.slice(Math.max(0, idx - 12), idx)
  const temps = windowPoints.map((p) => p.temperature).filter((t): t is number => t != null)
  if (temps.length === 0) return null
  return temps.reduce((a, b) => a + b, 0) / temps.length
}

type Cartesian2 = InstanceType<CesiumModule['Cartesian2']>

/* ------------------ component ------------------ */

interface CesiumGlobeProps {
  locations: GlobeLocation[]
  layers: LayersState
  storm?: StormTrackData | null
  series?: SeriesRegion[] | null
  /** Index into each region's merged timeline (null = static colors). */
  timeCursor?: number | null
  /** Which quantity colors the heat patches during replay. */
  timeColor?: 'temp' | 'model' | 'difference'
  /** location_id → data-confidence 0–100 (uncertainty overlay). */
  uncertainties?: Record<number, number>
  /** location_id → observation-need/priority 0–100 (priority overlay). */
  priorities?: Record<number, number>
  /** Argo float trajectories to draw as paths + current-position markers. */
  argoFloats?: ArgoFloat[]
  /** Real Argo floats to draw as clickable positions (from /api/v1/argo/floats). */
  realArgoFloats?: RealArgoFloat[]
  /** Fired when the user clicks a real Argo float marker. */
  onArgoFloatClick?: (floatId: string) => void
  /** Real NOAA ERSST v5 SST month grid, drawn as a temperature-colored field. */
  ersst?: ErsstLayer | null
  /** Real NOAA CoastWatch satellite Chl-a month grid, drawn as an ocean-colour field. */
  chlor?: ChlorLayer | null
  /** Colouring mode for each real grid layer (Linear/Log) on the dynamic scale. */
  scaleModes?: { sst?: ScaleMode; chl?: ScaleMode; modelgrid?: ScaleMode }
  /** Per-region model-vs-observation disagreement (colors the patches). */
  disagreement?: DisagreementPoint[]
  /** Ranked anomalies to draw as focus beacons. */
  anomalies?: AnomalyPoint[]
  /** TIDE observation candidates to draw as ranked decision markers. */
  tideCandidates?: TideGlobeMarker[]
  /** Phase 6 — Decision Replay markers (event / candidate / simulated observation). */
  replayMarkers?: ReplayGlobeMarker[]
  /** 3D vertical transect curtain (subsurface wall + thermocline + Argo). */
  transect?: TransectData | null
  /** When true, left-clicking the ocean picks transect endpoints (A then B). */
  transectActive?: boolean
  /** Per-layer opacity 0..1 applied to the dense data layers (default 1). */
  opacity?: Partial<Record<LayerKey, number>>
  /** Vertical terrain exaggeration factor for the scene (default 1). */
  exaggeration?: number
  /** Isosurface contour levels (°C) to draw over the real ERSST field (feature #11). */
  isolevels?: number[] | null
  /** True current velocity vectors from the real model grid (feature #14). */
  currentVectors?: CurrentVector[] | null
  /** One horizontal depth slice of the real model field (feature #7). */
  modelSlice?: ModelSlice | null
  /** Real glider deployment tracks (position + depth, feature #16). */
  gliderTracks?: GliderTrack[]
  /** Fired when the user left-clicks a real glider deployment track. */
  onGliderClick?: (deploymentId: string) => void
  /** Fired when the user left-clicks a region beacon/label on the globe. */
  onRegionClick?: (locId: number) => void
  /** Fired when the user picks a transect endpoint on the ocean surface. */
  onTransectPick?: (pt: { lat: number; lon: number }) => void
  /** Fly the camera to a region. Bump `n` to re-trigger. */
  flyToTarget?: { locId: number; n: number } | null
}

interface Scene {
  markers: VizEntity[]
  markerMap: { entity: VizEntity; locId: number }[]
  temps: { locId: number; entity: VizEntity; temp: number | null }[]
  waves: VizEntity[]
  currents: VizEntity[]
  storm: VizEntity[]
  rings: VizEntity[]
  focus: VizEntity[]
  argo: VizEntity[]
  realArgo: VizEntity[]
  /** Real Argo float markers → float id (click target). */
  argoMap: { entity: VizEntity; floatId: string }[]
  /** Real ERSST SST grid cells (temperature-colored dots). */
  sst: VizEntity[]
  /** Real satellite Chl-a grid cells (ocean-colour dots). */
  chl: VizEntity[]
  anomalies: VizEntity[]
  tide: VizEntity[]
  replay: VizEntity[]
  /** Marching-squares isosurface contour polylines (real SST field). */
  iso: VizEntity[]
  /** True current-velocity arrows (real model-grid u/v). */
  curVec: VizEntity[]
  /** One horizontal model-grid depth slice (feature #7). */
  slice: VizEntity[]
  /** Real glider deployment tracks + their clickable sample dots (#16). */
  glider: VizEntity[]
  /** Real glider entities → deployment id (click target). */
  glidersMap: { entity: VizEntity; deploymentId: string; baseColor: string }[]
  transect: (InstanceType<CesiumModule['Primitive']> | VizEntity)[]
}

export default function CesiumGlobe({ locations, layers, storm, series, timeCursor, timeColor = 'temp', uncertainties, priorities, argoFloats, realArgoFloats, ersst, chlor, scaleModes, disagreement, anomalies, tideCandidates, replayMarkers, transect, transectActive, opacity, exaggeration = 1, isolevels, currentVectors, modelSlice, gliderTracks, onGliderClick, onRegionClick, onArgoFloatClick, onTransectPick, flyToTarget }: CesiumGlobeProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const viewerRef = useRef<Viz | null>(null)
  const sceneRef = useRef<Scene>({ markers: [], markerMap: [], temps: [], waves: [], currents: [], storm: [], rings: [], focus: [], argo: [], realArgo: [], argoMap: [], sst: [], chl: [], anomalies: [], tide: [], replay: [], iso: [], curVec: [], slice: [], glider: [], glidersMap: [], transect: [] })
  const layersRef = useRef(layers)
  layersRef.current = layers
  const locatedRef = useRef(locations)
  locatedRef.current = locations
  const uncertaintyRef = useRef(uncertainties)
  uncertaintyRef.current = uncertainties
  const prioritiesRef = useRef(priorities)
  prioritiesRef.current = priorities
  const argoRef = useRef<ArgoFloat[]>([])
  argoRef.current = argoFloats ?? []
  const realArgoRef = useRef<RealArgoFloat[]>([])
  realArgoRef.current = realArgoFloats ?? []
  const onArgoFloatClickRef = useRef(onArgoFloatClick)
  onArgoFloatClickRef.current = onArgoFloatClick
  const ersstRef = useRef<ErsstLayer | null>(ersst ?? null)
  ersstRef.current = ersst ?? null
  const chlorRef = useRef<ChlorLayer | null>(chlor ?? null)
  chlorRef.current = chlor ?? null
  const scaleModesRef = useRef(scaleModes)
  scaleModesRef.current = scaleModes
  const opacityRef = useRef<Partial<Record<LayerKey, number>>>(opacity ?? {})
  opacityRef.current = opacity ?? {}
  const exaggerationRef = useRef(exaggeration)
  exaggerationRef.current = exaggeration
  const isolevelsRef = useRef<number[] | null>(isolevels ?? null)
  isolevelsRef.current = isolevels ?? null
  const currentVectorsRef = useRef<CurrentVector[]>(currentVectors ?? [])
  currentVectorsRef.current = currentVectors ?? []
  const modelSliceRef = useRef<ModelSlice | null>(modelSlice ?? null)
  modelSliceRef.current = modelSlice ?? null
  const gliderTracksRef = useRef<GliderTrack[]>(gliderTracks ?? [])
  gliderTracksRef.current = gliderTracks ?? []
  const onGliderClickRef = useRef(onGliderClick)
  onGliderClickRef.current = onGliderClick
  /** Cell values aligned with scene.sst / scene.chl, so opacity recolours map 1:1. */
  const sstSamplesRef = useRef<ErsstSample[]>([])
  const chlSamplesRef = useRef<ChlorSample[]>([])
  const seriesRef = useRef<SeriesRegion[]>([])
  seriesRef.current = series ?? []
  const cursorRef = useRef<number | null>(timeCursor ?? null)
  cursorRef.current = timeCursor ?? null
  const timeColorRef = useRef(timeColor)
  timeColorRef.current = timeColor
  const disagreementRef = useRef(disagreement ?? [])
  disagreementRef.current = disagreement ?? []
  const anomaliesRef = useRef(anomalies ?? [])
  anomaliesRef.current = anomalies ?? []
  const tideRef = useRef<TideGlobeMarker[]>([])
  tideRef.current = tideCandidates ?? []
  const replayRef = useRef<ReplayGlobeMarker[]>([])
  replayRef.current = replayMarkers ?? []
  const onRegionClickRef = useRef(onRegionClick)
  onRegionClickRef.current = onRegionClick
  const transectActiveRef = useRef(transectActive ?? false)
  transectActiveRef.current = transectActive ?? false
  const onTransectPickRef = useRef(onTransectPick)
  onTransectPickRef.current = onTransectPick
  const handlersRef = useRef<InstanceType<CesiumModule['ScreenSpaceEventHandler']>[]>([])

  // Build / rebuild the scene whenever the location list changes.
  useEffect(() => {
    let active = true
    loadCesium().then((Cesium) => {
      if (!active) return
      const container = containerRef.current
      if (!container) return

      let viewer = viewerRef.current
      if (!viewer) {
        try {
          viewer = new Cesium.Viewer(container, {
            animation: false,
            timeline: false,
            baseLayerPicker: false,
            geocoder: false,
            homeButton: false,
            sceneModePicker: false,
            navigationHelpButton: false,
            fullscreenButton: false,
            infoBox: false,
            selectionIndicator: false,
            baseLayer: false,
          })
        } catch {
          return
        }
        viewerRef.current = viewer
        viewer.scene.globe.baseColor = Cesium.Color.fromCssColorString('#0a2a4a')
        viewer.scene.globe.enableLighting = false
        // Keep the globe camera fully navigable: close surface inspection,
        // whole-earth views, and unrestricted rotate/tilt/look/pan controls.
        const camCtrl = viewer.scene.screenSpaceCameraController
        camCtrl.minimumZoomDistance = 1.0
        camCtrl.maximumZoomDistance = 50000000
        camCtrl.enableRotate = true
        camCtrl.enableTilt = true
        camCtrl.enableLook = true
        camCtrl.enableTranslate = true
        // Do not force the camera back from the terrain when navigating near it.
        camCtrl.enableCollisionDetection = false
        // `constrainedAxis` is a Camera property; leave it unset so tilt is free.
        viewer.camera.constrainedAxis = undefined
        void applyBaseLayer(Cesium, viewer)
      }

      buildScene(Cesium, viewer)
      applyLayers(Cesium, viewer, layersRef.current)
      applyExaggeration(Cesium, viewer)
      const curs = cursorRef.current
      if (curs != null) applyCursor(Cesium, viewer, curs)
    })
    return () => {
      active = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locations])

  // Toggle data layers without rebuilding entities.
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    loadCesium().then((Cesium) => applyLayers(Cesium, viewer, layers))
  }, [layers])

  // Keep the temperature patches in sync with the timeline scrubber.
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer || timeCursor == null) return
    loadCesium().then((Cesium) => applyCursor(Cesium, viewer, timeCursor))
  }, [timeCursor, locations, timeColor])

  // Storm-track layer. Rebuilt whenever the track or the base scene changes
  // (a full scene rebuild wipes all entities including the storm).
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer || !storm) return
    let cancelled = false
    loadCesium().then((Cesium) => {
      if (!cancelled) buildStorm(Cesium, viewer, storm)
    })
    return () => {
      cancelled = true
      clearStormEntities(viewer)
    }
  }, [storm, locations])

  // TIDE decision markers. Rebuilt whenever the candidate set or base scene
  // changes (a scene rebuild wipes all entities including the TIDE layer).
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    loadCesium().then((Cesium) => buildTideLayer(Cesium, viewer))
  }, [tideCandidates, locations])

  // Phase 6 — Decision Replay markers. Rebuilt whenever the marker set or the
  // base scene changes; per-marker visibility follows the current replay step.
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    loadCesium().then((Cesium) => buildReplayLayer(Cesium, viewer))
  }, [replayMarkers, locations])

  // Real Argo float markers. Drawn separately so they can arrive after the
  // base scene builds; also re-drawn after any full scene rebuild (locations).
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    let cancelled = false
    loadCesium().then((Cesium) => {
      if (cancelled) return
      const scene = sceneRef.current
      for (const e of scene.realArgo) viewer.entities.remove(e)
      scene.realArgo = []
      scene.argoMap = []
      for (const flt of realArgoRef.current) {
        if (flt.latitude == null || flt.longitude == null) continue
        const marker = viewer.entities.add({
          position: Cesium.Cartesian3.fromDegrees(flt.longitude, flt.latitude, 600),
          point: {
            pixelSize: 13,
            color: Cesium.Color.fromCssColorString('#f472b6'),
            outlineColor: Cesium.Color.WHITE,
            outlineWidth: 2,
          },
          label: {
            text: `Real Argo ${flt.float_id}`,
            font: '11px monospace',
            fillColor: Cesium.Color.WHITE,
            outlineColor: Cesium.Color.BLACK,
            outlineWidth: 2,
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            pixelOffset: new Cesium.Cartesian2(0, -14),
            distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 6.5e6),
          },
          show: layersRef.current.realArgo,
        })
        scene.realArgo.push(marker)
        scene.argoMap.push({ entity: marker, floatId: flt.float_id })
      }
      applyOpacity(Cesium, viewer, opacityRef.current)
      viewer.scene.requestRender()
    })
    return () => {
      cancelled = true
    }
  }, [realArgoFloats, locations])

  // Real NOAA ERSST v5 SST grid: one temperature-colored dot per real cell.
  // Drawn separately so it can arrive after the base scene builds.
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    let cancelled = false
    loadCesium().then((Cesium) => {
      if (cancelled) return
      const scene = sceneRef.current
      for (const e of scene.sst) viewer.entities.remove(e)
      scene.sst = []
      const grid = ersstRef.current
      if (grid && grid.samples) {
        const stats = grid.stats
        const domain = stats && stats.min !== null && stats.max !== null
          ? { min: stats.min, max: stats.max }
          : null
        const mode = scaleModes?.sst ?? 'linear'
        sstSamplesRef.current = grid.samples
        for (const s of grid.samples) {
          const marker = viewer.entities.add({
            position: Cesium.Cartesian3.fromDegrees(s.longitude, s.latitude, 120),
            point: {
              pixelSize: 4,
              color: Cesium.Color.fromCssColorString(tempColorCssFrom(s.sst, domain, mode)).withAlpha(0.8),
            },
            show: layersRef.current.realSST,
          })
          scene.sst.push(marker)
        }
        applyOpacity(Cesium, viewer, opacityRef.current)
      }
      viewer.scene.requestRender()
    })
    return () => {
      cancelled = true
    }
  }, [ersst, locations, scaleModes])

  // Real satellite Chl-a grid (NOAA CoastWatch VIIRS-Himawari): one
  // ocean-colour dot per real cell. Drawn separately like the real SST layer.
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    let cancelled = false
    loadCesium().then((Cesium) => {
      if (cancelled) return
      const scene = sceneRef.current
      for (const e of scene.chl) viewer.entities.remove(e)
      scene.chl = []
      const grid = chlorRef.current
      if (grid && grid.samples) {
        const stats = grid.stats
        const domain = stats && stats.min !== null && stats.max !== null
          ? { min: stats.min, max: stats.max }
          : null
        const mode = scaleModes?.chl ?? 'log'
        chlSamplesRef.current = grid.samples
        for (const s of grid.samples) {
          const marker = viewer.entities.add({
            position: Cesium.Cartesian3.fromDegrees(s.longitude, s.latitude, 120),
            point: {
              pixelSize: 4,
              color: Cesium.Color.fromCssColorString(chlorColorCssFrom(s.chlor_a, domain, mode)).withAlpha(0.8),
            },
            show: layersRef.current.realChl,
          })
          scene.chl.push(marker)
        }
        applyOpacity(Cesium, viewer, opacityRef.current)
      }
      viewer.scene.requestRender()
    })
    return () => {
      cancelled = true
    }
  }, [chlor, locations, scaleModes])

  // Per-layer opacity: recolour existing entities without rebuilding them.
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    loadCesium().then((Cesium) => applyOpacity(Cesium, viewer, opacityRef.current))
  }, [opacity])

  // Vertical terrain/ocean exaggeration (feature #13).
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    loadCesium().then((Cesium) => applyExaggeration(Cesium, viewer))
  }, [exaggeration])

  // Isosurface contour lines over the real ERSST SST field (feature #11).
  // Rebuilt whenever the contour levels or base scene change (a scene rebuild
  // wipes all entities, so the layer must be repainted after `locations`).
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    loadCesium().then((Cesium) => buildIsoLayer(Cesium, viewer))
  }, [isolevels, locations])

  // True current-velocity arrows from the real model grid (feature #14).
  // Rebuilt whenever the vector cells or base scene change, like the TIDE layer.
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    loadCesium().then((Cesium) => buildVectorsLayer(Cesium, viewer))
  }, [currentVectors, locations])

  // One horizontal depth slice of the real model field (feature #7).
  // Repainted after any scene rebuild, so it is keyed on `locations` too.
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    loadCesium().then((Cesium) => buildSliceLayer(Cesium, viewer))
  }, [modelSlice, locations])

  // Real glider deployment tracks (feature #16). Repainted on scene rebuilds.
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    loadCesium().then((Cesium) => buildGliderLayer(Cesium, viewer))
  }, [gliderTracks, locations])

  // Dispose the viewer on unmount.
  useEffect(() => {
    const container = containerRef.current
    // Keep the browser's context menu from stealing right-click drags.
    const onContextMenu = (ev: Event) => ev.preventDefault()
    container?.addEventListener('contextmenu', onContextMenu)
    return () => {
      container?.removeEventListener('contextmenu', onContextMenu)
      viewerRef.current?.destroy()
      viewerRef.current = null
      sceneRef.current = { markers: [], markerMap: [], temps: [], waves: [], currents: [], storm: [], rings: [], focus: [], argo: [], realArgo: [], argoMap: [], sst: [], chl: [], anomalies: [], tide: [], replay: [], iso: [], curVec: [], slice: [], glider: [], glidersMap: [], transect: [] }
    }
  }, [])

  // Left-click any region beacon/label → onRegionClick(locId).
  useEffect(() => {
    let active = true
    loadCesium().then((Cesium) => {
      if (!active) return
      const viewer = viewerRef.current
      if (!viewer) return
      const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas)
      handler.setInputAction(
        (click: unknown) => {
          const pos = (click as { position: Cartesian2 }).position
          if (!pos) return
          // Transect pick mode: capture the ocean point under the cursor.
          if (transectActiveRef.current) {
            const cartesian = viewer.camera.pickEllipsoid(pos, viewer.scene.globe.ellipsoid)
            if (cartesian) {
              const cart = Cesium.Cartographic.fromCartesian(cartesian)
              onTransectPickRef.current?.({
                lat: Cesium.Math.toDegrees(cart.latitude),
                lon: Cesium.Math.toDegrees(cart.longitude),
              })
            }
            return
          }
          const picked = viewer.scene.pick(pos)
          const entity = picked?.id
          if (!entity || !entity.id) return
          const hit = sceneRef.current.markerMap.find((m) => m.entity === entity)
          if (hit) {
            onRegionClickRef.current?.(hit.locId)
            ;(viewer.container as HTMLElement).style.cursor = 'default'
            return
          }
          const argoHit = sceneRef.current.argoMap.find((m) => m.entity === entity)
          if (argoHit) {
            onArgoFloatClickRef.current?.(argoHit.floatId)
            ;(viewer.container as HTMLElement).style.cursor = 'default'
            return
          }
          const gliderHit = sceneRef.current.glidersMap.find((m) => m.entity === entity)
          if (gliderHit) {
            onGliderClickRef.current?.(gliderHit.deploymentId)
            ;(viewer.container as HTMLElement).style.cursor = 'default'
          }
        },
        Cesium.ScreenSpaceEventType.LEFT_CLICK,
      )
      // Friendly pointer affordance when hovering a region beacon.
      handler.setInputAction(
        (movement: unknown) => {
          const pos = (movement as { endPosition?: Cartesian2 }).endPosition
          if (!pos) return
          if (transectActiveRef.current) {
            const ell = viewer.camera.pickEllipsoid(pos, viewer.scene.globe.ellipsoid)
            ;(viewer.container as HTMLElement).style.cursor = ell ? 'crosshair' : 'default'
            return
          }
          const picked = viewer.scene.pick(pos)
          const hit = picked?.id && sceneRef.current.markerMap.find((m) => m.entity === picked.id)
          const argoHit = picked?.id && sceneRef.current.argoMap.find((m) => m.entity === picked.id)
          ;(viewer.container as HTMLElement).style.cursor = hit || argoHit ? 'pointer' : 'default'
        },
        Cesium.ScreenSpaceEventType.MOUSE_MOVE,
      )
      handlersRef.current.push(handler)
    })
    return () => {
      active = false
      for (const h of handlersRef.current) h.destroy()
      handlersRef.current = []
    }
  }, [])

  // Fly the camera to a region when flyToTarget changes.
  useEffect(() => {
    if (!flyToTarget) return
    const viewer = viewerRef.current
    if (!viewer) return
    loadCesium().then((Cesium) => {
      const loc = locatedRef.current.find((l) => l.id === flyToTarget.locId)
      if (!loc || loc.latitude == null || loc.longitude == null) return
      viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(loc.longitude, loc.latitude, 2400000),
        orientation: { heading: 0, pitch: Cesium.Math.toRadians(-52), roll: 0 },
        duration: 2.6,
      })
    })
  }, [flyToTarget])

  // 3D vertical transect 'curtain': subsurface globe mode + wall + thermocline.
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    loadCesium().then((Cesium) => {
      if (transect) buildTransect(Cesium, viewer, transect)
      else if (transectActive) enableSubsurface(Cesium, viewer)
      else clearTransect(viewer)
    })
  }, [transect, transectActive])

  // Try Cesium Ion satellite imagery first; if the token can't load it,
  // fall back to free OpenStreetMap tiles so the globe never stays empty.
  async function applyBaseLayer(Cesium: CesiumModule, viewer: Viz) {
    try {
      const provider = await Cesium.IonImageryProvider.fromAssetId(2)
      viewer.imageryLayers.addImageryProvider(provider)
      return
    } catch {
      /* token unavailable for this asset — fall through */
    }
    try {
      viewer.imageryLayers.addImageryProvider(
        new Cesium.OpenStreetMapImageryProvider({ url: 'https://a.tile.openstreetmap.org/' }),
      )
    } catch {
      /* keep the styled baseColor globe */
    }
  }

  function buildScene(Cesium: CesiumModule, viewer: Viz) {
    viewer.entities.removeAll()
    clearStormEntities(viewer)
    const scene: Scene = { markers: [], markerMap: [], temps: [], waves: [], currents: [], storm: [], rings: [], focus: [], argo: [], realArgo: [], argoMap: [], sst: [], chl: [], anomalies: [], tide: [], replay: [], iso: [], curVec: [], slice: [], glider: [], glidersMap: [], transect: [] }

    const valid = (locations.length > 0 ? locations : FALLBACK_LOCATIONS).filter(
      (l) => l.latitude != null && l.longitude != null,
    )

    for (const loc of valid) {
      const lon = loc.longitude!
      const lat = loc.latitude!
      const phase = loc.id
      const pos = Cesium.Cartesian3.fromDegrees(lon, lat, 0)

      // ---- Marker (pinging beacon) + optional label ----
      const marker = viewer.entities.add({
        position: pos,
        billboard: {
          image: getBeaconUrl(),
          width: 52,
          height: 52,
          scaleByDistance: new Cesium.NearFarScalar(1.2e6, 1.0, 4.0e6, 0.55),
          scale: new Cesium.CallbackProperty(
            () => 0.82 + 0.35 * (0.5 + 0.5 * Math.sin(Date.now() / 1000 * 3.2 + phase)),
            false,
          ),
          verticalOrigin: Cesium.VerticalOrigin.CENTER,
        },
        label: {
          text: loc.name.split(' (')[0],
          font: '600 13px Inter, sans-serif',
          fillColor: Cesium.Color.fromCssColorString('#ffffff'),
          showBackground: true,
          backgroundColor: Cesium.Color.fromCssColorString('#06122a').withAlpha(0.85),
          backgroundPadding: new Cesium.Cartesian2(7, 5),
          pixelOffset: new Cesium.Cartesian2(0, -26),
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          outlineColor: Cesium.Color.fromCssColorString('#000000').withAlpha(0.45),
          outlineWidth: 2,
          distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 3.5e6),
          show: layersRef.current.labels,
        },
      })
      scene.markers.push(marker)
      scene.markerMap.push({ entity: marker, locId: loc.id })

      // ---- Temperature heat patches (recolored by model-vs-obs disagreement
      // when the disagreement layer is on) ----
      const tempC = Cesium.Color.fromCssColorString(tempColorCss(loc.temperature ?? 28))
      const disagree = disagreementRef.current.find((d) => d.location_id === loc.id)
      const disagreeOn = layersRef.current.disagreement
      const baseShow = layersRef.current.temperature
      const patchBand = disagreeOn && disagree ? disagree.band : null
      const patchColor = patchBand ? bandColor(Cesium, patchBand) : tempC
      const temp = viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(lon, lat, 300),
        ellipse: {
          semiMajorAxis: 62000,
          semiMinorAxis: 45000,
          rotation: Cesium.Math.toRadians(phase * 17),
          material: patchColor.withAlpha(patchBand ? 0.46 : 0.38),
          outline: true,
          outlineColor: patchColor.withAlpha(patchBand ? 0.95 : 0.9),
          outlineWidth: patchBand ? 3 : 2,
          height: 300,
        },
        show: baseShow || (disagreeOn && disagree != null),
      })
      scene.temps.push({ locId: loc.id, entity: temp, temp: loc.temperature ?? null })

      // ---- Wave ripples (3 expanding rings) ----
      for (let r = 0; r < 3; r++) {
        const ripplePhase = phase * 0.7 + r * 1.0
        const ripple = viewer.entities.add({
          position: Cesium.Cartesian3.fromDegrees(lon, lat, 260),
          ellipse: {
            semiMajorAxis: new Cesium.CallbackProperty(() => {
              const k = (Date.now() % 3000) / 3000 + ripplePhase / 3
              const t = (k + 1) % 1
              return 6000 + t * 52000
            }, false),
            semiMinorAxis: new Cesium.CallbackProperty(() => {
              const k = (Date.now() % 3000) / 3000 + ripplePhase / 3
              const t = (k + 1) % 1
              return (6000 + t * 52000) * 0.72
            }, false),
            rotation: Cesium.Math.toRadians(phase * 23),
            material: Cesium.Color.fromCssColorString('#a5f3fc').withAlpha(0.16),
            outline: true,
            outlineColor: new Cesium.CallbackProperty(() => {
              const k = ((Date.now() % 3000) / 3000 + ripplePhase / 3) % 1
              const fade = Math.max(0, 1 - k)
              return Cesium.Color.fromCssColorString('#67e8f9').withAlpha(fade * 0.9)
            }, false),
            outlineWidth: 3,
            height: 260,
          },
          show: layersRef.current.waves,
        })
        scene.waves.push(ripple)
      }

      // ---- Uncertainty rings (data-confidence gaps per region) ----
      const unc = uncertaintyRef.current?.[loc.id]
      if (unc != null) {
        const uncColor =
          unc >= 50 ? Cesium.Color.fromCssColorString('#f43f5e')
            : unc >= 25 ? Cesium.Color.fromCssColorString('#f59e0b')
            : Cesium.Color.fromCssColorString('#10b981')
        const ring = viewer.entities.add({
          position: Cesium.Cartesian3.fromDegrees(lon, lat, 200),
          ellipse: {
            semiMajorAxis: 42000 + unc * 420,
            semiMinorAxis: 30000 + unc * 300,
            rotation: Cesium.Math.toRadians(phase * 13),
            material: Cesium.Color.TRANSPARENT,
            outline: true,
            outlineColor: uncColor.withAlpha(0.9),
            outlineWidth: 2,
            height: 200,
          },
          show: layersRef.current.uncertainty,
        })
        scene.rings.push(ring)
      }

      // ---- Priority/focus rings (regions that need observation next) ----
      const prio = prioritiesRef.current?.[loc.id]
      if (prio != null && prio >= 10) {
        const prioColor = Cesium.Color.fromCssColorString('#a78bfa')
        const focusRing = viewer.entities.add({
          position: Cesium.Cartesian3.fromDegrees(lon, lat, 240),
          ellipse: {
            semiMajorAxis: new Cesium.CallbackProperty(() => 30000 + ((Date.now() % 2400) / 2400) * 42000, false),
            semiMinorAxis: new Cesium.CallbackProperty(() => (30000 + ((Date.now() % 2400) / 2400) * 42000) * 0.85, false),
            rotation: Cesium.Math.toRadians(phase * 29),
            material: prioColor.withAlpha(0.04),
            outline: true,
            outlineColor: new Cesium.CallbackProperty(() => {
              const k = (Date.now() % 2400) / 2400
              return prioColor.withAlpha(Math.max(0.05, 1 - k) * 0.9)
            }, false),
            outlineWidth: 3,
            height: 240,
          },
          show: layersRef.current.priority,
        })
        scene.focus.push(focusRing)
      }
    }

    // ---- Anomaly beacons (ranked model-vs-observation anomalies) ----
    const anomalyShow = layersRef.current.anomalies
    for (const a of anomaliesRef.current) {
      if (a.latitude == null || a.longitude == null) continue
      const pulse = 0.82 + 0.3 * (0.5 + 0.5 * Math.sin(Date.now() / 1000 * 4 + a.location_id))
      const beacon = viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(a.longitude, a.latitude, 350),
        billboard: {
          image: getAnomalySprite(a.severity),
          width: 64,
          height: 64,
          scale: new Cesium.CallbackProperty(() => pulse, false),
          scaleByDistance: new Cesium.NearFarScalar(1.0e6, 1.0, 5.0e6, 0.5),
          verticalOrigin: Cesium.VerticalOrigin.CENTER,
        },
        label: {
          text: `${a.label} ${a.difference != null ? (a.difference > 0 ? '+' : '') + a.difference.toFixed(1) : ''}${a.unit}`,
          font: '700 12px Inter, sans-serif',
          fillColor: Cesium.Color.fromCssColorString('#ffffff'),
          showBackground: true,
          backgroundColor: Cesium.Color.fromCssColorString('#0a1526').withAlpha(0.9),
          backgroundPadding: new Cesium.Cartesian2(6, 4),
          pixelOffset: new Cesium.Cartesian2(0, -18),
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          outlineColor: Cesium.Color.fromCssColorString('#000000').withAlpha(0.5),
          outlineWidth: 2,
          distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 4.5e6),
        },
        show: anomalyShow,
      })
      scene.anomalies.push(beacon)
      scene.markerMap.push({ entity: beacon, locId: a.location_id })
    }

    // ---- Argo float trajectories ----
    for (const flt of argoRef.current) {
      if (!flt.points || flt.points.length < 2) continue
      // Trail polyline: rising = red→yellow, sinking = cyan→blue
      const positions = flt.points.map((p) => Cesium.Cartesian3.fromDegrees(p.lon, p.lat, 50 + p.depth_m * 0.4))
      const trail = viewer.entities.add({
        polyline: {
          positions,
          width: 2.0,
          material: new Cesium.PolylineGlowMaterialProperty({
            glowPower: 0.15,
            color: Cesium.Color.fromCssColorString('#38bdf8').withAlpha(0.75),
          }),
          clampToGround: false,
        },
        show: layersRef.current.argo,
      })
      scene.argo.push(trail)
      // Current-position sphere
      const last = flt.points[flt.points.length - 1]
      const tempNorm = Math.max(0, Math.min(1, (last.temperature - 4) / 25))
      const sphereColor = Cesium.Color.fromHsl(0.6 - tempNorm * 0.55, 0.85, 0.55)
      const sphere = viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(last.lon, last.lat, 50 + last.depth_m * 0.4),
        point: { pixelSize: 10, color: sphereColor, outlineColor: Cesium.Color.WHITE, outlineWidth: 2 },
        label: {
          text: flt.label,
          font: '11px monospace',
          fillColor: Cesium.Color.WHITE,
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 2,
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
          pixelOffset: new Cesium.Cartesian2(0, -12),
        },
        show: layersRef.current.argo,
      })
      scene.argo.push(sphere)
    }

    // ---- Currents: glowing arcs along the coastline + streaming dots ----
    if (valid.length > 1) {
      const chain = valid.concat([valid[0]]) // close the loop
      for (let i = 0; i < chain.length - 1; i++) {
        const arc = viewer.entities.add({
          polyline: {
            positions: Cesium.Cartesian3.fromDegreesArray([
              chain[i].longitude!,
              chain[i].latitude!,
              chain[i + 1].longitude!,
              chain[i + 1].latitude!,
            ]),
            width: 4,
            arcType: Cesium.ArcType.GEODESIC,
            material: new Cesium.PolylineGlowMaterialProperty({
              color: Cesium.Color.fromCssColorString('#22d3ee').withAlpha(0.75),
              glowPower: 0.28,
            }),
          },
          show: layersRef.current.currents,
        })
        scene.currents.push(arc)
      }

      // Streams of glowing dots orbiting the ocean at 3 tilted paths.
      const R = 6378137 * 1.03
      const normals = [
        new Cesium.Cartesian3(0.2, 0.6, 0.8),
        new Cesium.Cartesian3(-0.6, 0.3, 0.8),
        new Cesium.Cartesian3(0.7, -0.4, 0.7),
      ]
      normals.forEach((n, oi) => {
        const nav = n.clone()
        const len = Cesium.Cartesian3.magnitude(nav)
        nav.x /= len
        nav.y /= len
        nav.z /= len
        const helper = new Cesium.Cartesian3(0, 1, 0)
        const u = new Cesium.Cartesian3()
        Cesium.Cartesian3.cross(helper, nav, u)
        const uLen = Cesium.Cartesian3.magnitude(u)
        if (uLen < 1e-3) Cesium.Cartesian3.clone(Cesium.Cartesian3.UNIT_X, u)
        else {
          u.x /= uLen
          u.y /= uLen
          u.z /= uLen
        }
        const v = new Cesium.Cartesian3()
        Cesium.Cartesian3.cross(nav, u, v)
        const vLen = Cesium.Cartesian3.magnitude(v)
        v.x /= vLen
        v.y /= vLen
        v.z /= vLen

        const iotaDots = 12
        for (let d = 0; d < iotaDots; d++) {
          const dotPhase = (d / iotaDots) * Math.PI * 2 + oi
          const speed = 0.25 + oi * 0.09
          const dot = viewer.entities.add({
            position: new Cesium.CallbackPositionProperty(() => {
              const a = dotPhase + (Date.now() / 1000) * speed
              const ca = Math.cos(a)
              const sa = Math.sin(a)
              return new Cesium.Cartesian3(
                (u.x * ca + v.x * sa) * R,
                (u.y * ca + v.y * sa) * R,
                (u.z * ca + v.z * sa) * R,
              )
            }, false),
            billboard: {
              image: getDotUrl(),
              width: 18,
              height: 18,
              verticalOrigin: Cesium.VerticalOrigin.CENTER,
            },
            show: layersRef.current.currents,
          })
          scene.currents.push(dot)
        }
      })
    }

    sceneRef.current = scene
  }

  function clearStormEntities(viewer: Viz | null) {
    const list = sceneRef.current.storm
    for (const e of list) {
      try {
        viewer?.entities.remove(e)
      } catch {
        /* already disposed */
      }
    }
    sceneRef.current = { ...sceneRef.current, storm: [] }
  }

  /** Remove all TIDE decision markers from the scene. */
  function clearTide(viewer: Viz | null) {
    for (const e of sceneRef.current.tide) {
      try {
        viewer?.entities.remove(e)
      } catch {
        /* already disposed */
      }
    }
    sceneRef.current = { ...sceneRef.current, tide: [] }
  }

  /** Draw ranked TIDE observation candidates as pulsing decision markers. */
  function buildTideLayer(Cesium: CesiumModule, viewer: Viz) {
    clearTide(viewer)
    const list = tideRef.current
    const show = layersRef.current.tide
    const scene = sceneRef.current
    list.forEach((c, index) => {
      if (c.latitude == null || c.longitude == null) return
      const rank = c.rank ?? index + 1
      const config = {
        decision: c.affected_decision,
        variable: c.variable,
        location: c.location,
      }
      const marker = viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(c.longitude, c.latitude, 480),
        billboard: {
          image: getTideSprite(),
          width: 46,
          height: 46,
          scale: new Cesium.CallbackProperty(
            () => 0.86 + 0.3 * (0.5 + 0.5 * Math.sin(Date.now() / 1000 * 3.6 + c.location_id)),
            false,
          ),
          scaleByDistance: new Cesium.NearFarScalar(1.4e6, 1.0, 5.5e6, 0.55),
          verticalOrigin: Cesium.VerticalOrigin.CENTER,
        },
        label: {
          text: `#${rank} · ${config.variable.replace('_', ' ').toUpperCase()}`,
          font: '700 12px Inter, sans-serif',
          fillColor: Cesium.Color.fromCssColorString('#ecfeff'),
          showBackground: true,
          backgroundColor: Cesium.Color.fromCssColorString('#062a38').withAlpha(0.92),
          backgroundPadding: new Cesium.Cartesian2(6, 4),
          pixelOffset: new Cesium.Cartesian2(0, -30),
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          outlineColor: Cesium.Color.fromCssColorString('#000000').withAlpha(0.5),
          outlineWidth: 2,
          distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 4.5e6),
        },
        show,
      })
      scene.tide.push(marker)
      scene.markerMap.push({ entity: marker, locId: c.location_id })
    })
    viewer.scene.requestRender()
  }

  /** Remove all Phase 6 replay markers from the scene. */
  function clearReplay(viewer: Viz | null) {
    for (const e of sceneRef.current.replay) {
      try {
        viewer?.entities.remove(e)
      } catch {
        /* already disposed */
      }
    }
    sceneRef.current = { ...sceneRef.current, replay: [] }
  }

  /** Draw Phase 6 Decision Replay markers (event / candidate / observation). */
  function buildReplayLayer(Cesium: CesiumModule, viewer: Viz) {
    clearReplay(viewer)
    const list = replayRef.current
    const scene = sceneRef.current
    for (const m of list) {
      if (m.lat == null || m.lon == null) continue
      const isObs = m.kind === 'observation'
      const isEvent = m.kind === 'event'
      const sprite = isObs ? getObsSprite() : isEvent ? getBeaconUrl() : getTideSprite()
      const tint = isObs ? '#fb7185' : isEvent ? '#a5f3fc' : '#22d3ee'
      const entity = viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(m.lon, m.lat, isEvent ? 520 : 500),
        billboard: {
          image: sprite,
          width: isEvent ? 60 : 44,
          height: isEvent ? 60 : 44,
          scale: new Cesium.CallbackProperty(
            () => 0.84 + 0.3 * (0.5 + 0.5 * Math.sin(Date.now() / 1000 * 3.4 + (m.id.length || 1))),
            false,
          ),
          scaleByDistance: new Cesium.NearFarScalar(1.2e6, 1.0, 5.5e6, 0.5),
          verticalOrigin: Cesium.VerticalOrigin.CENTER,
        },
        label: {
          text: m.label ? m.label.toUpperCase() : '',
          font: '700 12px Inter, sans-serif',
          fillColor: Cesium.Color.fromCssColorString(isObs ? '#fecdd3' : isEvent ? '#ecfeff' : '#ecfeff'),
          showBackground: true,
          backgroundColor: Cesium.Color.fromCssColorString(isObs ? '#31101a' : '#062a38').withAlpha(0.92),
          backgroundPadding: new Cesium.Cartesian2(6, 4),
          pixelOffset: new Cesium.Cartesian2(0, -30),
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          outlineColor: Cesium.Color.fromCssColorString('#000000').withAlpha(0.5),
          outlineWidth: 2,
          show: m.visible,
          distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 4.5e6),
        },
        show: m.visible,
      })
      scene.replay.push(entity)
      if (m.location_id != null) {
        scene.markerMap.push({ entity, locId: m.location_id })
      }
      // Event spatial-extent footprint: soft pulsing ellipse around the event.
      if (isEvent) {
        scene.replay.push(
          viewer.entities.add({
            position: Cesium.Cartesian3.fromDegrees(m.lon, m.lat, 240),
            ellipse: {
              semiMajorAxis: new Cesium.CallbackProperty(
                () => 38000 + ((Date.now() % 2600) / 2600) * 38000,
                false,
              ),
              semiMinorAxis: new Cesium.CallbackProperty(
                () => (38000 + ((Date.now() % 2600) / 2600) * 38000) * 0.8,
                false,
              ),
              rotation: Cesium.Math.toRadians((m.id.length || 1) * 11),
              material: Cesium.Color.fromCssColorString(tint).withAlpha(0.04),
              outline: true,
              outlineColor: new Cesium.CallbackProperty(() => {
                const k = (Date.now() % 2600) / 2600
                return Cesium.Color.fromCssColorString(tint).withAlpha(Math.max(0.05, 1 - k) * 0.8)
              }, false),
              outlineWidth: 2,
              height: 240,
            },
            show: m.visible,
          }),
        )
      }
    }
    viewer.scene.requestRender()
  }

  function buildStorm(Cesium: CesiumModule, viewer: Viz, data: StormTrackData) {
    clearStormEntities(viewer)
    const pts = (data.points ?? []).filter((p) => p.lat != null && p.lon != null)
    if (pts.length < 2) return

    const scene = sceneRef.current
    const positions = pts.map((p) => Cesium.Cartesian3.fromDegrees(p.lon, p.lat, 0))
    const show = layersRef.current.storm
    const stormRed = Cesium.Color.fromCssColorString('#f43f5e')

    // ---- Track path ----
    scene.storm.push(
      viewer.entities.add({
        polyline: {
          positions,
          width: 5,
          arcType: Cesium.ArcType.GEODESIC,
          material: new Cesium.PolylineGlowMaterialProperty({
            color: stormRed.withAlpha(0.85),
            glowPower: 0.45,
          }),
        },
        show,
      }),
    )

    // ---- Confidence cone (expanding-uncertainty ellipses along the path) ----
    pts.forEach((p, i) => {
      if (i % 3 !== 0) return
      const radius = (p.radius_km ?? 60) * 1000
      scene.storm.push(
        viewer.entities.add({
          position: Cesium.Cartesian3.fromDegrees(p.lon, p.lat, 400),
          ellipse: {
            semiMajorAxis: radius,
            semiMinorAxis: radius * 0.72,
            rotation: Cesium.Math.toRadians(-30 + (i % 5) * 8),
            material: stormRed.withAlpha(0.05),
            outline: true,
            outlineColor: stormRed.withAlpha(0.35),
            outlineWidth: 2,
            height: 400,
          },
          show,
        }),
      )
    })

    // ---- Origin + landfall markers ----
    scene.storm.push(
      viewer.entities.add({
        position: positions[0],
        point: {
          pixelSize: 10,
          color: Cesium.Color.fromCssColorString('#ffffff').withAlpha(0.95),
          outlineColor: stormRed.withAlpha(0.9),
          outlineWidth: 2,
        },
        label: {
          text: 'TRACK START',
          font: '700 11px Inter, sans-serif',
          fillColor: Cesium.Color.fromCssColorString('#fecaca'),
          pixelOffset: new Cesium.Cartesian2(0, -14),
        },
        show,
      }),
    )
    const landfall = pts[pts.length - 1]
    scene.storm.push(
      viewer.entities.add({
        position: positions[pts.length - 1],
        point: { pixelSize: 14, color: stormRed.withAlpha(0.95) },
        label: {
          text: `LANDFALL H+${pts.length - 1} · ${landfall.lon.toFixed(1)}°E`,
          font: '700 11px Inter, sans-serif',
          fillColor: Cesium.Color.fromCssColorString('#fecaca'),
          pixelOffset: new Cesium.Cartesian2(0, -16),
        },
        show,
      }),
    )

    // ---- Moving eye ----
    scene.storm.push(
      viewer.entities.add({
        position: new Cesium.CallbackPositionProperty(() => {
          const seg = positions.length - 1
          const t = ((Date.now() / 1000) * 0.06) % seg
          const i = Math.min(Math.floor(t), positions.length - 2)
          const f = t - i
          return Cesium.Cartesian3.lerp(positions[i], positions[i + 1], f, new Cesium.Cartesian3())
        }, false),
        billboard: {
          image: getStormEyeUrl(),
          width: 40,
          height: 40,
          verticalOrigin: Cesium.VerticalOrigin.CENTER,
        },
        show,
      }),
    )

    viewer.scene.requestRender()
  }

  /** Make the globe translucent so subsurface layers are visible. */
  function enableSubsurface(Cesium: CesiumModule, viewer: Viz) {
    const globe = viewer.scene.globe
    if (globe.translucency) {
      globe.translucency.enabled = true
      globe.translucency.frontFaceAlphaByDistance = new Cesium.NearFarScalar(1e2, 0.4, 1e6, 0.7)
      globe.translucency.backFaceAlpha = 0.5
      globe.undergroundColor = Cesium.Color.fromCssColorString('#020b14')
    }
    viewer.scene.requestRender()
  }

  /** Remove the curtain / thermocline / Argo transect layer + restore the globe. */
  function clearTransect(viewer: Viz | null) {
    if (!viewer) return
    for (const obj of sceneRef.current.transect) {
      try {
        viewer.scene.primitives.remove(obj)
      } catch {
        /* already removed */
      }
      try {
        viewer.entities.remove(obj as VizEntity)
      } catch {
        /* already removed */
      }
    }
    sceneRef.current = { ...sceneRef.current, transect: [] }
    const globe = viewer.scene.globe
    if (globe.translucency) {
      globe.translucency.enabled = false
      globe.undergroundColor = undefined as unknown as InstanceType<CesiumModule['Color']>
    }
    viewer.scene.requestRender()
  }

  /** Ocean temperature colormap: deep navy -> cyan -> teal -> amber -> crimson. */
  function tempToRgb(t: number) {
    const k = Math.max(0, Math.min(1, t))
    const stops: [number, number, number, number][] = [
      [0.0, 10, 20, 45],
      [0.22, 23, 163, 199],
      [0.45, 45, 212, 191],
      [0.6, 125, 211, 252],
      [0.75, 251, 191, 36],
      [0.9, 249, 115, 22],
      [1.0, 244, 63, 94],
    ]
    for (let i = 1; i < stops.length; i++) {
      if (k <= stops[i][0]) {
        const [t0, r0, g0, b0] = stops[i - 1]
        const [t1, r1, g1, b1] = stops[i]
        const f = (k - t0) / (t1 - t0)
        return [
          Math.round(r0 + (r1 - r0) * f),
          Math.round(g0 + (g1 - g0) * f),
          Math.round(b0 + (b1 - b0) * f),
        ]
      }
    }
    const last = stops[stops.length - 1]
    return [last[1], last[2], last[3]]
  }

  /** Build the 3D transect curtain: textured subsurface wall + thermocline + Argo. */
  function buildTransect(Cesium: CesiumModule, viewer: Viz, data: TransectData) {
    clearTransect(viewer)
    enableSubsurface(Cesium, viewer)

    const scene = sceneRef.current
    const samples = data.samples ?? []
    if (samples.length < 2) return

    // ---- 1. The subsurface curtain wall (procedurally textured) ----
    const positions = samples.map((s) => Cesium.Cartesian3.fromDegrees(s.lon, s.lat, 0))
    const W = Math.max(192, samples.length * 6)
    const H = Math.max(128, (data.depths ?? []).length * 6)
    const canvas = document.createElement('canvas')
    canvas.width = W
    canvas.height = H
    const ctx = canvas.getContext('2d')
    if (ctx) {
      let tMin = Infinity
      let tMax = -Infinity
      for (const s of samples) {
        for (const v of s.values ?? []) {
          if (v == null) continue
          if (v < tMin) tMin = v
          if (v > tMax) tMax = v
        }
      }
      if (!isFinite(tMin) || !isFinite(tMax) || tMax - tMin < 1e-6) {
        tMin = (data.variable === 'salinity' ? 34 : 4)
        tMax = (data.variable === 'salinity' ? 37 : 30)
      }
      const nS = samples.length
      const nD = (data.depths ?? []).length
      const cellW = Math.ceil(W / Math.max(1, nS))
      const cellH = Math.max(2, Math.ceil(H / Math.max(1, nD - 1)))
      for (let si = 0; si < nS; si++) {
        const x0 = Math.floor((si / Math.max(1, nS - 1)) * (W - 1))
        const values = samples[si].values ?? []
        for (let di = 0; di < nD; di++) {
          const v = values[di]
          if (v == null) continue
          const y = Math.floor((di / Math.max(1, nD - 1)) * (H - 1))
          const [r, g, b] = tempToRgb((v - tMin) / (tMax - tMin))
          ctx.fillStyle = `rgb(${r},${g},${b})`
          ctx.fillRect(x0, y, cellW, cellH)
        }
      }
    }

    const depth = -Math.max(200, Math.round(data.depth_max_m || 2000))
    const wall = new Cesium.Primitive({
      geometryInstances: new Cesium.GeometryInstance({
        geometry: new Cesium.WallGeometry({
          positions,
          maximumHeights: positions.map(() => 0),
          minimumHeights: positions.map(() => depth),
          granularity: Cesium.Math.toRadians(1.5),
        }),
      }),
      appearance: new Cesium.MaterialAppearance({
        material: Cesium.Material.fromType('Image', { image: canvas }),
        flat: true,
      }),
      asynchronous: false,
    })
    viewer.scene.primitives.add(wall)
    scene.transect.push(wall)

    // ---- 2. Glowing thermocline polyline (max-gradient layer) ----
    const thermoPoints = (data.thermocline_polyline ?? []).filter(
      (p) => p.depth_m > 0 && p.depth_m < Math.max(200, Math.round(data.depth_max_m || 2000)),
    )
    if (thermoPoints.length > 1) {
      const thermoPositions = thermoPoints.map((p) => Cesium.Cartesian3.fromDegrees(p.lon, p.lat, -p.depth_m))
      scene.transect.push(
        viewer.entities.add({
          polyline: {
            positions: thermoPositions,
            width: 4,
            clampToGround: false,
            material: new Cesium.PolylineGlowMaterialProperty({
              color: Cesium.Color.fromCssColorString('#38bdf8').withAlpha(0.95),
              glowPower: 0.4,
            }),
          },
        }),
      )
      // Endpoint labels
      const tm = thermoPoints[Math.floor(thermoPoints.length / 2)]
      scene.transect.push(
        viewer.entities.add({
          position: Cesium.Cartesian3.fromDegrees(tm.lon, tm.lat, -tm.depth_m),
          label: {
            text: `THERMOCLINE · ${Math.round(tm.depth_m)}m`,
            font: '700 11px Inter, sans-serif',
            fillColor: Cesium.Color.fromCssColorString('#bae6fd'),
            showBackground: true,
            backgroundColor: Cesium.Color.fromCssColorString('#06122a').withAlpha(0.9),
            backgroundPadding: new Cesium.Cartesian2(6, 4),
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            outlineColor: Cesium.Color.fromCssColorString('#000000').withAlpha(0.6),
            outlineWidth: 2,
          },
        }),
      )
    }

    // ---- 3. Argo in-situ subsurface profile markers (model-vs-in-situ) ----
    for (const f of data.argos ?? []) {
      const zs = (f.in_situ?.depths ?? [])
      const temps = (f.in_situ?.temperature ?? [])
      const pts: InstanceType<CesiumModule['Cartesian3']>[] = []
      zs.forEach((d, i) => {
        const t = temps[i]
        if (t != null && d <= Math.max(200, Math.round(data.depth_max_m || 2000))) {
          pts.push(Cesium.Cartesian3.fromDegrees(f.longitude, f.latitude, -d))
        }
      })
      if (pts.length < 2) continue
      const seg = viewer.entities.add({
        polyline: {
          positions: pts,
          width: 3,
          clampToGround: false,
          material: new Cesium.PolylineGlowMaterialProperty({
            color: Cesium.Color.fromCssColorString('#f59e0b').withAlpha(0.9),
            glowPower: 0.2,
          }),
        },
        label: {
          text: `ARGO ${f.label} · ${Math.round(f.max_depth_m)}m`,
          font: '600 11px monospace',
          fillColor: Cesium.Color.fromCssColorString('#fde68a'),
          showBackground: true,
          backgroundColor: Cesium.Color.fromCssColorString('#121a2a').withAlpha(0.92),
          backgroundPadding: new Cesium.Cartesian2(6, 4),
          pixelOffset: new Cesium.Cartesian2(10, 0),
          distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 5e6),
        },
      })
      scene.transect.push(seg)
      const mrk = viewer.entities.add({
        position: pts[0],
        point: {
          pixelSize: 7,
          color: Cesium.Color.fromCssColorString('#fbbf24'),
          outlineColor: Cesium.Color.WHITE,
          outlineWidth: 2,
        },
      })
      scene.transect.push(mrk)
    }

    // Frame the transect slightly above the surface so the whole water column reads.
    const mid = samples[Math.floor(samples.length / 2)]
    if (mid) {
      viewer.camera.flyTo({
        destination: Cesium.Cartesian3.fromDegrees(mid.lon, mid.lat, 1500000),
        orientation: { heading: 0, pitch: Cesium.Math.toRadians(-48), roll: 0 },
        duration: 2.0,
      })
    }
    viewer.scene.requestRender()
  }

  /** Recolor temperature patches from the merged timeline at the cursor. */
  function applyCursor(Cesium: CesiumModule, viewer: Viz, cursor: number) {
    const scene = sceneRef.current
    const mode = timeColorRef.current
    const disagreeActive = layersRef.current.disagreement
    for (const tge of scene.temps) {
      const reg = seriesRef.current.find((r) => r.location_id === tge.locId)
      if (!reg) continue
      // Regions colored by the disagreement layer keep their status colors.
      if (disagreeActive && disagreementRef.current.some((d) => d.location_id === tge.locId)) continue
      const idx = Math.min(cursor, reg.points.length - 1)
      const p = reg.points[idx]
      const entity = tge.entity
      if (!entity.ellipse || !p) continue

      let value = p.temperature
      let color = value != null ? Cesium.Color.fromCssColorString(tempColorCss(value)) : null
      if (mode !== 'temp' && p.temperature != null) {
        const base = rollingBaseline(reg, idx)
        if (mode === 'model') {
          value = base
          color = value != null ? Cesium.Color.fromCssColorString(tempColorCss(value)) : null
        } else if (mode === 'difference') {
          value = base != null ? p.temperature - base : null
          color = value != null ? deviationColor(Cesium, value) : null
        }
      }
      entity.ellipse.material = new Cesium.ColorMaterialProperty(
        (color ?? Cesium.Color.fromCssColorString('#2a4a6a')).withAlpha(0.38),
      )
    }
    viewer.scene.requestRender()
  }

  function applyExaggeration(_Cesium: CesiumModule, viewer: Viz) {
    const v = exaggerationRef.current
    if (v && Math.abs(v - 1) > 1e-6) {
      viewer.scene.verticalExaggeration = v
      viewer.scene.verticalExaggerationRelativeHeight = 0
    }
    viewer.scene.requestRender()
  }

  /** Marching-squares isotherm contours of the real ERSST SST field (#11). */
  function buildIsoLayer(Cesium: CesiumModule, viewer: Viz) {
    const scene = sceneRef.current
    for (const e of scene.iso) {
      try {
        viewer.entities.remove(e)
      } catch {
        /* already disposed */
      }
    }
    scene.iso = []
    const levels = isolevelsRef.current
    if (!levels || levels.length === 0) return
    const grid = ersstRef.current
    if (!grid || !grid.samples) return
    const field = buildLatLonField(grid.samples.map((s) => ({ latitude: s.latitude, longitude: s.longitude, value: s.sst })))
    if (!field) return
    const alpha = opacityRef.current.isos ?? 1
    for (const level of levels) {
      for (const seg of isoLines(field, level)) {
        scene.iso.push(
          viewer.entities.add({
            polyline: {
              positions: [
                Cesium.Cartesian3.fromDegrees(seg.lon0, seg.lat0, 220),
                Cesium.Cartesian3.fromDegrees(seg.lon1, seg.lat1, 220),
              ],
              width: 2.5,
              arcType: Cesium.ArcType.GEODESIC,
              material: new Cesium.PolylineGlowMaterialProperty({
                color: Cesium.Color.fromCssColorString('#0ea5e9').withAlpha(0.95 * alpha),
                glowPower: 0.12,
              }),
            },
            show: layersRef.current.isos,
          }),
        )
      }
    }
    viewer.scene.requestRender()
  }

  /** True current-velocity arrows for the real model-grid u/v cells (#14). */
  function buildVectorsLayer(Cesium: CesiumModule, viewer: Viz) {
    const scene = sceneRef.current
    for (const e of scene.curVec) {
      try {
        viewer.entities.remove(e)
      } catch {
        /* already disposed */
      }
    }
    scene.curVec = []
    const vecs = currentVectorsRef.current
    if (!vecs || vecs.length === 0) return
    // Cap the drawn set so a dense 1/12° grid stays responsive — always the
    // strongest cells, honestly labelled "strongest first" in the UI.
    const shown = vecs
      .slice()
      .sort((a, b) => Math.hypot((b.u || 0), (b.v || 0)) - Math.hypot((a.u || 0), (a.v || 0)))
      .slice(0, 600)
    const alpha = opacityRef.current.vectors ?? 1
    for (const cell of shown) {
      const arrow = arrowFor(cell)
      if (!arrow) continue
      const pos = (p: { latitude: number; longitude: number }) => Cesium.Cartesian3.fromDegrees(p.longitude, p.latitude, 210)
      scene.curVec.push(
        viewer.entities.add({
          polyline: {
            positions: [pos(arrow.tail), pos(arrow.head)],
            width: 2.2,
            arcType: Cesium.ArcType.GEODESIC,
            material: new Cesium.PolylineGlowMaterialProperty({
              color: Cesium.Color.fromCssColorString('#38bdf8').withAlpha(0.9 * alpha),
              glowPower: 0.2,
            }),
          },
          show: layersRef.current.vectors,
        }),
      )
      for (const fin of arrow.fins) {
        scene.curVec.push(
          viewer.entities.add({
            polyline: {
              positions: [pos(arrow.head), pos(fin)],
              width: 1.6,
              arcType: Cesium.ArcType.GEODESIC,
              material: new Cesium.PolylineGlowMaterialProperty({
                color: Cesium.Color.fromCssColorString('#a5f3fc').withAlpha(0.8 * alpha),
                glowPower: 0.15,
              }),
            },
            show: layersRef.current.vectors,
          }),
        )
      }
    }
    viewer.scene.requestRender()
  }

  /** One horizontal depth slice of the real model field (feature #7): dots
   * colored on the live cell domain (temp → heat, salinity → haline). Honest:
   * no layer is drawn while `available:false` (no real grid / depth level). */
  function buildSliceLayer(Cesium: CesiumModule, viewer: Viz) {
    const scene = sceneRef.current
    for (const e of scene.slice) {
      try {
        viewer.entities.remove(e)
      } catch {
        /* already disposed */
      }
    }
    scene.slice = []
    const slice = modelSliceRef.current
    if (!slice || !slice.available || !slice.cells || slice.cells.length === 0) return
    const domain = domainFrom(slice.cells.map((c) => c.value))
    if (!domain) return
    const mode = scaleModesRef.current?.modelgrid ?? 'linear'
    const sal = slice.variable === 'salinity'
    const alpha = opacityRef.current.modelgrid ?? 1
    const colorFor = (v: number) =>
      sal ? salColorCssFrom(v, domain, mode) : tempColorCssFrom(v, domain, mode)
    for (const c of slice.cells) {
      scene.slice.push(
        viewer.entities.add({
          position: Cesium.Cartesian3.fromDegrees(c.longitude, c.latitude, 120),
          point: {
            pixelSize: 4,
            color: Cesium.Color.fromCssColorString(colorFor(c.value)).withAlpha(0.8 * alpha),
          },
          show: layersRef.current.modelgrid,
        }),
      )
    }
    viewer.scene.requestRender()
  }

  /** Real glider deployment tracks (feature #16): one glow polyline per
   * deployment through its true sample positions + depth-colored dots.
   * Clicking a dot opens the deployment profile (feature #18). */
  const GLIDER_PALETTE = ['#f59e0b', '#22d3ee', '#a78bfa', '#34d399', '#fb7185', '#e879f9']

  function buildGliderLayer(Cesium: CesiumModule, viewer: Viz) {
    const scene = sceneRef.current
    for (const e of scene.glider) {
      try {
        viewer.entities.remove(e)
      } catch {
        /* already disposed */
      }
    }
    scene.glider = []
    scene.glidersMap = []
    const tracks = gliderTracksRef.current
    if (!tracks || tracks.length === 0) return
    let depthLo = Infinity
    let depthHi = -Infinity
    for (const t of tracks) {
      for (const s of t.samples) {
        if (Number.isFinite(s.depth_m)) {
          if (s.depth_m < depthLo) depthLo = s.depth_m
          if (s.depth_m > depthHi) depthHi = s.depth_m
        }
      }
    }
    if (!Number.isFinite(depthLo)) return
    const alpha = opacityRef.current.glider ?? 1
    tracks.forEach((t, i) => {
      const color = GLIDER_PALETTE[i % GLIDER_PALETTE.length]
      const pts = t.samples
        .filter((s) => Number.isFinite(s.latitude) && Number.isFinite(s.longitude))
        .map((s) => Cesium.Cartesian3.fromDegrees(s.longitude, s.latitude, 200))
      if (pts.length >= 2) {
        const line = viewer.entities.add({
          polyline: {
            positions: pts,
            width: 3,
            arcType: Cesium.ArcType.GEODESIC,
            material: new Cesium.PolylineGlowMaterialProperty({
              color: Cesium.Color.fromCssColorString(color).withAlpha(0.85 * alpha),
              glowPower: 0.18,
            }),
          },
          show: layersRef.current.glider,
        })
        scene.glider.push(line)
        scene.glidersMap.push({ entity: line, deploymentId: t.deploymentId, baseColor: color })
      }
      for (const s of t.samples) {
        if (!Number.isFinite(s.latitude) || !Number.isFinite(s.longitude)) continue
        const dot = viewer.entities.add({
          position: Cesium.Cartesian3.fromDegrees(s.longitude, s.latitude, 200),
          point: {
            pixelSize: 5,
            color: Cesium.Color.fromCssColorString(depthColorCss(s.depth_m, depthLo, depthHi)).withAlpha(0.95 * alpha),
          },
          show: layersRef.current.glider,
        })
        scene.glider.push(dot)
        scene.glidersMap.push({ entity: dot, deploymentId: t.deploymentId, baseColor: depthColorCss(s.depth_m, depthLo, depthHi) })
      }
    })
    viewer.scene.requestRender()
  }

  /** Recolour existing dense layers with their per-layer opacity (#12). */
  function applyOpacity(Cesium: CesiumModule, viewer: Viz, state: Partial<Record<LayerKey, number>>) {
    const scene = sceneRef.current
    const a = (key: LayerKey) => state[key] ?? 1

    // Real ERSST SST dots — base colours recomputed on the live data domain.
    const sstGrid = ersstRef.current
    const sstStats = sstGrid?.stats
    const sstDomain = sstStats && sstStats.min !== null && sstStats.max !== null ? { min: sstStats.min, max: sstStats.max } : null
    const sstMode = scaleModesRef.current?.sst ?? 'linear'
    const sstAlpha = a('realSST')
    for (let i = 0; i < scene.sst.length; i++) {
      const s = sstSamplesRef.current[i]
      const e = scene.sst[i]
      if (!s || !e.point) continue
      e.point.color = new Cesium.ConstantProperty(
        Cesium.Color.fromCssColorString(tempColorCssFrom(s.sst, sstDomain, sstMode)).withAlpha(0.8 * sstAlpha),
      )
    }

    // Real satellite Chl-a dots — base colours recomputed on the CHL domain.
    const chlGrid = chlorRef.current
    const chlStats = chlGrid?.stats
    const chlDomain = chlStats && chlStats.min !== null && chlStats.max !== null ? { min: chlStats.min, max: chlStats.max } : null
    const chlMode = scaleModesRef.current?.chl ?? 'log'
    const chlAlpha = a('realChl')
    for (let i = 0; i < scene.chl.length; i++) {
      const s = chlSamplesRef.current[i]
      const e = scene.chl[i]
      if (!s || !e.point) continue
      e.point.color = new Cesium.ConstantProperty(
        Cesium.Color.fromCssColorString(chlorColorCssFrom(s.chlor_a, chlDomain, chlMode)).withAlpha(0.8 * chlAlpha),
      )
    }

    // Temperature heat patches (the disagreement layer keeps its status colours).
    const tempAlpha = a('temperature')
    for (const t of scene.temps) {
      if (!t.entity.ellipse) continue
      const disagree = disagreementRef.current.find((d) => d.location_id === t.locId)
      if (layersRef.current.disagreement && disagree) continue
      const def = Cesium.Color.fromCssColorString(tempColorCss(t.temp ?? 28))
      t.entity.ellipse.material = new Cesium.ColorMaterialProperty(def.withAlpha(0.38 * tempAlpha))
    }

    // Wave ripples.
    const waveAlpha = a('waves')
    for (const e of scene.waves) {
      if (!e.ellipse) continue
      e.ellipse.material = new Cesium.ColorMaterialProperty(Cesium.Color.fromCssColorString('#a5f3fc').withAlpha(0.16 * waveAlpha))
    }

    // Currents: glowing arcs + streaming dots.
    const currentAlpha = a('currents')
    for (const e of scene.currents) {
      if (e.billboard) {
        e.billboard.color = new Cesium.ConstantProperty(Cesium.Color.WHITE.withAlpha(currentAlpha))
      } else if (e.polyline && e.polyline.material && 'color' in e.polyline.material) {
        const glow = e.polyline.material as { color: InstanceType<CesiumModule['Property']> }
        glow.color = new Cesium.ConstantProperty(Cesium.Color.fromCssColorString('#22d3ee').withAlpha(0.75 * currentAlpha))
      }
    }

    // Real Argo float markers.
    const argoAlpha = a('realArgo')
    for (const e of scene.realArgo) {
      if (!e.point) continue
      e.point.color = new Cesium.ConstantProperty(Cesium.Color.fromCssColorString('#f472b6').withAlpha(argoAlpha))
    }

    // Isosurface contours.
    const isoAlpha = a('isos')
    for (const e of scene.iso) {
      if (!e.polyline || !e.polyline.material || !('color' in e.polyline.material)) continue
      const glow = e.polyline.material as { color: InstanceType<CesiumModule['Property']> }
      glow.color = new Cesium.ConstantProperty(Cesium.Color.fromCssColorString('#0ea5e9').withAlpha(0.95 * isoAlpha))
    }

    // Current-velocity arrows (shaft + fins share one cyan ramp).
    const vecAlpha = a('vectors')
    for (const e of scene.curVec) {
      if (!e.polyline || !e.polyline.material || !('color' in e.polyline.material)) continue
      const glow = e.polyline.material as { color: InstanceType<CesiumModule['Property']> }
      glow.color = new Cesium.ConstantProperty(Cesium.Color.fromCssColorString('#38bdf8').withAlpha(0.9 * vecAlpha))
    }

    // Horizontal model-grid depth slice (feature #7): live-domain reelors.
    const slice = modelSliceRef.current
    const sliceDomain = slice && slice.available ? domainFrom(slice.cells.map((c) => c.value)) : null
    const sliceMode = scaleModesRef.current?.modelgrid ?? 'linear'
    const sliceSal = slice?.variable === 'salinity'
    const sliceAlpha = a('modelgrid')
    for (let i = 0; i < scene.slice.length; i++) {
      const cell = slice?.cells[i]
      const e = scene.slice[i]
      if (!cell || !sliceDomain || !e.point) continue
      e.point.color = new Cesium.ConstantProperty(
        Cesium.Color.fromCssColorString(sliceSal ? salColorCssFrom(cell.value, sliceDomain, sliceMode) : tempColorCssFrom(cell.value, sliceDomain, sliceMode)).withAlpha(0.8 * sliceAlpha),
      )
    }

    // Real glider tracks + dots (feature #16): restore base colors × alpha.
    const gliderAlpha = a('glider')
    for (const g of scene.glidersMap) {
      const e = g.entity
      if (e.point) {
        e.point.color = new Cesium.ConstantProperty(Cesium.Color.fromCssColorString(g.baseColor).withAlpha(0.95 * gliderAlpha))
      } else if (e.polyline && e.polyline.material && 'color' in e.polyline.material) {
        const glow = e.polyline.material as { color: InstanceType<CesiumModule['Property']> }
        glow.color = new Cesium.ConstantProperty(Cesium.Color.fromCssColorString(g.baseColor).withAlpha(0.85 * gliderAlpha))
      }
    }

    viewer.scene.requestRender()
  }

  function applyLayers(Cesium: CesiumModule, viewer: Viz, state: LayersState) {
    const scene = sceneRef.current
    scene.markers.forEach((m) => {
      if (m.label) (m.label as unknown as Showable).show = state.labels
    })
    scene.temps.forEach((t) => {
      const disagree = disagreementRef.current.find((d) => d.location_id === t.locId)
      const disagreeOn = state.disagreement && disagree != null
      t.entity.show = state.temperature || disagreeOn
      if (disagreeOn && t.entity.ellipse) {
        const col = bandColor(Cesium, disagree.band)
        t.entity.ellipse.material = new Cesium.ColorMaterialProperty(col.withAlpha(disagree.band === 'red' ? 0.5 : 0.42))
        t.entity.ellipse.outlineColor = new Cesium.ConstantProperty(col.withAlpha(0.95))
        t.entity.ellipse.outlineWidth = new Cesium.ConstantProperty(3)
      } else if (state.temperature && t.entity.ellipse && !disagreeOn) {
        const def = Cesium.Color.fromCssColorString(tempColorCss(t.temp ?? 28))
        t.entity.ellipse.material = new Cesium.ColorMaterialProperty(def.withAlpha(0.38))
        t.entity.ellipse.outlineColor = new Cesium.ConstantProperty(def.withAlpha(0.9))
        t.entity.ellipse.outlineWidth = new Cesium.ConstantProperty(2)
      }
    })
    scene.waves.forEach((e) => (e.show = state.waves))
    scene.currents.forEach((e) => (e.show = state.currents))
    scene.storm.forEach((e) => (e.show = state.storm))
    scene.rings.forEach((e) => (e.show = state.uncertainty))
    scene.focus.forEach((e) => (e.show = state.priority))
    scene.argo.forEach((e) => (e.show = state.argo))
    scene.realArgo.forEach((e) => (e.show = state.realArgo))
    scene.sst.forEach((e) => (e.show = state.realSST))
    scene.chl.forEach((e) => (e.show = state.realChl))
    scene.anomalies.forEach((e) => (e.show = state.anomalies))
    scene.tide.forEach((e) => (e.show = state.tide))
    scene.iso.forEach((e) => (e.show = state.isos))
    scene.curVec.forEach((e) => (e.show = state.vectors))
    scene.slice.forEach((e) => (e.show = state.modelgrid))
    scene.glider.forEach((e) => (e.show = state.glider))
    // Keep every per-layer opacity applied after any layer toggle re-colours it.
    applyOpacity(Cesium, viewer, opacityRef.current)
    viewer.scene.requestRender()
  }

  return (
    <div ref={containerRef} className="cesium-globe">
      <div className="cesium-hint">
        <span>Drag · spin globe</span>
        <span>Scroll · zoom</span>
        <span>Ctrl+drag · pan</span>
      </div>
    </div>
  )
}
