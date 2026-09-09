import { useRef, useState, useEffect, Suspense } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, Billboard, useTexture } from '@react-three/drei'
import * as THREE from 'three'
import type { GlobeMarker } from '../../../utils/globe'
import { buildMarkers } from '../../../utils/globe'
import './OceanGlobe.css'

/**
 * OceanGlobe
 * ============
 * The interactive 3D ocean earth with glowing, "live" coast markers.
 * Powered by Three.js + react-three-fiber.
 */

interface OceanGlobeProps {
  locations: { id: number; name: string; latitude: number | null; longitude: number | null }[]
  layers: { temperature: boolean; waves: boolean; currents: boolean; labels: boolean }
}

const EARTH_DAY_TEX =
  'https://unpkg.com/three-globe/example/img/earth-day.jpg'
const EARTH_CLOUDS_TEX =
  'https://threejs.org/examples/textures/planets/earth_clouds_1024.png'

/* ------- THE EARTH (bright, vivid day texture) ------- */
function Earth() {
  const groupRef = useRef<THREE.Group>(null)
  const [dayMap] = useTexture([EARTH_DAY_TEX])

  // Gentle auto-rotation so the globe feels alive
  useFrame((_, delta) => {
    if (groupRef.current) {
      groupRef.current.rotation.y += delta * 0.04
    }
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

/* ------- SLOW DRIFTING CLOUDS (the "live" sky) ------- */
function Clouds() {
  const groupRef = useRef<THREE.Group>(null)
  const [cloudsMap] = useTexture([EARTH_CLOUDS_TEX])

  // Clouds drift a touch faster than the surface below
  useFrame((_, delta) => {
    if (groupRef.current) {
      groupRef.current.rotation.y += delta * 0.055
    }
  })

  return (
    <group ref={groupRef}>
      <mesh>
        <sphereGeometry args={[1.004, 64, 64]} />
        <meshBasicMaterial
          map={cloudsMap}
          transparent
          opacity={0.38}
          depthWrite={false}
        />
      </mesh>
    </group>
  )
}

/* ------- GLOWING ATMOSPHERE (NASA vibe) ------- */
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

/* ------- EXPANDING SONAR PING (radar feel on the coast) ------- */
function MarkerPing({
  position,
  color,
  phase,
  maxSize,
}: {
  position: THREE.Vector3
  color: string
  phase: number
  maxSize: number
}) {
  const meshRef = useRef<THREE.Mesh>(null)
  const matRef = useRef<THREE.MeshBasicMaterial>(null)
  const DURATION = 3.2

  const outward: [number, number, number] = [
    position.x * 2,
    position.y * 2,
    position.z * 2,
  ]

  useFrame(({ clock }) => {
    const t = (clock.elapsedTime + phase) % DURATION
    const k = t / DURATION
    if (meshRef.current) {
      meshRef.current.scale.setScalar(0.012 + k * maxSize)
    }
    if (matRef.current) {
      matRef.current.opacity = (1 - k) * 0.55
    }
  })

  return (
    <mesh ref={meshRef} position={position} lookAt={outward}>
      <ringGeometry args={[0.85, 1, 40]} />
      <meshBasicMaterial
        ref={matRef}
        color={color}
        transparent
        side={THREE.DoubleSide}
        depthWrite={false}
        opacity={0.4}
      />
    </mesh>
  )
}

/* ------- A SINGLE "LIVE" COAST MARKER ------- */
function CoastMarker({ marker, showLabel }: { marker: GlobeMarker; showLabel: boolean }) {
  const color = '#22d3ee'
  const pulseRef = useRef<THREE.Mesh>(null)

  // Breathing pulse on the core pin
  useFrame(({ clock }) => {
    if (pulseRef.current) {
      const s = 1 + Math.sin(clock.elapsedTime * 3 + marker.id) * 0.18
      pulseRef.current.scale.setScalar(s)
    }
  })

  return (
    <group
      position={[marker.position.x, marker.position.y, marker.position.z]}
    >
      {/* two staggered sonar rings → continuous radar ping */}
      <MarkerPing position={marker.position} color={color} phase={marker.id * 0.53} maxSize={0.055} />
      <MarkerPing position={marker.position} color={color} phase={marker.id * 0.53 + 1.6} maxSize={0.05} />

      {/* solid "coast mark" ring sitting on the surface */}
      <mesh lookAt={[marker.position.x * 2, marker.position.y * 2, marker.position.z * 2]}>
        <ringGeometry args={[0.014, 0.024, 40]} />
        <meshBasicMaterial color={color} transparent opacity={0.9} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>

      {/* soft glow halo */}
      <mesh>
        <sphereGeometry args={[0.038, 16, 16]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={0.16}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </mesh>

      {/* bright pulsing core */}
      <mesh ref={pulseRef}>
        <sphereGeometry args={[0.019, 16, 16]} />
        <meshBasicMaterial color={color} />
      </mesh>

      {/* label */}
      {showLabel && (
        <Billboard>
          <div className="marker-label">{marker.name.split(' (')[0]}</div>
        </Billboard>
      )}
    </group>
  )
}

/* ------- LOCATION MARKERS (always visible coast marks) ------- */
function LocationMarkers({ markers, showLabels }: { markers: GlobeMarker[]; showLabels: boolean }) {
  return (
    <group>
      {markers.map((m) => (
        <CoastMarker key={m.id} marker={m} showLabel={showLabels} />
      ))}
    </group>
  )
}

/* ------- LAYER: sea temperature heat patches ------- */
function TemperatureLayer({ markers }: { markers: GlobeMarker[] }) {
  const heat = {
    uniforms: {
      min: { value: 20 },
      max: { value: 31 },
    },
    vertexShader: `
      attribute float value;
      varying float vValue;
      void main() {
        vValue = value;
        gl_PointSize = 9.0;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      uniform float min;
      uniform float max;
      varying float vValue;
      void main() {
        float t = clamp((vValue - min) / (max - min), 0.0, 1.0);
        if (length(gl_PointCoord - vec2(0.5)) > 0.5) discard;
        vec3 cool = vec3(0.16, 0.75, 0.92);
        vec3 warm = vec3(1.0, 0.55, 0.25);
        vec3 color = mix(cool, warm, t);
        gl_FragColor = vec4(color, 0.85);
      }
    `,
  }

  // Scatter dots in a small grid tangent to the surface around each marker
  const positions: number[] = []
  const values: number[] = []
  const up = new THREE.Vector3(0, 1, 0)

  markers.forEach((m) => {
    const pos = m.position.clone().normalize()
    const t1 = new THREE.Vector3().crossVectors(pos, up).normalize()
    if (t1.lengthSq() < 0.01) t1.set(1, 0, 0)
    const t2 = new THREE.Vector3().crossVectors(pos, t1).normalize()
    const r = pos.clone().multiplyScalar(1.006)
    for (let gx = -1; gx <= 1; gx++) {
      for (let gy = -1; gy <= 1; gy++) {
        if (gx === 0 && gy === 0) continue
        const p = r
          .clone()
          .add(t1.clone().multiplyScalar(gx * 0.03))
          .add(t2.clone().multiplyScalar(gy * 0.03))
          .normalize()
          .multiplyScalar(1.006)
        positions.push(p.x, p.y, p.z)
        values.push(m.temp ?? 28)
      }
    }
  })

  return (
    <points>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          args={[new Float32Array(positions), 3]}
        />
        <bufferAttribute
          attach="attributes-value"
          args={[new Float32Array(values), 1]}
        />
      </bufferGeometry>
      <shaderMaterial
        transparent
        depthWrite={false}
        blending={THREE.AdditiveBlending}
        {...(heat as unknown as Record<string, unknown>)}
      />
    </points>
  )
}

/* ------- MAIN EXPORTED COMPONENT ------- */
export default function OceanGlobe({ locations, layers }: OceanGlobeProps) {
  const [markers] = useState(() => buildMarkers(locations))
  const [globeKey, setGlobeKey] = useState(0)

  useEffect(() => {
    setGlobeKey((k) => k + 1)
  }, [locations])

  return (
    <div className="globe-stage">
      <Canvas key={globeKey} camera={{ position: [0, 0.35, 2.6], fov: 50 }}>
        {/* Bright, layered lighting so the earth pops */}
        <ambientLight intensity={0.75} />
        <directionalLight position={[4, 3, 2]} intensity={2.2} color="#ffffff" />
        <directionalLight position={[-4, -1, -3]} intensity={1.1} color="#bff0ff" />
        <pointLight position={[0, -2, -1]} intensity={0.5} color="#1e3a8a" />

        <Suspense fallback={null}>
          <Earth />
          <Suspense fallback={null}>
            <Clouds />
          </Suspense>
          <Atmosphere />
          <LocationMarkers markers={markers} showLabels={layers.labels} />
          {layers.temperature && <TemperatureLayer markers={markers} />}
        </Suspense>

        <OrbitControls
          enablePan={false}
          rotateSpeed={0.55}
          minDistance={1.35}
          maxDistance={4.5}
          autoRotate
          autoRotateSpeed={0.5}
        />
      </Canvas>

      {/* HUD overlay hint */}
      <div className="globe-hud">
        <span className="globe-hud-dot" />
        Drag to explore · Scroll to zoom
      </div>
    </div>
  )
}