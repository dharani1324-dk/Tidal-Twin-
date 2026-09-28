import { memo, useEffect, useRef, useState } from 'react'
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
  normalizedTempRgb,
  omegaColorCss,
  phColorCss,
  phDepthToAltitude,
  PH_DEPTH_SCALE_DEFAULT,
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
  reading_status?: string
  reading_source?: string | null
  reading_time?: string | null
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
  | 'oxygen'
  | 'oxygenHotspots'
  | 'acidification'
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

/** Real in-situ glider BGC dissolved-oxygen sample with source coordinates. */
export interface OxygenSample {
  deployment_id: string
  time: string
  latitude: number
  longitude: number
  depth_m: number
  dissolved_oxygen: number
  qc_flags?: string | null
  source_file?: string | null
}

/**
 * Real in-situ Argo BGC pH sample (from /api/v1/acidification/samples).
 *
 * `ph_total` is MEASURED. `omega_arag` is DERIVED from it via CO2SYS and is
 * null whenever temperature or practical salinity was unavailable - the layer
 * must never substitute a colour for a value that does not exist.
 */
export interface PhSample {
  id: number
  time: string | null
  latitude: number
  longitude: number
  depth_m: number
  ph_total: number
  omega_arag: number | null
  /** SQLite returns the SQLAlchemy Boolean as 0/1, so this is not a real bool. */
  omega_arag_derived: boolean | 0 | 1
  severity_label: string
  is_undersaturated: boolean
  region_distance_km?: number | null
  float_id?: string | null
  cycle?: number | null
  qc_flag?: string
  source_record_link?: string | null
}

/** Which quantity drives the acidification layer's colour. */
export type PhMetric = 'ph' | 'omega'

/** Deoxygenation hotspot (from /api/v1/deoxygenation/hotspots). */
export interface OxygenHotspot {
  region_id: number
  region: string
  depth_layer: string
  latitude: number
  longitude: number
  distance_to_region_km: number
  priority: number
  severity: string
  severity_ordinal: number
  is_hotspot: boolean
  statistics: {
    n_samples: number
    n_hypoxic: number
    n_dead_zone: number
    min_do_mg_l: number
    mean_do_mg_l: number
    max_do_mg_l: number
    centroid_lat: number
    centroid_lon: number
    distance_to_region_km: number
    severity_distribution: Record<string, number>
    temporal_span_days: number
    latest_sample_at: string | null
    persistence: number
  }
  trend: string
  medium_display: string
  unit: string
  published_class: string
  latest_sample_at: string | null
  action: string
  recommendations: Array<{
    action: string
    priority: string
    text: string
  }>
  confidence: number
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

/** Scenes that already have the globe's single `preRender` animation loop. */
const tickerInstalled = new WeakSet<object>()

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
type Cartesian3 = InstanceType<CesiumModule['Cartesian3']>
type PointCollection = InstanceType<CesiumModule['PointPrimitiveCollection']>
type BillboardCollection = InstanceType<CesiumModule['BillboardCollection']>
type Billboard = InstanceType<CesiumModule['Billboard']>
type PolylineCollection = InstanceType<CesiumModule['PolylineCollection']>

/* ==================================================================
 * Batched point / line / sprite layers
 * ------------------------------------------------------------------
 * Thousands of `Entity` objects are the worst thing you can hand
 * Cesium: every entity runs the EntityVisualizer property + updater
 * machinery on *every* frame, and every animated `ellipse` property
 * change re-tessellates its geometry and re-uploads a primitive.
 *
 * Everything dense therefore lives in a batched low-level primitive
 * (one draw call, plain typed arrays) and is only *built* when its data
 * actually changes. Opacity and layer toggles never rebuild anything:
 * they flip `collection.show` / per-point `color` in place.
 * ================================================================== */

/** One dense gridded field (ERSST SST, Chl-a, model depth slice). */
interface PointFieldLayer {
  /** Every real cell, batched into a single draw call. */
  full: PointCollection
  /**
   * Stride-sampled view of the *same* cells, shown at whole-earth range
   * where individual cells are sub-pixel. No invented data — fewer marks
   * of the identical field at a larger mark size, so the rendered
   * coverage is unchanged.
   */
  coarse: PointCollection
  /** Index-aligned base RGB of `full` (3 floats per cell). */
  rgb: Float32Array
  /** Cells actually plotted. */
  count: number
  /** Stride used for the coarse representation. */
  stride: number
  /** Intrinsic alpha of the layer before the user's opacity slider. */
  baseAlpha: number
  /** Mark size in pixels. */
  pixelSize: number
  /** Height above the ellipsoid, in metres. */
  height: number
  /** Reused so an opacity change never allocates thousands of Colours. */
  scratch: InstanceType<CesiumModule['Color']>
  /** Which LOD is currently displayed. */
  lod: 'full' | 'coarse'
  /** Whether the owning layer toggle is on. */
  enabled: boolean
  /**
   * Real rows behind the plotted cells, index-aligned with `full`. Kept only
   * for layers whose per-sample source value belongs in a readout; it is never
   * used to draw anything that the API did not return. Only the oxygen layer
   * populates it today.
   */
  samples?: OxygenSample[]
  /**
   * ECEF positions parallel to `samples`. `fromDegrees` is the expensive part
   * of a screen-space nearest search (trig + surface projection), so it is paid
   * once at build time rather than on every throttled hover.
   */
  positions?: Cartesian3[]
}

/** Screen-space ring pulses (wave ripples + sampling-priority rings). */
interface RingPulseLayer {
  collection: BillboardCollection
  items: { billboard: Billboard; phase: number; period: number; peakAlpha: number }[]
  enabled: boolean
  /** Layer opacity folded into the per-frame alpha envelope. */
  peakScale: number
}

const ringSpriteCache: Record<string, string> = {}

/**
 * Soft expanding ring used for wave ripples and sampling-priority pulses.
 * Animating a billboard `scale` is one float write per frame; animating an
 * `ellipse` entity re-tessellates geometry and re-uploads a primitive every
 * frame, which is what made the globe stutter while dragging.
 * The texture is white so each pulse can be tinted from the data ramp.
 */
function getRingUrl(aspect = 0.72) {
  const key = aspect.toFixed(2)
  const cached = ringSpriteCache[key]
  if (cached) return cached
  const size = 256
  const c = document.createElement('canvas')
  c.width = c.height = size
  const ctx = c.getContext('2d')!
  const half = size / 2
  ctx.translate(half, half)
  ctx.scale(1, aspect)
  const g = ctx.createRadialGradient(0, 0, 0, 0, 0, half)
  g.addColorStop(0, 'rgba(255,255,255,0)')
  g.addColorStop(0.72, 'rgba(255,255,255,0.05)')
  g.addColorStop(0.88, 'rgba(255,255,255,0.95)')
  g.addColorStop(0.965, 'rgba(255,255,255,0.32)')
  g.addColorStop(1, 'rgba(255,255,255,0)')
  ctx.fillStyle = g
  ctx.beginPath()
  ctx.arc(0, 0, half, 0, Math.PI * 2)
  ctx.fill()
  const url = c.toDataURL()
  ringSpriteCache[key] = url
  return url
}

/** Camera height (m) above which a field drops to its coarse representation. */
const LOD_FAR_HEIGHT = 9e6
/** Camera height (m) below which it returns to full detail. */
const LOD_NEAR_HEIGHT = 6.5e6
/** Cap on the number of marks in the coarse representation. */
const LOD_MAX_COARSE_MARKS = 1200
/** Screen-space pick radius (px) for the batched oxygen hover readout. */
const HOVER_RADIUS_PX = 11
/** Altitude (m) of the batched oxygen marks; matches the former entity height. */
const OXYGEN_POINT_ALTITUDE_M = 90

/** Escape untrusted text before it reaches the hover tooltip's innerHTML. */
function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function makePointField(
  Cesium: CesiumModule,
  viewer: Viz,
  pixelSize: number,
  baseAlpha: number,
  height = 120,
): PointFieldLayer {
  return {
    full: viewer.scene.primitives.add(new Cesium.PointPrimitiveCollection()),
    coarse: viewer.scene.primitives.add(new Cesium.PointPrimitiveCollection()),
    rgb: new Float32Array(0),
    count: 0,
    stride: 1,
    baseAlpha,
    pixelSize,
    height,
    scratch: new Cesium.Color(1, 1, 1, 1),
    lod: 'full',
    enabled: true,
  }
}

function disposePointField(viewer: Viz, field: PointFieldLayer | null) {
  if (!field) return
  // `PointPrimitiveCollection.destroyObject` is a no-op (it owns no
  // textures); removing it from the scene is what frees the GPU buffers.
  viewer.scene.primitives.remove(field.full)
  viewer.scene.primitives.remove(field.coarse)
  field.count = 0
  field.rgb = new Float32Array(0)
}

function disposeRingPulses(viewer: Viz, layer: RingPulseLayer | null) {
  if (!layer) return
  viewer.scene.primitives.remove(layer.collection)
  layer.items = []
}

/** Everything needed to draw one expanding ring; see `addRingPulses`. */
interface RingPulseSpec {
  lon: number
  lat: number
  height: number
  /** Fractional cycle offset so neighbouring rings are not in lock-step. */
  phase: number
  color: string
  peakAlpha: number
  /** Seconds for one expand-and-fade cycle. */
  period: number
  /** Radius at cycle start / growth per cycle, in metres. */
  base: number
  span: number
  /** Ellipse minor/major ratio, preserving the original ripple look. */
  squash: number
}

/**
 * Draw every expanding ring of one class into a single BillboardCollection.
 * `items` keeps the billboard handles so `stepRingPulses` can animate them
 * with two float writes per ring per frame.
 */
function addRingPulses(
  Cesium: CesiumModule,
  viewer: Viz,
  layer: RingPulseLayer,
  specs: RingPulseSpec[],
) {
  disposeRingPulses(viewer, layer)
  const items: RingPulseLayer['items'] = []
  if (specs.length === 0) return
  const collection = new Cesium.BillboardCollection({ scene: viewer.scene })
  const image = getRingUrl()
  for (const spec of specs) {
    // The sprite is drawn at the ring's *maximum* extent and scaled down by
    // the ticker, so the drawn radius range is base → base + span.
    const width = (spec.base + spec.span) * 2
    const color = Cesium.Color.fromCssColorString(spec.color)
    const billboard = collection.add({
      image,
      width,
      height: width * spec.squash,
      verticalOrigin: Cesium.VerticalOrigin.CENTER,
      // Alpha is driven per-frame by the ticker's fade envelope.
      color: color.withAlpha(0),
      position: Cesium.Cartesian3.fromDegrees(spec.lon, spec.lat, spec.height),
    })
    items.push({ billboard, phase: spec.phase, period: spec.period, peakAlpha: spec.peakAlpha })
  }
  viewer.scene.primitives.add(collection)
  layer.collection = collection
  layer.items = items
  collection.show = layer.enabled
}

/** `Cartesian3.fromDegrees` into a reused object: no allocation per cell. */
function setCartesianDegrees(
  Cesium: CesiumModule,
  out: InstanceType<CesiumModule['Cartesian3']>,
  lon: number,
  lat: number,
  height: number,
) {
  Cesium.Cartesian3.fromDegrees(lon, lat, height, Cesium.Ellipsoid.WGS84, out)
}

/**
 * Fill (or refill) a point field from real cells. Each cell's colour is
 * parsed once and cached as raw floats, so later opacity changes are pure
 * buffer writes instead of thousands of Colour parses.
 */
function fillPointField(
  Cesium: CesiumModule,
  field: PointFieldLayer,
  cells: { longitude: number; latitude: number; color: string }[],
  scaleByDistance?: InstanceType<CesiumModule['NearFarScalar']>,
) {
  const n = cells.length
  const stride = Math.max(1, Math.ceil(n / LOD_MAX_COARSE_MARKS))
  if (field.rgb.length < n * 3) field.rgb = new Float32Array(n * 3)

  const scratchPos = new Cesium.Cartesian3()
  const coarseSbd = scaleByDistance
    ? new Cesium.NearFarScalar(scaleByDistance.near * 2.4, 1.5, scaleByDistance.far * 2.4, 1.5)
    : undefined

  field.full.removeAll()
  field.coarse.removeAll()

  for (let i = 0; i < n; i++) {
    const cell = cells[i]
    // `Color.fromCssColorString` returns undefined for any string it cannot
    // parse, and several colour helpers can emit a malformed value if an
    // upstream number is NaN/Infinity. Degrade the single cell rather than
    // letting one bad value throw and take the whole layer down.
    const c = Cesium.Color.fromCssColorString(cell.color)
    if (!c) continue
    if (!Number.isFinite(cell.longitude) || !Number.isFinite(cell.latitude)) continue
    field.rgb[i * 3] = c.red
    field.rgb[i * 3 + 1] = c.green
    field.rgb[i * 3 + 2] = c.blue
    setCartesianDegrees(Cesium, scratchPos, cell.longitude, cell.latitude, field.height)
    field.full.add({
      position: scratchPos,
      pixelSize: field.pixelSize,
      color: c.withAlpha(1),
      scaleByDistance,
    })
    if (i % stride === 0) {
      setCartesianDegrees(Cesium, scratchPos, cell.longitude, cell.latitude, field.height)
      field.coarse.add({
        position: scratchPos,
        pixelSize: field.pixelSize * 1.5,
        color: c.withAlpha(1),
        scaleByDistance: coarseSbd,
      })
    }
  }
  field.count = n
  field.stride = stride
  field.lod = 'full'
  field.full.show = field.enabled
  field.coarse.show = false
}

/** Push the layer's effective alpha into the point buffers. No allocation. */
function applyPointFieldOpacity(field: PointFieldLayer | null, userAlpha: number) {
  if (!field) return
  const a = field.baseAlpha * Math.max(0, Math.min(1, userAlpha))
  const { scratch, rgb } = field
  for (let i = 0; i < field.count; i++) {
    const o = i * 3
    scratch.red = rgb[o]
    scratch.green = rgb[o + 1]
    scratch.blue = rgb[o + 2]
    scratch.alpha = a
    const p = field.full.get(i)
    if (p) p.color = scratch
  }
  for (let i = 0, n = Math.ceil(field.count / field.stride); i < n; i++) {
    const p = field.coarse.get(i)
    if (p) p.color = scratch
  }
}

function setPointFieldEnabled(field: PointFieldLayer | null, enabled: boolean) {
  if (!field) return
  field.enabled = enabled
  if (enabled) {
    field.full.show = field.lod === 'full'
    field.coarse.show = field.lod === 'coarse'
  } else {
    field.full.show = false
    field.coarse.show = false
  }
}

/** Apply a uniform alpha to every billboard in a batched collection. */
function setBillboardAlpha(
  _Cesium: CesiumModule,
  collection: BillboardCollection | null,
  alpha: number,
) {
  if (!collection) return
  const a = Math.max(0, Math.min(1, alpha))
  for (let i = 0; i < collection.length; i++) {
    const b = collection.get(i)
    if (!b?.color) continue
    b.color = b.color.withAlpha(a)
  }
}

/**
 * A batched line layer. `base` holds each polyline's intrinsic colour so the
 * opacity slider can be reapplied without re-parsing hex strings (or, worse,
 * rebuilding the collection) on every drag frame.
 */
interface PolyLayer {
  collection: PolylineCollection
  /** Intrinsic colour per polyline index. */
  base: InstanceType<CesiumModule['Color']>[]
}

/**
 * Fold the user alpha into each line's cached base colour, in place. The
 * uniform is *reassigned* rather than mutated so Cesium marks it dirty and
 * re-uploads; the base colours themselves are never touched.
 */
function applyPolyLayerOpacity(_Cesium: CesiumModule, layer: PolyLayer | null, alpha: number) {
  if (!layer) return
  const a = Math.max(0, Math.min(1, alpha))
  const { collection, base } = layer
  for (let i = 0; i < collection.length; i++) {
    const line = collection.get(i)
    const uniforms = line?.material?.uniforms as { color?: unknown } | undefined
    const c = base[i]
    if (!uniforms || !c) continue
    // Reassign (never mutate) so Cesium marks the uniform dirty and re-uploads.
    uniforms.color = c.withAlpha(a)
  }
}

/**
 * Camera-range level of detail, driven by the single `preRender` ticker and
 * never from React. Hysteresis keeps the two collections from flapping while
 * the user hovers the boundary.
 */
/**
 * Swap a point field between its full and coarse mark sets based on camera
 * height. Returns true when the LOD actually changed, so the caller can request
 * a render (the globe runs in requestRenderMode).
 */
function updatePointFieldLod(field: PointFieldLayer | null, cameraHeight: number): boolean {
  if (!field || !field.enabled || field.stride <= 1) return false
  if (field.lod === 'full' && cameraHeight > LOD_FAR_HEIGHT) {
    field.lod = 'coarse'
    field.full.show = false
    field.coarse.show = true
    return true
  } else if (field.lod === 'coarse' && cameraHeight < LOD_NEAR_HEIGHT) {
    field.lod = 'full'
    field.full.show = true
    field.coarse.show = false
    return true
  }
  return false
}

/**
 * Advance every time-based globe animation for this frame. Called only from the
 * single `preRender` ticker and only while the camera is idle, so a drag costs
 * no animation work at all. Nothing here touches React state.
 *
 * Returns true when something actually moved this frame. The globe runs in
 * `requestRenderMode`, so the scene only draws when `requestRender()` is called:
 * the ticker uses this flag to keep time-based animation alive while every
 * other idle state (all layers off, nothing selected, camera parked) stops
 * drawing entirely.
 */
function stepAnimations(scene: Scene, now: number): boolean {
  let animating = false
  if (stepRingPulses(scene.wavePulses, now)) animating = true
  if (stepRingPulses(scene.focusPulses, now)) animating = true
  if (stepCurrentStream(scene, now)) animating = true
  return animating
}

/** Returns true when the layer has visible pulses being advanced. */
function stepRingPulses(layer: RingPulseLayer, now: number): boolean {
  if (!layer.enabled || !layer.collection) return false
  const seconds = now / 1000
  const scale = layer.peakScale === undefined ? 1 : layer.peakScale
  for (const item of layer.items) {
    const k = (seconds / item.period + item.phase) % 1
    item.billboard.scale = 0.16 + k * 0.84
    // Fade in fast, out slow — the same envelope the old ellipse used.
    const a = k < 0.12 ? k / 0.12 : Math.max(0, 1 - (k - 0.12) / 0.88)
    const c = item.billboard.color
    if (c) c.alpha = a * item.peakAlpha * scale
  }
  return layer.items.length > 0
}

/**
 * Stream the current-path dots along their orbits by writing positions in
 * place. Previously each dot was an Entity with a `CallbackPositionProperty`
 * that allocated a fresh Cartesian3 sixty times a second.
 *
 * Returns true when at least one dot was moved this frame.
 */
function stepCurrentStream(scene: Scene, now: number): boolean {
  const collection = scene.currentDots
  if (!collection || collection.show === false || !scene.currentStream) return false
  const stream = scene.currentStream
  const seconds = now / 1000
  const pos = stream.scratch
  for (let i = 0; i < stream.dots.length; i++) {
    const d = stream.dots[i]
    const a = d.phase + seconds * d.speed
    const ca = Math.cos(a)
    const sa = Math.sin(a)
    pos.x = (d.u.x * ca + d.v.x * sa) * d.radius
    pos.y = (d.u.y * ca + d.v.y * sa) * d.radius
    pos.z = (d.u.z * ca + d.v.z * sa) * d.radius
    const billboard = collection.get(i)
    if (billboard) billboard.position = pos
  }
  return stream.dots.length > 0
}

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
  /** Real, non-interpolated glider dissolved-oxygen samples. */
  oxygenSamples?: OxygenSample[]
  /** Deoxygenation hotspots (hypoxic zones) from Argo BGC + NOAA data. */
  oxygenHotspots?: OxygenHotspot[]
  /** Real measured in-situ pH samples, drawn at their true depth. */
  phSamples?: PhSample[]
  /** Colour the pH layer by measured pH or by derived aragonite saturation. */
  phMetric?: PhMetric
  /** Depth window (m) to show in the pH layer; samples outside are not drawn. */
  phDepthRange?: { min: number; max: number } | null
  /** Metres of altitude per metre of real depth in the pH layer. */
  phDepthScale?: number
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
  /** entity → location_id, for O(1) click / hover resolution. */
  markerMap: Map<VizEntity, number>
  temps: { locId: number; entity: VizEntity; temp: number | null }[]
  /** Wave ripples + sampling-priority rings, batched as tinted ring sprites. */
  wavePulses: RingPulseLayer
  focusPulses: RingPulseLayer
  currents: VizEntity[]
  storm: VizEntity[]
  rings: VizEntity[]
  argo: VizEntity[]
  realArgo: VizEntity[]
  /** Real Argo float markers → float id (click target). */
  argoMap: Map<VizEntity, string>
  /** Real ERSST SST grid (batched point field + coarse LOD). */
  sst: PointFieldLayer | null
  /** Real satellite Chl-a grid (batched point field + coarse LOD). */
  chl: PointFieldLayer | null
  /** Real glider dissolved-oxygen samples (batched point field). */
  oxygen: PointFieldLayer | null
  /** Deoxygenation hotspots (hypoxic zone markers). */
  oxygenHotspots: VizEntity[]
  /** Real measured in-situ pH samples (batched point field, depth-placed). */
  ph: PointFieldLayer | null
  anomalies: VizEntity[]
  tide: VizEntity[]
  replay: VizEntity[]
  /** Marching-squares isosurface contours of the real SST field (batched). */
  iso: PolyLayer | null
  /** True current-velocity arrows from the real model grid (batched). */
  curVec: PolyLayer | null
  /** One horizontal model-grid depth slice (batched point field). */
  slice: PointFieldLayer | null
  /** Real glider deployment tracks (batched polylines). */
  gliderTracks: PolyLayer | null
  /** Real glider sample dots (batched point field, click target). */
  gliderDots: PointFieldLayer | null
  /** glider line polyline → deployment id (click target). */
  glidersMap: Map<InstanceType<CesiumModule['Polyline']>, string>
  /** Batched streaming dots that orbit the ocean along the current paths. */
  currentDots: BillboardCollection | null
  /** Orbits + phases backing `currentDots`, so the ticker writes in place. */
  currentStream: {
    dots: {
      u: InstanceType<CesiumModule['Cartesian3']>
      v: InstanceType<CesiumModule['Cartesian3']>
      radius: number
      phase: number
      speed: number
    }[]
    scratch: InstanceType<CesiumModule['Cartesian3']>
  } | null
  transect: (InstanceType<CesiumModule['Primitive']> | VizEntity)[]
}

function emptyScene(): Scene {
  return {
    markers: [],
    markerMap: new Map(),
    temps: [],
    wavePulses: { collection: null as unknown as BillboardCollection, items: [], enabled: true, peakScale: 0.16 },
    focusPulses: { collection: null as unknown as BillboardCollection, items: [], enabled: true, peakScale: 0.04 },
    currents: [],
    storm: [],
    rings: [],
    argo: [],
    realArgo: [],
    argoMap: new Map(),
    sst: null,
    chl: null,
  oxygen: null,
  oxygenHotspots: [],
  ph: null,
    anomalies: [],
    tide: [],
    replay: [],
    iso: null,
    curVec: null,
    slice: null,
    gliderTracks: null,
    gliderDots: null,
    glidersMap: new Map(),
    currentDots: null,
    currentStream: null,
    transect: [],
  }
}

function CesiumGlobe({ locations, layers, storm, series, timeCursor, timeColor = 'temp', uncertainties, priorities, argoFloats, realArgoFloats, ersst, chlor, oxygenSamples, oxygenHotspots, phSamples, phMetric = 'ph', phDepthRange = null, phDepthScale = PH_DEPTH_SCALE_DEFAULT, scaleModes, disagreement, anomalies, tideCandidates, replayMarkers, transect, transectActive, opacity, exaggeration = 1, isolevels, currentVectors, modelSlice, gliderTracks, onGliderClick, onRegionClick, onArgoFloatClick, onTransectPick, flyToTarget }: CesiumGlobeProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const viewerRef = useRef<Viz | null>(null)
  /** Set when WebGL/Viewer construction fails, so the blank container explains itself. */
  const [globeError, setGlobeError] = useState<string | null>(null)
  const sceneRef = useRef<Scene>(emptyScene())
  /** True while rotate / zoom / pan is in progress (drives the LOD + FX budget). */
  const interactingRef = useRef(false)
  /** Pending timer that restores full quality once the camera settles. */
  const settleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  /** Closed-over by the pick handler; keeps MOUSE_MOVE from re-subscribing. */
  const liveRef = useRef(false)
  /**
   * Oxygen samples are drawn as one batched `PointFieldLayer` (up to 5000 of
   * them), so they can no longer carry a per-entity `description` the way the
   * old `Entity` points did. The hover readout is therefore resolved here and
   * rendered as a plain HTML tooltip. Written straight into this ref by the
   * throttled MOUSE_MOVE handler, so a hover never re-renders the globe.
   */
  const oxygenHoverRef = useRef<HTMLDivElement | null>(null)
  /**
   * Reused result for the hover projection. `worldToWindowCoordinates`
   * allocates a `Cartesian2` when the caller passes none, which would be 5000
   * throwaway objects per hover, so it is created once the module is loaded.
   */
  const oxygenHoverWindowRef = useRef<Cartesian2 | null>(null)
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
  const oxygenRef = useRef<OxygenSample[]>([])
  oxygenRef.current = oxygenSamples ?? []
  const oxygenHotspotsRef = useRef<OxygenHotspot[]>([])
  oxygenHotspotsRef.current = oxygenHotspots ?? []
  const phRef = useRef<PhSample[]>([])
  phRef.current = phSamples ?? []
  const phMetricRef = useRef<PhMetric>(phMetric)
  phMetricRef.current = phMetric
  const phDepthRangeRef = useRef<{ min: number; max: number } | null>(phDepthRange)
  phDepthRangeRef.current = phDepthRange
  const phDepthScaleRef = useRef(phDepthScale)
  phDepthScaleRef.current = phDepthScale
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
  const transectRef = useRef(transect ?? null)
  transectRef.current = transect ?? null
  const onTransectPickRef = useRef(onTransectPick)
  onTransectPickRef.current = onTransectPick
  const handlersRef = useRef<InstanceType<CesiumModule['ScreenSpaceEventHandler']>[]>([])
  /** Set once the viewer exists; lets later effects run their deferred work. */
  const readyRef = useRef(false)
  /**
   * Bumped every time the viewer is created or destroyed. Every async layer
   * effect compares the revision it captured against this and bails out if the
   * scene it was going to write into no longer exists.
   */
  const revRef = useRef(0)
  /**
   * Last input tuple each layer was built from. This is the fix for the
   * re-render storm: `scaleModes` / `locations` arrive as fresh objects on
   * every parent render, so an effect keyed on them used to tear down and
   * re-add thousands of primitives even when the data was identical.
   */
  const builtRef = useRef<Record<string, readonly unknown[]>>({})

  /** Runs `build` only when the recorded inputs for `key` actually changed. */
  function ensureLayer(key: string, inputs: readonly unknown[], build: () => void) {
    const prev = builtRef.current[key]
    if (prev && prev.length === inputs.length && prev.every((p, i) => Object.is(p, inputs[i]))) return
    builtRef.current[key] = inputs
    build()
  }

  /**
   * Force `key` to rebuild on the next `ensureLayer` call.
   *
   * Needed for the *entity*-backed layers. `buildScene` calls
   * `entities.removeAll()`, which drops them from the scene without touching
   * their input data — so the identity guard would see "nothing changed" and
   * skip the repaint, leaving the layer permanently blank after any change to
   * the region set.
   */
  function invalidateLayers(...keys: string[]) {
    for (const key of keys) delete builtRef.current[key]
  }

  /**
   * The dense layers whose effects run *before* the viewer exists (Cesium is a
   * dynamic import, so on first mount every layer effect bails out at
   * `if (!viewer) return`). This paints them once the viewer is up, and re-paints
   * them after any full `buildScene`, so a layer toggle or a new data fetch is
   * never silently dropped.
   *
   * `entities.removeAll()` does not touch primitives, so the batched layers are
   * already intact; re-running the guards is cheap because the input tuples are
   * unchanged and `ensureLayer` short-circuits.
   */
  function syncDeferredLayers(Cesium: CesiumModule, viewer: Viz) {
    const scale = scaleModesRef.current
    ensureLayer('sst', [ersstRef.current, scale?.sst], () => buildSstLayer(Cesium, viewer))
    ensureLayer('chl', [chlorRef.current, scale?.chl], () => buildChlLayer(Cesium, viewer))
    ensureLayer('oxygen', [oxygenRef.current], () => buildOxygenLayer(Cesium, viewer))
  ensureLayer('acidification', [phRef.current, phMetricRef.current, phDepthRangeRef.current], () => buildPhLayer(Cesium, viewer))
    ensureLayer('iso', [ersstRef.current, isolevelsRef.current], () => buildIsoLayer(Cesium, viewer))
    ensureLayer('curVec', [currentVectorsRef.current], () => buildVectorsLayer(Cesium, viewer))
    ensureLayer('slice', [modelSliceRef.current], () => buildSliceLayer(Cesium, viewer))
    ensureLayer('glider', [gliderTracksRef.current], () => buildGliderLayer(Cesium, viewer))
    ensureLayer('tide', [tideRef.current], () => buildTideLayer(Cesium, viewer))
    ensureLayer('replay', [replayRef.current], () => buildReplayLayer(Cesium, viewer))
    ensureLayer('oxygenHotspots', [oxygenHotspotsRef.current], () => buildHotspotLayer(Cesium, viewer))
    ensureLayer('realArgo', [realArgoRef.current], () => buildRealArgoLayer(Cesium, viewer))
    // The transect curtain is entity-backed too, and has no `ensureLayer` guard of
    // its own, so `buildScene` repaints it directly.
    if (transectRef.current) buildTransect(Cesium, viewer, transectRef.current)
    else if (transectActiveRef.current) enableSubsurface(Cesium, viewer)
    else clearTransect(viewer)
    applyOpacity(Cesium, viewer, opacityRef.current)
  }

  /**
   * Interaction-aware render budget. Called by Cesium's own camera events —
   * never by React, never per React render. It only trims *decorative* fill
   * rate (atmosphere, MSAA resolve, drawing-buffer scale, tile LOD); no data
   * layer is hidden and nothing disappears.
   */
  function setInteractionMode(active: boolean) {
    if (settleTimerRef.current) {
      clearTimeout(settleTimerRef.current)
      settleTimerRef.current = null
    }
    const viewer = viewerRef.current
    if (interactingRef.current === active) return
    interactingRef.current = active
    if (!viewer || viewer.isDestroyed()) return
    const { scene } = viewer
    if (active) {
      scene.globe.showGroundAtmosphere = false
      scene.globe.maximumScreenSpaceError = 8
      if (scene.msaaSamples !== 1) scene.msaaSamples = 1
      viewer.resolutionScale = 0.75
    } else {
      scene.globe.showGroundAtmosphere = true
      scene.globe.maximumScreenSpaceError = 2
      if (scene.msaaSamples !== 4) scene.msaaSamples = 4
      viewer.resolutionScale = 1
    }
    // Restore full quality shortly after the gesture ends so a series of short
    // flicks does not thrash the framebuffer / globe configuration.
    if (!active) {
      settleTimerRef.current = setTimeout(() => {
        settleTimerRef.current = null
      }, 140)
    }
  }

  /**
   * The globe's only per-frame loop. One `preRender` listener drives every
   * animation and the camera-range LOD; it never touches React state and it
   * skips all animation work while the camera is being dragged.
   */
  function installRenderTicker(viewer: Viz) {
    const { scene } = viewer
    if (tickerInstalled.has(scene)) return
    tickerInstalled.add(scene)
    scene.preRender.addEventListener(() => {
      if (viewer.isDestroyed()) return
      const sceneNow = sceneRef.current
      const interacting = interactingRef.current
      // In requestRenderMode the scene only draws when something asks it to.
      // Time-based animation is the one thing that has to keep asking, or the
      // pulse rings and current-path dots freeze at a random scale/phase.
      let dirty = false
      if (!interacting) {
        if (stepAnimations(sceneNow, Date.now())) dirty = true
      }
      const height = viewer.camera.positionCartographic?.height ?? 0
      if (updatePointFieldLod(sceneNow.sst, height)) dirty = true
      if (updatePointFieldLod(sceneNow.chl, height)) dirty = true
      if (updatePointFieldLod(sceneNow.slice, height)) dirty = true
      if (updatePointFieldLod(sceneNow.oxygen, height)) dirty = true
      if (updatePointFieldLod(sceneNow.gliderDots, height)) dirty = true
      if (dirty) scene.requestRender()
    })
  }

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
            // Only draw a frame when something actually changed. The scene holds
            // tens of thousands of point marks and polylines, so the default
            // continuous 60 fps loop burns CPU/GPU for nothing while the user
            // is reading the control column. Every mutation path in this file
            // already calls scene.requestRender(), so the globe still updates
            // the instant a layer, camera or selection changes.
            requestRenderMode: true,
            maximumRenderTimeChange: Infinity,
          })
        } catch (err) {
          // Do not swallow this: without WebGL the globe is permanently dead and
          // the user would otherwise see an unexplained empty gradient.
          console.error('[CesiumGlobe] Viewer construction failed', err)
          setGlobeError('3D globe unavailable - WebGL could not be initialised.')
          return
        }
        viewerRef.current = viewer
        const scene = viewer.scene
        scene.globe.baseColor = Cesium.Color.fromCssColorString('#0a2a4a')
        scene.globe.enableLighting = false
        // Coarser terrain/imagery tiles while idle would look soft; keep the
        // default (2) and only coarsen it during an active camera gesture.
        scene.globe.maximumScreenSpaceError = 2
        // Keep the globe camera fully navigable: close surface inspection,
        // whole-earth views, and unrestricted rotate/tilt/look/pan controls.
        const camCtrl = scene.screenSpaceCameraController
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
        // Interaction mode: trim decorative fill rate only while the camera moves.
        // `moveStart` / `moveEnd` cover drag, programmatic flights and wheel
        // zoom alike, so one pair of listeners is enough.
        viewer.camera.moveStart.addEventListener(() => setInteractionMode(true))
        viewer.camera.moveEnd.addEventListener(() => setInteractionMode(false))
        installRenderTicker(viewer)
        readyRef.current = true
        void applyBaseLayer(Cesium, viewer)
      }

      buildScene(Cesium, viewer)
      applyLayers(Cesium, viewer, layersRef.current)
      applyExaggeration(Cesium, viewer)
      const curs = cursorRef.current
      if (curs != null) applyCursor(Cesium, viewer, curs)
      // Layers whose effects ran before the viewer existed must be (re)drawn.
      syncDeferredLayers(Cesium, viewer)
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

  // TIDE decision markers. Guarded so a stable candidate set is not re-added
  // on every unrelated re-render; a full scene rebuild re-syncs them.
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    let cancelled = false
    loadCesium().then((Cesium) => {
      if (cancelled || viewer.isDestroyed()) return
      ensureLayer('tide', [tideRef.current], () => buildTideLayer(Cesium, viewer))
    })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tideCandidates])

  // Phase 6 — Decision Replay markers. Per-marker visibility follows the
  // current replay step, so this is also guarded.
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    let cancelled = false
    loadCesium().then((Cesium) => {
      if (cancelled || viewer.isDestroyed()) return
      ensureLayer('replay', [replayRef.current], () => buildReplayLayer(Cesium, viewer))
    })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [replayMarkers])

  // Real Argo float markers. Drawn separately so they can arrive after the base
  // scene builds; also re-drawn after any full scene rebuild.
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    let cancelled = false
    loadCesium().then((Cesium) => {
      if (cancelled || viewer.isDestroyed()) return
      ensureLayer('realArgo', [realArgoRef.current], () => buildRealArgoLayer(Cesium, viewer))
    })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [realArgoFloats])

  // Real NOAA ERSST v5 SST grid. The 2.7k-cell field is a *batched*
  // PointPrimitiveCollection (one draw call) with a coarse decimation level for
  // far-out views, not 2.7k Cesium entities.
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    let cancelled = false
    loadCesium().then((Cesium) => {
      if (cancelled || viewer.isDestroyed()) return
      ensureLayer('sst', [ersstRef.current, scaleModesRef.current?.sst], () =>
        buildSstLayer(Cesium, viewer))
    })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ersst, scaleModes?.sst])

  // Real satellite Chl-a grid (NOAA CoastWatch VIIRS-Himawari), same batching.
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    let cancelled = false
    loadCesium().then((Cesium) => {
      if (cancelled || viewer.isDestroyed()) return
      ensureLayer('chl', [chlorRef.current, scaleModesRef.current?.chl], () =>
        buildChlLayer(Cesium, viewer))
    })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chlor, scaleModes?.chl])

  // Real glider dissolved-oxygen samples. Colors are relative to the displayed
  // sample range; no thresholds or interpolation are implied. Batched, and the
  // per-sample value rides on the primitive's own colour so the detail bubble
  // needs no entity at all.
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    let cancelled = false
    loadCesium().then((Cesium) => {
      if (cancelled || viewer.isDestroyed()) return
      ensureLayer('oxygen', [oxygenRef.current], () => buildOxygenLayer(Cesium, viewer))
  ensureLayer('acidification', [phRef.current, phMetricRef.current, phDepthRangeRef.current], () => buildPhLayer(Cesium, viewer))
    })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [oxygenSamples])

  // Deoxygenation hotspots (hypoxic zones) from Argo BGC + NOAA data.
  // Rendered as colored beacons with priority-based sizing and severity colors.
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    let cancelled = false
    loadCesium().then((Cesium) => {
      if (cancelled || viewer.isDestroyed()) return
      ensureLayer('oxygenHotspots', [oxygenHotspotsRef.current], () =>
        buildHotspotLayer(Cesium, viewer))
    })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [oxygenHotspots])

  /** Hypoxic-zone beacons. Split out of its effect so `syncDeferredLayers` can
   *  paint it on first mount and repaint it after a full `buildScene`. */
  function buildHotspotLayer(Cesium: CesiumModule, viewer: Viz) {
    const scene = sceneRef.current
    for (const entity of scene.oxygenHotspots) viewer.entities.remove(entity)
    scene.oxygenHotspots = []
    const hotspots = (oxygenHotspotsRef.current ?? []).filter((h) => h.is_hotspot)
    for (const h of hotspots) {
      // Color by severity: CRITICAL=dark red, HIGH=red, MODERATE=amber, LOW=teal
      let color: string
      switch (h.severity) {
        case 'CRITICAL': color = '#7f1d1d'; break
        case 'HIGH': color = '#f43f5e'; break
        case 'MODERATE': color = '#f59e0b'; break
        case 'LOW': color = '#22d3ee'; break
        default: color = '#10b981'
      }
      // Size by priority (30-100 -> 16-40 pixels)
      const pixelSize = 16 + Math.round((h.priority / 100) * 24)
      const entity = viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(h.longitude, h.latitude, 200),
        billboard: {
          image: getBeaconUrl(),
          width: pixelSize,
          height: pixelSize,
          scaleByDistance: new Cesium.NearFarScalar(1.2e6, 1.0, 4.0e6, 0.5),
          color: Cesium.Color.fromCssColorString(color).withAlpha(0.9),
          verticalOrigin: Cesium.VerticalOrigin.CENTER,
        },
        label: {
          text: `${h.region} (${h.depth_layer})`,
          font: '11px monospace',
          fillColor: Cesium.Color.WHITE,
          showBackground: true,
          backgroundColor: Cesium.Color.fromCssColorString(color).withAlpha(0.9),
          backgroundPadding: new Cesium.Cartesian2(6, 4),
          pixelOffset: new Cesium.Cartesian2(0, -pixelSize - 8),
          distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 5e6),
          show: layersRef.current.oxygenHotspots,
        },
        description: `DEOXYGENATION HOTSPOT<br/>
          Region: ${h.region}<br/>
          Depth layer: ${h.depth_layer}<br/>
          Severity: ${h.severity} (priority ${h.priority.toFixed(0)}/100)<br/>
          Min O₂: ${h.statistics.min_do_mg_l.toFixed(1)} mg/L<br/>
          Mean O₂: ${h.statistics.mean_do_mg_l.toFixed(1)} mg/L<br/>
          Hypoxic samples: ${h.statistics.n_hypoxic}/${h.statistics.n_samples}<br/>
          Dead zone samples: ${h.statistics.n_dead_zone}<br/>
          Trend: ${h.trend.toUpperCase()}<br/>
          Confidence: ${h.confidence}%<br/>
          Action: ${h.action.replace('_', ' ')}<br/>
          <br/>
          ${h.recommendations.map((r) => `• ${r.text}`).join('<br/>')}`,
        show: layersRef.current.oxygenHotspots,
      })
      scene.oxygenHotspots.push(entity)
    }
    viewer.scene.requestRender()
  }

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
  // 1508 marching-squares segments now live in a single PolylineCollection, and
  // the rebuild is guarded so a stable contour level never repaints.
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    let cancelled = false
    loadCesium().then((Cesium) => {
      if (cancelled || viewer.isDestroyed()) return
      ensureLayer('iso', [ersstRef.current, isolevelsRef.current], () =>
        buildIsoLayer(Cesium, viewer))
    })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ersst, isolevels])

  // True current-velocity arrows from the real model grid (feature #14).
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    let cancelled = false
    loadCesium().then((Cesium) => {
      if (cancelled || viewer.isDestroyed()) return
      ensureLayer('curVec', [currentVectorsRef.current], () => buildVectorsLayer(Cesium, viewer))
    })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentVectors])

  // One horizontal depth slice of the real model field (feature #7).
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    let cancelled = false
    loadCesium().then((Cesium) => {
      if (cancelled || viewer.isDestroyed()) return
      ensureLayer('slice', [modelSliceRef.current], () => buildSliceLayer(Cesium, viewer))
    })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelSlice])

  // Real glider deployment tracks (feature #16), batched into two
  // PolylineCollections (track + sample dots) with an O(1) click lookup.
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    let cancelled = false
    loadCesium().then((Cesium) => {
      if (cancelled || viewer.isDestroyed()) return
      ensureLayer('glider', [gliderTracksRef.current], () => buildGliderLayer(Cesium, viewer))
    })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gliderTracks])

  // Dispose the viewer on unmount.
  useEffect(() => {
    const container = containerRef.current
    // Keep the browser's context menu from stealing right-click drags.
    const onContextMenu = (ev: Event) => ev.preventDefault()
    container?.addEventListener('contextmenu', onContextMenu)
    return () => {
      container?.removeEventListener('contextmenu', onContextMenu)
      if (settleTimerRef.current) clearTimeout(settleTimerRef.current)
      const viewer = viewerRef.current
      if (viewer) {
        // Primitives are NOT owned by the entity collection, so they must be
        // torn down explicitly or they leak on every remount.
        const s = sceneRef.current
        for (const f of [s.sst, s.chl, s.oxygen, s.slice, s.gliderDots]) {
          if (f) disposePointField(viewer, f)
        }
        for (const p of [s.iso, s.curVec, s.gliderTracks]) {
          if (p) viewer.scene.primitives.remove(p.collection)
        }
        if (s.currentDots) viewer.scene.primitives.remove(s.currentDots)
        disposeRingPulses(viewer, s.wavePulses)
        disposeRingPulses(viewer, s.focusPulses)
        for (const obj of s.transect) {
          try {
            viewer.scene.primitives.remove(obj)
          } catch {
            /* already removed */
          }
        }
        viewer.destroy()
      }
      viewerRef.current = null
      readyRef.current = false
      revRef.current += 1
      builtRef.current = {}
      interactingRef.current = false
      liveRef.current = false
      sceneRef.current = emptyScene()
    }
  }, [])

  /**
   * Resolve the oxygen sample nearest the pointer and show its source-reported
   * details, replacing the `description` balloon the per-sample `Entity` points
   * used to provide.
   *
   * `PointPrimitiveCollection` renders as a single draw call and supports
   * neither `id` nor `description`, so the lookup is a screen-space nearest
   * search over the ECEF positions cached at build time. It is run from the
   * already-throttled ~20 Hz MOUSE_MOVE handler, is skipped while the camera is
   * moving, and rejects anything past `HOVER_RADIUS_PX`, so the cost is bounded
   * by the payload size and involves no per-sample allocation.
   */
  function showOxygenHover(
    Cesium: CesiumModule,
    viewer: Viz,
    pos: Cartesian2,
    pointerBusy: boolean,
  ) {
    const el = oxygenHoverRef.current
    if (!el) return
    const field = sceneRef.current.oxygen
    const samples = field?.samples
    const positions = field?.positions
    if (pointerBusy || !samples || !positions || !layersRef.current.oxygen || field?.full.show === false) {
      el.style.display = 'none'
      return
    }
    let best = -1
    let bestDist = HOVER_RADIUS_PX * HOVER_RADIUS_PX
    const windowScratch = oxygenHoverWindowRef.current ?? new Cesium.Cartesian2()
    oxygenHoverWindowRef.current = windowScratch
    for (let i = 0; i < positions.length; i++) {
      // Reuse one result object: `worldToWindowCoordinates` allocates a
      // Cartesian2 when the caller passes none.
      const projected = Cesium.SceneTransforms.worldToWindowCoordinates(
        viewer.scene,
        positions[i],
        windowScratch,
      )
      if (!projected) continue
      const dx = projected.x - pos.x
      const dy = projected.y - pos.y
      const d2 = dx * dx + dy * dy
      if (d2 < bestDist) {
        bestDist = d2
        best = i
      }
    }
    if (best < 0) {
      el.style.display = 'none'
      return
    }
    const sample = samples[best]
    // `innerHTML` is safe here: every interpolated value is a number or comes
    // from a CSS colour, and the free-text `source_file` is HTML-escaped.
    el.innerHTML = [
      '<strong>REAL glider dissolved oxygen sample</strong>',
      `Source-reported value: ${sample.dissolved_oxygen}`,
      `Depth: ${sample.depth_m} m`,
      `Time: ${sample.time}`,
      `Deployment: ${sample.deployment_id}`,
      `QC: ${sample.qc_flags ?? 'source flag unavailable'}`,
      `Source: ${escapeHtml(sample.source_file ?? 'GliderDAC')}`,
    ].join('<br/>')
    el.style.display = 'block'
  }

  // Left-click any region beacon/label → onRegionClick(locId).
  // Subscribed once for the lifetime of the viewer; every value it needs is read
  // from a ref, so this never re-subscribes and never thrashes Cesium's
  // ScreenSpaceEventHandler. The hover test used to run `scene.pick` plus two
  // linear array scans on *every* mouse event, which is what made dragging the
  // globe stutter; it is now throttled and backed by Maps.
  useEffect(() => {
    let active = true
    const rev = revRef.current
    const hoverTip = oxygenHoverRef.current
    const hideTip = () => { if (hoverTip) hoverTip.style.display = 'none' }
    loadCesium().then((Cesium) => {
      if (!active || revRef.current !== rev) return
      const viewer = viewerRef.current
      if (!viewer) return
      liveRef.current = true
      const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas)
      /** Resolve a picked primitive to a region / float / glider callback. */
      const resolve = (id: unknown): boolean => {
        if (!id) return false
        const scene = sceneRef.current
        const container = viewer.container as HTMLElement
        const marker = scene.markerMap.get(id as never)
        if (marker != null) {
          onRegionClickRef.current?.(marker)
          container.style.cursor = 'default'
          return true
        }
        const argoHit = scene.argoMap.get(id as never)
        if (argoHit != null) {
          onArgoFloatClickRef.current?.(argoHit)
          container.style.cursor = 'default'
          return true
        }
        const gliderHit = scene.glidersMap.get(id as never)
        if (gliderHit) {
          onGliderClickRef.current?.(gliderHit)
          container.style.cursor = 'default'
          return true
        }
        return false
      }
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
          resolve(viewer.scene.pick(pos)?.id)
        },
        Cesium.ScreenSpaceEventType.LEFT_CLICK,
      )
      // Friendly pointer affordance when hovering an interactive mark. Throttled
      // to ~20 Hz and skipped entirely while the camera is moving, because the
      // pointer is dragging the globe in that case, not aiming at a target.
      // Cesium has no MOUSE_LEAVE event, so a drag that carries the pointer out
      // of the canvas would otherwise leave the readout stuck on screen.
      viewer.scene.canvas.addEventListener('mouseleave', hideTip)
      let lastHover = 0
      handler.setInputAction(
        (movement: unknown) => {
          if (interactingRef.current) {
            // The globe moved under a visible tooltip: it no longer points at
            // the sample it described.
            hideTip()
            return
          }
          const now = performance.now()
          if (now - lastHover < 50) return
          lastHover = now
          const pos = (movement as { endPosition?: Cartesian2 }).endPosition
          if (!pos) return
          const container = viewer.container as HTMLElement
          if (transectActiveRef.current) {
            const ell = viewer.camera.pickEllipsoid(pos, viewer.scene.globe.ellipsoid)
            container.style.cursor = ell ? 'crosshair' : 'default'
            hideTip()
            return
          }
          const scene = sceneRef.current
          // Batched primitives (SST/Chl/oxygen/slice dots) are never click
          // targets, so skip the full scene pick when the pointer is over
          // dense data.
          const picked = viewer.scene.pick(pos)
          const id = picked?.id
          const interactive = Boolean(id) &&
            (scene.markerMap.has(id as never) || scene.argoMap.has(id as never) || scene.glidersMap.has(id as never))
          container.style.cursor = interactive ? 'pointer' : 'default'
          showOxygenHover(Cesium, viewer, pos, interactive)
        },
        Cesium.ScreenSpaceEventType.MOUSE_MOVE,
      )
      hideTip()
      handlersRef.current.push(handler)
    })
    return () => {
      active = false
      liveRef.current = false
      hideTip()
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
    // Bounded texture cache. Cesium's default memoryThreshold is 128MB, which
    // on a 4K/retina display is not a GPU bound at all — it is an almost
    // unbounded pile of decoded tile textures. A 32MB budget evicts the
    // least-recently-used tile sets and forces re-decoding on zoom-back, which
    // is far cheaper than holding ~400MB resident. The property exists on the
    // runtime class but is absent from the bundled type declarations.
    ;(viewer.imageryLayers as unknown as { memoryThreshold: number }).memoryThreshold = 32
    try {
      const provider = await Cesium.IonImageryProvider.fromAssetId(2)
      viewer.imageryLayers.addImageryProvider(provider)
      return
    } catch {
      /* token unavailable for this asset — fall through */
    }
    try {
      // `addImageryProvider` is async and the returned promise rejects on tile
      // errors, long after this builder has returned. Unhandled, that surfaces
      // as a global unhandledrejection and is the usual "globe stayed blank"
      // report. Swallow it: the styled baseColor globe is the intended result.
      // The bundled types declare a synchronous `ImageryLayer` return.
      const added = viewer.imageryLayers.addImageryProvider(
        new Cesium.OpenStreetMapImageryProvider({ url: 'https://a.tile.openstreetmap.org/' }),
      ) as unknown as Promise<unknown> | undefined
      added?.catch?.(() => {
        /* keep the styled baseColor globe */
      })
    } catch {
      /* keep the styled baseColor globe */
    }
  }

  function buildScene(Cesium: CesiumModule, viewer: Viz) {
    viewer.entities.removeAll()
    clearStormEntities(viewer)
    // Start from a *fresh* scene but carry the batched primitives (point fields,
    // polyline collections) across, because `entities.removeAll()` only clears
    // the entity collection — primitives would otherwise be orphaned or leak.
    const previous = sceneRef.current
    const scene: Scene = emptyScene()
    // The transect curtain wall is a raw `Primitive`, not an entity, so
    // `entities.removeAll()` above does NOT reclaim it. `previous.transect` is
    // the only remaining reference, and dropping `previous` would strand the
    // geometry, its VertexArrayFormat and its procedural texture on the GPU
    // for the life of the WebGL context. Release it explicitly before the
    // carry-forward below. `scene.transect` is already `[]` from `emptyScene()`,
    // and `syncDeferredLayers` repaints the transect straight after.
    for (const obj of previous.transect) {
      try {
        viewer.scene.primitives.remove(obj)
      } catch {
        /* already removed */
      }
      try {
        viewer.entities.remove(obj as VizEntity)
      } catch {
        /* entity form */
      }
    }
    // Only the *primitive*-backed layers survive `entities.removeAll()`. The
    // entity-backed ones (hotspots / TIDE / replay) are deliberately left empty
    // and their build guards cleared, so `syncDeferredLayers` repaints them
    // instead of leaving a scene that silently lost them.
    scene.sst = previous.sst
    scene.chl = previous.chl
    scene.oxygen = previous.oxygen
    scene.iso = previous.iso
    scene.curVec = previous.curVec
    scene.slice = previous.slice
    scene.gliderTracks = previous.gliderTracks
    scene.gliderDots = previous.gliderDots
    scene.currentDots = previous.currentDots
    scene.currentStream = previous.currentStream
    scene.wavePulses = previous.wavePulses
    scene.focusPulses = previous.focusPulses
    invalidateLayers('oxygenHotspots', 'tide', 'replay')

    const valid = (locations.length > 0 ? locations : FALLBACK_LOCATIONS).filter(
      (l) => l.latitude != null && l.longitude != null,
    )

    /** Ring specs collected per location and batched into one collection. */
    const waveSpecs: RingPulseSpec[] = []
    const focusSpecs: RingPulseSpec[] = []

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
      scene.markerMap.set(marker as never, loc.id)

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

      // ---- Wave ripples: 3 ring billboards per location, positions/scale/alpha
      // written in place by the ticker. Previously each ripple was an Entity
      // whose ellipse geometry was regenerated from a CallbackProperty on every
      // frame — one geometry rebuild per ring, per frame.
      for (let r = 0; r < 3; r++) {
        waveSpecs.push({
          lon,
          lat,
          height: 260,
          phase: phase * 0.7 + r,
          color: '#67e8f9',
          peakAlpha: 0.9,
          period: 3,
          base: 6000,
          span: 52000,
          squash: 0.72,
        })
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
        focusSpecs.push({
          lon,
          lat,
          height: 240,
          phase: phase * 0.29,
          color: '#a78bfa',
          peakAlpha: 0.9,
          period: 2.4,
          base: 30000,
          span: 42000,
          squash: 0.85,
        })
      }
    }

    // One BillboardCollection for every expanding wave ring on the globe.
    addRingPulses(Cesium, viewer, scene.wavePulses, waveSpecs)
    addRingPulses(Cesium, viewer, scene.focusPulses, focusSpecs)
    scene.wavePulses.enabled = layersRef.current.waves
    scene.focusPulses.enabled = layersRef.current.priority

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
      scene.markerMap.set(beacon as never, a.location_id)
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

      // Streams of glowing dots orbiting the ocean at 3 tilted paths. These used
      // to be 36 Entities each holding a `CallbackPositionProperty` that
      // allocated a brand-new Cartesian3 sixty times a second; they are now one
      // BillboardCollection whose positions the ticker mutates in place.
      if (scene.currentDots) {
        viewer.scene.primitives.remove(scene.currentDots)
        scene.currentDots = null
        scene.currentStream = null
      }
      const R = 6378137 * 1.03
      const normals = [
        new Cesium.Cartesian3(0.2, 0.6, 0.8),
        new Cesium.Cartesian3(-0.6, 0.3, 0.8),
        new Cesium.Cartesian3(0.7, -0.4, 0.7),
      ]
      const dots: Scene['currentStream'] = { dots: [], scratch: new Cesium.Cartesian3() }
      const dotCollection = new Cesium.BillboardCollection({ scene: viewer.scene })
      for (let oi = 0; oi < normals.length; oi++) {
        const nav = normals[oi].clone()
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

        const perOrbit = 12
        for (let d = 0; d < perOrbit; d++) {
          const a = (d / perOrbit) * Math.PI * 2 + oi
          dots.dots.push({
            u: u.clone(),
            v: v.clone(),
            radius: R,
            phase: a,
            speed: 0.25 + oi * 0.09,
          })
          dotCollection.add({
            image: getDotUrl(),
            width: 18,
            height: 18,
            verticalOrigin: Cesium.VerticalOrigin.CENTER,
            // The ticker overwrites this every frame; the initial value only
            // has to be a valid on-globe position.
            position: Cesium.Cartesian3.fromDegrees(0, 0, R),
          })
        }
      }
      if (dotCollection.length > 0) {
        viewer.scene.primitives.add(dotCollection)
        scene.currentDots = dotCollection
        scene.currentStream = dots
        dotCollection.show = layersRef.current.currents
      } else {
        dotCollection.destroy()
      }
    }

    sceneRef.current = scene
  }

  /** Real NOAA Argo float markers, one entity each (there are only a handful). */
  function buildRealArgoLayer(Cesium: CesiumModule, viewer: Viz) {
    const scene = sceneRef.current
    for (const e of scene.realArgo) viewer.entities.remove(e)
    scene.realArgo = []
    scene.argoMap = new Map()
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
      scene.argoMap.set(marker as never, flt.float_id)
    }
    viewer.scene.requestRender()
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
      scene.markerMap.set(marker as never, c.location_id)
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
        scene.markerMap.set(entity as never, m.location_id)
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

  /** Ocean temperature colormap: shared with the transect HUD + colorbar.
   *  Single source in layerMath (normalizedTempRgb) — never fork the ramp. */
  function tempToRgb(t: number) {
    return normalizedTempRgb(t)
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

  /**
   * Real NOAA ERSST v5 SST grid: one batched PointPrimitiveCollection holding
   * every real cell, plus a stride-sampled coarse twin for whole-earth views.
   * `addPointField` is the "build once" half; opacity and layer toggles are
   * pure buffer writes (see `applyOpacity` / `applyLayers`).
   */
  function buildSstLayer(Cesium: CesiumModule, viewer: Viz) {
    const scene = sceneRef.current
    const grid = ersstRef.current
    if (!grid || !grid.samples || grid.samples.length === 0) {
      disposePointField(viewer, scene.sst)
      scene.sst = null
      viewer.scene.requestRender()
      return
    }
    const stats = grid.stats
    const domain = stats && stats.min !== null && stats.max !== null
      ? { min: stats.min, max: stats.max }
      : null
    const mode = scaleModesRef.current?.sst ?? 'linear'
    const cells: { longitude: number; latitude: number; color: string }[] = []
    for (const s of grid.samples) {
      cells.push({
        longitude: s.longitude,
        latitude: s.latitude,
        color: tempColorCssFrom(s.sst, domain, mode),
      })
    }
    if (!scene.sst) scene.sst = makePointField(Cesium, viewer, 4, 0.8, 120)
    fillPointField(Cesium, scene.sst, cells)
    setPointFieldEnabled(scene.sst, layersRef.current.realSST)
    applyPointFieldOpacity(scene.sst, opacityRef.current.realSST ?? 1)
    viewer.scene.requestRender()
  }

  /** Real satellite Chl-a grid, same batching as the SST field. */
  function buildChlLayer(Cesium: CesiumModule, viewer: Viz) {
    const scene = sceneRef.current
    const grid = chlorRef.current
    if (!grid || !grid.samples || grid.samples.length === 0) {
      disposePointField(viewer, scene.chl)
      scene.chl = null
      viewer.scene.requestRender()
      return
    }
    const stats = grid.stats
    const domain = stats && stats.min !== null && stats.max !== null
      ? { min: stats.min, max: stats.max }
      : null
    const mode = scaleModesRef.current?.chl ?? 'log'
    const cells: { longitude: number; latitude: number; color: string }[] = []
    for (const s of grid.samples) {
      cells.push({
        longitude: s.longitude,
        latitude: s.latitude,
        color: chlorColorCssFrom(s.chlor_a, domain, mode),
      })
    }
    if (!scene.chl) scene.chl = makePointField(Cesium, viewer, 4, 0.8, 120)
    fillPointField(Cesium, scene.chl, cells)
    setPointFieldEnabled(scene.chl, layersRef.current.realChl)
    applyPointFieldOpacity(scene.chl, opacityRef.current.realChl ?? 1)
    viewer.scene.requestRender()
  }

  /**
   * Real glider dissolved-oxygen samples. Colours are relative to the displayed
   * sample range; no thresholds or interpolation are implied. The per-sample
   * source value rides in the PointFieldLayer so the detail bubble can still be
   * read without a 1:1 entity per sample.
   */
  function buildOxygenLayer(Cesium: CesiumModule, viewer: Viz) {
    const scene = sceneRef.current
    const valid = (oxygenRef.current ?? []).filter((sample) => Number.isFinite(sample.dissolved_oxygen) &&
      Number.isFinite(sample.latitude) && Number.isFinite(sample.longitude) &&
      Math.abs(sample.latitude) <= 90 && Math.abs(sample.longitude) <= 180)
    if (valid.length === 0) {
      disposePointField(viewer, scene.oxygen)
      scene.oxygen = null
      viewer.scene.requestRender()
      return
    }
    let min = Infinity
    let max = -Infinity
    for (const s of valid) {
      if (s.dissolved_oxygen < min) min = s.dissolved_oxygen
      if (s.dissolved_oxygen > max) max = s.dissolved_oxygen
    }
    const blue = Cesium.Color.fromCssColorString('#2563eb')
    const teal = Cesium.Color.fromCssColorString('#14b8a6')
    const amber = Cesium.Color.fromCssColorString('#f59e0b')
    const ramp = new Cesium.Color()
    const cells: { longitude: number; latitude: number; color: string }[] = []
    for (const sample of valid) {
      const t = max > min ? (sample.dissolved_oxygen - min) / (max - min) : 0.5
      if (t < 0.5) Cesium.Color.lerp(blue, teal, t * 2, ramp)
      else Cesium.Color.lerp(teal, amber, (t - 0.5) * 2, ramp)
      cells.push({ longitude: sample.longitude, latitude: sample.latitude, color: ramp.toCssColorString() })
    }
    if (!scene.oxygen) scene.oxygen = makePointField(Cesium, viewer, 7, 0.9, 90)
    fillPointField(Cesium, scene.oxygen, cells)
    scene.oxygen.samples = valid
    scene.oxygen.positions = valid.map((s) =>
      Cesium.Cartesian3.fromDegrees(s.longitude, s.latitude, OXYGEN_POINT_ALTITUDE_M))
    setPointFieldEnabled(scene.oxygen, layersRef.current.oxygen)
    applyPointFieldOpacity(scene.oxygen, opacityRef.current.oxygen ?? 1)
    viewer.scene.requestRender()
  }

  /**
   * Real measured in-situ pH, placed at its true depth below the surface.
   *
   * Two honesty rules are encoded here rather than left to the UI:
   *
   *  1. The colour comes from the shared ramps in layerMath, which use the
   *     BACKEND severity ladder's thresholds. A cell therefore cannot be
   *     coloured more or less severely than the badge the API returns for the
   *     same row.
   *  2. When the metric is aragonite and a sample has none, it is NOT drawn.
   *     Painting it slate would put a derived-but-absent value into a layer
   *     that otherwise only contains real numbers.
   */
  function buildPhLayer(Cesium: CesiumModule, viewer: Viz) {
    const scene = sceneRef.current
    const metric = phMetricRef.current
    const range = phDepthRangeRef.current
    const valid = (phRef.current ?? []).filter((s) => Number.isFinite(s.ph_total) &&
      Number.isFinite(s.latitude) && Number.isFinite(s.longitude) &&
      Number.isFinite(s.depth_m) &&
      Math.abs(s.latitude) <= 90 && Math.abs(s.longitude) <= 180 &&
      (!range || (s.depth_m >= range.min && s.depth_m <= range.max)) &&
      // Aragonite mode: a sample with no derived omega has nothing to show.
      (metric !== 'omega' || (s.omega_arag != null && Number.isFinite(s.omega_arag))))
    if (valid.length === 0) {
      disposePointField(viewer, scene.ph)
      scene.ph = null
      viewer.scene.requestRender()
      return
    }
    const cells: { longitude: number; latitude: number; color: string }[] = []
    const scaleM = phDepthScaleRef.current
    for (const sample of valid) {
      const color = metric === 'omega' ? omegaColorCss(sample.omega_arag) : phColorCss(sample.ph_total)
      cells.push({ longitude: sample.longitude, latitude: sample.latitude, color })
    }
    if (!scene.ph) scene.ph = makePointField(Cesium, viewer, 6, 0.85, 100)
    fillPointField(Cesium, scene.ph, cells)
    // `samples` is deliberately NOT set here. It exists so the oxygen layer's
    // hover readout can recover the source-reported value from a batched point,
    // and there is no pH readout yet; populating it would widen the shared
    // `OxygenSample[]` type for a consumer that does not exist.
    scene.ph.positions = valid.map((s) =>
      Cesium.Cartesian3.fromDegrees(s.longitude, s.latitude, phDepthToAltitude(s.depth_m, scaleM)))
    setPointFieldEnabled(scene.ph, layersRef.current.acidification)
    applyPointFieldOpacity(scene.ph, opacityRef.current.acidification ?? 1)
    viewer.scene.requestRender()
  }

  /**
   * One horizontal depth slice of the real model field (feature #7): a batched
   * point field coloured on the live cell domain (temp → heat, salinity →
   * haline). Honest: nothing is drawn while `available:false` (no real grid /
   * depth level) — that verdict comes from the API, it is not invented here.
   */
  function buildSliceLayer(Cesium: CesiumModule, viewer: Viz) {
    const scene = sceneRef.current
    const slice = modelSliceRef.current
    const domain = slice && slice.available && slice.cells.length > 0
      ? domainFrom(slice.cells.map((c) => c.value))
      : null
    if (!slice || !domain) {
      disposePointField(viewer, scene.slice)
      scene.slice = null
      viewer.scene.requestRender()
      return
    }
    const mode = scaleModesRef.current?.modelgrid ?? 'linear'
    const sal = slice.variable === 'salinity'
    const cells: { longitude: number; latitude: number; color: string }[] = []
    for (const c of slice.cells) {
      cells.push({
        longitude: c.longitude,
        latitude: c.latitude,
        color: sal ? salColorCssFrom(c.value, domain, mode) : tempColorCssFrom(c.value, domain, mode),
      })
    }
    if (!scene.slice) scene.slice = makePointField(Cesium, viewer, 4, 0.8, 120)
    fillPointField(Cesium, scene.slice, cells)
    setPointFieldEnabled(scene.slice, layersRef.current.modelgrid)
    applyPointFieldOpacity(scene.slice, opacityRef.current.modelgrid ?? 1)
    viewer.scene.requestRender()
  }

  /**
   * Marching-squares isotherm contours of the real ERSST SST field (#11).
   * The measured 6-level contour set is ~1500 segments; as entities that was
   * 1500 updaters running their property machinery every frame. One
   * PolylineCollection draws the whole set in a single pass.
   */
  function buildIsoLayer(Cesium: CesiumModule, viewer: Viz) {
    const scene = sceneRef.current
    if (scene.iso) {
      viewer.scene.primitives.remove(scene.iso.collection)
      scene.iso = null
    }
    const levels = isolevelsRef.current
    const grid = ersstRef.current
    if (!levels || levels.length === 0 || !grid || !grid.samples) {
      viewer.scene.requestRender()
      return
    }
    const field = buildLatLonField(
      grid.samples.map((s) => ({ latitude: s.latitude, longitude: s.longitude, value: s.sst })),
    )
    if (!field) {
      viewer.scene.requestRender()
      return
    }
    const collection = new Cesium.PolylineCollection()
    const material = Cesium.Material.fromType('Color', {
      color: Cesium.Color.fromCssColorString('#0ea5e9'),
    })
    const base: InstanceType<CesiumModule['Color']>[] = []
    for (const level of levels) {
      for (const seg of isoLines(field, level)) {
        collection.add({
          positions: Cesium.Cartesian3.fromDegreesArray([
            seg.lon0, seg.lat0, 220,
            seg.lon1, seg.lat1, 220,
          ]),
          width: 2.5,
          arcType: Cesium.ArcType.GEODESIC,
          material,
        })
        base.push(Cesium.Color.fromCssColorString('#0ea5e9'))
      }
    }
    viewer.scene.primitives.add(collection)
    scene.iso = { collection, base }
    collection.show = layersRef.current.isos
    applyPolyLayerOpacity(Cesium, scene.iso, 0.95 * (opacityRef.current.isos ?? 1))
    viewer.scene.requestRender()
  }

  /**
   * True current-velocity arrows for the real model-grid u/v cells (#14).
   * Shaft + both fins per cell land in one PolylineCollection, so the 600-cell
   * draw set is ~1800 lines in a single pass instead of 1800 entities.
   */
  function buildVectorsLayer(Cesium: CesiumModule, viewer: Viz) {
    const scene = sceneRef.current
    if (scene.curVec) {
      viewer.scene.primitives.remove(scene.curVec.collection)
      scene.curVec = null
    }
    const vecs = currentVectorsRef.current
    if (!vecs || vecs.length === 0) {
      viewer.scene.requestRender()
      return
    }
    // Cap the drawn set so a dense 1/12° grid stays responsive — always the
    // strongest cells, honestly labelled "strongest first" in the UI.
    const shown = vecs
      .slice()
      .sort((a, b) => Math.hypot(b.u || 0, b.v || 0) - Math.hypot(a.u || 0, a.v || 0))
      .slice(0, 600)
    const collection = new Cesium.PolylineCollection()
    const shaftMaterial = Cesium.Material.fromType('Color', {
      color: Cesium.Color.fromCssColorString('#38bdf8'),
    })
    const finMaterial = Cesium.Material.fromType('Color', {
      color: Cesium.Color.fromCssColorString('#a5f3fc'),
    })
    const base: InstanceType<CesiumModule['Color']>[] = []
    for (const cell of shown) {
      const arrow = arrowFor(cell)
      if (!arrow) continue
      collection.add({
        positions: Cesium.Cartesian3.fromDegreesArray([
          arrow.tail.longitude, arrow.tail.latitude, 210,
          arrow.head.longitude, arrow.head.latitude, 210,
        ]),
        width: 2.2,
        arcType: Cesium.ArcType.GEODESIC,
        material: shaftMaterial,
      })
      base.push(Cesium.Color.fromCssColorString('#38bdf8'))
      for (const fin of arrow.fins) {
        collection.add({
          positions: Cesium.Cartesian3.fromDegreesArray([
            arrow.head.longitude, arrow.head.latitude, 210,
            fin.longitude, fin.latitude, 210,
          ]),
          width: 1.6,
          arcType: Cesium.ArcType.GEODESIC,
          material: finMaterial,
        })
        base.push(Cesium.Color.fromCssColorString('#a5f3fc'))
      }
    }
    viewer.scene.primitives.add(collection)
    scene.curVec = { collection, base }
    collection.show = layersRef.current.vectors
    applyPolyLayerOpacity(Cesium, scene.curVec, 0.9 * (opacityRef.current.vectors ?? 1))
    viewer.scene.requestRender()
  }


  /**
   * Real glider deployment tracks (feature #16): one polyline per deployment
   * through its true sample positions, batched into a single
   * PolylineCollection, plus a batched point field of depth-coloured sample
   * dots. Clicking a deployment line opens its profile (feature #18); the
   * Polyline → deployment id map below makes that an O(1) lookup.
   */
  const GLIDER_PALETTE = ['#f59e0b', '#22d3ee', '#a78bfa', '#34d399', '#fb7185', '#e879f9']

  function buildGliderLayer(Cesium: CesiumModule, viewer: Viz) {
    const scene = sceneRef.current
    if (scene.gliderTracks) {
      viewer.scene.primitives.remove(scene.gliderTracks.collection)
      scene.gliderTracks = null
    }
    disposePointField(viewer, scene.gliderDots)
    scene.gliderDots = null
    scene.glidersMap = new Map()
    const tracks = gliderTracksRef.current
    if (!tracks || tracks.length === 0) {
      viewer.scene.requestRender()
      return
    }
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
    if (!Number.isFinite(depthLo)) {
      viewer.scene.requestRender()
      return
    }

    const collection = new Cesium.PolylineCollection()
    const materials = GLIDER_PALETTE.map((c) => Cesium.Material.fromType('Color', {
      color: Cesium.Color.fromCssColorString(c),
    }))
    const base: InstanceType<CesiumModule['Color']>[] = []
    const dotCells: { longitude: number; latitude: number; color: string }[] = []
    tracks.forEach((t, i) => {
      const colorIndex = i % GLIDER_PALETTE.length
      const pts = t.samples.filter((s) => Number.isFinite(s.latitude) && Number.isFinite(s.longitude))
      if (pts.length >= 2) {
        const flat: number[] = []
        for (const s of pts) flat.push(s.longitude, s.latitude, 200)
        const line = collection.add({
          positions: Cesium.Cartesian3.fromDegreesArray(flat),
          width: 3,
          arcType: Cesium.ArcType.GEODESIC,
          material: materials[colorIndex],
        })
        scene.glidersMap.set(line, t.deploymentId)
        base.push(Cesium.Color.fromCssColorString(GLIDER_PALETTE[colorIndex]))
      }
      for (const s of pts) {
        dotCells.push({
          longitude: s.longitude,
          latitude: s.latitude,
          color: depthColorCss(s.depth_m, depthLo, depthHi),
        })
      }
    })
    viewer.scene.primitives.add(collection)
    scene.gliderTracks = { collection, base }
    collection.show = layersRef.current.glider
    applyPolyLayerOpacity(Cesium, scene.gliderTracks, 0.85 * (opacityRef.current.glider ?? 1))

    if (dotCells.length > 0) {
      scene.gliderDots = makePointField(Cesium, viewer, 5, 0.95, 200)
      fillPointField(Cesium, scene.gliderDots, dotCells)
      setPointFieldEnabled(scene.gliderDots, layersRef.current.glider)
      applyPointFieldOpacity(scene.gliderDots, opacityRef.current.glider ?? 1)
    }
    viewer.scene.requestRender()
  }

  /**
   * Recolour existing dense layers with their per-layer opacity (#12).
   * The three batched point fields and the three polyline collections are
   * mutated in place; nothing is rebuilt, so dragging an opacity slider costs
   * a few thousand float writes instead of thousands of entity removals.
   */
  function applyOpacity(Cesium: CesiumModule, viewer: Viz, state: Partial<Record<LayerKey, number>>) {
    const scene = sceneRef.current
    const a = (key: LayerKey) => state[key] ?? 1

    // Batched point fields: base RGB is already cached, so this is pure
    // buffer writes with a single reused Colour instance.
    applyPointFieldOpacity(scene.sst, a('realSST'))
    applyPointFieldOpacity(scene.chl, a('realChl'))
    applyPointFieldOpacity(scene.oxygen, a('oxygen'))
    applyPointFieldOpacity(scene.ph, a('acidification'))
    applyPointFieldOpacity(scene.slice, a('modelgrid'))
    applyPointFieldOpacity(scene.gliderDots, a('glider'))

    // Batched polyline collections: one cached base colour per line, so this is
    // a uniform reassign per line and never a rebuild.
    applyPolyLayerOpacity(Cesium, scene.iso, 0.95 * a('isos'))
    applyPolyLayerOpacity(Cesium, scene.curVec, 0.9 * a('vectors'))
    applyPolyLayerOpacity(Cesium, scene.gliderTracks, 0.85 * a('glider'))

    // Temperature heat patches (the disagreement layer keeps its status colours).
    const tempAlpha = a('temperature')
    for (const t of scene.temps) {
      if (!t.entity.ellipse) continue
      const disagree = disagreementRef.current.find((d) => d.location_id === t.locId)
      if (layersRef.current.disagreement && disagree) continue
      const def = Cesium.Color.fromCssColorString(tempColorCss(t.temp ?? 28))
      t.entity.ellipse.material = new Cesium.ColorMaterialProperty(def.withAlpha(0.38 * tempAlpha))
    }

    // Wave / focus ring pulses keep their own per-frame alpha envelope; the
    // slider is folded into the peak so the animation shape is preserved.
    scene.wavePulses.peakScale = 0.16 * a('waves')
    scene.focusPulses.peakScale = 0.04 * a('priority')

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
    if (scene.currentDots) setBillboardAlpha(Cesium, scene.currentDots, currentAlpha)

    // Real Argo float markers.
    const argoAlpha = a('realArgo')
    for (const e of scene.realArgo) {
      if (!e.point) continue
      e.point.color = new Cesium.ConstantProperty(Cesium.Color.fromCssColorString('#f472b6').withAlpha(argoAlpha))
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
    scene.wavePulses.enabled = state.waves
    if (scene.wavePulses.collection) scene.wavePulses.collection.show = state.waves
    scene.focusPulses.enabled = state.priority
    if (scene.focusPulses.collection) scene.focusPulses.collection.show = state.priority
    scene.currents.forEach((e) => (e.show = state.currents))
    if (scene.currentDots) scene.currentDots.show = state.currents
    scene.storm.forEach((e) => (e.show = state.storm))
    scene.rings.forEach((e) => (e.show = state.uncertainty))
    scene.argo.forEach((e) => (e.show = state.argo))
    scene.realArgo.forEach((e) => (e.show = state.realArgo))
    scene.anomalies.forEach((e) => (e.show = state.anomalies))
    scene.tide.forEach((e) => (e.show = state.tide))
    setPointFieldEnabled(scene.sst, state.realSST)
    setPointFieldEnabled(scene.chl, state.realChl)
    setPointFieldEnabled(scene.oxygen, state.oxygen)
    setPointFieldEnabled(scene.ph, state.acidification)
    setPointFieldEnabled(scene.slice, state.modelgrid)
    setPointFieldEnabled(scene.gliderDots, state.glider)
    if (scene.iso) scene.iso.collection.show = state.isos
    if (scene.curVec) scene.curVec.collection.show = state.vectors
    if (scene.gliderTracks) scene.gliderTracks.collection.show = state.glider
    // Keep every per-layer opacity applied after any layer toggle re-colours it.
    applyOpacity(Cesium, viewer, opacityRef.current)
    viewer.scene.requestRender()
  }

  return (
    <div ref={containerRef} className="cesium-globe">
      {globeError && (
        <div className="cesium-globe-error" role="alert">
          {globeError}
        </div>
      )}
      <div className="cesium-hint">
        <span>Drag · spin globe</span>
        <span>Scroll · zoom</span>
        <span>Ctrl+drag · pan</span>
      </div>
      {/* Hover readout for the batched oxygen layer. Written imperatively by the
          throttled MOUSE_MOVE handler, so it never re-renders the globe. */}
      <div ref={oxygenHoverRef} className="cesium-sample-hover" style={{ display: 'none' }} />
    </div>
  )
}

/**
 * The globe holds a live WebGL scene and an imperative Cesium viewer, none of
 * which React can reconcile. `memo` means a parent re-render (the replay
 * timeline ticks four times a second) no longer even reaches this component
 * unless a prop that the globe actually reads has changed — on top of the
 * per-layer `ensureLayer` guards, which stop a changed *identity* from
 * rebuilding primitives when the *contents* are identical.
 */
export default memo(CesiumGlobe)

