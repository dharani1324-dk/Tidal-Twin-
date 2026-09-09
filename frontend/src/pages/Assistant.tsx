import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Send, Sparkles, Bot, User, Waves, Radar, ShieldCheck, TrendingUp, GitCompare } from 'lucide-react'
import { askAssistant } from '../api/client'
import './Assistant.css'

interface Message {
  id: number
  role: 'user' | 'assistant'
  text: string
  intent?: string
}

const SUGGESTIONS = [
  { icon: <ShieldCheck size={14} />, text: 'Is it safe to sail near Goa?' },
  { icon: <Radar size={14} />, text: "What's the temperature at Mumbai coast now?" },
  { icon: <TrendingUp size={14} />, text: 'Is the sea warming up recently?' },
  { icon: <GitCompare size={14} />, text: 'Compare Chennai and Kochi conditions' },
  { icon: <Waves size={14} />, text: 'Which region has the largest waves?' },
]

let msgId = 0

export default function Assistant() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: ++msgId,
      role: 'assistant',
      text:
        "Hi, I'm the Ocean Intelligence Assistant. 🌊 Ask me anything about India's coastal waters — safety, temperature, waves, comparisons, and trends — all answered with real ocean data.",
    },
  ])
  const [input, setInput] = useState('')
  const [typing, setTyping] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, typing])

  const send = async (text: string) => {
    const question = text.trim()
    if (!question || typing) return
    setInput('')
    setMessages((m) => [...m, { id: ++msgId, role: 'user', text: question }])
    setTyping(true)
    try {
      const res = await askAssistant(question)
      setMessages((m) => [
        ...m,
        { id: ++msgId, role: 'assistant', text: res.answer, intent: res.intent },
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
    } finally {
      setTyping(false)
    }
  }

  // Render simple markdown-ish: **bold**, *italic*, line breaks
  const renderText = (text: string) => {
    const lines = text.split('\n')
    return lines.map((line, i) => {
      const bold = line.split('**').map((seg, j) =>
        j % 2 === 1 ? <strong key={j} className="msg-strong">{seg}</strong> : <span key={j}>{seg}</span>,
      )
      const italic = bold.map((node, k) => {
        if (typeof node === 'string' || node.type === 'span') {
          const s = node.props?.children as string
          if (s && s.includes('*')) {
            const parts = s.split('*')
            return (
              <span key={k}>
                {parts.map((p, pi) =>
                  pi % 2 === 1 ? <em key={pi} className="msg-em">{p}</em> : <span key={pi}>{p}</span>,
                )}
              </span>
            )
          }
        }
        return node
      })
      return <div key={i} className="msg-line">{italic}</div>
    })
  }

  return (
    <div className="page assistant-page animate-in">
      <div className="page-header">
        <h1 className="page-title title-glow">
          Ocean <span className="text-gradient">AI Assistant</span>
        </h1>
        <p className="page-subtitle">
          Natural language ocean intelligence — ask in plain English, get answers from real data.
        </p>
      </div>

      <div className="assistant-shell glass-card">
        {/* Chat window */}
        <div className="chat-scroll" ref={scrollRef}>
          <AnimatePresence initial={false}>
            {messages.map((m) => (
              <motion.div
                key={m.id}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.35 }}
                className={`msg-row ${m.role === 'user' ? 'msg-row-user' : 'msg-row-bot'}`}
              >
                {m.role === 'assistant' && (
                  <div className="msg-avatar bot">
                    <Bot size={17} />
                  </div>
                )}
                <div className={`msg-bubble ${m.role === 'user' ? 'msg-bubble-user' : 'msg-bubble-bot'}`}>
                  {renderText(m.text)}
                  {m.role === 'assistant' && m.intent && m.intent !== 'general' && (
                    <div className="msg-tag">
                      <Sparkles size={11} /> {m.intent}
                    </div>
                  )}
                </div>
                {m.role === 'user' && (
                  <div className="msg-avatar user">
                    <User size={17} />
                  </div>
                )}
              </motion.div>
            ))}
          </AnimatePresence>

          {typing && (
            <div className="msg-row msg-row-bot">
              <div className="msg-avatar bot"><Bot size={17} /></div>
              <div className="msg-bubble msg-bubble-bot">
                <span className="typing-dot" /><span className="typing-dot" /><span className="typing-dot" />
              </div>
            </div>
          )}
        </div>

        {/* Suggestions */}
        <div className="suggestion-row">
          {SUGGESTIONS.map((s, i) => (
            <button
              key={i}
              className="suggestion-chip"
              onClick={() => send(s.text)}
              disabled={typing}
            >
              {s.icon} {s.text}
            </button>
          ))}
        </div>

        {/* Input */}
        <div className="chat-input-row">
          <input
            className="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send(input)}
            placeholder="Ask about the ocean… e.g. 'How rough are waves near Puri?'"
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