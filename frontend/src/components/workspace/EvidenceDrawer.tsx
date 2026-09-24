/**
 * EvidenceDrawer — Phase 7 global evidence drawer.
 * Renders the SAME TideEvidence contract used by TIDE, What-If and Replay —
 * one evidence record, one renderer — so every surface is consistent.
 * Only real records are shown; unknown status renders honestly.
 */
import { useEffect } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { FileSearch, X } from 'lucide-react'
import type { TideEvidence } from '../../types/tide'
import TrustBadge from './TrustBadge'

function groupBySource(evidence: TideEvidence[]): TideEvidence[] {
  return [...evidence]
    .sort((a, b) => (a.source_system ?? '').localeCompare(b.source_system ?? ''))
}

function dedupe(evidence: TideEvidence[]): TideEvidence[] {
  const seen = new Set<string>()
  const out: TideEvidence[] = []
  for (const e of evidence) {
    const key = `${e.source_system ?? ''}|${e.evidence_id ?? ''}|${e.type}|${e.location_id ?? ''}|${e.depth_m ?? ''}`
    if (seen.has(key)) continue
    seen.add(key)
    out.push(e)
  }
  return out
}

interface Props {
  evidence: TideEvidence[]
  open: boolean
  onOpen: () => void
  onClose: () => void
}

export default function EvidenceDrawer({ evidence, open, onOpen, onClose }: Props) {
  const unique = dedupe(evidence)
  const grouped = groupBySource(unique)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  return (
    <>
      <button className="ev-tab" onClick={onOpen} aria-label="Open evidence drawer">
        <FileSearch size={14} />
        EVIDENCE
        <span className="ev-count">{unique.length}</span>
      </button>

      <AnimatePresence>
        {open && (
          <>
            <motion.div
              className="ev-backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.16 }}
              onClick={() => onClose()}
            />
            <motion.aside
              className="ev-drawer"
              role="dialog" aria-label="Evidence drawer"
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ type: 'tween', duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
            >
              <div className="ev-head">
                <FileSearch size={16} color="#8b8cf8" />
                <b>Global Evidence Drawer</b>
                <span className="ev-count">{unique.length} records</span>
                <button className="ev-close" onClick={() => onClose()} aria-label="Close evidence drawer">
                  <X size={16} />
                </button>
              </div>

              <div className="ev-body">
                {grouped.length === 0 ? (
                  <div className="ev-empty">
                    <FileSearch size={26} />
                    No evidence records are currently available.
                    Evidence only appears when a real TIDE / twin / forensics signal exists.
                  </div>
                ) : (
                  grouped.map((e, i) => (
                    <div className="ev-group" key={i}>
                      <span className="ev-group-title">{e.source_system ?? 'TidalTwin'}</span>
                      <div className="ev-item">
                        <div className="ev-item-top">
                          <TrustBadge status={e.data_status ?? null} />
                          <span style={{ fontSize: 10.5, color: '#9fb4d4', fontWeight: 700 }}>
                            {e.type.replace(/_/g, ' ')}
                          </span>
                        </div>
                        <span className="ev-item-desc">{e.description}</span>
                        <div className="ev-strength">
                          <i style={{ width: `${Math.round((e.strength ?? 0) * 100)}%` }} />
                        </div>
                        <span className="ev-item-meta">
                          {e.strength != null && <span>strength {Math.round(e.strength * 100)}%</span>}
                          {e.variable != null && <span>{e.variable.replace(/_/g, ' ')}</span>}
                          {e.depth_m != null && <span>{e.depth_m} m</span>}
                          {e.location_id != null && <span>location #{e.location_id}</span>}
                          <span>{e.evidence_id ?? `ev-${i + 1}`}</span>
                        </span>
                      </div>
                    </div>
                  ))
                )}
              </div>

              <div className="ev-foot">
                One evidence contract renders everywhere (TIDE, What-If, Replay, this drawer) — no separate
                evidence system was built. SIMULATED records are demonstration-only and never written to the
                observation store.
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  )
}
