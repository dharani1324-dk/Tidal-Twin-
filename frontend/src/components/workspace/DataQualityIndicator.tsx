/**
 * DataQualityIndicator — Phase 7 data-quality vocabulary derived from real
 * backend inputs (region coverage %, observation confidence %).
 * States: GOOD COVERAGE / LIMITED COVERAGE / DATA GAP / INSUFFICIENT EVIDENCE.
 */
import { Database, Waves, AlertTriangle, ShieldQuestion } from 'lucide-react'

export type DataQualityLevel =
  | 'GOOD_COVERAGE'
  | 'LIMITED_COVERAGE'
  | 'DATA_GAP'
  | 'INSUFFICIENT_EVIDENCE'
  | (string & {})

const QUALITY_META: Record<string, { color: string; icon: typeof Database; note: string }> = {
  GOOD_COVERAGE: { color: '#10b981', icon: Waves, note: 'Enough recent observations to trust the picture' },
  LIMITED_COVERAGE: { color: '#fbbf24', icon: Database, note: 'Some coverage, but gaps remain — treat conclusions as provisional' },
  DATA_GAP: { color: '#fb6b84', icon: AlertTriangle, note: 'Significant gaps in the observation stream for this region' },
  INSUFFICIENT_EVIDENCE: { color: '#64748b', icon: ShieldQuestion, note: 'No recent observations — evidence does not exist' },
}

function resolveLevel(
  quality?: string | null,
  coverage?: number | null,
  confidence?: number | null,
): { level: DataQualityLevel; score: number } {
  const q = (quality ?? '').toUpperCase()
  if (q && QUALITY_META[q]) return { level: q, score: q === 'GOOD_COVERAGE' ? 100 : q === 'LIMITED_COVERAGE' ? 65 : q === 'DATA_GAP' ? 30 : 0 }
  const value = coverage ?? confidence
  if (value == null) return { level: 'INSUFFICIENT_EVIDENCE', score: 0 }
  if (value >= 70) return { level: 'GOOD_COVERAGE', score: value }
  if (value >= 40) return { level: 'LIMITED_COVERAGE', score: value }
  return { level: 'DATA_GAP', score: value }
}

export default function DataQualityIndicator({
  quality,
  coverage,
  confidence,
  location,
}: {
  quality?: string | null
  coverage?: number | null
  confidence?: number | null
  location?: string
}) {
  const { level, score } = resolveLevel(quality, coverage, confidence)
  const meta = QUALITY_META[level] ?? QUALITY_META.INSUFFICIENT_EVIDENCE
  const Icon = meta.icon
  return (
    <div className="dq-wrap">
      <span
        className="dq-pill"
        style={{ color: meta.color, background: `${meta.color}18`, borderColor: `${meta.color}45` }}
        title={`${location ? location + ' — ' : ''}${meta.note}`}
      >
        <Icon size={12} />
        {level.replace(/_/g, ' ')}
      </span>
      <div className="dq-bar">
        <i style={{ width: `${score}%`, background: meta.color }} />
      </div>
      <span className="dq-note">
        {coverage != null ? `coverage ${Math.round(coverage)}%` : confidence != null ? `confidence ${Math.round(confidence)}%` : 'no data stream'}
      </span>
    </div>
  )
}