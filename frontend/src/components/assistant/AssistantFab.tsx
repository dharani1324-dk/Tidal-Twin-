/**
 * AssistantFab - floating "Ask Ocean AI" action button (bottom-right)
 * ==================================================================
 * Global quick-access to the Ocean AI Copilot. Clicking the glowing
 * button opens a popup drawer that embeds the full Assistant without
 * leaving the current page. Rendered once in the App shell.
 */
import { lazy, Suspense, useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Sparkles, X, ChevronDown } from 'lucide-react'
import './AssistantFab.css'

const Assistant = lazy(() => import('../../pages/Assistant'))

export default function AssistantFab({ visible }: { visible: boolean }) {
  const [open, setOpen] = useState(false)
  const [tip, setTip] = useState(true)

  useEffect(() => {
    if (!visible) setOpen(false)
  }, [visible])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  const close = () => setOpen(false)

  return (
    <>
      <AnimatePresence>
        {visible && !open && (
          <motion.div
            className="fab-wrap"
            initial={{ opacity: 0, y: 24, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 24, scale: 0.9 }}
            transition={{ type: 'spring', stiffness: 340, damping: 24, mass: 0.8 }}
          >
            {tip && (
              <button className="fab-tip" onClick={() => setTip(false)}>
                <span>Ask the ocean anything — live data, instant analyst answers</span>
                <X size={11} />
              </button>
            )}
            <button className="fab-btn" onClick={() => { setOpen(true); setTip(false) }} aria-label="Open Ocean AI Copilot">
              <span className="fab-ring" />
              <span className="fab-sonar" />
              <span className="fab-sonar fab-sonar-2" />
              <span className="fab-sparkles">
                <Sparkles size={20} />
                <Sparkles size={8} className="fab-spark-mini" />
              </span>
              <span className="fab-label">Ask Ocean AI</span>
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {open && (
          <>
            <motion.div
              className="fab-backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
              onClick={close}
            />
            <motion.div
              className="fab-popup"
              role="dialog"
              aria-modal="true"
              aria-label="Ocean AI Copilot quick access"
              initial={{ opacity: 0, y: 40, scale: 0.92 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 40, scale: 0.92 }}
              transition={{ type: 'spring', stiffness: 320, damping: 26, mass: 0.9 }}
            >
              <div className="fab-pop-head">
                <ChevronDown size={13} />
                <span>AI COPILOT · QUICK ACCESS</span>
                <button className="fab-close" onClick={close} aria-label="Close copilot">
                  <X size={16} />
                </button>
              </div>
              <div className="fab-pop-body">
                <Suspense fallback={<div className="fab-loading" role="status">Loading Copilot…</div>}>
                  <Assistant embedded />
                </Suspense>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  )
}