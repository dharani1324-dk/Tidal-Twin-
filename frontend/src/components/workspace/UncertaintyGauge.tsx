/**
 * UncertaintyGauge — Phase 7 shows UNCERTAINTY, CONFIDENCE, OBSERVATION VALUE
 * and DECISION IMPACT as separate meters so the four concepts stay distinct.
 * Values are ratios 0..1 unless unit === 'pct'. Missing values render as
 * DATA UNAVAILABLE — never estimated.
 */
import { Gauge } from 'lucide-react'

export interface GaugeItem {
  label: string
  value: number | null
  unit?: 'pct' | 'ratio'
  color?: string
  hint?: string
}

export default function UncertaintyGauge({ items }: { items: GaugeItem[] }) {
  return (
    <div className="unc-list" role="group" aria-label="Confidence and value meters">
      {items.map((item) => {
        const pct = item.unit === 'pct' ? item.value! : item.value! * 100
        const shown = `${Math.round(pct)}%`
        const color = item.color ?? '#22d3ee'
        return (
          <div className="unc-item" key={item.label}>
            <span className="unc-label">
              <Gauge size={11} style={{ color }} />
              {item.label}
            </span>
            {item.value == null ? (
              <>
                <span className="unc-bar" />
                <span className="unc-value unc-empty">DATA UNAVAILABLE</span>
              </>
            ) : (
              <>
                <span className="unc-bar">
                  <i style={{ width: `${Math.max(0, Math.min(100, pct))}%`, background: color }} />
                </span>
                <span className="unc-value">{shown}</span>
              </>
            )}
            {item.hint && <span className="unc-hint">{item.hint}</span>}
          </div>
        )
      })}
    </div>
  )
}