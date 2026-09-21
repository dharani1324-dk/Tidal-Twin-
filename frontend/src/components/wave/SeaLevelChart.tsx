import { useMemo, useState } from 'react'
import { useInView, useReducedMotion } from '../ocean/hooks'
import type { SlrPoint } from '../data/slrReference'
import './SeaLevelChart.css'

const W = 720
const H = 300
const ML = 34
const MR = 54
const MT = 18
const MB = 34

function smoothPath(points: SlrPoint[], x: (v: number) => number, y: (v: number) => number): string {
  if (points.length === 0) return ''
  let d = 'M ' + x(points[0].year).toFixed(1) + ' ' + y(points[0].valueMm).toFixed(1)
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i - 1] ?? points[i]
    const p1 = points[i]
    const p2 = points[i + 1]
    const p3 = points[i + 2] ?? p2
    const c1x = x(p1.year) + (x(p2.year) - x(p0.year)) / 6
    const c1y = y(p1.valueMm) + (y(p2.valueMm) - y(p0.valueMm)) / 6
    const c2x = x(p2.year) - (x(p3.year) - x(p1.year)) / 6
    const c2y = y(p2.valueMm) - (y(p3.valueMm) - y(p1.valueMm)) / 6
    d += ' C ' + c1x.toFixed(1) + ' ' + c1y.toFixed(1) + ', ' + c2x.toFixed(1) + ' ' + c2y.toFixed(1) + ', ' + x(p2.year).toFixed(1) + ' ' + y(p2.valueMm).toFixed(1)
  }
  return d
}

export function SeaLevelChart({ points, yearStart, yearEnd, sourceLabel }: {
  points: SlrPoint[]
  yearStart: number
  yearEnd: number
  sourceLabel: string
}) {
  const { ref, inView } = useInView<HTMLDivElement>()
  const reduced = useReducedMotion()
  const [hover, setHover] = useState<SlrPoint | null>(null)

  const values = points.map((p) => p.valueMm)
  const vMin = Math.floor((Math.min(...values, 0) - 8) / 25) * 25
  const vMax = Math.ceil((Math.max(...values) + 8) / 25) * 25
  const span = vMax - vMin

  const x = useMemo(
    () => (year: number) => ML + ((year - yearStart) / (yearEnd - yearStart)) * (W - ML - MR),
    [yearStart, yearEnd],
  )
  const y = useMemo(
    () => (v: number) => MT + (1 - (v - vMin) / span) * (H - MT - MB),
    [vMin, span],
  )

  const lineD = useMemo(() => smoothPath(points, x, y), [points, x, y])
  const areaD = useMemo(() => {
    if (points.length === 0) return ''
    const first = points[0]
    const last = points[points.length - 1]
    const bottom = MT + (H - MT - MB)
    return `${lineD} L ${x(last.year).toFixed(1)} ${bottom} L ${x(first.year).toFixed(1)} ${bottom} Z`
  }, [points, lineD, x])

  const onMove = (e: { currentTarget: SVGSVGElement; clientX: number; clientY: number }) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const px = ((e.clientX - rect.left) / rect.width) * W
    const year = yearStart + ((px - ML) / (W - ML - MR)) * (yearEnd - yearStart)
    const idx = Math.max(0, Math.min(points.length - 1, Math.round(year - yearStart)))
    setHover(points[idx])
  }

  const gridVals: number[] = []
  for (let v = vMin; v <= vMax; v += 25) gridVals.push(v)
  const yearTicks = [1993, 2000, 2010, 2020, 2026]
  const drawn = inView && !reduced

  return (
    <div className="slr-wrap" ref={ref}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label="Global mean sea level change relative to 1993, in millimetres, indicative NASA/NOAA altimetry composite"
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
      >
        <defs>
          <linearGradient id="slrFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#00D4FF" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#00FFB3" stopOpacity="0.02" />
          </linearGradient>
          <linearGradient id="slrStroke" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#00D4FF" />
            <stop offset="100%" stopColor="#00FFB3" />
          </linearGradient>
        </defs>

        {gridVals.map((v) => (
          <g key={v}>
            <line x1={ML} x2={W - MR} y1={y(v)} y2={y(v)} className="slr-gridline" />
            <text x={W - MR + 8} y={y(v) + 3.5} className="slr-axis-num">{v}</text>
          </g>
        ))}
        <line x1={ML} x2={W - MR} y1={y(0)} y2={y(0)} className="slr-base" />
        <path d={areaD} fill="url(#slrFill)" className="slr-area" />

        <path
          d={lineD}
          pathLength={1}
          fill="none"
          stroke="url(#slrStroke)"
          strokeWidth={2.4}
          strokeLinecap="round"
          className="slr-line"
          style={{ strokeDasharray: 1, strokeDashoffset: drawn ? 0 : 1 }}
        />

        {hover && (
          <g>
            <line x1={x(hover.year)} x2={x(hover.year)} y1={MT} y2={H - MB} className="slr-hair" />
            <circle cx={x(hover.year)} cy={y(hover.valueMm)} r={4.5} className="slr-hover-dot" />
          </g>
        )}

        {yearTicks.map((yr) => (
          <text key={yr} x={x(yr)} y={H - MB + 16} className="slr-year" textAnchor="middle">{yr}</text>
        ))}
        <text x={ML} y={H - MB + 34} className="slr-axis-num">mm vs 1993</text>
      </svg>

      {hover && (
        <div
          className="slr-tooltip"
          style={{ left: `${(x(hover.year) / W) * 100}%`, top: `${(y(hover.valueMm) / H) * 100}%` }}
          role="status"
        >
          <div className="slr-tt-row"><span>YEAR</span><b>{hover.year}</b></div>
          <div className="slr-tt-row"><span>VALUE</span><b>{hover.valueMm >= 0 ? '+' : ''}{hover.valueMm} mm</b></div>
          <div className="slr-tt-row"><span>UNIT</span><b>mm (relative)</b></div>
          <div className="slr-tt-row"><span>SOURCE</span><b className="slr-tt-src">{sourceLabel}</b></div>
        </div>
      )}
    </div>
  )
}