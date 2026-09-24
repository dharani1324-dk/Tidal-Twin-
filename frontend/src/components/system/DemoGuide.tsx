/**
 * Phase 9 — one-click TIDE demonstration launcher + dismissible guide.
 *
 * The guide only NAVIGATES the real application. It never fabricates a
 * calculation or animation. Demonstration data is always labelled.
 */
import { useCallback, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Beaker, ChevronRight, RotateCcw, X } from 'lucide-react'
import { fetchDemoStatus, resetDemoData, seedDemoData } from '../../api/client'
import type { DemoStatusResponse } from '../../types/system'
import './DemoGuide.css'

const DISMISS_KEY = 'tidaltwin.demo.guide.hidden'

export default function DemoGuide() {
  const navigate = useNavigate()
  const location = useLocation()
  const [open, setOpen] = useState(false)
  const [hidden, setHidden] = useState(() => localStorage.getItem(DISMISS_KEY) === '1')
  const [status, setStatus] = useState<DemoStatusResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setStatus(await fetchDemoStatus())
    } catch {
      setStatus(null)
      setError('Demonstration status is unavailable (backend unreachable).')
    } finally {
      setLoading(false)
    }
  }, [])

  const openGuide = () => {
    setOpen(true)
    localStorage.removeItem(DISMISS_KEY)
    setHidden(false)
    if (!status) load()
  }

  const dismiss = () => {
    setOpen(false)
    localStorage.setItem(DISMISS_KEY, '1')
    setHidden(true)
  }

  const doSeed = async () => {
    setBusy(true)
    setMessage(null)
    setError(null)
    try {
      const res = await seedDemoData()
      setMessage(
        res.skipped
          ? `Demo data already present (${res.reason ?? ''})`
          : `Created ${res.created} SIMULATED observation(s); detected events: ${res.detected_events ?? 0}.`,
      )
      await load()
    } catch {
      setError('Could not seed demonstration data.')
    } finally {
      setBusy(false)
    }
  }

  const doReset = async () => {
    setBusy(true)
    setMessage(null)
    setError(null)
    try {
      const res = await resetDemoData()
      setMessage(`Reset removed ${res.deleted} simulation row(s). Real observations untouched.`)
      await load()
    } catch {
      setError('Could not reset demonstration data.')
    } finally {
      setBusy(false)
    }
  }

  const demoEvent = status?.demonstration_event

  return (
    <>
      <button
        type="button"
        className={`demo-launch ${open ? 'active' : ''}`}
        onClick={openGuide}
        aria-expanded={open}
        title="Start the guided TIDE demonstration"
      >
        <Beaker size={13} />
        <span>{hidden ? 'RESUME DEMO' : 'START TIDE DEMO'}</span>
      </button>

      {open && (
        <aside className="demo-guide" role="dialog" aria-label="TIDE demonstration guide">
          <header className="demo-guide-head">
            <div>
              <b>TIDE DEMONSTRATION</b>
              <span className="demo-guide-sub">
                {status?.demo_data_present ? 'DEMONSTRATION DATA active' : 'No demonstration data loaded'}
              </span>
            </div>
            <button className="demo-guide-x" onClick={dismiss} aria-label="Hide demonstration guide">
              <X size={16} />
            </button>
          </header>

          {status?.demo_data_present && (
            <div className="demo-guide-marker" title={status.labels.simulated_observation}>
              {status.labels.dataset} · {status.simulated_observations} SIMULATED row(s)
            </div>
          )}

          {loading && <p className="demo-guide-note">Loading demonstration status…</p>}

          <ol className="demo-steps">
            {(status?.guide_steps ?? []).map((step) => {
              const current = location.pathname === step.route
              return (
                <li key={step.step} className={current ? 'current' : ''}>
                  <button onClick={() => navigate(step.route)} title={step.description}>
                    <span className="demo-step-num">{step.step}</span>
                    <span className="demo-step-txt">{step.title}</span>
                    <ChevronRight size={13} />
                  </button>
                </li>
              )
            })}
          </ol>

          {!loading && status && (
            <div className="demo-guide-event">
              {demoEvent?.available ? (
                <>
                  <b>DEMONSTRATION EVENT</b>
                  <span>
                    {demoEvent.label ?? demoEvent.event_type} — {demoEvent.location}
                    {typeof demoEvent.completeness_score === 'number' && ` · ${demoEvent.completeness_score}/4 criteria`}
                  </span>
                  <em>{demoEvent.reason}</em>
                </>
              ) : (
                <>
                  <b>DEMONSTRATION EVENT</b>
                  <span>Not available.</span>
                  <em>{demoEvent?.reason ?? 'No detected events in the current dataset.'}</em>
                </>
              )}
            </div>
          )}

          {error && <p className="demo-guide-error" role="alert">{error}</p>}
          {message && <p className="demo-guide-message">{message}</p>}

          <footer className="demo-guide-foot">
            {status && !status.demo_data_present ? (
              <button className="demo-btn primary" onClick={doSeed} disabled={busy}>
                Seed demonstration data
              </button>
            ) : (
              <button className="demo-btn" onClick={doSeed} disabled={busy}>
                Re-seed if stale
              </button>
            )}
            <button className="demo-btn" onClick={doReset} disabled={busy}>
              <RotateCcw size={12} /> Reset demo
            </button>
          </footer>
          <p className="demo-guide-legal">
            Simulated observations are labelled and excluded from real-observation reporting. Reset
            deletes only simulation rows.
          </p>
        </aside>
      )}
    </>
  )
}
