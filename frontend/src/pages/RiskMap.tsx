import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import {
  Map, ShieldCheck, Shield, ShieldAlert, Wind, Crosshair, TrendingUp,
} from 'lucide-react'
import { fetchSafetyAdvisory, fetchStormTrack, fetchModelTrust, fetchLocations } from '../api/client'
import './RiskMap.css'

interface Region {
  location_id: number
  location: string
  status: 'safe' | 'caution' | 'danger'
  risk_index: number
  safe_window: string
  latest_temperature: number | null
  wave_height: number | null
}

interface StormPoint {
  hour?: number
  time?: string
  lat: number
  lon: number
  wind_kmh?: number
  radius_km?: number
}

interface MapLoc {
  id: number
  name: string
  latitude: number | null
  longitude: number | null
}

const STATUS_META = {
  safe: { color: '#34d399', label: 'SAFE' },
  caution: { color: '#f59e0b', label: 'CAUTION' },
  danger: { color: '#f43f5e', label: 'DANGER' },
}

/* Rough India silhouette (lon, lat) — stylized command-center map. */
const INDIA: [number, number][] = [
  [69.0, 23.5], [68.6, 26.5], [69.5, 29.0], [70.5, 31.2], [72.2, 30.8], [73.8, 32.0],
  [75.0, 33.5], [77.0, 34.8], [79.0, 35.5], [81.0, 35.0], [83.0, 34.5], [84.8, 34.2],
  [86.5, 33.0], [88.0, 31.5], [88.8, 30.0], [90.2, 29.7], [91.5, 28.2], [92.6, 26.6],
  [93.8, 26.0], [95.2, 27.0], [96.7, 26.9], [95.8, 28.4], [93.8, 29.2], [92.0, 28.7],
  [90.2, 28.0], [88.6, 26.6], [88.0, 25.0], [87.2, 23.4], [85.6, 21.6], [83.2, 19.0],
  [81.2, 16.2], [80.2, 14.1], [78.6, 11.3], [77.9, 9.7], [77.6, 8.2], [79.5, 9.0],
  [80.3, 10.4], [80.2, 12.8], [81.0, 15.6], [82.0, 17.7], [83.5, 18.6], [85.7, 20.1],
  [86.9, 21.4], [88.1, 22.5], [89.5, 23.8], [90.5, 25.0], [92.0, 26.3], [93.6, 27.4],
  [95.1, 28.0], [94.6, 27.2], [93.2, 26.2], [92.0, 25.0], [90.8, 23.9], [89.8, 25.5],
  [89.5, 27.0], [88.5, 28.3], [87.3, 29.8], [86.0, 31.2], [84.0, 32.5], [82.0, 33.0],
  [80.0, 32.8], [78.5, 32.0], [77.0, 30.8], [76.0, 29.3], [75.0, 27.8], [73.8, 26.0],
  [72.5, 24.6], [71.3, 23.7], [69.0, 23.5],
]

const LON0 = 63.5
const LON1 = 98.5
const LAT0 = 5.5
const LAT1 = 36.5
const W = 780
const H = 720
const M = 22

function proj(lon: number, lat: number): [number, number] {
  const x = M + ((lon - LON0) / (LON1 - LON0)) * (W - 2 * M)
  const y = M + ((LAT1 - lat) / (LAT1 - LAT0)) * (H - 2 * M)
  return [x, y]
}

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: (i: number) => ({
    opacity: 1, y: 0,
    transition: { delay: i * 0.07, duration: 0.5, ease: 'easeOut' as const },
  }),
}

export default function RiskMap() {
  const [advisory, setAdvisory] = useState<Region[]>([])
  const [locs, setLocs] = useState<MapLoc[]>([])
  const [storm, setStorm] = useState<StormPoint[]>([])
  const [stormName, setStormName] = useState('')
  const [trust, setTrust] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      fetchSafetyAdvisory(),
      fetchStormTrack(),
      fetchModelTrust(),
      fetchLocations(),
    ])
      .then(([a, s, t, l]) => {
        setAdvisory(a.regions ?? [])
        setStorm(s.points ?? [])
        setStormName(s.name ?? '')
        const tr = (t.regions ?? []) as { trust_score: number }[]
        setTrust(tr.length ? Math.round(tr.reduce((x, r) => x + r.trust_score, 0) / tr.length) : 0)
        setLocs((l as MapLoc[]) ?? [])
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const indiaPath = useMemo(
    () => `M${INDIA.map(([lon, lat]) => proj(lon, lat).map((n) => n.toFixed(1)).join(',')).join('L')}Z`,
    [],
  )

  const stormPath = useMemo(() => {
    if (storm.length < 2) return ''
    return `M${storm.map((p) => proj(p.lon, p.lat).map((n) => n.toFixed(1)).join(',')).join('L')}`
  }, [storm])

  const ranked = useMemo(
    () => [...advisory].sort((p, q) => q.risk_index - p.risk_index),
    [advisory],
  )

  const counts = useMemo(() => ({
    danger: advisory.filter((r) => r.status === 'danger').length,
    caution: advisory.filter((r) => r.status === 'caution').length,
    safe: advisory.filter((r) => r.status === 'safe').length,
  }), [advisory])

  const eye = storm[storm.length - 1]

  return (
    <div className="page risk-page animate-in">
      <div className="page-header risk-header">
        <div>
          <h1 className="page-title title-glow">
            National <span className="text-gradient">Risk Map</span>
          </h1>
          <p className="page-subtitle">
            One-screen situational view of every monitored Indian coast — risk, storms and model confidence at a glance.
          </p>
        </div>
        <div className="risk-count glass-card">
          <Map size={16} />
          <span>{loading ? '…' : advisory.length} COASTS TRACKED</span>
        </div>
      </div>

      {/* ---- Quick stats ---- */}
      <div className="stats-grid risk-stats">
        <StatChip icon={<ShieldAlert size={20} />} label="Danger" value={counts.danger} color="#f43f5e" i={0} />
        <StatChip icon={<Shield size={20} />} label="Caution" value={counts.caution} color="#f59e0b" i={1} />
        <StatChip icon={<ShieldCheck size={20} />} label="Safe" value={counts.safe} color="#34d399" i={2} />
        <StatChip icon={<Wind size={20} />} label="Storm Wind" value={eye ? `${eye.wind_kmh} km/h` : '—'} color="#fb7185" i={3} />
      </div>

      <div className="risk-layout">
        {/* ---- Map ---- */}
        <motion.div className="glass-card risk-map-panel" variants={fadeUp} initial="hidden" animate="show" custom={0}>
          <div className="panel-header">
            <h3>Coastal Command View</h3>
            <span className="panel-badge"><Crosshair size={12} /> INDIA · EEZ</span>
          </div>

          <svg viewBox={`0 0 ${W} ${H}`} className="risk-svg" role="img" aria-label="India national risk map">
            {/* faint graticule */}
            {[14, 22, 30].map((lat) => {
              const [, y] = proj(74, lat)
              return <line key={lat} x1={M} y1={y} x2={W - M} y2={y} className="graticule" />
            })}
            {[70, 78, 86, 94].map((lon) => {
              const [x] = proj(lon, 30)
              return <line key={lon} x1={x} y1={M} x2={x} y2={H - M} className="graticule" />
            })}

            {/* India silhouette */}
            <path d={indiaPath} fill="rgba(34,211,238,0.06)" stroke="rgba(120,190,255,0.55)" strokeWidth={1.6} />

            {/* storm track */}
            {stormPath && (
              <>
                <path d={stormPath} fill="none" stroke="#f43f5e" strokeWidth={2.4} strokeDasharray="7 6" />
                {storm.filter((_, i) => i % 4 === 0).map((p, i) => {
                  const [x, y] = proj(p.lon, p.lat)
                  return <circle key={`${p.hour}-${i}`} cx={x} cy={y} r={3.4} fill="#f43f5e" opacity={0.7} />
                })}
              </>
            )}

            {/* coastal markers colored by risk band */}
            {advisory.map((r) => {
              const loc = locs.find((l) => l.id === r.location_id)
              if (!loc || loc.latitude == null || loc.longitude == null) return null
              const [x, y] = proj(loc.longitude, loc.latitude)
              const color = STATUS_META[r.status].color
              return (
                <g key={r.location_id}>
                  <circle cx={x} cy={y} r={13} fill={color} opacity={0.18} className="marker-pulse" />
                  <circle cx={x} cy={y} r={5.5} fill={color} stroke="#04121f" strokeWidth={1.6} />
                </g>
              )
            })}

            {/* storm eye */}
            {eye && (
              <g>
                <circle cx={proj(eye.lon, eye.lat)[0]} cy={proj(eye.lon, eye.lat)[1]} r={16} fill="rgba(244,63,94,0.2)" className="marker-pulse" />
                <circle cx={proj(eye.lon, eye.lat)[0]} cy={proj(eye.lon, eye.lat)[1]} r={7} fill="#fb7185" stroke="#fff" strokeWidth={1.5} />
              </g>
            )}
          </svg>

          <div className="risk-legend">
            <span><i style={{ background: '#34d399' }} /> SAFE</span>
            <span><i style={{ background: '#f59e0b' }} /> CAUTION</span>
            <span><i style={{ background: '#f43f5e' }} /> DANGER</span>
            <span className="legend-line"><i className="dash" /> STORM TRACK</span>
            <span className="legend-eye"><i /> STORM EYE</span>
          </div>
        </motion.div>

        {/* ---- Right rail ---- */}
        <div className="risk-rail">
          <motion.div className="glass-card panel" variants={fadeUp} initial="hidden" animate="show" custom={1}>
            <div className="panel-header">
              <h3>Threat Ranking</h3>
              <span className="panel-badge"><TrendingUp size={12} /> TOP RISK</span>
            </div>
            <div className="risk-list">
              {loading && <div className="hint">Loading…</div>}
              {ranked.slice(0, 7).map((r, i) => {
                const color = STATUS_META[r.status].color
                return (
                  <div key={r.location_id} className="risk-row">
                    <span className="risk-rank">#{i + 1}</span>
                    <div className="risk-row-body">
                      <div className="risk-row-top">
                        <span className="risk-row-name">{r.location.split(' (')[0]}</span>
                        <span className="risk-row-score" style={{ color }}>{r.risk_index}</span>
                      </div>
                      <div className="risk-bar">
                        <div className="risk-bar-fill" style={{ width: `${Math.max(4, r.risk_index)}%`, background: color }} />
                      </div>
                      <div className="risk-row-meta">
                        <span>window {r.safe_window}</span>
                        <span>SST {r.latest_temperature?.toFixed(1) ?? '—'}°C · wave {r.wave_height?.toFixed(1) ?? '—'} m</span>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </motion.div>

          <motion.div className="glass-card panel risk-trust" variants={fadeUp} initial="hidden" animate="show" custom={2}>
            <div className="panel-header">
              <h3>Fleet Model Confidence</h3>
            </div>
            <div className="trust-ring" style={{ '--pct': `${trust}%` } as React.CSSProperties}>
              <span className="trust-ring-value">{trust}%</span>
              <span className="trust-ring-label">avg trust</span>
            </div>
            <p className="hint-center">
              {stormName ? `${stormName} is being watched over the Bay of Bengal.` : ''} All advisories stream live to coastal
              command centers and fishing beacons.
            </p>
          </motion.div>
        </div>
      </div>
    </div>
  )
}

function StatChip({ icon, label, value, color, i }: {
  icon: React.ReactNode; label: string; value: number | string; color: string; i: number
}) {
  return (
    <motion.div className="glass-card stat-card" variants={fadeUp} initial="hidden" animate="show" custom={i}>
      <div className="stat-icon" style={{ color, background: `${color}1c`, borderColor: `${color}40` }}>
        {icon}
      </div>
      <div className="stat-body">
        <span className="stat-label">{label}</span>
        <span className="stat-value" style={{ color }}>{value}</span>
      </div>
    </motion.div>
  )
}