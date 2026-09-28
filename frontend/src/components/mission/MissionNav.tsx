/**
 * Mission Intro — command navigation
 * ===================================
 * A restrained, transparent-top / frosted-on-scroll header. Anchors stay on
 * this page; "ENTER TWIN" leaves it for the real Digital Twin.
 *
 * Desktop: brand · five anchors · ENTER TWIN.
 * Mobile:  brand + a circular menu control that opens a full-screen dark
 *          mission menu (not a shrunken desktop bar).
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Menu, X } from 'lucide-react'
import { useReducedMotion } from '../ocean/hooks'

const ANCHORS = [
  { id: 'problem', label: 'MISSION' },
  { id: 'twin', label: 'THE TWIN' },
  { id: 'sources', label: 'DATA' },
  { id: 'loop', label: 'INTELLIGENCE' },
  { id: 'tide', label: 'TIDE' },
  { id: 'honesty', label: 'SCIENCE' },
  { id: 'domains', label: 'DOMAINS' },
] as const

export default function MissionNav() {
  const [scrolled, setScrolled] = useState(false)
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState<string>('')
  const reduced = useReducedMotion()

  // Frost the bar once the cinematic opening is behind us. Observed rather than
  // scroll-driven so it costs one boolean, not a scroll handler.
  useEffect(() => {
    const hero = document.getElementById('overview')
    if (!hero || typeof IntersectionObserver === 'undefined') return
    const io = new IntersectionObserver(
      ([entry]) => setScrolled(!entry.isIntersecting),
      { threshold: 0, rootMargin: '-72px 0px 0px 0px' },
    )
    io.observe(hero)
    return () => io.disconnect()
  }, [])

  // Scroll-spy over the narrative sections.
  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return
    const nodes = ANCHORS.map((a) => document.getElementById(a.id)).filter(
      (n): n is HTMLElement => n != null,
    )
    if (nodes.length === 0) return
    const io = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0]
        if (visible) setActive(visible.target.id)
      },
      { rootMargin: '-25% 0px -60% 0px', threshold: [0, 0.15, 0.4] },
    )
    nodes.forEach((n) => io.observe(n))
    return () => io.disconnect()
  }, [])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  useEffect(() => {
    document.body.classList.toggle('drawer-open', open)
    return () => document.body.classList.remove('drawer-open')
  }, [open])

  const jump = (id: string) => {
    setOpen(false)
    const el = document.getElementById(id)
    if (!el) return
    el.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' })
  }

  return (
    <>
      <header className={`mi-nav${scrolled ? ' mi-nav--solid' : ''}`}>
        <button
          type="button"
          className="mi-nav__brand"
          onClick={() => jump('overview')}
          aria-label="TidalTwin — back to the top"
        >
          TIDAL<span>TWIN</span>
        </button>

        <nav className="mi-nav__links" aria-label="Mission sections">
          {ANCHORS.map((a) => (
            <button
              key={a.id}
              type="button"
              className={`mi-nav__link${active === a.id ? ' is-active' : ''}`}
              onClick={() => jump(a.id)}
              aria-current={active === a.id ? 'true' : undefined}
            >
              {a.label}
            </button>
          ))}
        </nav>

        <div className="mi-nav__actions">
          <Link className="mi-nav__enter" to="/globe">
          Enter TidalTwin
          </Link>
          <button
            type="button"
            className="mi-nav__burger"
            onClick={() => setOpen(true)}
            aria-label="Open mission menu"
            aria-expanded={open}
          >
            <Menu size={18} />
          </button>
        </div>
      </header>

      {open && (
        <div className="mi-menu" role="dialog" aria-modal="true" aria-label="Mission menu">
          <div className="mi-menu__grid" aria-hidden="true" />
          <div className="mi-menu__top">
            <span className="mi-menu__brand">
              TIDAL<span>TWIN</span>
            </span>
            <button
              type="button"
              className="mi-menu__close"
              onClick={() => setOpen(false)}
              aria-label="Close mission menu"
            >
              <X size={20} />
            </button>
          </div>
          <nav className="mi-menu__list" aria-label="Mission sections">
            {ANCHORS.map((a, i) => (
              <button
                key={a.id}
                type="button"
                className="mi-menu__item"
                onClick={() => jump(a.id)}
                style={{ animationDelay: reduced ? '0ms' : `${60 + i * 55}ms` }}
              >
                <em>{String(i + 1).padStart(2, '0')}</em>
                <span>{a.label}</span>
              </button>
            ))}
          </nav>
          <Link className="mi-menu__cta" to="/globe" onClick={() => setOpen(false)}>
            ENTER TWIN →
          </Link>
          <p className="mi-menu__foot">4D OCEAN DIGITAL TWIN · TRUST-AWARE</p>
        </div>
      )}
    </>
  )
}
