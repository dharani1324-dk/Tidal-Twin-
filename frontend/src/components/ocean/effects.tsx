import { useEffect, useRef } from 'react'
import { useReducedMotion } from './hooks'

/** CSS ocean grid backdrop (pure presentational layer). */
export function OceanGrid() {
  return <div className="oh-grid-bg" aria-hidden="true" />
}

interface Particle {
  x: number
  y: number
  r: number
  vx: number
  vy: number
  hue: 'cyan' | 'teal'
  tw: number
}

/** Drifting particle field on <canvas>. rAF is cancelled on unmount; particles
 *  are drawn statically when the user prefers reduced motion. */
export function ParticleLayer({ count = 90 }: { count?: number }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const reduced = useReducedMotion()

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const parent = canvas.parentElement
    if (!parent) return

    let width = parent.clientWidth
    let height = parent.clientHeight
    const dpr = Math.min(2, window.devicePixelRatio || 1)
    const resize = () => {
      width = parent.clientWidth
      height = parent.clientHeight
      canvas.width = width * dpr
      canvas.height = height * dpr
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    resize()
    window.addEventListener('resize', resize)

    const n = Math.max(12, Math.min(count, Math.floor(width / 9)))
    const particles: Particle[] = Array.from({ length: n }, () => {
      const cyan = Math.random() > 0.55
      return {
        x: Math.random() * width,
        y: Math.random() * height,
        r: 0.6 + Math.random() * 1.4,
        vx: (Math.random() - 0.5) * 0.12,
        vy: -0.02 - Math.random() * 0.1,
        hue: cyan ? 'cyan' : 'teal',
        tw: 0.4 + Math.random() * 0.6,
      }
    })

    let raf = 0
    const draw = (t: number) => {
      ctx.clearRect(0, 0, width, height)
      for (const p of particles) {
        const alpha = p.tw * (0.35 + 0.3 * Math.sin(t / 1400 + p.x))
        ctx.fillStyle = p.hue === 'cyan'
          ? `rgba(0, 212, 255, ${alpha})`
          : `rgba(0, 255, 179, ${alpha})`
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
        ctx.fill()
        p.x += p.vx
        p.y += p.vy
        if (p.x < -4) p.x = width + 4
        if (p.x > width + 4) p.x = -4
        if (p.y < -4) p.y = height + 4
        if (p.y > height + 4) p.y = -4
      }
      if (!reduced) raf = requestAnimationFrame(draw)
    }

    if (reduced) {
      draw(0)
    } else {
      raf = requestAnimationFrame(draw)
    }

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
    }
  }, [count, reduced])

  return <canvas ref={canvasRef} className="oh-particles" aria-hidden="true" />
}

/** Expanding sonar rings. Quiet when reduced motion is preferred. */
export function SonarPulse({ active = true }: { active?: boolean }) {
  const reduced = useReducedMotion()
  if (!active) return null
  return (
    <div className="oh-sonar" aria-hidden="true">
      <span className="oh-sonar__ring" style={reduced ? { animation: 'none', opacity: 0.12 } : undefined} />
      <span className="oh-sonar__ring" style={reduced ? { animation: 'none', opacity: 0.12 } : undefined} />
      <span className="oh-sonar__ring" style={reduced ? { animation: 'none', opacity: 0.12 } : undefined} />
    </div>
  )
}

/** Vertical depth rail — SURFACE → abyss, JetBrains Mono labels. */
export function DepthMarkers({ marks }: { marks: Array<{ value: string; label: string }> }) {
  return (
    <div className="oh-depth" aria-hidden="true">
      {marks.map((m) => (
        <span className="oh-depth__mark" key={m.value}>
          <b>{m.value}</b>&nbsp;{m.label}
        </span>
      ))}
    </div>
  )
}