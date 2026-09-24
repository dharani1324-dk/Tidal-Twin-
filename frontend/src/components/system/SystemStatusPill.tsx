/**
 * Phase 9 — live system-status indicator.
 * Uses the REAL /api/v1/health payload. Never shows "healthy" unless the
 * backend reports it. Colour is never the only signal: every state also has a
 * text label and a title.
 */
import { useEffect, useRef, useState } from 'react'
import { Activity } from 'lucide-react'
import { fetchSystemHealth } from '../../api/client'
import type { SystemHealthResponse } from '../../types/system'
import './SystemStatusPill.css'

const CHECK_LABELS: Record<string, string> = {
  backend: 'Backend',
  database: 'Database',
  ocean_data: 'Ocean data',
  tide: 'TIDE',
  copilot: 'Copilot',
  cesium: 'Cesium',
}

const CHECK_ORDER = ['backend', 'database', 'ocean_data', 'tide', 'copilot', 'cesium']

function toneFor(status?: string): string {
  switch ((status ?? '').toUpperCase()) {
    case 'AVAILABLE':
      return 'ok'
    case 'LIMITED':
      return 'warn'
    case 'OPTIONAL / UNAVAILABLE':
      return 'off'
    default:
      return 'crit'
  }
}

export default function SystemStatusPill() {
  const [health, setHealth] = useState<SystemHealthResponse | null>(null)
  const [offline, setOffline] = useState(false)
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const res = await fetchSystemHealth()
        if (!alive) return
        setHealth(res)
        setOffline(false)
      } catch {
        if (alive) setOffline(true)
      }
    }
    load()
    const poll = setInterval(load, 60000)
    return () => {
      alive = false
      clearInterval(poll)
    }
  }, [])

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  const dataUnavailable = health?.checks?.ocean_data?.status === 'UNAVAILABLE'
  const overall = offline
    ? 'OFFLINE'
    : !health
      ? '…'
      : health.status === 'healthy'
        ? 'ONLINE'
        : health.status === 'degraded'
          ? 'DEGRADED'
          : dataUnavailable
            ? 'DATA UNAVAILABLE'
            : 'UNAVAILABLE'
  const tone = offline ? 'crit' : health?.status === 'healthy' ? 'ok' : health?.status === 'degraded' ? 'warn' : health ? 'crit' : 'off'
  const simulationMode = !offline && Boolean(health?.simulation_mode)

  return (
    <div className="sys-pill-wrap" ref={ref}>
      <button
        type="button"
        className={`status-tag ${tone} sys-pill-btn`}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => setOpen((v) => !v)}
        title="System status"
      >
        <Activity size={11} /> <b>SYSTEM</b> {overall}
      </button>

      {simulationMode && (
        <span className="status-tag off sys-sim-tag" title="Labelled demonstration rows are present (SIMULATION MODE).">
          SIM
        </span>
      )}

      {open && (
        <div className="sys-pop" role="dialog" aria-label="System status details">
          <div className="sys-pop-head">
            <b>SYSTEM STATUS</b>
            <span>
              {offline
                ? 'Backend unreachable'
                : health
                  ? `v${health.version} · ${health.environment ?? 'unknown'} · ${new Date(health.checked_at).toLocaleTimeString()}`
                  : 'checking…'}
            </span>
          </div>
          <div className="sys-pop-list">
            {offline && <div className="sys-pop-row"><span className="sys-pop-dot crit" />Backend<span className="sys-pop-state crit">UNAVAILABLE</span></div>}
            {!offline && !health && <div className="sys-pop-empty">Checking subsystems…</div>}
            {health &&
              CHECK_ORDER.filter((k) => health.checks[k]).map((key) => {
                const check = health.checks[key]
                const t = toneFor(check.status)
                return (
                  <div className="sys-pop-row" key={key} title={check.detail}>
                    <span className={`sys-pop-dot ${t}`} />
                    {CHECK_LABELS[key] ?? key}
                    <span className={`sys-pop-state ${t}`}>{check.status}</span>
                  </div>
                )
              })}
          </div>
          <p className="sys-pop-foot">
            {simulationMode
              ? 'SIMULATION MODE: labelled demonstration rows are present. They are always marked SIMULATED and are never presented as real observations.'
              : 'Optional services may be unavailable without affecting core TIDE analysis. No values are fabricated during an outage.'}
          </p>
        </div>
      )}
    </div>
  )
}
