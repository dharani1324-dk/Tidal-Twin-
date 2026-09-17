/**
 * TrustBadge — Phase 7 trust/data-status visual language.
 * Every dataset surface (TIDE, What-If, Replay, Forensics, Anomaly Intel)
 * now carries a consistent trust chip: REAL / HISTORICAL / MODEL_DERIVED /
 * SIMULATED / SYNTHETIC + the explicit simulation caveat.
 */
import type { TideStatus } from '../../types/tide'

export type DataStatus = TideStatus | (string & {})

export interface TrustMeta {
  label: string
  color: string
  bg: string
  hint: string
}

export const TRUST_META: Record<string, TrustMeta> = {
  REAL: {
    label: 'REAL',
    color: '#10b981',
    bg: 'rgba(16,185,129,0.13)',
    hint: 'Ground-truth observation from the live stream',
  },
  HISTORICAL: {
    label: 'HISTORICAL',
    color: '#38bdf8',
    bg: 'rgba(56,189,248,0.13)',
    hint: 'Recorded historical observation',
  },
  MODEL_DERIVED: {
    label: 'MODEL DERIVED',
    color: '#8b8cf8',
    bg: 'rgba(139,140,248,0.14)',
    hint: 'Computed by the ocean model — not directly measured',
  },
  SIMULATED: {
    label: 'SIMULATED',
    color: '#f59e0b',
    bg: 'rgba(245,158,11,0.16)',
    hint: 'SIMULATED OBSERVATION — DEMONSTRATION ONLY',
  },
  SYNTHETIC: {
    label: 'SYNTHETIC',
    color: '#94a3b8',
    bg: 'rgba(148,163,184,0.13)',
    hint: 'Synthetic placeholder — not a real measurement',
  },
  INSUFFICIENT_EVIDENCE: {
    label: 'INSUFFICIENT EVIDENCE',
    color: '#64748b',
    bg: 'rgba(100,116,139,0.14)',
    hint: 'Not enough evidence to classify trust',
  },
  UNKNOWN: {
    label: 'UNKNOWN',
    color: '#64748b',
    bg: 'rgba(100,116,139,0.14)',
    hint: 'No trust classification is available for this record',
  },
}

export default function TrustBadge({
  status,
  title,
}: {
  status?: string | null
  title?: string
}) {
  const key = (status ?? '').toUpperCase()
  const meta = TRUST_META[key] ?? TRUST_META.UNKNOWN
  return (
    <span
      className="trust-chip"
      style={{ color: meta.color, background: meta.bg, borderColor: `${meta.color}44` }}
      title={title ?? meta.hint}
    >
      <span className="trust-dot" style={{ background: meta.color }} />
      {meta.label}
    </span>
  )
}

export function TrustLegend() {
  return (
    <div className="trust-legend" role="list" aria-label="Trust vocabulary">
      {Object.values(TRUST_META)
        .filter((m) => m.label !== TRUST_META.INSUFFICIENT_EVIDENCE.label && m.label !== TRUST_META.UNKNOWN.label)
        .map((m) => (
          <span
            key={m.label}
            className="trust-chip"
            style={{ color: m.color, background: m.bg, borderColor: `${m.color}44` }}
            title={m.hint}
          >
            <span className="trust-dot" style={{ background: m.color }} />
            {m.label}
          </span>
        ))}
    </div>
  )
}