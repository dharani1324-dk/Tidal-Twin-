import { useRef, useState, useEffect, Suspense } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls, Billboard, useTexture } from '@react-three/drei'
import * as THREE from 'three'
import type { GlobeMarker } from '../../../utils/globe'
import { buildMarkers } from '../../../utils/globe'
import './OceanGlobe.css'

/**
 * OceanGlobe
 * ============
 * The interactive 3D ocean earth with glowing location markers.
 * Powered by Three.js + react-three-fiber.
 */

interface OceanGlobeProps {
  locations: { id: number; name: string; latitude: number | null; longitude: number | null }[]
  layers: { temperature: boolean; waves: boolean; currents: boolean; labels: boolean }
}

/* ------- THE EARTH ------- */
function Earth() {
  const groupRef = useRef<THREE.Group>(null)

  // Realistic earth texture (Blue Marble style) from a public CDN
  const [earthMap] = useTexture([
    'https://unpkg.com/three-globe/example/img/earth-blue-marble.jpg',
  ])

  // Gentle auto-rotation
  useFrame((_, delta) => {
    if (groupRef.current) {
      groupRef.current.rotation.y += delta * 0.045
    }
  })

  return (
    <group ref={groupRef}>
      <mesh>
        <sphereGeometry args={[1, 64, 64]} />
        <meshPhongMaterial
          map={earthMap}
          specular={new THREE.Color(0x112244)}
          shininess={8}
        />
      </mesh>
    </group>
  )
}

/* ------- GLOWING ATMOSPHERE (NASA vibe) ------- */
function Atmosphere() {
  const shader = {
    uniforms: {
      c: { value: 0.27 },
      p: { value: 6.2 },
      glowColor: { value: new THREE.Color(0x22d3ee) },
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
    <mesh scale={1.15}>
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

/* ------- LOCATION MARKERS ------- */
function LocationMarkers({ markers, showLabels }: { markers: GlobeMarker[]; showLabels: boolean }) {
  return (
    <group>
      {markers.map((m) => (
        <group key={m.id} position={[m.position.x, m.position.y, m.position.z]}>
          {/* glowing pin */}
          <mesh>
            <sphereGeometry args={[0.014, 16, 16]} />
            <meshBasicMaterial color="#22d3ee" />
          </mesh>
          {/* soft glow halo */}
          <mesh>
            <sphereGeometry args={[0.032, 16, 16]} />
            <meshBasicMaterial
              color="#7dd3fc"
              transparent
              opacity={0.25}
            />
          </mesh>
          {/* label */}
          {showLabels && (
            <Billboard>
              <div className="marker-label">
                {m.name.split(' (')[0]}
              </div>
            </Billboard>
          )}
        </group>
      ))}
    </group>
  )
}

/* ------- LAYER: temperature dots (visual proxy) ------- */
function TemperatureLayer({ markers }: { markers: GlobeMarker[] }) {
  const { camera } = useThree()
  const heat = {
    uniforms: {
      min: { value: 20 },
      max: { value: 30 },
    },
    vertexShader: `
      attribute float value;
      varying float vValue;
      void main() {
        vValue = value;
        gl_PointSize = 6.0;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      uniform float min;
      uniform float max;
      varying float vValue;
      void main() {
        float t = (vValue - min) / max;
        if (length(gl_PointCoord - vec2(0.5)) > 0.5) discard;
        vec3 color = mix(vec3(0.13, 0.72, 0.90), vec3(1.0, 0.55, 0.25), clamp(t, 0.0, 1.0));
        gl_FragColor = vec4(color, 0.9);
      }
    `,
  }

  void camera

  // Build a ring of points around each marker to suggest a heat region
  const points: number[][] = []
  const values: number[] = []
  markers.forEach((m) => {
    for (let a = 0; a < 12; a++) {
      void a
      points.push([m.position.x * 1.01, m.position.y * 1.02, m.position.z * 1.0])
      values.push(m.temp ?? 28)
    }
  })

  const positions = new Float32Array(points.flat())
  const valueAttr = new Float32Array(values)

  return (
    <points>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        <bufferAttribute attach="attributes-value" args={[valueAttr, 1]} />
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
        <ambientLight intensity={0.35} />
        <directionalLight position={[3, 2, 1]} intensity={1.5} />
        <pointLight position={[-2, -1, -2]} intensity={0.4} />

        <Suspense fallback={null}>
          <Earth />
          <Atmosphere />
          {layers.labels && <LocationMarkers markers={markers} showLabels={layers.labels} />}
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