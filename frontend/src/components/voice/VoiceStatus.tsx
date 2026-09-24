/**
 * TIDE Voice Agent - compact status pill under the transcript.
 * Shows live phase, model/voice and a WEB badge when outside-world results
 * were folded in (so web answers are never confused with ocean data).
 */
import type { VoiceSessionState } from '../../services/voice/voiceSession'

const PHASE_TEXT: Record<VoiceSessionState['phase'], string> = {
  idle: 'Standby',
  ready: 'Ready',
  connecting: 'Connecting',
  listening: 'Listening',
  thinking: 'Thinking',
  speaking: 'Speaking',
  paused: 'Paused',
  error: 'Error',
  fallback: 'Copilot',
}

export default function VoiceStatus({ state }: { state: VoiceSessionState }) {
  const live = state.phase === 'listening' || state.phase === 'speaking' || state.phase === 'thinking'
  return (
    <div className="voice-status">
      <span className={`vs-dot${live ? ' live' : ''}`} />
      <span>{PHASE_TEXT[state.phase]}</span>
      {state.session && <span>· {state.session.model}</span>}
      <span className="vs-spacer" />
      {state.webUsed && <span className="vs-web">WEB</span>}
    </div>
  )
}