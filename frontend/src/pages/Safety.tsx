import { useEffect, useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ShieldAlert, ShieldCheck, Shield, BellRing, Volume2, Share2,
  Smartphone, MapPin, Clock, Languages, CheckCircle2, AlertTriangle, Wind,
} from 'lucide-react'
import {
  Area, AreaChart, ResponsiveContainer, Tooltip,
} from 'recharts'
import { fetchSafetyAdvisory, fetchModelTrust } from '../api/client'
import './Safety.css'

interface AdvisoryRegion {
  location_id: number
  location: string
  status: 'safe' | 'caution' | 'danger'
  risk_index: number
  band: string
  safe_window: string
  latest_temperature: number | null
  temperature_anomaly: number
  wave_height: number | null
  active_alerts: number
  headline: string
  message: string
}

interface TrustRegion {
  location_id: number
  location: string
  trust_score: number
  mean_mae: number
  drift: boolean
  series: { time: string; mae: number }[]
}

const STATUS_META = {
  safe: { color: '#34d399', label: 'SAFE', Icon: ShieldCheck },
  caution: { color: '#f59e0b', label: 'CAUTION', Icon: Shield },
  danger: { color: '#f43f5e', label: 'DANGER', Icon: ShieldAlert },
}

const LANGS = [
  { code: 'en-IN', label: 'English (India)' },
  { code: 'hi-IN', label: 'हिन्दी' },
  { code: 'ta-IN', label: 'தமிழ்' },
  { code: 'mr-IN', label: 'मराठी' },
  { code: 'bn-IN', label: 'বাংলা' },
  { code: 'te-IN', label: 'తెలుగు' },
]

const GREET: Record<string, string> = {
  'en-IN': 'Coastal safety bulletin.',
  'hi-IN': 'सागर सुरक्षा बुलेटिन।',
  'ta-IN': 'கடலோர பாதுகாப்பு செய்தி.',
  'mr-IN': 'समुद्री सुरक्षा बुलेटिन.',
  'bn-IN': 'উপকূলীয় নিরাপত্তা বুলেটিন।',
  'te-IN': 'తీరప్రాంత భద్రతా బులెటిన్.',
}

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: (i: number) => ({
    opacity: 1, y: 0,
    transition: { delay: i * 0.07, duration: 0.5, ease: 'easeOut' as const },
  }),
}

interface LiveSnapshot {
  type: string
  t: string
  danger_zones: number
  caution_zones: number
  top_risk: { location: string; risk_index: number; status: string }[]
  trust_avg: number
  alerts: { id: number; location: string | null; severity: string; type: string; confidence: number | null; created_at: string | null }[]
  storm: { name: string; lat: number; lon: number; wind_kmh: number; headline: string } | null
}

export default function Safety() {
  const [advisory, setAdvisory] = useState<AdvisoryRegion[]>([])
  const [trust, setTrust] = useState<TrustRegion[]>([])
  const [loading, setLoading] = useState(true)
  const [phoneMsg, setPhoneMsg] = useState<AdvisoryRegion | null>(null)
  const [sent, setSent] = useState(false)
  const [lang, setLang] = useState('en-IN')
  const [speakingLoc, setSpeakingLoc] = useState<number | null>(null)
  const [copiedId, setCopiedId] = useState<number | null>(null)
  const [live, setLive] = useState<LiveSnapshot | null>(null)
  const [liveOn, setLiveOn] = useState(false)
  const [liveAlerts, setLiveAlerts] = useState<LiveSnapshot['alerts']>([])

  useEffect(() => {
    const base = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/^http/, 'ws')
    let ws: WebSocket | null = null
    let retry: number | undefined
    let alive = true

    const connect = () => {
      ws = new WebSocket(`${base}/api/v1/safety/ws/live`)
      ws.onopen = () => setLiveOn(true)
      ws.onmessage = (ev) => {
        try {
          const d = JSON.parse(ev.data)
          if (d.type === 'live') {
            setLive(d)
            setLiveAlerts((prev) => {
              const incoming = d.alerts ?? []
              if (incoming.length === 0) return prev
              return incoming.slice(0, 5)
            })
          }
        } catch {
          /* non-JSON keepalive */
        }
      }
      ws.onclose = () => {
        setLiveOn(false)
        if (alive) retry = window.setTimeout(connect, 4000)
      }
      ws.onerror = () => ws?.close()
    }
    connect()

    return () => {
      alive = false
      if (retry) window.clearTimeout(retry)
      ws?.close()
    }
  }, [])

  const load = async () => {
    setLoading(true)
    try {
      const [a, t] = await Promise.all([fetchSafetyAdvisory(), fetchModelTrust()])
      setAdvisory(a.regions ?? [])
      setTrust(t.regions ?? [])
    } catch {
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const stats = useMemo(() => {
    const danger = advisory.filter((a) => a.status === 'danger').length
    const caution = advisory.filter((a) => a.status === 'caution').length
    const safe = advisory.filter((a) => a.status === 'safe').length
    const avgTrust = trust.length
      ? Math.round(trust.reduce((s, t) => s + t.trust_score, 0) / trust.length)
      : 0
    return { danger, caution, safe, avgTrust }
  }, [advisory, trust])

  const simulateAlert = (r: AdvisoryRegion) => {
    setPhoneMsg(r)
    setSent(true)
    window.setTimeout(() => setSent(false), 3200)
  }

  const speak = (r: AdvisoryRegion) => {
    if (!('speechSynthesis' in window)) return
    window.speechSynthesis.cancel()
    const text = `${GREET[lang] ?? GREET['en-IN']} ${r.message} ${r.headline} Safe window, ${r.safe_window}.`
    const u = new SpeechSynthesisUtterance(text)
    u.lang = lang
    u.rate = 0.95
    const voices = window.speechSynthesis.getVoices()
    const voice =
      voices.find((v) => v.lang === lang) ??
      voices.find((v) => v.lang.startsWith(lang.split('-')[0]))
    if (voice) u.voice = voice
    u.onstart = () => setSpeakingLoc(r.location_id)
    u.onend = () => setSpeakingLoc(null)
    u.onerror = () => setSpeakingLoc(null)
    window.speechSynthesis.speak(u)
  }

  const share = async (r: AdvisoryRegion) => {
    const text =
      `⚓ COASTAL BULLETIN — ${r.location.toUpperCase()}\n` +
      `Status: ${STATUS_META[r.status].label} · Risk index ${r.risk_index}\n\n` +
      `SST ${r.latest_temperature?.toFixed(1) ?? '—'}°C (Δ${r.temperature_anomaly > 0 ? '+' : ''}${r.temperature_anomaly.toFixed(2)}°C) · ` +
      `Wave ${r.wave_height?.toFixed(1) ?? '—'} m\n` +
      `Safe window: ${r.safe_window}\n\n` +
      `${r.headline}\n\n— OceanVerse AI · fisherman safety`
    try {
      if (navigator.share) {
        await navigator.share({ title: 'Coastal Safety Bulletin', text })
      } else {
        await navigator.clipboard.writeText(text)
        setCopiedId(r.location_id)
        window.setTimeout(() => setCopiedId(null), 2000)
      }
    } catch {
      /* user cancelled */
    }
  }

  return (
    <div className="page safety-page animate-in">
      <div className="page-header safety-header">
        <div>
          <h1 className="page-title title-glow">
            Fishermen <span className="text-gradient">Safety Center</span>
          </h1>
          <p className="page-subtitle">
            One-tap coastal advisories for every fishing community — voice, SMS and multilingual by default.
          </p>
        </div>
        <div className="safety-header-actions">
          <div className="lang-picker glass-card">
            <Languages size={16} />
            <select value={lang} onChange={(e) => setLang(e.target.value)} aria-label="Bulletin language">
              {LANGS.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.label}
                </option>
              ))}
            </select>
          </div>
          <span className="live-pill">
            <span className="live-dot" /> BULLETINS LIVE
          </span>
        </div>
      </div>

      {/* ---- Live command feed (WebSocket push) ---- */}
      <motion.div
        className={`glass-card live-feed ${liveOn ? 'live-feed-on' : ''}`}
        variants={fadeUp}
        initial="hidden"
        animate="show"
        custom={0}
      >
        <div className="live-feed-head">
          <span className={`live-feed-dot ${liveOn ? '' : 'live-feed-dot-off'}`} />
          <span className="live-feed-title">LIVE COMMAND FEED</span>
          <span className="live-feed-ts">
            {live
              ? new Date(live.t).toLocaleTimeString('en-IN', {
                  timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true,
                })
              : 'connecting…'}
          </span>
        </div>
        {live && (
          <div className="live-feed-grid">
            <FeedStat label="Danger" value={live.danger_zones} color="#f43f5e" />
            <FeedStat label="Caution" value={live.caution_zones} color="#f59e0b" />
            <FeedStat label="Model Trust" value={`${live.trust_avg}%`} color="#22d3ee" />
            {live.storm && (
              <div className="feed-storm">
                <Wind size={14} />
                <span>
                  <b>{live.storm.name}</b> · {live.storm.lat.toFixed(1)}N, {live.storm.lon.toFixed(1)}E · <b>{live.storm.wind_kmh} km/h</b>
                </span>
              </div>
            )}
            <div className="feed-alerts">
              {liveAlerts.map((a) => (
                <span key={a.id} className="feed-alert">
                  <AlertTriangle size={11} /> {a.location} · {a.severity}
                </span>
              ))}
              {liveAlerts.length === 0 && <span className="feed-alert muted">No active alerts pushed</span>}
            </div>
          </div>
        )}
      </motion.div>

      {/* ---- Overview stats ---- */}
      <div className="stats-grid safety-stats">
        <AddCard color="#f43f5e" label="Danger Zones" value={stats.danger} icon={<ShieldAlert size={20} />} i={0} />
        <AddCard color="#f59e0b" label="Caution" value={stats.caution} icon={<Shield size={20} />} i={1} />
        <AddCard color="#34d399" label="Safe to Sail" value={stats.safe} icon={<ShieldCheck size={20} />} i={2} />
        <AddCard color="#22d3ee" label="Avg Model Trust" value={`${stats.avgTrust}%`} icon={<Wind size={20} />} i={3} />
      </div>

      {/* ---- Advisory grid ---- */}
      <div className="safety-layout">
        <div className="advisory-grid">
          {loading && <div className="hint">Loading advisories…</div>}
          {!loading && advisory.length === 0 && (
            <div className="hint">No advisories yet.</div>
          )}
          {advisory.map((r) => {
            const meta = STATUS_META[r.status]
            const Icon = meta.Icon
            return (
              <motion.div
                key={r.location_id}
                className="glass-card advisory-card"
                variants={fadeUp}
                initial="hidden"
                animate="show"
                custom={advisory.indexOf(r)}
              >
                <div className="advisory-top">
                  <div className="advisory-loc">
                    <MapPin size={14} />
                    <span>{r.location}</span>
                  </div>
                  <span className="status-pill" style={{ color: meta.color, borderColor: `${meta.color}55`, background: `${meta.color}1a` }}>
                    <Icon size={12} /> {meta.label}
                  </span>
                </div>

                <p className="advisory-headline">{r.headline}</p>

                <div className="advisory-metrics">
                  <Metric label="Risk Index" value={`${r.risk_index}`} />
                  <Metric label="SST" value={r.latest_temperature != null ? `${r.latest_temperature.toFixed(1)}°C` : '—'} />
                  <Metric label="Δ Anomaly" value={`${r.temperature_anomaly > 0 ? '+' : ''}${r.temperature_anomaly.toFixed(2)}°C`} tone={r.temperature_anomaly > 1 ? 'warn' : 'ok'} />
                  <Metric label="Wave" value={r.wave_height != null ? `${r.wave_height.toFixed(1)} m` : '—'} />
                </div>

                <div className="advisory-window">
                  <Clock size={13} />
                  <span>Safe window</span>
                  <b>{r.safe_window}</b>
                </div>

                <div className="advisory-actions">
                  <button className="a-btn a-btn-primary" onClick={() => simulateAlert(r)}>
                    <BellRing size={14} /> SMS Alert
                  </button>
                  <button
                    className={`a-btn ${speakingLoc === r.location_id ? 'a-btn-speaking' : 'a-btn-ghost'}`}
                    onClick={() => speak(r)}
                  >
                    <Volume2 size={14} /> {speakingLoc === r.location_id ? 'Playing…' : 'Voice'}
                  </button>
                  <button className="a-btn a-btn-ghost" onClick={() => share(r)}>
                    <Share2 size={14} /> {copiedId === r.location_id ? 'Copied!' : 'Share'}
                  </button>
                </div>
              </motion.div>
            )
          })}
        </div>

        {/* ---- Right rail: phone + trust ---- */}
        <div className="safety-rail">
          <motion.div className="glass-card phone-panel" variants={fadeUp} initial="hidden" animate="show" custom={4}>
            <div className="panel-header">
              <h3>SMS / WhatsApp Simulation</h3>
              <Smartphone size={15} className="phone-icon" />
            </div>
            <div className="phone-mock">
              <div className="phone-notch" />
              <div className="phone-appbar">
                <div className="phone-brand">
                  <span className="phone-avatar">OV</span>
                  <div>
                    <div className="phone-appname">OceanVerse AI</div>
                    <div className="phone-typing"><span className="live-dot" /> broadcasting</div>
                  </div>
                </div>
              </div>
              <div className="phone-body">
                <AnimatePresence mode="wait">
                  {phoneMsg ? (
                    <motion.div
                      key={phoneMsg.location_id}
                      initial={{ opacity: 0, y: 14, scale: 0.96 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0 }}
                      className="phone-bubble"
                    >
                      <div className="bubble-msg">{phoneMsg.message}</div>
                      <div className="bubble-meta">
                        <span>{new Date().toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', hour12: true })}</span>
                        <span className="bubble-tick">✓✓</span>
                      </div>
                    </motion.div>
                  ) : (
                    <div className="phone-placeholder">
                      <BellRing size={18} />
                      <span>Tap “SMS Alert” on any advisory to simulate a live push to a fishing beacon.</span>
                    </div>
                  )}
                </AnimatePresence>
              </div>
            </div>
            <AnimatePresence>
              {sent && (
                <motion.div
                  initial={{ opacity: 0, y: -6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="sent-tag"
                >
                  <CheckCircle2 size={13} /> Alert dispatched to 2,400 vessels <b>{phoneMsg?.location}</b>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>

          <motion.div className="glass-card panel trust-panel" variants={fadeUp} initial="hidden" animate="show" custom={5}>
            <div className="panel-header">
              <h3>Regional Model Trust</h3>
              <span className="panel-badge">MAE SPARKLINES</span>
            </div>
            <div className="trust-list">
              {trust.length === 0 && <div className="hint">Trust scores loading…</div>}
              {trust.map((t) => (
                <div key={t.location_id} className="trust-card">
                  <div className="trust-top">
                    <span className="trust-name">{t.location.split(' (')[0]}</span>
                    <span className="trust-score" style={{ color: t.trust_score > 50 ? '#34d399' : t.trust_score > 30 ? '#f59e0b' : '#f43f5e' }}>
                      {t.trust_score}%
                    </span>
                  </div>
                  <div className="trust-chart">
                    <ResponsiveContainer width="100%" height={52}>
                      <AreaChart data={t.series} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
                        <Area
                          type="monotone"
                          dataKey="mae"
                          stroke={t.drift ? '#f43f5e' : '#22d3ee'}
                          strokeWidth={2}
                          fill={t.drift ? '#f43f5e' : '#22d3ee'}
                          fillOpacity={0.18}
                          dot={false}
                          isAnimationActive={false}
                        />
                        <Tooltip contentStyle={{ background: '#06122a', border: '1px solid rgba(34,211,238,0.3)', fontSize: 11 }} formatter={(v) => [`${Number(v).toFixed(2)}°C`, 'MAE']} />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="trust-foot">
                    <span>rolling MAE {t.mean_mae.toFixed(2)}°C</span>
                    {t.drift && (
                      <span className="drift-tag"><AlertTriangle size={11} /> MODEL DRIFT</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  )
}

function AddCard({ icon, label, value, color, i }: {
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

function FeedStat({ label, value, color }: { label: string; value: number | string; color: string }) {
  return (
    <div className="feed-stat">
      <span className="feed-stat-label">{label}</span>
      <span className="feed-stat-value" style={{ color }}>{value}</span>
    </div>
  )
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: 'warn' | 'ok' }) {
  return (
    <div className="metric">
      <span className="metric-label">{label}</span>
      <span className={`metric-value ${tone === 'warn' ? 'metric-warn' : ''}`}>{value}</span>
    </div>
  )
}