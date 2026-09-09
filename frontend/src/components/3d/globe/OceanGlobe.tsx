import { useMemo, useRef, useState, useEffect, Suspense, Component } from 'react'
import type { ReactNode } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, Html, useTexture } from '@react-three/drei'
import * as THREE from 'three'
import type { GlobeMarker } from '../../../utils/globe'
import { buildMarkers } from '../../../utils/globe'
import './OceanGlobe.css'

/**
 * OceanGlobe
 * ============
 * The interactive 3D ocean earth.
 *
 * DESIGN NOTES (robustness):
 *  - Markers and data layers render OUTSIDE the texture <Suspense>, so they
 *    appear from frame one even if the (internet-hosted) earth/cloud textures
 *    are still loading or unreachable.
 *  - All coast marks / rings are camera-facing SPRITES (no lookAt/orientation
 *    math) — reliable across react-three-fiber versions.
 *  - Labels use drei <Html> which correctly overlays DOM on the canvas.
 */

interface OceanGlobeProps {
  locations: { id: number; name: string; latitude: number | null; longitude: number | null }[]
  layers: { temperature: boolean; waves: boolean; currents: boolean; labels: boolean }
}

const EARTH_DAY_TEX =
  'https://unpkg.com/three-globe/example/img/earth-day.jpg'
const EARTH_CLOUDS_TEX =
  'https://threejs.org/examples/textures/planets/earth_clouds_1024.png'

/* ================= SHARED SPRITE TEXTURES ================= */

let radarTex: THREE.CanvasTexture | null = null
/** Beacon style marker: white-hot core + cyan glow + crisp ring. */
function getRadarTexture() {
  if (radarTex) return radarTex
  const size = 128
  const c = document.createElement('canvas')
  c.width = c.height = size
  const ctx = c.getContext('2d')!
  const cx = size / 2
  // glow disc
  const g = ctx.createRadialGradient(cx, cx, 0, cx, cx, 54)
  g.addColorStop(0, 'rgba(255,255,255,1)')
  g.addColorStop(0.16, 'rgba(159,243,255,0.95)')
  g.addColorStop(0.42, 'rgba(34,211,238,0.35)')
  g.addColorStop(1, 'rgba(34,211,238,0)')
  ctx.fillStyle = g
  ctx.beginPath(); ctx.arc(cx, cx, 54, 0, Math.PI * 2); ctx.fill()
  // outer ring
  ctx.strokeStyle = 'rgba(34,211,238,0.9)'
  ctx.lineWidth = 6
  ctx.beginPath(); ctx.arc(cx, cx, 52, 0, Math.PI * 2); ctx.stroke()
  ctx.strokeStyle = 'rgba(255,255,255,0.6)'
  ctx.lineWidth = 2
  ctx.beginPath(); ctx.arc(cx, cx, 40, 0, Math.PI * 2); ctx.stroke()
  // white core
  ctx.fillStyle = '#ffffff'
  ctx.beginPath(); ctx.arc(cx, cx, 5, 0, Math.PI * 2); ctx.fill()
  radarTex = new THREE.CanvasTexture(c)
  return radarTex
}

let pingTex: THREE.CanvasTexture | null = null
/** Expanding sonar ring (outline only). */
function getPingTexture() {
  if (pingTex) return pingTex
  const size = 128
  const c = document.createElement('canvas')
  c.width = c.height = size
  const ctx = c.getContext('2d')!
  const cx = size / 2
  ctx.strokeStyle = 'rgba(159,243,255,0.95)'
  ctx.lineWidth = 5
  ctx.beginPath(); ctx.arc(cx, cx, 50, 0, Math.PI * 2); ctx.stroke()
  ctx.strokeStyle = 'rgba(34,211,238,0.6)'
  ctx.lineWidth = 3
  ctx.beginPath(); ctx.arc(cx, cx, 36, 0, Math.PI * 2); ctx.stroke()
  pingTex = new THREE.CanvasTexture(c)
  return pingTex
}

let dotTex: THREE.CanvasTexture | null = null
/** Soft filled dot for temperature patches. */
function getDotTexture() {
  if (dotTex) return dotTex
  const size = 64
  const c = document.createElement('canvas')
  c.width = c.height = size
  const ctx = c.getContext('2d')!
  const cx = size / 2
  const g = ctx.createRadialGradient(cx, cx, 0, cx, cx, cx)
  g.addColorStop(0, 'rgba(255,255,255,1)')
  g.addColorStop(1, 'rgba(255,255,255,0)')
  ctx.fillStyle = g
  ctx.beginPath(); ctx.arc(cx, cx, cx, 0, Math.PI * 2); ctx.fill()
  dotTex = new THREE.CanvasTexture(c)
  return dotTex
}

/** Map temperature (°C) to a color: 20 cyan → 31 orange. */
function tempColor(t: number) {
  const cold = new THREE.Color(0x22d3ee)
  const hot = new THREE.Color(0xff8a28)
  return cold.lerp(hot, THREE.MathUtils.clamp((t - 20) / 11, 0, 1))
}

/* ================= THE EARTH ================= */

/** Catches texture-load failures so the stage never blanks to black. */
class GlobeErrorBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

/** Instantly-available fallback so the stage never looks empty. */
function BasicGlobe() {
  return (
    <mesh>
      <sphereGeometry args={[1, 32, 32]} />
      <meshStandardMaterial color="#2a6f97" emissive="#0c2a44" emissiveIntensity={0.4} />
    </mesh>
  )
}

function Earth() {
  const groupRef = useRef<THREE.Group>(null)
  const dayMap = useTexture(EARTH_DAY_TEX)

  useFrame((_, delta) => {
    if (groupRef.current) groupRef.current.rotation.y += delta * 0.04
  })

  return (
    <group ref={groupRef}>
      <mesh>
        <sphereGeometry args={[1, 64, 64]} />
        <meshPhongMaterial
          map={dayMap}
          specular={new THREE.Color(0x334466)}
          shininess={18}
          emissive={new THREE.Color(0x0a1830)}
          emissiveIntensity={0.22}
        />
      </mesh>
    </group>
  )
}

function Clouds() {
  const groupRef = useRef<THREE.Group>(null)
  const cloudsMap = useTexture(EARTH_CLOUDS_TEX)

  useFrame((_, delta) => {
    if (groupRef.current) groupRef.current.rotation.y += delta * 0.055
  })

  return (
    <group ref={groupRef}>
      <mesh>
        <sphereGeometry args={[1.004, 64, 64]} />
        <meshBasicMaterial map={cloudsMap} transparent opacity={0.38} depthWrite={false} />
      </mesh>
    </group>
  )
}

function Atmosphere() {
  const shader = {
    uniforms: {
      c: { value: 0.3 },
      p: { value: 5.8 },
      glowColor: { value: new THREE.Color(0x38bdf8) },
    },
    vertexShader: `
      varying vec3 vNormal;
      void main() {
        vNormal = normalize(normalMatrix * normal);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      uniform float c;
      uniform float p;
      uniform vec3 glowColor;
      varying vec3 vNormal;
      void main() {
        float intensity = pow(c - dot(vNormal, vec3(0.0, 0.0, 1.0)), p);
        gl_FragColor = vec4(glowColor, 1.0) * intensity;
      }
    `,
  }

  return (
    <mesh scale={1.16}>
      <sphereGeometry args={[1, 64, 64]} />
      <shaderMaterial
        side={THREE.BackSide}
        blending={THREE.AdditiveBlending}
        transparent
        {...(shader as unknown as Record<string, unknown>)}
      />
    </mesh>
  )
}

/* ================= COAST MARKERS (always visible) ================= */

function CoastMarker({ marker, showLabel }: { marker: GlobeMarker; showLabel: boolean }) {
  const spriteRef = useRef<THREE.Sprite>(null)
  const tex = getRadarTexture()

  // Gentle breathing
  useFrame(({ clock }) => {
    if (spriteRef.current) {
      const s = 0.14 * (1 + Math.sin(clock.elapsedTime * 3 + marker.id) * 0.08)
      spriteRef.current.scale.setScalar(s)
    }
  })

  return (
    <group position={[marker.position.x, marker.position.y, marker.position.z]}>
      <sprite ref={spriteRef} scale={[0.14, 0.14, 1]}>
        <spriteMaterial
          map={tex}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </sprite>

      {showLabel && (
        <Html center position={[0, 0.1, 0]} zIndexRange={[20, 0]}>
          <div className="marker-label">{marker.name.split(' (')[0]}</div>
        </Html>
      )}
    </group>
  )
}

function LocationMarkers({ markers, showLabels }: { markers: GlobeMarker[]; showLabels: boolean }) {
  return (
    <group>
      {markers.map((m) => (
        <CoastMarker key={m.id} marker={m} showLabel={showLabels} />
      ))}
    </group>
  )
}

/** Expanding + fading sonar ring sprite. */
function Ping({
  color,
  phase,
  maxSize,
}: {
  color: string
  phase: number
  maxSize: number
}) {
  const spriteRef = useRef<THREE.Sprite>(null)
  const matRef = useRef<THREE.SpriteMaterial>(null)
  const tex = getPingTexture()
  const DURATION = 3

  useFrame(({ clock }) => {
    const k = ((clock.elapsedTime + phase) % DURATION) / DURATION
    if (spriteRef.current) spriteRef.current.scale.setScalar(0.03 + k * maxSize)
    if (matRef.current) matRef.current.opacity = (1 - k) * 0.75
  })

  return (
    <sprite ref={spriteRef} scale={[0.04, 0.04, 1]}>
      <spriteMaterial
        ref={matRef}
        map={tex}
        color={color}
        transparent
        depthWrite={false}
        opacity={0.7}
        blending={THREE.AdditiveBlending}
      />
    </sprite>
  )
}

/* ================= LAYER: sea temperature (heat patches) ================= */

function TemperatureLayer({ markers }: { markers: GlobeMarker[] }) {
  const tex = getDotTexture()

  const dots = useMemo(() => {
    const up = new THREE.Vector3(0, 1, 0)
    const out: { pos: THREE.Vector3; color: THREE.Color }[] = []
    markers.forEach((m) => {
      const pos = m.position.clone().normalize()
      const t1 = new THREE.Vector3().crossVectors(pos, up)
      if (t1.lengthSq() < 0.01) t1.set(1, 0, 0)
      t1.normalize()
      const t2 = new THREE.Vector3().crossVectors(pos, t1).normalize()
      const color = tempColor(m.temp ?? 28)
      for (let gx = -2; gx <= 2; gx++) {
        for (let gy = -2; gy <= 2; gy++) {
          if (gx === 0 && gy === 0) continue
          const p = pos
            .clone()
            .add(t1.clone().multiplyScalar(gx * 0.035))
            .add(t2.clone().multiplyScalar(gy * 0.035))
            .normalize()
            .multiplyScalar(1.007)
          out.push({ pos: p, color })
        }
      }
    })
    return out
  }, [markers])

  return (
    <group>
      {dots.map((d, i) => (
        <sprite key={i} position={[d.pos.x, d.pos.y, d.pos.z]} scale={[0.05, 0.05, 1]}>
          <spriteMaterial
            map={tex}
            color={d.color}
            transparent
            depthWrite={false}
            opacity={0.9}
            blending={THREE.AdditiveBlending}
          />
        </sprite>
      ))}
    </group>
  )
}

/* ================= LAYER: wave ripples ================= */

function WavesLayer({ markers }: { markers: GlobeMarker[] }) {
  return (
    <group>
      {markers.map((m) => (
        <group key={m.id} position={[m.position.x, m.position.y, m.position.z]}>
          <Ping color="#a5f3fc" phase={m.id * 0.7} maxSize={0.16} />
          <Ping color="#67e8f9" phase={m.id * 0.7 + 1.5} maxSize={0.13} />
        </group>
      ))}
    </group>
  )
}

/* ================= LAYER: ocean currents (moving streams) ================= */

const CURRENT_ORBIT_NORMALS = [
  new THREE.Vector3(0.2, 0.6, 0.8),
  new THREE.Vector3(-0.6, 0.3, 0.8),
  new THREE.Vector3(0.7, -0.4, 0.7),
]
const DOTS_PER_ORBIT = 22
const CURRENT_DOTS = CURRENT_ORBIT_NORMALS.length * DOTS_PER_ORBIT

interface Orbit {
  u: THREE.Vector3
  v: THREE.Vector3
  speed: number
}

function buildOrbits(): Orbit[] {
  return CURRENT_ORBIT_NORMALS.map((n, i) => {
    const nav = n.clone().normalize()
    const helper = new THREE.Vector3(0, 1, 0)
    const u = new THREE.Vector3().crossVectors(helper, nav)
    if (u.lengthSq() < 1e-3) u.set(1, 0, 0)
    u.normalize()
    const v = new THREE.Vector3().crossVectors(nav, u).normalize()
    return { u, v, speed: 1 + i * 0.4 }
  })
}

function CurrentsLayer() {
  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(CURRENT_DOTS * 3), 3))
    return g
  }, [])
  const orbits = useMemo(buildOrbits, [])

  useFrame(({ clock }) => {
    const attr = geometry.getAttribute('position') as THREE.BufferAttribute
    const arr = attr.array as Float32Array
    const t = clock.elapsedTime * 0.22
    orbits.forEach(({ u, v, speed }, oi) => {
      for (let d = 0; d < DOTS_PER_ORBIT; d++) {
        const a = (d / DOTS_PER_ORBIT) * Math.PI * 2 + t * speed
        const idx = (oi * DOTS_PER_ORBIT + d) * 3
        arr[idx] = (u.x * Math.cos(a) + v.x * Math.sin(a)) * 1.016
        arr[idx + 1] = (u.y * Math.cos(a) + v.y * Math.sin(a)) * 1.016
        arr[idx + 2] = (u.z * Math.cos(a) + v.z * Math.sin(a)) * 1.016
      }
    })
    attr.needsUpdate = true
  })

  return (
    <points geometry={geometry}>
      <pointsMaterial
        size={0.022}
        color="#a5f3fc"
        transparent
        opacity={0.9}
        depthWrite={false}
        sizeAttenuation
        blending={THREE.AdditiveBlending}
      />
    </points>
  )
}

/* ================= MAIN COMPONENT ================= */

export default function OceanGlobe({ locations, layers }: OceanGlobeProps) {
  const [markers] = useState(() => buildMarkers(locations))
  const [globeKey, setGlobeKey] = useState(0)

  useEffect(() => {
    setGlobeKey((k) => k + 1)
  }, [locations])

  return (
    <div className="globe-stage">
      <Canvas key={globeKey} camera={{ position: [-2.5, 0.35, -0.6], fov: 50 }}>
        {/* Lighting */}
        <ambientLight intensity={0.75} />
        <directionalLight position={[4, 3, 2]} intensity={2.2} color="#ffffff" />
        <directionalLight position={[-4, -1, -3]} intensity={1.1} color="#bff0ff" />
        <pointLight position={[0, -2, -1]} intensity={0.5} color="#1e3a8a" />

        {/* Textured earth + clouds (Suspense-safe) */}
        <Suspense fallback={<BasicGlobe />}>
          <GlobeErrorBoundary fallback={<BasicGlobe />}>
            <Earth />
          </GlobeErrorBoundary>
          <Suspense fallback={null}>
            <Clouds />
          </Suspense>
        </Suspense>
        <Atmosphere />

        {/* Markers + layers render immediately, outside texture Suspense */}
        <LocationMarkers markers={markers} showLabels={layers.labels} />
        {layers.temperature && <TemperatureLayer markers={markers} />}
        {layers.waves && <WavesLayer markers={markers} />}
        {layers.currents && <CurrentsLayer />}

        <OrbitControls
          enablePan={false}
          rotateSpeed={0.55}
          minDistance={1.35}
          maxDistance={4.5}
          autoRotate
          autoRotateSpeed={0.5}
        />
      </Canvas>

      <div className="globe-hud">
        <span className="globe-hud-dot" />
        Drag to explore · Scroll to zoom
      </div>
    </div>
  )
}