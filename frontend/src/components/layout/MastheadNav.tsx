import { Link } from 'react-router-dom'

const ANCHORS = [
  { href: '#overview', label: 'OVERVIEW' },
  { href: '#sea-level', label: 'SEA LEVEL' },
  { href: '#regions', label: 'REGIONS' },
  { href: '#tide-loop', label: 'TIDE' },
  { href: '#forensics', label: 'FORENSICS' },
  { href: '#projections', label: 'PROJECTIONS' },
]

const ROUTES = [
  { to: '/globe', label: 'DIGITAL TWIN' },
  { to: '/anomalies', label: 'ANOMALIES' },
]

/** Sticky cinematic navigation: transparent at the top of the page, frosted glass
 *  once the hero has been scrolled out of view. Anchors stay on-page; route links
 *  open real pages. "scrolled" is driven by the hero's IntersectionObserver so it
 *  works inside the app's main-content scroll container. */
export default function MastheadNav({ scrolled = false }: { scrolled?: boolean }) {
  return (
    <nav className={`masthead${scrolled ? ' masthead--scrolled' : ''}`} aria-label="Ocean command">
      <span className="masthead__logo">TIDAL<em>TWIN</em></span>
      {ANCHORS.map((a) => (
        <a key={a.href} className="mh-link" href={a.href}>{a.label}</a>
      ))}
      {ROUTES.map((r) => (
        <Link key={r.to} className="mh-link mh-link--route" to={r.to}>{r.label}</Link>
      ))}
      <span className="masthead__more">INDICATIVE SERIES · REAL TIDE ENGINE</span>
    </nav>
  )
}