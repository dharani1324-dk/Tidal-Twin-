import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Thermometer, Waves, Droplets, Tag, Globe2, Crosshair, Layers } from 'lucide-react'
import CesiumGlobe from '../components/3d/globe/CesiumGlobe'
import type { GlobeLocation } from '../components/3d/globe/CesiumGlobe'
import { fetchLocations, fetchObservations } from '../api/client'
import './DigitalTwin.css'

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: 'easeOut' as const } },
}

export default function DigitalTwin() {
  const [locations, setLocations] = useState<GlobeLocation[]>([])
  const [loading, setLoading] = useState(true)
  const [activeLoc, setActiveLoc] = useState<GlobeLocation | null>(null)
  const [layers, setLayers] = useState({
    temperature: true,
    waves: true,
    currents: true,
    labels: true,
  })

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
        setActiveLoc(withData[0] ?? null)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const toggleLayer = (key: keyof typeof layers) => {
    setLayers((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  const LAYER_PANEL = [
    { key: 'labels' as const, icon: <Tag size={16} />, name: 'Region Labels', desc: 'Floating labels on the globe' },
    { key: 'temperature' as const, icon: <Thermometer size={16} />, name: 'Sea Temperature', desc: 'Heat signature layer' },
    { key: 'waves' as const, icon: <Waves size={16} />, name: 'Wave Height', desc: 'Wave energy layer' },
    { key: 'currents' as const, icon: <Droplets size={16} />, name: 'Ocean Currents', desc: 'Flow field layer' },
  ]

  return (
    <div className="page digital-twin animate-in">
      <div className="page-header twin-header">
        <div>
          <h1 className="page-title title-glow">
            3D Ocean <span className="text-gradient">Digital Twin</span>
          </h1>
          <p className="page-subtitle">
            An immersive, interactive replica of India's coastal waters — powered by real ocean data.
          </p>
        </div>
        <div className="twin-count glass-card">
          <Crosshair size={16} />
          <span>{loading ? '…' : locations.length} MONITORED</span>
        </div>
      </div>

      <motion.div variants={fadeUp} initial="hidden" animate="show" className="twin-layout">
        {/* Globe */}
        <div className="twin-globe-wrap">
          <CesiumGlobe locations={locations} layers={layers} />
        </div>

        {/* Control panel */}
        <div className="twin-controls">
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

          {/* Selected region info */}
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
        </div>
      </motion.div>
    </div>
  )
}