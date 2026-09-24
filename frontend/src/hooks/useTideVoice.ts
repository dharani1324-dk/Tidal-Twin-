/**
 * TIDE Voice Agent - React hook.
 *
 * Bridges the browser-only voice session/orchestrator into the React shell:
 *  - fetches `/api/v1/voice/status` to know whether Realtime voice is usable
 *  - instantiates one TideVoiceSession per mounted agent
 *  - exposes start / stop / clear + live session state
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchVoiceStatus } from '../api/client'
import type { AudioLevels } from '../services/voice/geminiClient'
import type { VoiceApiStatus } from '../services/voice/types'
import { TideVoiceSession, emptySessionState, type VoiceSessionState } from '../services/voice/voiceSession'

export interface UseTideVoice {
  status: VoiceApiStatus | null
  checking: boolean
  state: VoiceSessionState
  levels: AudioLevels
  connected: boolean
  start: () => Promise<void>
  stop: () => Promise<void>
  clear: () => void
}

export function useTideVoice(): UseTideVoice {
  const [status, setStatus] = useState<VoiceApiStatus | null>(null)
  const [checking, setChecking] = useState(true)
  const [state, setState] = useState<VoiceSessionState>(() => emptySessionState())
  const [levels, setLevels] = useState<AudioLevels>({ input: 0, output: 0 })
  const sessionRef = useRef<TideVoiceSession | null>(null)
  const startedRef = useRef(false)

  useEffect(() => {
    let alive = true
    fetchVoiceStatus()
      .then((s) => {
        if (!alive) return
        setStatus(s)
        setChecking(false)
      })
      .catch(() => {
        if (!alive) return
        setStatus(null)
        setChecking(false)
      })
    return () => {
      alive = false
    }
  }, [])

  const getSession = useCallback(() => {
    if (!sessionRef.current) {
      sessionRef.current = new TideVoiceSession(setState, (l) => setLevels(l))
    }
    return sessionRef.current
  }, [])

  useEffect(() => {
    return () => {
      startedRef.current = false
      void sessionRef.current?.disconnect().catch(() => undefined)
      sessionRef.current = null
    }
  }, [])

  const start = useCallback(async () => {
    const session = getSession()
    if (startedRef.current && !session.isConnected) {
      startedRef.current = false
    }
    if (!startedRef.current) {
      startedRef.current = true
      await session.start()
    }
  }, [getSession])

  const stop = useCallback(async () => {
    startedRef.current = false
    const session = sessionRef.current
    if (session) await session.disconnect()
  }, [])

  const clear = useCallback(() => {
    sessionRef.current?.clearTranscript()
  }, [])

  return {
    status,
    checking,
    state,
    levels,
    connected: state.phase !== 'idle' && state.phase !== 'error',
    start,
    stop,
    clear,
  }
}