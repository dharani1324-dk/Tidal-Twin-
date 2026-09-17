/**
 * IntelligenceGraph — Phase 7 Event DNA → TIDE → Decision chain visual.
 * Nodes navigate to the existing Forensics / TIDE / Decision Replay surfaces.
 * Missing data renders as DATA UNAVAILABLE — never synthesized.
 */
import { useNavigate } from 'react-router-dom'
import { Dna, Crosshair, Scale, ChevronDown } from 'lucide-react'
import type { TideCandidate, TideDecision } from '../../types/tide'

export interface GraphDecision {
  affected_decision?: TideDecision | null
  decision_impact?: number | null
  replayable?: boolean
}

interface Props {
  eventType?: string | null
  eventLocation?: string | null
  eventConfidence?: number | null
  candidate: TideCandidate | null
  decision: GraphDecision | null
}

export default function IntelligenceGraph({ eventType, eventLocation, eventConfidence, candidate, decision }: Props) {
  const navigate = useNavigate()
  const eventNode = eventType ? `${eventType.replace(/_/g, ' ').toLowerCase()}`
    : eventLocation ? `event at ${eventLocation}` : null

  return (
    <div className="graph-chain" role="list" aria-label="Event DNA to TIDE to Decision chain">
      <button className="graph-node" onClick={() => navigate('/forensics')} title="Open Ocean Forensics — Event DNA">
        <span className="graph-node-icon" style={{ background: 'rgba(16,185,129,0.14)', color: '#34d399' }}>
          <Dna size={15} />
        </span>
        <span>
          <span className="graph-node-title">Event DNA</span>
          <span className="graph-node-value">
            {eventNode ? eventNode : <span className="data-unavailable">DATA UNAVAILABLE</span>}
          </span>
          <span style={{ display: 'block', fontSize: 9, color: '#64748b' }}>
            {eventConfidence != null ? `${Math.round(eventConfidence * 100)}% detection confidence` : eventLocation ? `location ${eventLocation}` : 'no mapped event'}
          </span>
        </span>
      </button>

      <span className="graph-link"><span className="graph-link-line" /> maps into {candidate ? <b style={{ color: '#22d3ee' }}>TIDE</b> : 'TIDE (empty)'}</span>

      <button className="graph-node" onClick={() => navigate('/tide')} title="Open TIDE Command Center — ranking & verdict">
        <span className="graph-node-icon" style={{ background: 'rgba(139,140,248,0.14)', color: '#a5b4fc' }}>
          <Crosshair size={15} />
        </span>
        <span>
          <span className="graph-node-title">TIDE Ranking</span>
          <span className="graph-node-value">
            {candidate ? `${candidate.location} · ${candidate.variable.replace(/_/g, ' ')} @ ${candidate.depth_m} m` : <span className="data-unavailable">DATA UNAVAILABLE</span>}
          </span>
          <span style={{ display: 'block', fontSize: 9, color: '#64748b' }}>
            {candidate ? `observation value ${candidate.observation_value.toFixed(4)} · ${candidate.affected_decision.replace(/_/g, ' ')}` : 'no candidate — insufficient evidence'}
          </span>
        </span>
      </button>

      <span className="graph-link"><span className="graph-link-line" /> decides</span>

      <button className="graph-node" onClick={() => navigate('/tide/replay')} title="Open Decision Replay — the decided path">
        <span className="graph-node-icon" style={{ background: 'rgba(245,158,11,0.14)', color: '#fbbf24' }}>
          <Scale size={15} />
        </span>
        <span>
          <span className="graph-node-title">Decision</span>
          <span className="graph-node-value">
            {decision?.affected_decision ? (
              <>{(decision.affected_decision as string).replace(/_/g, ' ')}</>
            ) : (
              <span className="data-unavailable">DATA UNAVAILABLE</span>
            )}
          </span>
          <span style={{ display: 'block', fontSize: 9, color: '#64748b' }}>
            {decision?.decision_impact != null ? `decision impact ${decision.decision_impact.toFixed(2)}` : 'no decision rules applied yet'}
          </span>
        </span>
      </button>

      <span className="graph-link">
        <ChevronDown size={12} />
        replayable path {decision?.replayable ? 'available' : '— no threshold-crossing event'}
      </span>
    </div>
  )
}