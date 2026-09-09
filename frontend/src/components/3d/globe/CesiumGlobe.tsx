import { useEffect, useRef } from 'react'
import 'cesium/Build/Cesium/Widgets/widgets.css'
import './CesiumGlobe.css'

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

export type LayerKey = 'labels' | 'temperature' | 'waves' | 'currents' | 'storm'
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

function tempColor(Cesium: CesiumModule, temp: number) {
  const cold = Cesium.Color.fromCssColorString('#22d3ee')
  const hot = Cesium.Color.fromCssColorString('#ff8a28')
  const k = Cesium.Math.clamp((temp - 20) / 11, 0, 1)
  return Cesium.Color.lerp(cold, hot, k, new Cesium.Color())
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

/** Rolling 12h baseline of a region's merged timeline up to (excluding) idx. */
function rollingBaseline(reg: SeriesRegion, idx: number): number | null {
  const windowPoints = reg.points.slice(Math.max(0, idx - 12), idx)
  const temps = windowPoints.map((p) => p.temperature).filter((t): t is number => t != null)
  if (temps.length === 0) return null
  return temps.reduce((a, b) => a + b, 0) / temps.length
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
}

interface Scene {
  markers: VizEntity[]
  temps: { locId: number; entity: VizEntity }[]
  waves: VizEntity[]
  currents: VizEntity[]
  storm: VizEntity[]
}

export default function CesiumGlobe({ locations, layers, storm, series, timeCursor, timeColor = 'temp' }: CesiumGlobeProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const viewerRef = useRef<Viz | null>(null)
  const sceneRef = useRef<Scene>({ markers: [], temps: [], waves: [], currents: [], storm: [] })
  const layersRef = useRef(layers)
  layersRef.current = layers
  const locatedRef = useRef(locations)
  locatedRef.current = locations
  const seriesRef = useRef<SeriesRegion[]>([])
  seriesRef.current = series ?? []
  const cursorRef = useRef<number | null>(timeCursor ?? null)
  cursorRef.current = timeCursor ?? null
  const timeColorRef = useRef(timeColor)
  timeColorRef.current = timeColor
  const flownRef = useRef(false)

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
        // Normal Cesium navigation (left-drag spins the globe, scroll zooms,
        // Ctrl/right-drag pans), with generous zoom guardrails.
        const camCtrl = viewer.scene.screenSpaceCameraController
        camCtrl.minimumZoomDistance = 300000
        camCtrl.maximumZoomDistance = 20000000
        // A freshly created viewer sits at the default "home" view — make sure
        // the camera is pointed at India again (StrictMode remounts viewers).
        flownRef.current = false
        void applyBaseLayer(Cesium, viewer)
      }

      if (!flownRef.current) {
        flownRef.current = true
        const indiaFocus = Cesium.Cartesian3.fromDegrees(78.6, 18.0, 0)
        viewer.camera.lookAt(
          indiaFocus,
          new Cesium.HeadingPitchRange(0, Cesium.Math.toRadians(-48), 3600000),
        )
      }

      buildScene(Cesium, viewer)
      applyLayers(viewer, layersRef.current)
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
    loadCesium().then(() => applyLayers(viewer, layers))
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
      sceneRef.current = { markers: [], temps: [], waves: [], currents: [], storm: [] }
    }
  }, [])

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
    const scene: Scene = { markers: [], temps: [], waves: [], currents: [], storm: [] }

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

      // ---- Temperature heat patches ----
      const tempC = tempColor(Cesium, loc.temperature ?? 28)
      const temp = viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(lon, lat, 300),
        ellipse: {
          semiMajorAxis: 62000,
          semiMinorAxis: 45000,
          rotation: Cesium.Math.toRadians(phase * 17),
          material: tempC.withAlpha(0.38),
          outline: true,
          outlineColor: tempC.withAlpha(0.9),
          outlineWidth: 2,
          height: 300,
        },
        show: layersRef.current.temperature,
      })
      scene.temps.push({ locId: loc.id, entity: temp })

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

  /** Recolor temperature patches from the merged timeline at the cursor. */
  function applyCursor(Cesium: CesiumModule, viewer: Viz, cursor: number) {
    const scene = sceneRef.current
    const mode = timeColorRef.current
    for (const tge of scene.temps) {
      const reg = seriesRef.current.find((r) => r.location_id === tge.locId)
      if (!reg) continue
      const idx = Math.min(cursor, reg.points.length - 1)
      const p = reg.points[idx]
      const entity = tge.entity
      if (!entity.ellipse || !p) continue

      let value = p.temperature
      let color = value != null ? tempColor(Cesium, value) : null
      if (mode !== 'temp' && p.temperature != null) {
        const base = rollingBaseline(reg, idx)
        if (mode === 'model') {
          value = base
          color = value != null ? tempColor(Cesium, value) : null
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

  function applyLayers(viewer: Viz, state: LayersState) {
    const scene = sceneRef.current
    scene.markers.forEach((m) => {
      if (m.label) (m.label as unknown as Showable).show = state.labels
    })
    scene.temps.forEach((t) => (t.entity.show = state.temperature))
    scene.waves.forEach((e) => (e.show = state.waves))
    scene.currents.forEach((e) => (e.show = state.currents))
    scene.storm.forEach((e) => (e.show = state.storm))
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