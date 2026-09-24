/**
 * IntelligenceBrief — Phase 7 brief tiles + direct actions.
 * Heat-of-action answers: WHAT / WHERE / WHEN / CHANGED / CONFIDENCE /
 * DISAGREES / MATTERS / OBSERVE NEXT / EVIDENCE / WHAT IF / VALIDATION.
 * Values are real payloads (or literally "DATA UNAVAILABLE").
 */
import { FileSearch, ArrowRight } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import TrustBadge from './TrustBadge'

export interface BriefTile {
  key: string
  label: string
  value: string
  tone?: 'good' | 'warn' | 'bad' | 'muted'
  hint?: string
}

export interface BriefAction {
  key: string
  label: string
  to: string
  evidence?: boolean
  icon: LucideIcon
}

interface Props {
  locationName: string
  tiles: BriefTile[]
  actions: BriefAction[]
  overallStatus?: string | null
  onNavigate: (to: string) => void
  onOpenEvidence: () => void
}

export default function IntelligenceBrief({
  locationName,
  tiles,
  actions,
  overallStatus,
  onNavigate,
  onOpenEvidence,
}: Props) {
  return (
    <div className="ws-section">
      <div className="ws-section-head">
        <h3>Ocean Intelligence Brief</h3>
        <span className="ws-kicker">{locationName || 'network'}</span>
        {overallStatus && <TrustBadge status={overallStatus} />}
      </div>

      <div className="brief-grid">
        {tiles.map((t) => (
          <div className="brief-tile" key={t.key}>
            <span className="brief-tile-label">{t.label}</span>
            <span className={`brief-tile-value tone-${t.tone ?? 'good'}`}>{t.value}</span>
            {t.hint && <span className="brief-tile-hint">{t.hint}</span>}
          </div>
        ))}
      </div>

      <div className="brief-actions">
        {actions.map((a) => {
          const Icon = a.icon
          return (
            <button
              key={a.key}
              className={`ws-action${a.evidence ? ' ws-action-evidence' : ''}`}
              onClick={() => (a.evidence ? onOpenEvidence() : onNavigate(a.to))}
              title={`Open ${a.label}`}
            >
              {a.evidence ? <FileSearch size={12} /> : <Icon size={12} />}
              {a.label}
              <ArrowRight size={11} style={{ opacity: 0.6 }} />
            </button>
          )
        })}
      </div>
    </div>
  )
}