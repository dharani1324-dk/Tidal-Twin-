import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Send, Bot, User, RotateCcw, Cpu, MapPin, Sparkles, BadgeCheck, ArrowRight, ListChecks,
} from 'lucide-react'
import { askAssistant, fetchAssistantCapabilities } from '../api/client'
import './Assistant.css'

interface CardData {
  type: 'metrics' | 'table' | 'sparkline'
  items?: { label: string; value: string; color?: string }[]
  columns?: string[]
  rows?: string[][]
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
}

let msgId = 0

const DEFAULT_SUGGESTIONS = [
  'Is it safe to fish near Goa today?',
  'How confident are we in the model at Goa?',
  'Any marine heatwaves right now?',
  'Rank all coasts by risk today.',
  'What if wind increases by 30%?',
  'Where is the cyclone heading?',
]

export default function Assistant() {
  const [messages, setMessages] = useState<Message[]>([
    { id: ++msgId, role: 'assistant', text: "Hi, I'm **OceanVerse Copilot**. 🌊 I read the live ocean data and our AI engines to answer like a senior ocean analyst — and I remember context, so you can chain questions." },
  ])
  const [input, setInput] = useState('')
  const [typing, setTyping] = useState(false)
  const [thinking, setThinking] = useState<string>('')
  const [suggestions, setSuggestions] = useState<string[]>(DEFAULT_SUGGESTIONS)
  const [caps, setCaps] = useState<Capability[]>([])
  const contextRef = useRef<Record<string, unknown>>({})
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetchAssistantCapabilities().then((d) => setCaps(d.capabilities ?? [])).catch(() => {})
  }, [])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, typing, thinking])

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
    setSuggestions(DEFAULT_SUGGESTIONS)
    setMessages([{ id: ++msgId, role: 'assistant', text: "Fresh start. Ask me anything about India's coastal oceans 🌊" }])
  }

  return (
    <div className="page assistant-page animate-in">
      <div className="page-header">
        <div>
          <h1 className="page-title title-glow">
            Ocean <span className="text-gradient">AI Copilot</span>
          </h1>
          <p className="page-subtitle">
            A conversational ocean analyst — safety, events, risk, model validation, forecasts and what-if scenarios, all from live data.
          </p>
        </div>
        <button className="btn-ghost reset-btn" onClick={reset} title="New conversation">
          <RotateCcw size={14} /> New conversation
        </button>
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
                  <div key={c.key} className="cap-chip">
                    <b>{c.label}</b>
                    <span>{c.desc}</span>
                  </div>
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

        <div className="suggestion-row">
          {suggestions.slice(0, 4).map((s) => (
            <button key={s} className="suggestion-chip" onClick={() => send(s)} disabled={typing}>
              <ArrowRight size={12} /> {s}
            </button>
          ))}
        </div>

        <div className="chat-input-row">
          <input
            className="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send(input)}
            placeholder="Ask the copilot… e.g. 'Is it safe to fish near Puri today?'"
          />
          <motion.button
            className="btn-primary send-btn"
            onClick={() => send(input)}
            whileTap={{ scale: 0.95 }}
            disabled={typing || !input.trim()}
          >
            <Send size={17} />
          </motion.button>
        </div>
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
    return (
      <table className="data-table">
        <thead>
          <tr>{data.columns.map((c) => <th key={c}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {(data.rows ?? []).map((r, i) => (
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