/**
 * TIDE Voice Agent - the floating orb (talk/stop button + live audio levels).
 * The rings pulse with the microphone level; the wheel lifts with output.
 */
import { Mic, Square } from 'lucide-react'
import type { AudioLevels } from '../../services/voice/geminiClient'
import type { VoicePhase } from '../../services/voice/types'

function phaseLabel(phase: VoicePhase, connected: boolean): string {
  switch (phase) {
    case 'connecting':
      return 'Connecting…'
    case 'ready':
      return connected ? 'Tap to stop' : 'Tap to talk'
    case 'listening':
      return 'Listening…'
    case 'thinking':
      return 'Thinking…'
    case 'speaking':
      return 'Speaking…'
    case 'paused':
      return 'Paused'
    case 'error':
      return 'Tap to retry'
    case 'fallback':
      return 'Copilot fallback'
    default:
      return 'Tap to talk'
  }
}

export default function VoiceOrb({
  phase,
  connected,
  levels,
  disabled,
  onToggle,
}: {
  phase: VoicePhase
  connected: boolean
  levels: AudioLevels
  disabled: boolean
  onToggle: () => void
}) {
  const active = connected || phase === 'connecting' || phase === 'error'
  const talking = phase === 'listening'
  const listening = phase === 'listening'

  return (
    <button
      className={`voice-orb-btn${active ? ' on' : ''}`}
      onClick={onToggle}
      disabled={disabled && !connected}
      aria-label={phaseLabel(phase, connected)}
      aria-pressed={active}
    >
      <span className="voice-orb-ring" aria-hidden />
      {talking && <span className="voice-sonar src" aria-hidden />}
      <span className="voice-orb-body">
        <span className="voice-orb-wheel" aria-hidden>
          {[0, 1, 2, 3, 4].map((i) => {
            const base = 8 + Math.sin(i * 1.7) * 6
            const h = connected ? base + levels.input * 22 : base
            return <span key={i} className="voice-orb-bar" style={{ height: `${Math.min(26, h)}px` }} />
          })}
        </span>
        {!connected && <Mic size={16} style={{ position: 'relative', zIndex: 1 }} />}
        {connected && <Square size={12} fill="currentColor" style={{ position: 'relative', zIndex: 1 }} />}
      </span>
      <span className="voice-orb-label">{phaseLabel(phase, connected)}{listening ? ' · LIVE' : ''}</span>
    </button>
  )
}