import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import {
  Search, MapPin, Fingerprint, GitCompareArrows, Clock,
  AlertTriangle, ChevronDown, ChevronUp, FileText, Shield,
  Crosshair, Waves, Thermometer, Dna, Target, Scan,
} from 'lucide-react'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, ReferenceLine,
} from 'recharts'
import {
  fetchLocations, fetchEvents, investigateEvent,
  fetchFingerprint, fetchSimilar, fetchTimeline, fetchAutopsy,
} from '../api/client'
import './Forensics.css'

interface Region {
  id: number
  name: string
  latitude: number | null
  longitude: number | null
}

interface OceanEvent {
  location_id: number
  location: string
  event_type: string
  label: string
  icon: string
  intensity: 'high' | 'medium' | 'low'
  confidence: number
  variable: string
  value: number | null
  status: string
  began_hours_ago?: number
  evolution?: string
}

interface ContributingFactor {
  factor: string
  contribution: number
  evidence: string
  confidence: number
}

interface Investigation {
  location: string
  location_id: number
  what_happened: string
  change: string
  contributing_factors: ContributingFactor[]
  depth_range: string
  started_at: string
  investigation_confidence: number
}

interface FingerprintData {
  temp_anomaly: number
  salinity: number
  oxygen: number
  chlorophyll: number
  nutrients: number
  wave_height: number
  current_speed: number
  duration_h: number
  peak_intensity: number
}

interface SimilarEvent {
  location: string
  similarity: number
  match_label: string
}

interface TimelinePoint {
  time: string
  temp: number | null
  wave: number | null
  event: string | null
  event_type: string | null
}

interface AutopsyReport {
  title: string
  generated_at: string
  location: string
  location_id: number
  what_happened: string
  timeline_summary: string
  contributing_factors: ContributingFactor[]
  evidence: string[]
  uncertainty: string
  similar_events: { location: string; similarity: number; match_label: string }[]
  ecosystem_risk: string
  recommendations: string[]
  executive_summary: string
}

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: (i: number) => ({
    opacity: 1, y: 0,
    transition: { delay: i * 0.07, duration: 0.5, ease: 'easeOut' as const },
  }),
}

const FINGERPRINT_DIMS: { key: keyof Omit<FingerprintData, 'duration_h' | 'peak_intensity'>; label: string; icon: React.ReactNode; color: string }[] = [
  { key: 'temp_anomaly', label: 'Temperature', icon: <Thermometer size={13} />, color: '#f43f5e' },
  { key: 'salinity', label: 'Salinity', icon: <Waves size={13} />, color: '#06b6d4' },
  { key: 'oxygen', label: 'Oxygen', icon: <Dna size={13} />, color: '#10b981' },
  { key: 'chlorophyll', label: 'Chlorophyll', icon: <Target size={13} />, color: '#22c55e' },
  { key: 'nutrients', label: 'Nutrients', icon: <Scan size={13} />, color: '#f59e0b' },
  { key: 'wave_height', label: 'Waves', icon: <Waves size={13} />, color: '#8b5cf6' },
  { key: 'current_speed', label: 'Current', icon: <GitCompareArrows size={13} />, color: '#ec4899' },
]

const INTENSITY_COLOR: Record<string, string> = {
  high: '#f43f5e',
  medium: '#f59e0b',
  low: '#10b981',
}

export default function Forensics() {
  const [locs, setLocs] = useState<Region[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [events, setEvents] = useState<OceanEvent[]>([])
  const [selectedEventIdx, setSelectedEventIdx] = useState<number | null>(null)
  const [investigation, setInvestigation] = useState<Investigation | null>(null)
  const [fingerprint, setFingerprint] = useState<FingerprintData | null>(null)
  const [similar, setSimilar] = useState<SimilarEvent[]>([])
  const [timeline, setTimeline] = useState<TimelinePoint[]>([])
  const [autopsy, setAutopsy] = useState<AutopsyReport | null>(null)
  const [autopsyOpen, setAutopsyOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const [panelLoading, setPanelLoading] = useState(false)

  useEffect(() => {
    fetchLocations()
      .then((data) => {
        setLocs(data)
        setSelectedId(data[0]?.id ?? null)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (selectedId == null) return
    setPanelLoading(true)
    setSelectedEventIdx(null)
    setInvestigation(null)
    setFingerprint(null)
    setSimilar([])
    setAutopsy(null)
    setAutopsyOpen(false)

    Promise.all([
      fetchEvents().catch(() => ({ events: [] as OceanEvent[] })),
      fetchTimeline(selectedId).catch(() => ({ timeline: [] as TimelinePoint[] })),
      investigateEvent(selectedId).catch(() => null),
      fetchAutopsy(selectedId).catch(() => null),
    ])
      .then(([evRes, tlRes, inv, aut]) => {
        const allEvents = (evRes.events ?? evRes) as OceanEvent[]
        const local = allEvents.filter((e) => e.location_id === selectedId)
        const rest = allEvents.filter((e) => e.location_id !== selectedId)
        setEvents([...local, ...rest])
        setTimeline(tlRes.timeline ?? [])
        setInvestigation(inv)
        setAutopsy(aut)
      })
      .catch(() => {})
      .finally(() => setPanelLoading(false))
  }, [selectedId])

  const loadEventDetail = (idx: number) => {
    if (idx === selectedEventIdx) {
      setSelectedEventIdx(null)
      setFingerprint(null)
      setSimilar([])
      return
    }
    setSelectedEventIdx(idx)
    setFingerprint(null)
    setSimilar([])
    Promise.all([
      fetchFingerprint(idx).catch(() => null),
      fetchSimilar(idx).catch(() => null),
    ])
      .then(([fp, sim]) => {
        setFingerprint(fp)
        if (sim) {
          setSimilar(sim.similar ?? [])
        }
      })
      .catch(() => {})
  }

  const localEvents = useMemo(
    () => events.filter((e) => e.location_id === selectedId),
    [events, selectedId],
  )
  const otherEvents = useMemo(
    () => events.filter((e) => e.location_id !== selectedId),
    [events, selectedId],
  )

  const chartData = useMemo(() =>
    timeline.map((p) => ({
      time: new Date(p.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      temp: p.temp,
      wave: p.wave,
      event: p.event,
      event_type: p.event_type,
    })),
    [timeline],
  )

  const selectedLoc = useMemo(() => locs.find((l) => l.id === selectedId) ?? null, [locs, selectedId])

  return (
    <div className="page forensics-page animate-in">
      <div className="page-header forensics-header">
        <div>
          <h1 className="page-title title-glow">
            Ocean <span className="text-gradient">Forensics</span>
          </h1>
          <p className="page-subtitle">
            Post-event Investigation &amp; Root Cause Analysis
          </p>
        </div>
        <div className="forensics-badge glass-card">
          <Search size={16} />
          <span>{loading ? '...' : 'INVESTIGATION LAB'}</span>
        </div>
      </div>

      <div className="forensics-location-bar">
        <div className="forensics-location-label">
          <MapPin size={14} />
          <span>Select Location</span>
        </div>
        <select
          className="forensics-select"
          value={selectedId ?? ''}
          onChange={(e) => setSelectedId(Number(e.target.value) || null)}
        >
          {locs.map((loc) => (
            <option key={loc.id} value={loc.id}>{loc.name}</option>
          ))}
        </select>
      </div>

      {!selectedLoc && !loading && (
        <motion.div className="glass-card panel forensics-empty" variants={fadeUp} initial="hidden" animate="show" custom={0}>
          <Search size={40} className="forensics-empty-icon" />
          <h3>Select a Location</h3>
          <p>Choose a coastal region to begin forensic investigation of ocean events.</p>
        </motion.div>
      )}

      {loading && (
        <div className="forensics-grid">
          <div className="glass-card panel">
            <div className="skel skel-title" />
            <div className="skel skel-block" />
            <div className="skel skel-block" />
          </div>
          <div className="glass-card panel">
            <div className="skel skel-title" />
            <div className="skel skel-block" />
          </div>
        </div>
      )}

      {selectedLoc && !loading && (
        <div className="forensics-grid">
          <div className="forensics-left">
            <motion.div className="glass-card panel forensics-events-panel" variants={fadeUp} initial="hidden" animate="show" custom={0}>
              <div className="panel-header">
                <h3><AlertTriangle size={14} /> Detected Events</h3>
                <span className="panel-badge">
                  <Crosshair size={12} /> {localEvents.length} LOCAL
                </span>
              </div>
              {events.length === 0 ? (
                <div className="hint">
                  {panelLoading ? 'Scanning for events...' : 'No active ocean events detected.'}
                </div>
              ) : (
                <div className="forensics-event-list">
                  {[...localEvents, ...otherEvents].map((ev, i) => {
                    const globalIdx = events.indexOf(ev)
                    const isSelected = selectedEventIdx === globalIdx
                    const isLocal = ev.location_id === selectedId
                    return (
                      <motion.div
                        key={`${ev.location_id}-${ev.event_type}`}
                        className={`event-card ${isSelected ? 'event-card-selected' : ''} ${!isLocal ? 'event-card-other' : ''}`}
                        variants={fadeUp}
                        initial="hidden"
                        animate="show"
                        custom={i}
                        onClick={() => loadEventDetail(globalIdx)}
                      >
                        <div className="event-top-row">
                          <span className="event-icon">{ev.icon}</span>
                          <b className="event-label">{ev.label}</b>
                          <span
                            className="event-badge"
                            style={{ background: `${INTENSITY_COLOR[ev.intensity]}18`, color: INTENSITY_COLOR[ev.intensity] }}
                          >
                            {ev.intensity.toUpperCase()}
                          </span>
                        </div>
                        <div className="event-meta">
                          <span className="event-location-name">
                            <MapPin size={11} /> {ev.location}
                          </span>
                          <span className="event-confidence">
                            <Shield size={11} /> {ev.confidence}%
                          </span>
                        </div>
                        {ev.evolution && isLocal && (
                          <div className="event-evolution">{ev.evolution}</div>
                        )}
                      </motion.div>
                    )
                  })}
                </div>
              )}
            </motion.div>
          </div>

          <div className="forensics-right">
            {investigation && (
              <motion.div className="glass-card panel forensics-investigation" variants={fadeUp} initial="hidden" animate="show" custom={1}>
                <div className="panel-header">
                  <h3><Scan size={14} /> Investigation</h3>
                  <span className="panel-badge">
                    <Shield size={12} /> {investigation.investigation_confidence}% CONF
                  </span>
                </div>
                <div className="investigation-headline">{investigation.what_happened}</div>
                <div className="investigation-change">{investigation.change}</div>
                {investigation.depth_range && (
                  <div className="investigation-meta">
                    <span>Depth: {investigation.depth_range}</span>
                    {investigation.started_at && (
                      <span>Started: {new Date(investigation.started_at).toLocaleString()}</span>
                    )}
                  </div>
                )}
                <div className="factors-section">
                  <div className="factors-title">Contributing Factors</div>
                  {investigation.contributing_factors.map((f) => (
                    <div key={f.factor} className="factor-row">
                      <div className="factor-info">
                        <span className="factor-name">{f.factor}</span>
                        <span className="factor-evidence">{f.evidence}</span>
                      </div>
                      <div className="factor-bar-wrap">
                        <div className="factor-bar">
                          <div
                            className="factor-bar-fill"
                            style={{ width: `${f.contribution}%` }}
                          />
                        </div>
                        <div className="factor-bar-labels">
                          <span className="factor-conf">CONF {f.confidence}%</span>
                          <span className="factor-pct">{f.contribution}%</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}

            {fingerprint && (
              <motion.div className="glass-card panel forensics-fingerprint" variants={fadeUp} initial="hidden" animate="show" custom={2}>
                <div className="panel-header">
                  <h3><Fingerprint size={14} /> Ocean Fingerprint</h3>
                  <span className="panel-badge">
                    <Dna size={12} /> 7-DIM SIGNATURE
                  </span>
                </div>
                <div className="fingerprint-grid">
                  {FINGERPRINT_DIMS.map((dim) => {
                    const val = fingerprint[dim.key]
                    const maxVal = Math.max(
                      fingerprint.temp_anomaly, fingerprint.salinity, fingerprint.oxygen,
                      fingerprint.chlorophyll, fingerprint.nutrients, fingerprint.wave_height,
                      fingerprint.current_speed, 1,
                    )
                    const pct = Math.min(100, (val / maxVal) * 100)
                    return (
                      <div key={dim.key} className="fingerprint-dim">
                        <div className="dim-header">
                          <span className="dim-icon" style={{ color: dim.color }}>{dim.icon}</span>
                          <span className="dim-label">{dim.label}</span>
                          <span className="dim-value">{val.toFixed(2)}</span>
                        </div>
                        <div className="dim-bar">
                          <div
                            className="dim-bar-fill"
                            style={{ width: `${pct}%`, background: `linear-gradient(90deg, ${dim.color}44, ${dim.color})` }}
                          />
                        </div>
                      </div>
                    )
                  })}
                </div>
                <div className="fingerprint-stats">
                  <div className="fp-stat">
                    <span>Duration</span>
                    <b>{fingerprint.duration_h}h</b>
                  </div>
                  <div className="fp-stat">
                    <span>Peak Intensity</span>
                    <b>{fingerprint.peak_intensity.toFixed(2)}</b>
                  </div>
                </div>
              </motion.div>
            )}

            {similar.length > 0 && (
              <motion.div className="glass-card panel forensics-similar" variants={fadeUp} initial="hidden" animate="show" custom={3}>
                <div className="panel-header">
                  <h3><GitCompareArrows size={14} /> Similar Events</h3>
                  <span className="panel-badge">
                    <Scan size={12} /> COSINE MATCH
                  </span>
                </div>
                <div className="similar-list">
                  {similar.map((s, i) => (
                    <div key={`${s.location}-${i}`} className="similar-row">
                      <div className="similar-info">
                        <span className="similar-location">{s.location}</span>
                        <span className="similar-label">{s.match_label}</span>
                      </div>
                      <div className="similar-similarity">
                        <div className="similar-bar">
                          <div
                            className="similar-bar-fill"
                            style={{ width: `${s.similarity * 100}%` }}
                          />
                        </div>
                        <span className="similar-pct">{(s.similarity * 100).toFixed(1)}%</span>
                      </div>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}

            {chartData.length > 0 && (
              <motion.div className="glass-card panel forensics-timeline" variants={fadeUp} initial="hidden" animate="show" custom={4}>
                <div className="panel-header">
                  <h3><Clock size={14} /> Timeline</h3>
                  <span className="panel-badge">
                    <Waves size={12} /> TEMP + WAVE
                  </span>
                </div>
                <div className="timeline-chart">
                  <ResponsiveContainer width="100%" height={220}>
                    <AreaChart data={chartData} margin={{ top: 6, right: 12, bottom: 0, left: -14 }}>
                      <defs>
                        <linearGradient id="gradTemp" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.35} />
                          <stop offset="95%" stopColor="#f43f5e" stopOpacity={0} />
                        </linearGradient>
                        <linearGradient id="gradWave" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.35} />
                          <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke="rgba(148,163,184,0.12)" vertical={false} />
                      <XAxis dataKey="time" tick={{ fill: '#5b7493', fontSize: 10 }} tickLine={false} axisLine={false} minTickGap={40} />
                      <YAxis tick={{ fill: '#5b7493', fontSize: 10 }} tickLine={false} axisLine={false} width={44} />
                      <Tooltip
                        contentStyle={{
                          background: 'rgba(6,18,40,0.92)',
                          border: '1px solid rgba(34,211,238,0.3)',
                          borderRadius: 12,
                          color: '#e6f1ff',
                          fontSize: 12,
                        }}
                      />
                      {chartData.map((p, i) =>
                        p.event ? (
                          <ReferenceLine
                            key={i}
                            x={p.time}
                            stroke={p.event_type === 'high' ? '#f43f5e' : '#f59e0b'}
                            strokeDasharray="4 4"
                            label={{ value: p.event, position: 'top', fill: '#a8bcd8', fontSize: 9 }}
                          />
                        ) : null,
                      )}
                      <Area type="monotone" dataKey="temp" name="Temperature" stroke="#f43f5e" fill="url(#gradTemp)" strokeWidth={2} dot={false} />
                      <Area type="monotone" dataKey="wave" name="Wave Height" stroke="#06b6d4" fill="url(#gradWave)" strokeWidth={2} dot={false} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </motion.div>
            )}

            {autopsy && (
              <motion.div className="glass-card panel forensics-autopsy" variants={fadeUp} initial="hidden" animate="show" custom={5}>
                <div className="panel-header forensics-autopsy-header" onClick={() => setAutopsyOpen(!autopsyOpen)}>
                  <h3><FileText size={14} /> Full Autopsy Report</h3>
                  <span className="panel-badge">
                    <FileText size={12} /> {autopsyOpen ? 'COLLAPSE' : 'EXPAND'}
                    {autopsyOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                  </span>
                </div>
                {autopsyOpen && (
                  <div className="autopsy-body">
                    {autopsy.executive_summary && (
                      <div className="autopsy-section">
                        <h4>Executive Summary</h4>
                        <p>{autopsy.executive_summary}</p>
                      </div>
                    )}

                    <div className="autopsy-section">
                      <h4>What Happened</h4>
                      <p>{autopsy.what_happened}</p>
                    </div>

                    {autopsy.timeline_summary && (
                      <div className="autopsy-section">
                        <h4>Timeline Summary</h4>
                        <p>{autopsy.timeline_summary}</p>
                      </div>
                    )}

                    {autopsy.contributing_factors.length > 0 && (
                      <div className="autopsy-section">
                        <h4>Contributing Factors</h4>
                        <div className="autopsy-factors">
                          {autopsy.contributing_factors.map((f) => (
                            <div key={f.factor} className="autopsy-factor-card">
                              <div className="autopsy-factor-top">
                                <span className="autopsy-factor-name">{f.factor}</span>
                                <span className="autopsy-factor-conf">{f.confidence}%</span>
                              </div>
                              <div className="factor-bar">
                                <div className="factor-bar-fill" style={{ width: `${f.contribution}%` }} />
                              </div>
                              <p className="autopsy-factor-evidence">{f.evidence}</p>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {autopsy.evidence.length > 0 && (
                      <div className="autopsy-section">
                        <h4>Evidence</h4>
                        <ul className="autopsy-list">
                          {autopsy.evidence.map((ev, i) => <li key={i}>{ev}</li>)}
                        </ul>
                      </div>
                    )}

                    {autopsy.similar_events.length > 0 && (
                      <div className="autopsy-section">
                        <h4>Similar Historical Events</h4>
                        <div className="autopsy-similar">
                          {autopsy.similar_events.map((s, i) => (
                            <div key={i} className="autopsy-similar-chip">
                              <span>{s.location}</span>
                              <b>{(s.similarity * 100).toFixed(0)}%</b>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {autopsy.ecosystem_risk && (
                      <div className="autopsy-section autopsy-risk">
                        <h4>Ecosystem Risk</h4>
                        <p>{autopsy.ecosystem_risk}</p>
                      </div>
                    )}

                    {autopsy.uncertainty && (
                      <div className="autopsy-section autopsy-uncertainty">
                        <h4>Uncertainty</h4>
                        <p>{autopsy.uncertainty}</p>
                      </div>
                    )}

                    {autopsy.recommendations.length > 0 && (
                      <div className="autopsy-section">
                        <h4>Recommendations</h4>
                        <ul className="autopsy-list autopsy-recommendations">
                          {autopsy.recommendations.map((r, i) => <li key={i}>{r}</li>)}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </motion.div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
