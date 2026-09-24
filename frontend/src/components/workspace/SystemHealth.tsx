/**
 * SystemHealth — Phase 7 subsystem status board.
 * States derive from the ACTUAL response of each surface (reachable + data →
 * AVAILABLE; reachable + empty → LIMITED; unreachable → UNAVAILABLE).
 */
export interface HealthProbe {
  key: string
  label: string
  state: 'available' | 'limited' | 'unavailable'
  detail?: string
}

const STATE_COLOR = {
  available: '#10b981',
  limited: '#fbbf24',
  unavailable: '#fb6b84',
}

const STATE_TEXT = {
  available: 'AVAILABLE',
  limited: 'LIMITED',
  unavailable: 'UNAVAILABLE',
}

export default function SystemHealth({ probes, backendDown }: { probes: HealthProbe[]; backendDown?: boolean }) {
  return (
    <div className="sys-grid" role="group" aria-label="System health">
      {probes.map((p) => {
        const state = backendDown ? 'unavailable' : p.state
        const color = STATE_COLOR[state]
        return (
          <div className="sys-chip" key={p.key} title={p.detail}>
            <span className="sys-dot" style={{ background: color, boxShadow: `0 0 8px ${color}66` }} />
            <span className="sys-chip-body">
              <span className="sys-chip-label">{p.label}</span>
              <span className="sys-chip-state" style={{ color }}>
                {STATE_TEXT[state]}
              </span>
            </span>
          </div>
        )
      })}
    </div>
  )
}