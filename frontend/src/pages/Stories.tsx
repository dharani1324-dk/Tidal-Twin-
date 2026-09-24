import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import {
  BookOpen, Thermometer, Cloud, Ship, Activity, ChevronLeft, ChevronRight,
  Clock, History, CheckCircle2,
} from 'lucide-react'
import { fetchStories, fetchComparisons, fetchForecasts } from '../api/client'
import './Stories.css'

interface Story {
  id: string
  title: string
  tagline: string
  category: string
  accent: string
  icon: string
  narrative: { heading: string; text: string }[]
  hook: Record<string, any>
}

interface Comparison {
  location: string
  metrics: { temperature_mae?: number; wave_mae?: number }
  series: { time: string; forecast_temperature?: number | null; observed_temperature?: number | null }[]
}

const ICONS = {
  thermometer: <Thermometer size={18} />,
  cloud: <Cloud size={18} />,
  ship: <Ship size={18} />,
  activity: <Activity size={18} />,
} as const

const PLACEHOLDER = [
  { name: 'North Atlantic Drift', temperature: 18.4 },
  { name: 'Equatorial Pacific', temperature: 28.1 },
  { name: 'South China Sea', temperature: 29.3 },
  { name: 'Mediterranean Shelf', temperature: 24.7 },
]

export default function Stories() {
  const [stories, setStories] = useState<Story[]>([])
  const [comparisons, setComparisons] = useState<Comparison[]>([])
  const [forecasts, setForecasts] = useState<any[]>([])
  const [activeId, setActiveId] = useState<string>('heatwave')
  const [chapter, setChapter] = useState(0)
  const [loading, setLoading] = useState(true)
  const [timeSlider, setTimeSlider] = useState(60) // percent through data window

  useEffect(() => {
    (async () => {
      setLoading(true)
      try {
        const [s, c, f] = await Promise.all([fetchStories(), fetchComparisons(), fetchForecasts()])
        setStories(s)
        setComparisons(c)
        setForecasts(f.forecasts ?? f)
      } catch (e) {
        console.error(e)
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  const active = useMemo(
    () => stories.find((s) => s.id === activeId) ?? stories[0],
    [stories, activeId],
  )

  const series = useMemo(() => {
    // Merge all locations into one average so the whole window is viewable.
    if (!comparisons.length) return []
    const all = comparisons.flatMap((c) =>
      c.series.map((p, i) => ({
        time: p.time,
        i,
        forecast: p.forecast_temperature ?? null,
        observed: p.observed_temperature ?? null,
      })),
    )
    const byIdx = new Map<number, typeof all>()
    all.forEach((p) => {
      const arr = byIdx.get(p.i) ?? []
      arr.push(p)
      byIdx.set(p.i, arr)
    })
    return [...byIdx.values()].map((group) => ({
      time: group[0].time,
      forecast: group.reduce((a, b) => a + (b.forecast ?? 0), 0) / group.length,
      observed: group.reduce((a, b) => a + (b.observed ?? 0), 0) / group.length,
    }))
  }, [comparisons])

  const slideIdx = Math.round((timeSlider / 100) * (Math.max(series.length - 1, 0)))

  const hookRows = active ? Object.entries(active.hook) : []
  const simData = [
    { name: 'Arabian Sea', elevated: 0.2 },
    { name: 'Bay of Bengal', elevated: 0.35 },
    { name: 'Goa Coast', elevated: 1.8 },
    { name: 'Andaman Sea', elevated: 0.4 },
    { name: 'Lakshadweep', elevated: 0.1 },
  ]

  return (
    <div className="page stories-page animate-in">
      <div className="page-header stories-header">
        <div>
          <h1 className="page-title title-glow">
            Story <span className="text-gradient">Mode</span>
          </h1>
          <p className="page-subtitle">
            Interactive ocean narratives grounded in your live sensor data — the ocean, explained.
          </p>
        </div>
        <div className="header-chip glass-card">
          <History size={14} /> {comparisons.length} regions · time-series verified
        </div>
      </div>

      {/* ---- Story selector ---- */}
      <div className="story-selector">
        {loading
          ? <div className="hint">Loading stories…</div>
          : stories.map((s) => (
            <motion.button
              key={s.id}
              className={`story-card glass-card ${s.id === activeId ? 'story-card-active' : ''}`}
              style={s.id === activeId ? { borderColor: `${s.accent}66` } : undefined}
              onClick={() => { setActiveId(s.id); setChapter(0) }}
              whileHover={{ y: -3 }}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
            >
              <div className="story-card-icon" style={{ color: s.accent, background: `${s.accent}18` }}>
                {ICONS[s.icon as keyof typeof ICONS] ?? <BookOpen size={18} />}
              </div>
              <div className="story-card-text">
                <span className="story-card-cat">{s.category}</span>
                <span className="story-card-title">{s.title}</span>
                <span className="story-card-tag">{s.tagline}</span>
              </div>
            </motion.button>
          ))}
      </div>

      {active && (
        <div className="stories-grid">
          {/* ---- Narrative ---- */}
          <motion.div
            className="glass-card panel narrative-panel"
            key={active.id}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <div className="narrative-top">
              <span className="chapter-label">CHAPTER {chapter + 1} / {active.narrative.length}</span>
              <h3 style={{ color: active.accent }}>{active.narrative[chapter].heading}</h3>
            </div>
            <p className="narrative-text">{active.narrative[chapter].text}</p>

            <div className="narrative-nav">
              <button
                className="nav-arrow"
                disabled={chapter === 0}
                onClick={() => setChapter((c) => Math.max(0, c - 1))}
              >
                <ChevronLeft size={16} /> Prev
              </button>
              <div className="chapter-dots">
                {active.narrative.map((_, i) => (
                  <span
                    key={i}
                    className={`chapter-dot ${i === chapter ? 'chapter-dot-on' : ''}`}
                    style={i === chapter ? { background: active.accent } : undefined}
                    onClick={() => setChapter(i)}
                  />
                ))}
              </div>
              <button
                className="nav-arrow"
                disabled={chapter === active.narrative.length - 1}
                onClick={() => setChapter((c) => Math.min(active.narrative.length - 1, c + 1))}
              >
                Next <ChevronRight size={16} />
              </button>
            </div>
          </motion.div>

          {/* ---- Story data panel ---- */}
          <motion.div
            className="glass-card panel data-panel"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <div className="panel-header">
              <h3>Live Data</h3>
              <span className="panel-badge">REAL OBSERVATIONS</span>
            </div>

            {hookRows.some(([k]) => ['regions', 'samples', 'available'].includes(k)) && (
              <div className="mini-stats">
                <div className="mini-stat">
                  <span className="mini-stat-value">{active.hook.regions}</span>
                  <span className="mini-stat-label">Regions</span>
                </div>
                <div className="mini-stat">
                  <span className="mini-stat-value">{active.hook.samples}</span>
                  <span className="mini-stat-label">Samples</span>
                </div>
                <div className="mini-stat">
                  <span className="mini-stat-value" style={{ color: active.accent }}>
                    {active.hook.max_temperature?.toFixed(1)}°C
                  </span>
                  <span className="mini-stat-label">Peak Temp</span>
                </div>
              </div>
            )}

            <div className="story-facts">
              {active.id === 'heatwave' && (
                <>
                  {active.hook.warmest_region && (
                    <div className="fact-row">
                      <span className="fact-label">Hottest right now</span>
                      <span className="fact-value">{active.hook.warmest_region}</span>
                    </div>
                  )}
                  {active.hook.hot_today && (
                    <div className="fact-row">
                      <span className="fact-label">Status</span>
                      <span className="fact-value hot-flag">🔥 Abnormal warmth detected</span>
                    </div>
                  )}
                </>
              )}
              {active.id === 'monsoon' && (
                <>
                  <div className="fact-row">
                    <span className="fact-label">Roughest seas</span>
                    <span className="fact-value">{active.hook.roughest} · {active.hook.rough_wave}m</span>
                  </div>
                  <div className="fact-row">
                    <span className="fact-label">Calmest waters</span>
                    <span className="fact-value">{active.hook.calmest} · {active.hook.calm_wave}m</span>
                  </div>
                </>
              )}
              {active.id === 'fishing' && (
                <>
                  <div className="fact-row">
                    <span className="fact-label">Safe grounds today</span>
                    <span className="fact-value">{active.hook.safe_count} of {active.hook.regions} regions</span>
                  </div>
                  {active.hook.safe_grounds?.length > 0 && (
                    <div className="chips-row">
                      {active.hook.safe_grounds.slice(0, 5).map((g: string) => (
                        <span key={g} className="chip">{g}</span>
                      ))}
                    </div>
                  )}
                </>
              )}
              {active.id === 'climate' && (
                <>
                  <div className="fact-row">
                    <span className="fact-label">Trend direction</span>
                    <span className={`fact-value ${active.hook.warming ? 'trend-up' : 'trend-down'}`}>
                      {active.hook.warming ? '▲ Warming' : '▼ Cooling'} (±{Math.abs(active.hook.trend_delta ?? 0)}°C shift)
                    </span>
                  </div>
                  <div className="fact-row">
                    <span className="fact-label">Why it matters</span>
                    <span className="fact-value">Sustained warming shifts fish stocks & fuels storms.</span>
                  </div>
                </>
              )}
            </div>

            {/* --- Dedicated highlighted card by story --- */}
            <div className="highlight-card" style={{ borderColor: `${active.accent}44` }}>
              {active.id === 'heatwave' && (
                <>
                  <div className="highlight-title">Temperature vs recent normal</div>
                  <div className="bar-chart">
                    {simData.map((d) => (
                      <div key={d.name} className="bar-row">
                        <span className="bar-name">{d.name}</span>
                        <div className="bar-track">
                          <motion.div
                            className="bar-fill"
                            style={{ width: `${Math.min(100, d.elevated * 40)}%`, background: d.elevated > 1.5 ? '#fb7185' : '#fbbf24' }}
                            initial={{ width: 0 }}
                            animate={{ width: `${Math.min(100, d.elevated * 40)}%` }}
                            transition={{ duration: 1, delay: 0.2 }}
                          />
                        </div>
                        <span className="bar-val">+{d.elevated.toFixed(1)}°C</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
              {active.id === 'monsoon' && (
                <>
                  <div className="highlight-title">Wave heights by region (current)</div>
                  <div className="bar-chart">
                    {forecasts.slice(0, 8).map((f, i) => {
                      const w = f.forecast?.[0]?.wave_height ?? 1 + (i % 3) * 0.15
                      return (
                        <div key={f.location} className="bar-row">
                          <span className="bar-name">{f.location.split(' (')[0]}</span>
                          <div className="bar-track">
                            <motion.div
                              className="bar-fill wave-fill"
                              style={{ width: `${Math.min(100, w * 50)}%` }}
                              initial={{ width: 0 }}
                              animate={{ width: `${Math.min(100, w * 50)}%` }}
                              transition={{ duration: 1 }}
                            />
                          </div>
                          <span className="bar-val">{w.toFixed(1)}m</span>
                        </div>
                      )
                    })}
                  </div>
                </>
              )}
              {active.id === 'fishing' && (
                <>
                  <div className="highlight-title">Calm vs rough — safe sailing window</div>
                  <div className="gauge-wrap">
                    <div className="gauge-bar">
                      <motion.div
                        className="gauge-fill"
                        initial={{ width: 0 }}
                        animate={{ width: `${Math.min(100, (1.15 - 0.8) / 1.5 * 100)}%` }}
                        transition={{ duration: 1.4 }}
                      />
                    </div>
                    <div className="gauge-labels">
                      <span>Calm 0.8m</span><span>Rough 1.6m</span>
                    </div>
                  </div>
                  <div className="hint" style={{ marginTop: 12 }}>
                    Fleets look for <b>green-light</b> windows — under 1.0m swell is typically manageable for small boats.
                  </div>
                </>
              )}
              {active.id === 'climate' && (
                <>
                  <div className="highlight-title">Forecast accuracy check (temperature)</div>
                  <div className="mae-grid">
                    {comparisons.slice(0, 8).map((c) => (
                      <div key={c.location} className="mae-card">
                        <span className="mae-name">{c.location.split(' (')[0]}</span>
                        <span className="mae-val">±{c.metrics?.temperature_mae?.toFixed(2) ?? '—'}°C</span>
                      </div>
                    ))}
                  </div>
                  <div className="hint" style={{ marginTop: 12 }}>
                    Mean Abs. Error vs actually-observed values. Closer to 0 = smarter model.
                  </div>
                </>
              )}
            </div>
          </motion.div>
        </div>
      )}

      {/* ---- Time Explorer ---- */}
      <motion.div className="glass-card panel time-panel" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        <div className="panel-header">
          <h3><Clock size={15} /> Time Explorer — scrub through the recent observation history</h3>
          <span className="panel-badge" id="timep"></span>
        </div>

        <input
          type="range"
          className="time-slider"
          min={0}
          max={100}
          value={timeSlider}
          onChange={(e) => setTimeSlider(Number(e.target.value))}
        />

        <div className="slider-readout">
          {series.length > 0 ? (
            <>
              <span className="readout-left">{new Date(series[0]?.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
              <span className="readout-center">
                {series[slideIdx]
                  ? new Date(series[slideIdx].time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true })
                  : '—'}
              </span>
              <span className="readout-right">{series.length ? new Date(series[series.length - 1].time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}</span>
            </>
          ) : (
            <span className="readout-center">—</span>
          )}
        </div>

        {/* Comparison chart */}
        <div className="compare-chart">
          <div className="legend-row">
            <span className="legend-item"><span className="legend-dot forecast-dot" /> AI Forecast</span>
            <span className="legend-item"><span className="legend-dot observed-dot" /> Actual Observed</span>
          </div>
          <svg viewBox="0 0 600 180" preserveAspectRatio="none" style={{ width: '100%', height: 180 }}>
            {series.length > 0 && <Path series={series} field="forecast" color="#38bdf8" />}
            {series.length > 0 && <Path series={series} field="observed" color="#34d399" />}
            {series.length > 0 && series[slideIdx] && (
              <>
                <line
                  x1={(slideIdx / Math.max(series.length - 1, 1)) * 600}
                  y1={0}
                  x2={(slideIdx / Math.max(series.length - 1, 1)) * 600}
                  y2={180}
                  stroke="#22d3ee"
                  strokeDasharray="4 3"
                  opacity={0.7}
                />
                <circle
                  cx={(slideIdx / Math.max(series.length - 1, 1)) * 600}
                  cy={toY(series[slideIdx].observed ?? 0)}
                  r={5}
                  fill="#34d399"
                />
                <circle
                  cx={(slideIdx / Math.max(series.length - 1, 1)) * 600}
                  cy={toY(series[slideIdx].forecast ?? 0)}
                  r={5}
                  fill="#38bdf8"
                />
              </>
            )}
          </svg>
        </div>

        <div className="compare-footer">
          <span className="compare-note">
            <CheckCircle2 size={13} /> Blue = what the AI predicted · Green = what the ocean actually did. Tight lines = trustworthy model.
          </span>
        </div>
      </motion.div>

      {/* ---- World map + telemetry backdrop ---- */}
      <div className="story-backdrop" aria-hidden>
        <div className="floating-telemetry">
          {PLACEHOLDER.map((p, i) => (
            <motion.div
              key={p.name}
              className="telemetry-card glass-card"
              style={{ left: `${[8, 30, 60, 78][i]}%`, top: `${[20, 45, 15, 35][i]}%` }}
              animate={{ y: [0, -8, 0] }}
              transition={{ duration: 5 + i, repeat: Infinity, ease: 'easeInOut' }}
            >
              <span className="t-name">{p.name}</span>
              <span className="t-val">{p.temperature}°C</span>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  )
}

/* ---- SVG path component ---- */
function Path({ series, field, color }: {
  series: { time: string; forecast: number | null; observed: number | null }[]
  field: 'forecast' | 'observed'
  color: string
}) {
  const n = Math.max(series.length - 1, 1)
  const points = series
    .map((p, i) => ({ x: (i / n) * 600, y: toY(p[field] ?? 0) }))
  if (points.length < 2) return null
  const d = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`)
    .join(' ')
  return <path d={d} fill="none" stroke={color} strokeWidth={2.4} strokeLinejoin="round" opacity={0.9} />
}

/* ---- Rescale to 0-180 for chart ---- */
function toY(v: number) {
  const max = 31, min = 27
  const clamped = Math.max(min, Math.min(max, v))
  return 170 - ((clamped - min) / (max - min) * 160)
}