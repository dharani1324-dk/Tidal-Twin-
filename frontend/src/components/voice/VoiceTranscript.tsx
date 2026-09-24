/**
 * TIDE Voice Agent - transcript + tool-invocation activity feed.
 * Pure presentation; reads session state from the hook.
 */
import { motion, AnimatePresence } from 'framer-motion'
import type { VoiceSessionState } from '../../services/voice/voiceSession'

const TOOL_LABELS: Record<string, string> = {
  'tidetwin_get_region_overview': 'region',
  'tidetwin_get_ocean_field': 'ocean field',
  'tidetwin_get_depth_profile': 'depth profile',
  'tidetwin_get_satellite_observations': 'satellite',
  'tidetwin_get_argo_observations': 'Argo',
  'tidetwin_get_anomalies': 'anomalies',
  'tidetwin_get_anomaly_statistics': 'anomaly stats',
  'tidetwin_get_events': 'events',
  'tidetwin_investigate_event': 'forensics',
  'tidetwin_get_tide_candidates': 'TIDE candidates',
  'tidetwin_get_tide_explanation': 'TIDE explanation',
  'tidetwin_get_tide_evidence': 'TIDE evidence',
  'tidetwin_get_tide_verdict': 'TIDE verdict',
  'tidetwin_get_tide_uncertainty': 'TIDE uncertainty',
  'tidetwin_recommend_next_observation': 'TIDE recommendation',
  'tidetwin_get_event_context': 'event context',
  'tidetwin_get_replay': 'decision replay',
  'tidetwin_get_validation_status': 'TIDE validation',
  'tidetwin_get_model_comparison': 'model comparison',
  'tidetwin_run_whatif': 'what-if',
  'tidetwin_compare_scenarios': 'scenarios',
  'web_search': 'web search',
  'ui_focus_region': 'focus',
  'ui_set_depth': 'depth',
  'ui_set_time': 'time',
  'ui_set_variable': 'variable',
  'ui_toggle_layer': 'layer',
  'ui_navigate': 'navigate',
  'ui_reveal_panel': 'panel',
}

function toolName(name: string): string {
  const short = TOOL_LABELS[name]
  return short ?? name.split('.').pop() ?? name
}

export default function VoiceTranscript({ state }: { state: VoiceSessionState }) {
  const { messages, toolInvocations, error } = state

  return (
    <div className="voice-panel" role="log" aria-label="Voice transcript">
      <div className="voice-panel-head">
        <span className="vs-dot live" aria-hidden />
        <b>Voice Analyst</b>
        {state.webUsed && <span className="vp-web">· WEB SOURCED</span>}
        <span className="vp-model">{state.session ? `${state.session.model} · ${state.session.voice}` : ''}</span>
      </div>

      <div className="voice-msg-list">
        {error && <div className="voice-error">{error}</div>}

        {toolInvocations.map((inv) => (
          <div key={inv.id} className="voice-tool">
            <span className="vt-name">▸ {toolName(inv.name)}</span>
            {inv.status === 'executing' ? (
              <span className="vt-spinner" aria-hidden>
                <span className="voice-spinner" />
              </span>
            ) : (
              <span className={`vt-status ${inv.status}`}>{inv.status === 'ok' ? '✓' : '✕'}</span>
            )}
          </div>
        ))}
        {toolInvocations.length > 0 && <div className="voice-tool"><span className="vt-fb">{toolInvocations[toolInvocations.length - 1].feedback ?? ''}</span></div>}

        <AnimatePresence initial={false}>
          {messages.map((m) => (
            <motion.div
              key={m.id}
              className={`voice-msg ${m.role}`}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
            >
              <span className="vm-who">{m.role === 'assistant' ? 'AI' : 'YOU'}</span>
              <span className="vm-text">{m.text}</span>
            </motion.div>
          ))}
        </AnimatePresence>

        {messages.length === 0 && toolInvocations.length === 0 && !error && (
          <div className="voice-msg">
            <span className="vm-who">AI</span>
            <span className="vm-text">
              Tap the orb and talk. Try “focus Bay of Bengal”, “show me the TIDE verdict here”,
              or “what made this anomaly happen?”.
            </span>
          </div>
        )}
      </div>
    </div>
  )
}