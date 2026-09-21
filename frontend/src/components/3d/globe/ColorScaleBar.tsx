import type { ScaleDomain, ScaleMode } from './layerMath'
import { kForValue } from './layerMath'

export interface ColorScaleBarProps {
  /** Short layer name shown above the bar (e.g. "ERSST v5 SST"). */
  label: string
  /** Physical unit of the values (e.g. "°C", "mg/m³"). */
  unit: string
  /** Live min/max of the real grid. `null` hides the bar (no data). */
  domain: ScaleDomain | null
  /** Current Linear/Log mode. */
  mode: ScaleMode
  /** Called when the user toggles the scale. */
  onModeChange?: (mode: ScaleMode) => void
  /** A single value to pin on the bar (e.g. the active region's cell). */
  value?: number | null
  /** Gradient stops, left → right (e.g. cold → hot). */
  stops?: string[]
  /** Optional formatter for the min/max/current labels. */
  format?: (value: number) => string
}

function fmtDefault(value: number): string {
  if (!Number.isFinite(value)) return '—'
  const abs = Math.abs(value)
  return abs >= 100 ? value.toFixed(0) : abs >= 1 ? value.toFixed(1) : value.toFixed(2)
}

/** Data-driven continuous colour scale for the real grid layers:
 *  gradient bar + live min/max range + Linear/Log toggle + value pin. */
export default function ColorScaleBar({
  label,
  unit,
  domain,
  mode,
  onModeChange,
  value,
  stops = ['#22d3ee', '#ff8a28'],
  format = fmtDefault,
}: ColorScaleBarProps) {
  if (domain === null) return null

  const fmt = (v: number | null) => (v === null ? '—' : format(v))
  const hasPin = value !== null && value !== undefined && Number.isFinite(value)
  const pct = hasPin ? kForValue(value!, domain, mode) * 100 : null
  const wrap = stops.length === 1 ? [stops[0], stops[0]] : stops

  return (
    <div className="colorbar" aria-label={`${label} colour scale (${mode})`}>
      <div className="colorbar-head">
        <span className="colorbar-label">{label}</span>
        <span className="colorbar-unit">{unit}</span>
      </div>
      <div className="colorbar-track-wrap">
        <div
          className="colorbar-track"
          style={{ background: `linear-gradient(90deg, ${wrap.join(', ')})` }}
        >
          {pct !== null && (
            <span className="colorbar-pin" style={{ left: `${pct}%` }} title={`${format(value!)} ${unit}`} />
          )}
        </div>
      </div>
      <div className="colorbar-foot">
        <span className="colorbar-min">{fmt(domain.min)}</span>
        {onModeChange ? (
          <span className="colorbar-scale" role="group" aria-label="Scale">
            <button
              type="button"
              className={mode === 'linear' ? 'on' : ''}
              onClick={() => onModeChange('linear')}
            >
              Linear
            </button>
            <button
              type="button"
              className={mode === 'log' ? 'on' : ''}
              onClick={() => onModeChange('log')}
            >
              Log
            </button>
          </span>
        ) : (
          <span className="colorbar-mode">{mode}</span>
        )}
        <span className="colorbar-max">{fmt(domain.max)}</span>
      </div>
    </div>
  )
}