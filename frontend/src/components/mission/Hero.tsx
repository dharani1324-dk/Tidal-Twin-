/**
 * Mission Intro — Section 00/01, the cinematic opening
 * ====================================================
 * A full-bleed ocean-surface opening that establishes the product's thesis
 * before any product surface appears:
 *
 *     TidalTwin is not another ocean viewer.
 *     It decides where the next observation should be spent, and shows its work.
 *
 * The visuals are deliberately *not* a globe. A 3D globe in the first viewport
 * would say "here is a map", which is precisely the wrong promise for a page
 * about deciding what to measure. Instead: bathymetric isobath contours, depth
 * markers, drifting motes, and one line of caustic light.
 *
 * The status strip under the CTA is real, live-on-load telemetry from
 * /api/v1/twin/sources, /api/v1/tide/candidates and the observation ledger. It
 * disappears rather than fakes anything if a request fails.
 */
import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, ChevronDown, Radar, Waves } from 'lucide-react'
import { ParticleLayer } from '../ocean/effects'
import { useInView, useReducedMotion } from '../ocean/hooks'
import { Reveal } from './Primitives'
import type { MissionCore } from './missionData'
import { formatTimestamp } from './missionData'

/* ------------------------------------------------------------------ */
/* Bathymetric isobath field                                           */
/* ------------------------------------------------------------------ */

/**
 * A cheap analytic bathymetry field: a continental shelf falling to a basin,
 * built from a few sine terms. Iso-contours are traced per row, which is far
 * cheaper than per-pixel marching squares and gives the same "chart" reading.
 *
 * Cost control: DPR capped at 1.5, ~44 contour rows, no shadow blur, no
 * per-pixel work, and the loop is suspended entirely when scrolled away.
 */
function IsobathField() {
  const { ref, inView } = useInView<HTMLCanvasElement>({ once: false, margin: '120px' })
  const reduced = useReducedMotion()

  useEffect(() => {
    const canvas = ref.current
    if (!canvas || !inView) return
    const ctx = canvas.getContext('2d', { alpha: true })
    if (!ctx) return

    const DPR_CAP = 1.5
    let w = 0
    let h = 0
    let raf = 0
    let running = true
    const t0 = performance.now()

    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      const dpr = Math.min(window.devicePixelRatio || 1, DPR_CAP)
      w = Math.max(1, Math.round(rect.width))
      h = Math.max(1, Math.round(rect.height))
      canvas.width = Math.round(w * dpr)
      canvas.height = Math.round(h * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    resize()
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null
    ro?.observe(canvas)

    /** Elevation proxy in [-1, 1]; negative is deeper. */
    const field = (x: number, y: number, t: number) => {
      const u = x / Math.max(w, 1)
      const v = y / Math.max(h, 1)
      const shelf = -0.55 * Math.sin(u * 2.1 + 0.6) * (1 - v * 0.65)
      const drift = 0.12 * Math.sin(u * 5.3 + t * 0.00018)
      const ripple = 0.05 * Math.sin(u * 11.0 + v * 4.0 - t * 0.0004)
      return shelf + drift + ripple
    }

    const draw = (now: number) => {
      if (!running) return
      ctx.clearRect(0, 0, w, h)
      const rows = 46
      const step = 5
      ctx.lineWidth = 1

      for (let r = 0; r < rows; r += 1) {
        const y = (h / rows) * r + 1
        // Depth band drives hue: shallow shelves warm-cyan, basin deep indigo.
        const depth = r / rows
        const level = 0.42 - depth * 0.95
        const alpha = (0.05 + (1 - depth) * 0.16).toFixed(3)
        const stroke =
          depth > 0.66
            ? `rgba(4,86,148,${alpha})`
            : depth > 0.33
              ? `rgba(0,212,255,${alpha})`
              : `rgba(0,255,179,${alpha})`

        ctx.beginPath()
        let started = false
        for (let x = 0; x <= w; x += step) {
          const value = field(x, y, now)
          if (Math.abs(value - level) < 0.02) {
            const py = y + value * 26
            if (started) ctx.lineTo(x, py)
            else {
              ctx.moveTo(x, py)
              started = true
            }
          } else {
            started = false
          }
        }
        ctx.strokeStyle = stroke
        ctx.stroke()
      }

      // One slow caustic band — the only "light" in the composition.
      const sweep = ((now - t0) % 14000) / 14000
      const grad = ctx.createLinearGradient(0, sweep * h - h * 0.3, 0, sweep * h + h * 0.3)
      grad.addColorStop(0, 'rgba(0,212,255,0)')
      grad.addColorStop(0.5, 'rgba(0,212,255,0.05)')
      grad.addColorStop(1, 'rgba(0,212,255,0)')
      ctx.fillStyle = grad
      ctx.fillRect(0, sweep * h - h * 0.3, w, h * 0.6)

      if (!reduced) raf = requestAnimationFrame(draw)
    }

    const onVisibility = () => {
      running = !document.hidden
      if (running) raf = requestAnimationFrame(draw)
      else cancelAnimationFrame(raf)
    }

    if (reduced) {
      // One static chart. The opening still reads as an ocean; it just stops moving.
      draw(t0)
    } else {
      raf = requestAnimationFrame(draw)
      document.addEventListener('visibilitychange', onVisibility)
    }
    return () => {
      running = false
      cancelAnimationFrame(raf)
      ro?.disconnect()
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [ref, inView, reduced])

  return <canvas ref={ref} className="mi-hero__isobaths" aria-hidden="true" />
}

/* ------------------------------------------------------------------ */
/* Real status strip                                                   */
/* ------------------------------------------------------------------ */

function StatusStrip({ core }: { core: MissionCore }) {
  const sources = core.sources.data?.health
  const candidates = core.candidates.data?.length
  const ledger = core.demo.data
  const sites = core.disagreement.data?.points?.length
  const generated = core.sources.data?.generated_at

  const cells: { label: string; value: string; hint?: string }[] = []

  if (sources) {
    cells.push({
      label: 'DATA SOURCES ONLINE',
      value: `${sources.online} / ${sources.total}`,
      hint: sources.degraded.length ? `Degraded: ${sources.degraded.join(', ')}` : 'All registered sources reporting',
    })
  }
  if (ledger) {
    cells.push({
      label: 'LEDGER OBSERVATIONS',
      value: String(ledger.total_observations),
      hint: `${ledger.real_observations} real · ${ledger.simulated_observations} simulated — counted separately, never blended`,
    })
  }
  if (candidates != null) {
    cells.push({
      label: 'TIDE RANKED SITES',
      value: String(candidates),
      hint: 'Locations the ranking engine scored for this request',
    })
  }
  if (sites != null) {
    cells.push({
      label: 'LOCATIONS COMPARED',
      value: String(sites),
      hint: 'Reference locations where a model value has an observation to compare against',
    })
  }

  return (
    <div className="mi-hero__status" aria-live="polite">
      {cells.length === 0 ? (
        <p className="mi-hero__status-idle">
          <Radar size={13} aria-hidden="true" />
          Querying the twin — figures appear once the data server answers.
        </p>
      ) : (
        cells.map((c) => (
          <div className="mi-hero__stat" key={c.label}>
            <b>{c.value}</b>
            <span>{c.label}</span>
            {c.hint ? <i title={c.hint}>{c.hint}</i> : null}
          </div>
        ))
      )}
      {generated ? (
        <p className="mi-hero__status-time">source registry read {formatTimestamp(generated)} IST</p>
      ) : null}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Hero                                                                */
/* ------------------------------------------------------------------ */

export default function Hero({ core }: { core: MissionCore }) {
  return (
    <section className="mi-hero" id="overview" aria-label="TidalTwin mission">
      <IsobathField />
      <div className="mi-hero__vignette" aria-hidden="true" />
      <video className="mi-bg-video" autoPlay muted loop playsInline aria-hidden="true" tabIndex={-1}>
        <source src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260809_012548_ef22562c-c0ae-4816-ad9f-f8922af4e6a7.mp4" type="video/mp4" />
      </video>
      <div className="mi-hero__particles" aria-hidden="true">
        <ParticleLayer count={54} />
      </div>

      <div className="mi-hero__content">
        <Reveal className="mi-hero__eyebrow">
          <Waves size={14} aria-hidden="true" />
          <span>4D OCEAN DIGITAL TWIN</span>
          <span className="mi-hero__eyebrow-dim">· TRUST-AWARE OBSERVATION PLANNING</span>
        </Reveal>

        <Reveal className="mi-hero__title" delay={0.08}>
          <h1>
            <span className="mi-hero__mark">Where Should<br />We Measure Next?</span>
            <span className="mi-hero__thesis">
              TidalTwin turns ocean uncertainty into an observable decision.
            </span>
          </h1>
        </Reveal>

        <Reveal className="mi-hero__lede" delay={0.16}>
          <p>
            A 4D digital twin of the Indian Ocean that compares models with real observations,
            investigates disagreement, and identifies where the next measurement could provide the
            most decision value.
          </p>
        </Reveal>

        <Reveal className="mi-hero__cta" delay={0.24}>
          <Link className="oh-btn oh-btn--solid" to="/globe">
            EXPLORE THE DIGITAL TWIN
            <ArrowRight size={15} />
          </Link>
          <Link className="oh-btn oh-btn--ghost" to="/tide">
            SEE HOW TIDE WORKS
          </Link>
          <p className="mi-hero__cta-note">
            <span>MODEL <span aria-hidden="true">↔</span> REALITY</span>
            <span>OBSERVE · COMPARE · EXPLAIN · PRIORITIZE</span>
          </p>
        </Reveal>

        <Reveal className="mi-hero__strip" delay={0.32}>
          <StatusStrip core={core} />
        </Reveal>
      </div>

      <a className="mi-hero__scroll" href="#problem">
        <ChevronDown size={16} aria-hidden="true" />
        <span>SCROLL TO BEGIN</span>
      </a>
    </section>
  )
}
