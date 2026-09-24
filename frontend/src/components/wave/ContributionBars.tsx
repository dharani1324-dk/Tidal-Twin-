import { useInView } from '../ocean/hooks'

export interface Contribution {
  label: string
  pct: number
  detail: string
  color: string
}

export function ContributionBars({ items, source }: { items: Contribution[]; source: string }) {
  const { ref, inView } = useInView<HTMLDivElement>()
  const maxPct = Math.max(...items.map((i) => i.pct))

  return (
    <div ref={ref} className="contrib">
      {items.map((c, i) => (
        <div className="contrib-row" key={c.label}>
          <div className="contrib-head">
            <span className="contrib-label">{c.label}</span>
            <b className="contrib-pct">{c.pct}%</b>
          </div>
          <div className="contrib-track">
            <div
              className="contrib-fill"
              style={{
                width: `${(c.pct / maxPct) * 100}%`,
                transform: inView ? 'scaleY(1)' : 'scaleY(0)',
                transitionDelay: `${i * 120}ms`,
                background: `linear-gradient(90deg, ${c.color}, rgba(2,12,24,0.4))`,
              }}
            />
          </div>
          <span className="contrib-detail">{c.detail}</span>
        </div>
      ))}
      <div className="contrib-src">SRC: {source}</div>
    </div>
  )
}