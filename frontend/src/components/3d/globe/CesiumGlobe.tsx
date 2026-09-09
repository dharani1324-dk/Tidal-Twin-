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

export type LayerKey = 'labels' | 'temperature' | 'waves' | 'currents'
export type LayersState = Record<LayerKey, boolean>

type CesiumModule = typeof import('cesium')
type Viz = InstanceType<CesiumModule['Viewer']>
type VizEntity = InstanceType<CesiumModule['Entity']>
/** Cesium wraps raw booleans into ConstantProperty at runtime; TS types lag it. */
type Showable = { show: boolean }

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

function tempColor(Cesium: CesiumModule, temp: number) {
  const cold = Cesium.Color.fromCssColorString('#22d3ee')
  const hot = Cesium.Color.fromCssColorString('#ff8a28')
  const k = Cesium.Math.clamp((temp - 20) / 11, 0, 1)
  return Cesium.Color.lerp(cold, hot, k, new Cesium.Color())
}

/* ------------------ component ------------------ */

interface CesiumGlobeProps {
  locations: GlobeLocation[]
  layers: LayersState
}

interface Scene {
  markers: VizEntity[]
  temps: VizEntity[]
  waves: VizEntity[]
  currents: VizEntity[]
}

export default function CesiumGlobe({ locations, layers }: CesiumGlobeProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const viewerRef = useRef<Viz | null>(null)
  const sceneRef = useRef<Scene>({ markers: [], temps: [], waves: [], currents: [] })
  const layersRef = useRef(layers)
  layersRef.current = layers
  const locatedRef = useRef(locations)
  locatedRef.current = locations
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
        // Make the globe feel like a map: left-drag pans, right-drag spins,
        // scroll zooms, middle-drag tilts. Add zoom guardrails so it never
        // flies into space or through the earth.
        const camCtrl = viewer.scene.screenSpaceCameraController
        camCtrl.translateEventTypes = [Cesium.CameraEventType.LEFT_DRAG, Cesium.CameraEventType.PINCH]
        camCtrl.rotateEventTypes = Cesium.CameraEventType.RIGHT_DRAG
        camCtrl.lookEventTypes = Cesium.CameraEventType.RIGHT_DRAG
        camCtrl.tiltEventTypes = Cesium.CameraEventType.MIDDLE_DRAG
        camCtrl.zoomEventTypes = [Cesium.CameraEventType.WHEEL, Cesium.CameraEventType.PINCH]
        camCtrl.minimumZoomDistance = 1200000
        camCtrl.maximumZoomDistance = 9000000
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
    })
    return () => {
      active = false
    }
  }, [locations])

  // Toggle data layers without rebuilding entities.
  useEffect(() => {
    const viewer = viewerRef.current
    if (!viewer) return
    loadCesium().then(() => applyLayers(viewer, layers))
  }, [layers])

  // Dispose the viewer on unmount.
  useEffect(() => {
    return () => {
      viewerRef.current?.destroy()
      viewerRef.current = null
      sceneRef.current = { markers: [], temps: [], waves: [], currents: [] }
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
    const scene: Scene = { markers: [], temps: [], waves: [], currents: [] }

    const valid = locations.filter((l) => l.latitude != null && l.longitude != null)

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
          width: 44,
          height: 44,
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
      scene.temps.push(temp)

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

  function applyLayers(viewer: Viz, state: LayersState) {
    const scene = sceneRef.current
    scene.markers.forEach((m) => {
      if (m.label) (m.label as unknown as Showable).show = state.labels
    })
    scene.temps.forEach((e) => (e.show = state.temperature))
    scene.waves.forEach((e) => (e.show = state.waves))
    scene.currents.forEach((e) => (e.show = state.currents))
    viewer.scene.requestRender()
  }

  return (
    <div ref={containerRef} className="cesium-globe">
      <div className="cesium-hint">
        <span>Left-drag · move map</span>
        <span>Right-drag · spin globe</span>
        <span>Scroll · zoom</span>
      </div>
    </div>
  )
}