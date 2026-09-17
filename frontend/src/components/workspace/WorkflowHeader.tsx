/**
 * WorkflowHeader — Phase 7 unified intelligence workflow (01–09 + EXPLAIN).
 * Every stage navigates to an EXISTING page/engine; nothing here is rebuilt.
 */
import { useLocation, useNavigate } from 'react-router-dom'
import { ArrowRight, Bot, ChevronRight } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import {
  Eye, Radar, Search, Brain, Crosshair, Cable, FlaskConical, Scale, FileCheck,
} from 'lucide-react'

interface Stage {
  num: string
  label: string
  route: string
  routeNote: string
  icon: LucideIcon
  targets: string[]
}

const STAGES: Stage[] = [
  { num: '01', label: 'OBSERVE', route: '/globe', routeNote: 'Digital Twin · live telemetry', icon: Eye, targets: ['/globe', '/monitoring'] },
  { num: '02', label: 'DETECT', route: '/anomalies', routeNote: 'Anomaly Intel · alerts', icon: Radar, targets: ['/anomalies'] },
  { num: '03', label: 'INVESTIGATE', route: '/forensics', routeNote: 'Fingerprint · timeline · autopsy', icon: Search, targets: ['/forensics'] },
  { num: '04', label: 'UNDERSTAND', route: '/intelligence', routeNote: 'Health · causal · relations', icon: Brain, targets: ['/intelligence'] },
  { num: '05', label: 'PRIORITIZE', route: '/tide', routeNote: 'TIDE rankings · verdict', icon: Crosshair, targets: ['/tide'] },
  { num: '06', label: 'OBSERVE NEXT', route: '/tide', routeNote: 'Highest-value observation', icon: Cable, targets: ['/tide'] },
  { num: '07', label: 'SIMULATE', route: '/scenarios', routeNote: 'What-If · counterfactual', icon: FlaskConical, targets: ['/scenarios'] },
  { num: '08', label: 'DECIDE', route: '/tide/replay', routeNote: 'Decision Replay · rules', icon: Scale, targets: ['/tide/replay'] },
  { num: '09', label: 'VALIDATE', route: '/validate', routeNote: 'Skill · confidence · provenance', icon: FileCheck, targets: ['/validate'] },
]

export default function WorkflowHeader() {
  const navigate = useNavigate()
  const location = useLocation()

  return (
    <div className="ws-section">
      <div className="ws-section-head">
        <h3>Integrated Ocean Intelligence Workflow</h3>
      </div>
      <div className="ws-workflow" role="navigation" aria-label="Intelligence workflow">
        {STAGES.map((s) => {
          const active = s.targets.some((t) => location.pathname.startsWith(t))
          const Icon = s.icon
          return (
            <button
              key={s.num}
              className={`ws-stage${active ? ' ws-stage-active' : ''}`}
              onClick={() => navigate(s.route)}
              title={`${s.label} — ${s.routeNote}`}
            >
              <span className="ws-stage-top">
                <span className="ws-stage-num">{s.num}</span>
                <ChevronRight size={12} className="ws-stage-arrow" />
              </span>
              <span className="ws-stage-label">
                <Icon size={11} style={{ position: 'relative', top: 1 }} /> {s.label}
              </span>
              <span className="ws-stage-route">{s.routeNote}</span>
            </button>
          )
        })}
        <button className="ws-explain-chip" onClick={() => navigate('/assistant')} title="Ask the Copilot to explain any step in ordinary language">
          <Bot size={14} /> EXPLAIN · COPILOT <ArrowRight size={12} />
        </button>
      </div>
      <span className="ws-workflow-note">
        Each stage opens the real TidalTwin engine for that step — OBSERVE→DETECT→INVESTIGATE→UNDERSTAND→PRIORITIZE→OBSERVE NEXT→SIMULATE→DECIDE→VALIDATE, explainable by the Copilot.
      </span>
    </div>
  )
}