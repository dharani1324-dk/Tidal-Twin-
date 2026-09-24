import { type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useCountUp } from './hooks'

/* ============================================================
   TidalTwin — Cinematic Ocean UI primitives (Figma design system)
   Presentation-only: they never attach data semantics, so honesty
   labels always travel with the data passed in.
   ============================================================ */

export interface BadgeProps {
  children: ReactNode
  tone?: 'cyan' | 'teal' | 'ref' | 'live' | 'off' | 'warn'
}

export function ScientificBadge({ children, tone = 'cyan' }: BadgeProps) {
  const cls =
    tone === 'teal' ? 'oh-badge--teal'
    : tone === 'ref' ? 'oh-badge--ref'
    : tone === 'live' ? 'oh-badge--live'
    : tone === 'off' ? 'oh-badge--off'
    : tone === 'warn' ? 'oh-badge--warn'
    : 'oh-badge'
  return <span className={`oh-badge ${cls}`}>{children}</span>
}

/** Mono source attribution — the mandatory "where does this come from" label. */
export function DataSourceBadge({ label }: { label: string }) {
  return <span className="oh-badge oh-badge--src" title={label}>{label}</span>
}

/** Live-data pulse dot + label (used only for REAL project telemetry). */
export function LiveDot({ label = 'LIVE' }: { label?: string }) {
  return (
    <span className="oh-badge oh-badge--live">
      <span className="oh-live-dot" />
      {label}
    </span>
  )
}

const STATUS_TONE = {
  ok: 'oh-status--ok',
  warn: 'oh-status--warn',
  crit: 'oh-status--crit',
  off: 'oh-status--off',
} as const

export function StatusIndicator({ tone, children }: { tone: keyof typeof STATUS_TONE; children: ReactNode }) {
  return (
    <span className={`oh-status ${STATUS_TONE[tone]}`}>
      <span className="oh-status__dot" />
      {children}
    </span>
  )
}

export function AnimatedNumber({ target, decimals = 0, prefix = '', suffix = '', enabled = false, duration = 1400 }: {
  target: number
  decimals?: number
  prefix?: string
  suffix?: string
  enabled?: boolean
  duration?: number
}) {
  const { formatted } = useCountUp(target, { decimals, duration, enabled })
  return <>{prefix}{formatted}{suffix}</>
}

/** Data-label block: label / value+unit / source / live flag. */
export function DataLabel({ label, value, unit, source, live }: {
  label: string
  value: string
  unit?: string
  source?: string
  live?: boolean
}) {
  return (
    <div className="oh-kpi">
      <span className="oh-kpi__label">{label}{live ? <span className="oh-live-dot" /> : null}</span>
      <span className="oh-kpi__value">
        {value}{unit ? <em>{unit}</em> : null}
      </span>
      {source ? <span className="oh-kpi__foot"><b>{source}</b></span> : null}
    </div>
  )
}

export function SectionHeader({ eyebrow, title, sub, right }: {
  eyebrow: string
  title: ReactNode
  sub?: ReactNode
  right?: ReactNode
}) {
  return (
    <div className="oh-head-row">
      <div>
        <span className="oh-eyebrow">{eyebrow}</span>
        <h2 className="oh-title">{title}</h2>
        {sub ? <p className="oh-sub">{sub}</p> : null}
      </div>
      {right ? <div className="oh-head-right">{right}</div> : null}
    </div>
  )
}

export function RiskBar({ pct, label, value, heat }: {
  pct: number
  label: string
  value?: string
  heat?: boolean
}) {
  const clamped = Math.max(0, Math.min(100, pct))
  const cls = !heat ? '' : clamped >= 66 ? ' oh-risk__fill--hot' : ' oh-risk__fill--heat'
  return (
    <div className="oh-risk">
      <div className="oh-risk__meta">
        <span>{label}</span>
        <b>{value ?? `${Math.round(clamped)}%`}</b>
      </div>
      <div className="oh-risk__track">
        <div className={`oh-risk__fill${cls}`} style={{ transform: `scaleX(${clamped / 100})` }} />
      </div>
    </div>
  )
}

export function Timeline({ items, activeYear }: { items: { year: number; label: string }[]; activeYear?: number }) {
  return (
    <div className="oh-timeline" role="list">
      {items.map((it) => (
        <div className="oh-timeline__grp" role="listitem" key={it.year}>
          <span className={it.year === activeYear ? 'oh-timeline__dot' : 'oh-timeline__dot'} style={it.year !== activeYear ? { opacity: 0.35 } : undefined} />
          <span className="oh-timeline__year">{it.year}</span>
          <span className="oh-timeline__label">{it.label}</span>
        </div>
      ))}
    </div>
  )
}

export function GlowButton({ to, children, variant = 'solid', onClick }: {
  to?: string
  children: ReactNode
  variant?: 'solid' | 'ghost'
  onClick?: () => void
}) {
  const cls = `oh-btn${variant === 'ghost' ? ' oh-btn--ghost' : ' oh-btn--solid'}`
  if (to) {
    return (
      <Link to={to} className={cls}>
        {children}
      </Link>
    )
  }
  return (
    <button type="button" className={cls} onClick={onClick}>
      {children}
    </button>
  )
}

export function ScanlineCard({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`oh-card oh-scanline ${className}`}>
      {children}
    </div>
  )
}