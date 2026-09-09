import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { Thermometer, Waves, Droplets, Tag, Globe2, Crosshair, Layers, Tornado, Clock, Play, Pause, Repeat } from 'lucide-react'
import CesiumGlobe from '../components/3d/globe/CesiumGlobe'
import type { GlobeLocation, SeriesRegion, StormTrackData } from '../components/3d/globe/CesiumGlobe'
import { fetchLocations, fetchObservations, fetchStormTrack, fetchSafetyTimeseries } from '../api/client'
import './DigitalTwin.css'

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: 'easeOut' as const } },
}

type ReplayMode = 'temp' | 'model' | 'difference'

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
  const [locations, setLocations] = useState<GlobeLocation[]>([])
  const [loading, setLoading] = useState(true)
  const [activeLoc, setActiveLoc] = useState<GlobeLocation | null>(null)
  const [layers, setLayers] = useState({
    temperature: true,
    waves: true,
    currents: true,
    labels: true,
    storm: false,
  })
  const [storm, setStorm] = useState<StormTrackData | null>(null)
  const [series, setSeries] = useState<SeriesRegion[]>([])
  const [cursor, setCursor] = useState<number>(0)
  const [playing, setPlaying] = useState(false)
  const [replayMode, setReplayMode] = useState<ReplayMode>('temp')

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
  }, [])

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
  ]

  const cursorTime = series[0]?.points[cursor]?.time
  const cursorLabel = cursorTime
    ? new Date(cursorTime).toLocaleString([], {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
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

  const replayLabel =
    replayMode === 'temp' ? 'OBSERVED' : replayMode === 'model' ? 'MODEL' : 'DIFFERENCE'

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
          <CesiumGlobe
            locations={locations}
            layers={layers}
            storm={storm}
            series={series}
            timeCursor={series.length > 0 ? cursor : null}
            timeColor={replayMode}
          />
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

          {/* Timeline scrubber — 4D Event Replay */}
          <div className="glass-card control-card">
            <div className="control-title">
              <Clock size={16} />
              <span>Event Replay</span>
              <span className={`live-dot ${playing ? '' : 'live-dot-off'}`} />
            </div>

            {/* Replay mode: what the patches are colored by */}
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

                {/* Live deviation readout */}
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