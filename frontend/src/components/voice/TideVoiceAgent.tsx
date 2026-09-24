/**
 * TIDE Voice Agent - root component (rendered once in the App shell).
 *
 * Responsibilities:
 *  - capability status + disabled-state hint
 *  - publishing the base page context whenever the route changes
 *  - executing `voice:navigate` commands (route-owning App shell)
 *  - rendering the floating orb + transcript + status pill
 *
 * Page-level commands (focus/depth/time/layer/variable/reveal) are handled by
 * the pages themselves (e.g. DigitalTwin) via the voice command bus.
 */

import { Suspense, lazy, useCallback, useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useTideVoice } from '../../hooks/useTideVoice'
import { setVoiceContext } from '../../services/voice/voiceContext'
import { voiceBus } from '../../services/voice/voiceBus'
import { PAGE_ROUTES } from '../../services/voice/types'
import VoiceOrb from './VoiceOrb'
import VoiceTranscript from './VoiceTranscript'
import './voice.css'

const VoiceStatusPill = lazy(() => import('./VoiceStatus'))

const ROUTE_TO_PAGE: Record<string, string> = Object.fromEntries(
  Object.entries(PAGE_ROUTES).map(([page, route]) => [route, page]),
)

export default function TideVoiceAgent() {
  const { status, checking, state, levels, connected, start, stop } = useTideVoice()
  const location = useLocation()
  const navigate = useNavigate()

  // Publish the base page context each time the route changes so the voice
  // model always knows which surface the user is on.
  useEffect(() => {
    const page = ROUTE_TO_PAGE[location.pathname] ?? 'home'
    setVoiceContext({ page })
  }, [location.pathname])

  useEffect(() => {
    return voiceBus.subscribe((event) => {
      if (event.type !== 'voice:navigate') return
      const route = typeof event.payload?.route === 'string'
        ? event.payload.route
        : PAGE_ROUTES[String(event.payload?.page ?? '')]
      if (!route) return
      const dest = (event.payload?.locationId != null
        ? { pathname: route, search: `?focus=${event.payload.locationId}&var=${event.payload.variable ?? 'temperature'}` }
        : { pathname: route })
      navigate(dest)
    })
  }, [navigate])

  const toggle = useCallback(() => {
    if (connected) {
      void stop()
    } else {
      void start()
    }
  }, [connected, start, stop])

  const disabled = !status?.enabled && !checking

  return (
    <div className="voice-root">
      <AnimatePresence>
        {connected && (
          <motion.div
            key="panel"
            initial={{ opacity: 0, y: 16, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 16, scale: 0.97 }}
            transition={{ duration: 0.2 }}
          >
            <VoiceTranscript state={state} />
          </motion.div>
        )}
      </AnimatePresence>

      {!checking && !disabled && (
        <Suspense fallback={null}>
          <VoiceStatusPill state={state} />
        </Suspense>
      )}

      {disabled && (
        <div className="voice-status" title="Set OPENAI_API_KEY on the backend to enable realtime voice">
          <span className="vs-dot vs-err-dot" />
          <span>Voice offline · use the text Copilot (Ask Ocean AI)</span>
        </div>
      )}

      <VoiceOrb
        phase={state.phase}
        connected={connected}
        levels={levels}
        disabled={disabled}
        onToggle={toggle}
      />
    </div>
  )
}