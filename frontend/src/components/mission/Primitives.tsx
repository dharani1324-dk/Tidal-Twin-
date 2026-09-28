/**
 * Mission Intro — shared primitives
 * ==================================
 * The vocabulary the whole page is built from: an entrance animation, the
 * section shell, the provenance chip, and — most importantly — the
 * *structured absence* block.
 *
 * The absence block exists because it is the single most differentiating thing
 * about TidalTwin. A conventional dashboard renders a plausible number when it
 * has no data. This one renders "No data available" and the reason, which is
 * exactly the `available:false + reason` contract the API uses.
 */
import { type ReactNode } from 'react'
import { motion } from 'framer-motion'
import { AlertCircle, Compass, Loader2 } from 'lucide-react'
import TrustBadge from '../workspace/TrustBadge'
import { useInView, useReducedMotion } from '../ocean/hooks'
import type { Resource } from './missionData'

/* ------------------------------------------------------------------ */
/* Entrance                                                            */
/* ------------------------------------------------------------------ */

/**
 * The project's house entrance: 22px rise, 0.98 → 1 scale, 6px → 0 blur on
 * `cubic-bezier(0.22, 1, 0.36, 1)`. Under reduced motion the content is simply
 * present — no transform, no filter, no stagger.
 */
export function Reveal({
  children,
  delay = 0,
  className,
  as = 'div',
}: {
  children: ReactNode
  delay?: number
  className?: string
  as?: 'div' | 'li' | 'section' | 'header'
}) {
  const { ref, inView } = useInView<HTMLDivElement>({ margin: '0px 0px -8% 0px' })
  const reduced = useReducedMotion()
  const Tag = motion[as]

  if (reduced) {
    const Plain = as
    return (
      <Plain ref={ref as never} className={className}>
        {children}
      </Plain>
    )
  }

  return (
    <Tag
      ref={ref as never}
      className={className}
      initial={{ opacity: 0, y: 22, scale: 0.98, filter: 'blur(6px)' }}
      animate={inView ? { opacity: 1, y: 0, scale: 1, filter: 'blur(0px)' } : undefined}
      transition={{ duration: 0.78, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </Tag>
  )
}

/* ------------------------------------------------------------------ */
/* Section shell                                                       */
/* ------------------------------------------------------------------ */

export function MissionSection({
  id,
  index,
  eyebrow,
  title,
  sub,
  aside,
  children,
}: {
  id: string
  /** Two-digit position in the narrative — printed in the section rail. */
  index: string
  eyebrow: string
  title: ReactNode
  sub?: ReactNode
  aside?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="mi-section" id={id} aria-labelledby={`${id}-title`}>
      <Reveal className="mi-section__head">
        <div className="mi-section__marker">
          <span className="mi-section__num">{index}</span>
          <span className="mi-section__rule" aria-hidden="true" />
          <span className="oh-eyebrow">{eyebrow}</span>
        </div>
        <div className="mi-section__headrow">
          <div className="mi-section__headtext">
            <h2 className="oh-title" id={`${id}-title`}>
              {title}
            </h2>
            {sub ? <p className="oh-sub">{sub}</p> : null}
          </div>
          {aside ? <div className="mi-section__aside">{aside}</div> : null}
        </div>
      </Reveal>
      <div className="mi-section__body">{children}</div>
    </section>
  )
}

/* ------------------------------------------------------------------ */
/* Honesty surfaces                                                    */
/* ------------------------------------------------------------------ */

export function OriginTag({ status, title }: { status?: string | null; title?: string }) {
  if (!status) return null
  return <TrustBadge status={status} title={title} />
}

/**
 * The honest empty state. Two lines, always: what is missing, and why.
 * `value` is the word a conventional dashboard would have invented.
 */
export function Absence({ reason, compact = false }: { reason: string | null; compact?: boolean }) {
  return (
    <div className={`mi-absence${compact ? ' mi-absence--compact' : ''}`} role="note">
      <AlertCircle size={compact ? 13 : 15} aria-hidden="true" />
      <div>
        <b>No data available</b>
        <span>{reason ?? 'This value is not present in the current observation store.'}</span>
      </div>
    </div>
  )
}

export function Loading({ label }: { label: string }) {
  return (
    <div className="mi-loading" role="status" aria-live="polite">
      <Loader2 size={14} className="mi-spin" aria-hidden="true" />
      <span>{label}</span>
    </div>
  )
}

/** Renders `data` or the structured absence — never a fallback number. */
export function ResourceBlock<T>({
  resource,
  loadingLabel,
  children,
}: {
  resource: Resource<T>
  loadingLabel: string
  children: (data: T) => ReactNode
}) {
  if (resource.loading) return <Loading label={loadingLabel} />
  if (!resource.data) return <Absence reason={resource.reason} />
  return <>{children(resource.data)}</>
}

/* ------------------------------------------------------------------ */
/* Mandatory schematic / demonstration labels                          */
/* ------------------------------------------------------------------ */

/**
 * Used anywhere a visual is composed rather than measured. The project already
 * badges its candidate map "SCHEMATIC — NOT A NAVIGATION CHART"; this carries
 * that discipline across the whole page.
 */
export function SchematicTag({ children, compact = false }: { children?: ReactNode; compact?: boolean }) {
  return (
    <span className={`mi-schematic${compact ? ' mi-schematic--compact' : ''}`}>
      <Compass size={11} aria-hidden="true" />
      {children ?? 'SCHEMATIC — NOT A NAVIGATION CHART'}
    </span>
  )
}

export function SimulatedTag({ children }: { children?: ReactNode }) {
  return (
    <span className="mi-simulated">
      <AlertCircle size={11} aria-hidden="true" />
      {children ?? 'SIMULATED — DEMONSTRATION ONLY'}
    </span>
  )
}

/** A one-line note that qualifies a claim, set apart from the claim itself. */
export function Caveat({ children, tone = 'quiet' }: { children: ReactNode; tone?: 'quiet' | 'edge' }) {
  return <p className={`mi-caveat mi-caveat--${tone}`}>{children}</p>
}
