import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Send, Bot, User, RotateCcw, Cpu, MapPin, Sparkles, BadgeCheck, ArrowRight, ListChecks,
  FileText, Radar, MessagesSquare,
} from 'lucide-react'
import { askAssistant, fetchAssistantCapabilities, askMultimodal } from '../api/client'
import './Assistant.css'

interface Chip { label: string; value: string | string[] }
interface ClaimRow {
  location: string
  variable: string
  claimed: number
  unit: string
  live: number | null
  verdict: 'supports' | 'disagrees' | 'unverifiable'
  note: string
}
interface CardData {
  type: 'metrics' | 'table' | 'sparkline' | 'chips'
  items?: { label: string; value: string; color?: string }[]
  columns?: string[]
  rows?: string[][] | ClaimRow[]
  chips?: Chip[]
  alerts?: { type: string; severity: string; description: string }[]
  events?: { type: string; label?: string; intensity?: string; confidence?: number }[]
  label?: string
  values?: number[]
}

interface AssayAnswer {
  answer: string
  intent: string
  location?: string | null
  location_id?: number | null
  data?: CardData | null
  suggestions?: string[]
  sources?: string[]
  steps?: string[]
  context?: { last_location_id?: number | null; last_intent?: string }
}

interface Message {
  id: number
  role: 'user' | 'assistant'
  text: string
  payload?: AssayAnswer
  thinking?: string[]
}

interface Capability {
  key: string
  label: string
  desc: string
  ask?: string
}

let msgId = 0

const DEFAULT_SUGGESTIONS = [
  'Give me the ocean intelligence brief.',
  'Is it safe to fish near Goa today?',
  'How confident are we in the model at Goa?',
  'Any marine heatwaves right now?',
  'Rank all coasts by risk today.',
  'What if wind increases by 30%?',
  'Where is the cyclone heading?',
  'Is TIDE scientifically validated?',
]

export default function Assistant({ embedded }: { embedded?: boolean } = {}) {
  const [messages, setMessages] = useState<Message[]>([
    { id: ++msgId, role: 'assistant', text: "Hi, I'm **TidalTwin Copilot**. 🌊 I read the live ocean data and our AI engines to answer like a senior ocean analyst — and I remember context, so you can chain questions." },
  ])
  const [input, setInput] = useState('')
  const [typing, setTyping] = useState(false)
  const [thinking, setThinking] = useState<string>('')
  const [suggestions, setSuggestions] = useState<string[]>(DEFAULT_SUGGESTIONS)
  const [caps, setCaps] = useState<Capability[]>([])
  const [mode, setMode] = useState<'chat' | 'multimodal'>('chat')
  const [docText, setDocText] = useState('')
  const [docType, setDocType] = useState('field')
  const [instrument, setInstrument] = useState('')
  const [memory, setMemory] = useState<string | null>(null)
  const contextRef = useRef<Record<string, unknown>>({})
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    fetchAssistantCapabilities().then((d) => setCaps(d.capabilities ?? [])).catch(() => {})
  }, [])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, typing, thinking])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        inputRef.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const send = async (text: string) => {
    const question = text.trim()
    if (!question || typing) return
    setInput('')
    setMessages((m) => [...m, { id: ++msgId, role: 'user', text: question }])
    setTyping(true)
    setThinking('Reading your question…')
    try {
      setThinking('Resolving intent & location…')
      const res: AssayAnswer = await askAssistant(question, contextRef.current)
      contextRef.current = res.context ?? {}
      setMemory(res.context?.last_intent ?? null)
      setSuggestions(res.suggestions?.length ? res.suggestions : DEFAULT_SUGGESTIONS)
      setMessages((m) => [
        ...m,
        { id: ++msgId, role: 'assistant', text: res.answer, payload: res },
      ])
    } catch (e: any) {
      setMessages((m) => [
        ...m,
        {
          id: ++msgId,
          role: 'assistant',
          text: `⚠️ I couldn't reach the ocean brain. Is the backend running? (${e.message})`,
        },
      ])
      setSuggestions(DEFAULT_SUGGESTIONS)
    } finally {
      setTyping(false)
      setThinking('')
    }
  }

  const reset = () => {
    contextRef.current = {}
    setMemory(null)
    setSuggestions(DEFAULT_SUGGESTIONS)
    setMessages([{ id: ++msgId, role: 'assistant', text: "Fresh start. Ask me anything about India's coastal oceans 🌊" }])
  }

  const clearMemory = () => {
    contextRef.current = {}
    setMemory(null)
  }

  /** Clicking a capability affordance card sends its question as a chat message. */
  const capClick = (cap: Capability) => {
    if (cap.key === 'multimodal') {
      setMode('multimodal')
      setTimeout(() => inputRef.current?.focus(), 50)
      return
    }
    send(cap.ask || `Tell me about ${cap.label}.`)
  }

  const sendMultimodal = async () => {
    const text = docText.trim()
    if (!text || typing) return
    setMessages((m) => [
      ...m,
      { id: ++msgId, role: 'user', text: `📄 Multimodal analysis · ${docType}${instrument ? ` · ${instrument}` : ''}\n${text}` },
    ])
    setDocText('')
    setTyping(true)
    setThinking('Parsing document, extracting claims…')
    try {
      setThinking('Cross-checking claims against live sensors…')
      const res: AssayAnswer = await askMultimodal(text, { type: docType, instrument: instrument || undefined })
      contextRef.current = res.context ?? {}
      setSuggestions(res.suggestions?.length ? res.suggestions : DEFAULT_SUGGESTIONS)
      setMessages((m) => [...m, { id: ++msgId, role: 'assistant', text: res.answer, payload: res }])
      setMode('chat')
    } catch (e: any) {
      setMessages((m) => [
        ...m,
        { id: ++msgId, role: 'assistant', text: `⚠️ Multimodal fusion failed. (${e.message})` },
      ])
    } finally {
      setTyping(false)
      setThinking('')
    }
  }

  return (
    <div className={`page assistant-page${embedded ? ' assistant-embedded' : ''} animate-in`}>
      <div className="page-header">
        {!embedded ? (
          <div>
            <h1 className="page-title title-glow">
              Ocean <span className="text-gradient">AI Copilot</span>
            </h1>
            <p className="page-subtitle">
              A conversational ocean analyst — safety, events, risk, model validation, forecasts and what-if scenarios, all from live data.
            </p>
          </div>
        ) : (
          <div className="assistant-embedded-title">
            <div className="msg-avatar bot"><Bot size={16} /></div>
            <div>
              <b>Ocean AI Copilot</b>
              <span>Live ocean analyst — safety, events, risk</span>
            </div>
          </div>
        )}
        <div className="assistant-header-actions">
          <div className="mode-switch">
            <button
              className={`mode-btn ${mode === 'chat' ? 'mode-btn-on' : ''}`}
              onClick={() => setMode('chat')}
            >
              <MessagesSquare size={14} /> Chat
            </button>
            <button
              className={`mode-btn ${mode === 'multimodal' ? 'mode-btn-on' : ''}`}
              onClick={() => setMode('multimodal')}
            >
              <Radar size={14} /> Multimodal
            </button>
          </div>
          <button className="btn-ghost reset-btn" onClick={reset} title="New conversation">
            <RotateCcw size={14} /> New
          </button>
        </div>
      </div>

      <div className="assistant-shell glass-card">
        <div className="chat-scroll" ref={scrollRef}>
          <AnimatePresence initial={false}>
            {messages.map((m) => (
              <motion.div
                key={m.id}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
                className={`msg-row ${m.role === 'user' ? 'msg-row-user' : 'msg-row-bot'}`}
              >
                {m.role === 'assistant' && (
                  <div className="msg-avatar bot"><Bot size={17} /></div>
                )}
                <div className={`msg-bubble ${m.role === 'user' ? 'msg-bubble-user' : 'msg-bubble-bot'}`}>
                  {m.role === 'assistant' && m.payload && m.payload.steps?.length ? (
                    <div className="msg-thinking">
                      <Cpu size={11} />
                      {m.payload.steps.map((s) => (
                        <span key={s}>{s}</span>
                      ))}
                    </div>
                  ) : null}
                  <div className="msg-text">{renderText(m.text)}</div>

                  {m.payload?.data && <CardView data={m.payload.data} />}

                  {m.role === 'assistant' && m.payload && (
                    <div className="msg-meta">
                      {m.payload.location && m.payload.intent && (
                        <span className="msg-tag">
                          <MapPin size={11} /> {m.payload.location} · {m.payload.intent}
                        </span>
                      )}
                      {!m.payload.location && m.payload.intent && (
                        <span className="msg-tag"><Sparkles size={11} /> {m.payload.intent}</span>
                      )}
                      {m.payload.sources?.length ? (
                        <span className="msg-src"><BadgeCheck size={11} /> {m.payload.sources.join(' · ')}</span>
                      ) : null}
                    </div>
                  )}
                </div>
                {m.role === 'user' && (
                  <div className="msg-avatar user"><User size={17} /></div>
                )}
              </motion.div>
            ))}
          </AnimatePresence>

          {/* capability affordance card on first message */}
          {caps.length > 0 && messages.length === 1 && (
            <div className="caps-card">
              <div className="caps-title"><ListChecks size={13} /> What I can do</div>
              <div className="caps-grid">
                {caps.map((c) => (
                  <button
                    key={c.key}
                    className="cap-chip"
                    onClick={() => capClick(c)}
                    disabled={typing}
                    title={`Ask: ${c.ask ?? c.label}`}
                  >
                    <b>{c.label} <ArrowRight size={11} className="cap-ask-arrow" /></b>
                    <span>{c.desc}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {typing && (
            <div className="msg-row msg-row-bot">
              <div className="msg-avatar bot"><Bot size={17} /></div>
              <div className="msg-bubble msg-bubble-bot">
                {thinking && <div className="msg-thinking"><Cpu size={11} /> {thinking}</div>}
                <span className="typing-dot" /><span className="typing-dot" /><span className="typing-dot" />
              </div>
            </div>
          )}
        </div>

        {mode === 'chat' && (
          <div className="suggestion-row">
            {suggestions.slice(0, 4).map((s) => (
              <button key={s} className="suggestion-chip" onClick={() => send(s)} disabled={typing}>
                <ArrowRight size={12} /> {s}
              </button>
            ))}
          </div>
        )}

        {mode === 'multimodal' && (
          <div className="multimodal-panel">
            <div className="multimodal-title">
              <FileText size={14} />
              Paste a field report / news snippet / NetCDF summary — I'll cross-check it against live ocean sensors.
            </div>
            <div className="multimodal-row">
              <select
                className="multimodal-select"
                value={docType}
                onChange={(e) => setDocType(e.target.value)}
              >
                <option value="field">Field survey report</option>
                <option value="news">News / situational report</option>
                <option value="satellite">Satellite metadata</option>
                <option value="netcdf">NetCDF summary</option>
                <option value="buoy">Buoy / mooring feed</option>
                <option value="document">Attached document</option>
              </select>
              <input
                className="multimodal-instr"
                value={instrument}
                onChange={(e) => setInstrument(e.target.value)}
                placeholder="Detector / instrument (optional)"
              />
            </div>
            <textarea
              className="multimodal-textarea"
              rows={5}
              value={docText}
              onChange={(e) => setDocText(e.target.value)}
              placeholder='e.g. "SST at Goa reached 30.2°C, chlorophyll surged to 4.5 mg/m3, oxygen dropped to 5.0 mg/L."'
            />
            <button
              className="btn-primary"
              disabled={typing || !docText.trim()}
              onClick={sendMultimodal}
            >
              <Radar size={14} /> Fuse with live sensors
            </button>
          </div>
        )}

        <div className="chat-input-row">
          <span className="prompt-mark">›</span>
          <input
            ref={inputRef}
            className="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send(input)}
            placeholder="Ask the copilot… e.g. 'Is it safe to fish near Puri today?'"
          />
          <kbd className="kbd-hint">⌘K</kbd>
          <motion.button
            className="btn-primary send-btn"
            onClick={() => send(input)}
            whileTap={{ scale: 0.95 }}
            disabled={typing || !input.trim()}
          >
            <Send size={17} />
          </motion.button>
        </div>
        {memory && (
          <div className="context-bar">
            <span className="context-dot" />
            Remembering <b>{memory}</b> — I reuse this for follow-ups
            <button className="context-clear" onClick={clearMemory}>Clear context</button>
          </div>
        )}
      </div>
    </div>
  )
}

/* ---- lightweight markdown-ish rendering ---- */
function inline(content: string): (string | React.ReactNode)[] {
  const nodes: (string | React.ReactNode)[] = []
  const parts = content.split(/(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`)/g)
  parts.forEach((p, i) => {
    if (!p) return
    if (p.startsWith('**') && p.endsWith('**')) {
      nodes.push(<strong key={i} className="msg-strong">{p.slice(2, -2)}</strong>)
    } else if (p.startsWith('`') && p.endsWith('`')) {
      nodes.push(<code key={i} className="msg-code">{p.slice(1, -1)}</code>)
    } else if (p.startsWith('*') && p.endsWith('*') && p.length > 2) {
      nodes.push(<em key={i} className="msg-em">{p.slice(1, -1)}</em>)
    } else {
      nodes.push(p)
    }
  })
  return nodes
}

function renderText(text: string) {
  return text.split('\n').map((line, i) => {
    const t = line.trim()
    const bullet = /^[-•]\s+/.test(t)
    const content = bullet ? t.replace(/^[-•]\s+/, '') : t
    if (!content) return <div key={i} className="msg-line" />
    return (
      <div key={i} className={`msg-line ${bullet ? 'msg-bullet' : ''}`}>
        {bullet && <span className="msg-dot">•</span>}
        {inline(content)}
      </div>
    )
  })
}

/* ---- structured data cards ---- */
function CardView({ data }: { data: CardData }) {
  if (data.type === 'chips' && data.chips?.length) {
    return <ChipView data={data} />
  }
  if (data.type === 'metrics' && data.items) {
    return (
      <div className="data-metrics">
        {data.items.map((it) => (
          <div key={it.label} className="data-metric">
            <span>{it.label}</span>
            <b style={{ color: it.color || 'inherit' }}>{it.value}</b>
          </div>
        ))}
      </div>
    )
  }
  if (data.type === 'table' && data.columns) {
    const rows = (data.rows ?? []) as string[][]
    return (
      <table className="data-table">
        <thead>
          <tr>{data.columns.map((c) => <th key={c}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>{r.map((cell, j) => <td key={j}>{cell}</td>)}</tr>
          ))}
        </tbody>
      </table>
    )
  }
  if (data.type === 'sparkline' && data.values) {
    return <Sparkline label={data.label ?? ''} values={data.values} />
  }
  return null
}

function ChipView({ data }: { data: CardData }) {
  const chips = data.chips ?? []
  const rows = (data.rows ?? []) as ClaimRow[]
  const alerts = data.alerts ?? []
  const events = data.events ?? []
  const verdictColor = (v: string) => v === 'supports' ? '#22c55e' : v === 'disagrees' ? '#ef4444' : '#94a3b8'

  return (
    <div className="data-chips">
      <div className="chip-row">
        {chips.map((c) => (
          <span key={c.label} className="chip-badge">
            <b>{c.label}</b>{' '}
            {Array.isArray(c.value) ? c.value.join(', ') : c.value}
          </span>
        ))}
      </div>
      {rows.length > 0 && (
        <table className="data-table claim-table">
          <thead><tr>
            <th>Coast</th><th>Variable</th><th>Claimed</th><th>Live</th><th>Verdict</th>
          </tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td>{r.location}</td>
                <td>{r.variable}</td>
                <td>{r.claimed} {r.unit}</td>
                <td>{r.live != null ? r.live : '—'}</td>
                <td style={{ color: verdictColor(r.verdict) }}>
                  {r.verdict === 'supports' ? '✓' : r.verdict === 'disagrees' ? '✗' : '?'}{' '}
                  {r.verdict.toUpperCase()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {alerts.length > 0 && (
        <div className="verdict-section">
          <b>Sensor alerts</b>
          {alerts.slice(0, 3).map((a, i) => (
            <div key={i} className="verdict-line alert-line">
              <span className="alert-sev" style={{ color: a.severity === 'high' ? '#f43f5e' : '#f59e0b' }}>
                {a.severity}
              </span>
              {a.type}
            </div>
          ))}
        </div>
      )}
      {events.length > 0 && (
        <div className="verdict-section">
          <b>Classified events</b>
          {events.slice(0, 3).map((e, i) => (
            <div key={i} className="verdict-line event-line">
              <span className="event-int" style={{ color: e.intensity === 'high' ? '#f43f5e' : '#22d3ee' }}>
                {e.intensity}
              </span>
              {e.label ?? e.type}
              <span className="conf-tag">{e.confidence}%</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function Sparkline({ label, values }: { label: string; values: number[] }) {
  const w = 260, h = 54
  const max = Math.max(...values), min = Math.min(...values)
  const span = max - min || 1
  const pts = values.map((v, i) => {
    const x = (i / Math.max(1, values.length - 1)) * w
    const y = h - 6 - ((v - min) / span) * (h - 14)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  const poly = pts.join(' ')
  return (
    <div className="data-spark">
      <span>{label}</span>
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
        <polyline points={poly} fill="none" stroke="#22d3ee" strokeWidth="2" strokeLinejoin="round" />
        <polygon points={`0,${h} ${poly} ${w},${h}`} fill="rgba(34,211,238,0.10)" />
      </svg>
      <b>{min.toFixed(1)} → {max.toFixed(1)}</b>
    </div>
  )
}