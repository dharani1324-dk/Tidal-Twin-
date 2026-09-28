/**
 * TidalTwin — Mission Intro data layer
 * ====================================
 * Every figure rendered on the Mission Intro comes from the real backend.
 * Nothing here fabricates a measurement, and a failed or empty response never
 * degrades into a plausible-looking number: it becomes a *structured absence*
 * carrying a reason, which is the same `available:false + reason` contract the
 * API itself uses.
 *
 * Fetch discipline (this page must not slow the rest of the app down):
 *   - mounted once, never polled
 *   - each request fails independently, so one dead endpoint cannot blank the
 *     page (the pattern already used by Decision Intelligence)
 *   - the two expensive reports (benchmark + decision replay) are deferred
 *     until their section scrolls into view
 */
import { useEffect, useState } from 'react'
import {
  fetchDataSources,
  fetchDemoStatus,
  fetchDecisionReplay,
  fetchSystemHealth,
  fetchTideBenchmarks,
  fetchTideCandidates,
  fetchTideEventIndex,
  fetchTideValidationStatus,
  fetchTwinDisagreement,
} from '../../api/client'
import type { DemoStatusResponse, SystemHealthResponse } from '../../types/system'
import type {
  DecisionReplay,
  TideBenchmarkReport,
  TideCandidate,
  TideValidationStatus,
} from '../../types/tide'

/* ------------------------------------------------------------------ */
/* Provenance vocabulary                                                */
/* ------------------------------------------------------------------ */

/** Mirrors `origin_status` across the backend models and TrustBadge.tsx. */
export type OriginStatus =
  | 'REAL'
  | 'HISTORICAL'
  | 'MODEL_DERIVED'
  | 'DERIVED'
  | 'SIMULATED'
  | 'SYNTHETIC'
  | 'UNKNOWN'

export const PROVENANCE_STATES: { status: OriginStatus; means: string }[] = [
  { status: 'REAL', means: 'Observation. A reading the system received from a source.' },
  { status: 'HISTORICAL', means: 'Archive. A stored earlier measurement, not a live feed.' },
  { status: 'MODEL_DERIVED', means: 'Model output. Produced by a numerical or statistical model.' },
  { status: 'DERIVED', means: 'Calculated. Computed from other values, never measured directly.' },
  { status: 'SIMULATED', means: 'What-if demonstration. Not collected by any sensor.' },
  { status: 'SYNTHETIC', means: 'Generated for a test or exercise. Not an observation.' },
  { status: 'UNKNOWN', means: 'Unavailable. The origin could not be established.' },
]

/* ------------------------------------------------------------------ */
/* Structured absence                                                  */
/* ------------------------------------------------------------------ */

export interface Resource<T> {
  data: T | null
  /** Present exactly when `data` is null and loading has finished. */
  reason: string | null
  loading: boolean
}

function pending<T>(): Resource<T> {
  return { data: null, reason: null, loading: true }
}

function resolved<T>(data: T): Resource<T> {
  return { data, reason: null, loading: false }
}

function missing<T>(reason: string): Resource<T> {
  return { data: null, reason, loading: false }
}

/** Turn a transport/API failure into a human-readable, non-fabricated reason. */
function reasonFor(label: string, error: unknown): string {
  const detail =
    error && typeof error === 'object' && 'response' in error
      ? (error as { response?: { data?: { detail?: { message?: string } | string } } }).response?.data
          ?.detail
      : null
  if (typeof detail === 'string' && detail) return `${label} unavailable — ${detail}`
  if (detail && typeof detail === 'object' && detail.message) {
    return `${label} unavailable — ${detail.message}`
  }
  return `${label} unavailable — the data server did not answer this request.`
}

async function load<T>(label: string, fn: () => Promise<T>): Promise<Resource<T>> {
  try {
    return resolved(await fn())
  } catch (error) {
    return missing<T>(reasonFor(label, error))
  }
}

/**
 * TIDE endpoints answer `{ success, data, error }`, so they need the envelope
 * unwrapped *and* the transport guarded. This does both without nesting one
 * `Resource` inside another.
 */
async function loadEnvelope<T>(label: string, empty: string, fn: () => Promise<unknown>) {
  try {
    return unwrap<T>(await fn(), label, empty)
  } catch (error) {
    return missing<T>(reasonFor(label, error))
  }
}

/* ------------------------------------------------------------------ */
/* Twin payload shapes we read on this page                            */
/* ------------------------------------------------------------------ */

/**
 * Mirrors `SensorPlugin.info()` as returned by /api/v1/twin/sources.
 * Only `name` and `status` are treated as guaranteed: a plugin that raises
 * returns a degraded payload instead, and the page must still render it.
 */
export interface TwinSource {
  id?: string
  name: string
  kind?: string
  status: string
  status_detail?: string
  origin_status?: string | null
  last_update?: string | null
  variables?: string[]
  coverage_pct?: number
  note?: string
}

export interface TwinSourceRegistry {
  generated_at: string
  sources: TwinSource[]
  health: { online: number; total: number; degraded: string[] }
}

export interface DisagreementRow {
  location_id: number
  location: string
  latitude: number | null
  longitude: number | null
  variable: string
  model: number | null
  observed: number | null
  difference: number | null
  percent_difference: number | null
  status: string
  severity: string | null
  band: string
  confidence: number | null
  confidence_level?: string | null
  data_status: string | null
}

export interface DisagreementMap {
  generated_at: string
  variable: string
  depth_m: number
  points: DisagreementRow[]
}

export interface TideEventIndexItem {
  event_id: string
  event_type: string
  label: string
  location_id: number
  location: string
  variable: string
  began_hours_ago: number | null
  data_status: string | null
}

/** The TIDE routers wrap every payload as `{ success, data, error }`. */
interface Envelope<T> {
  success?: boolean
  data?: T
  error?: unknown
}

function unwrap<T>(payload: unknown, label: string, empty: string): Resource<T> {
  const envelope = payload as Envelope<T> | null
  const data = envelope?.data
  if (data == null) return missing<T>(`${label} unavailable — the response carried no data.`)
  if (Array.isArray(data) && data.length === 0) return missing<T>(empty)
  return resolved(data)
}

/* ------------------------------------------------------------------ */
/* Core payload — fetched once on mount, never polled                  */
/* ------------------------------------------------------------------ */

export interface MissionCore {
  health: Resource<SystemHealthResponse>
  demo: Resource<DemoStatusResponse>
  sources: Resource<TwinSourceRegistry>
  disagreement: Resource<DisagreementMap>
  candidates: Resource<TideCandidate[]>
  validation: Resource<TideValidationStatus>
}

const EMPTY_CANDIDATES =
  'No TIDE candidate is available for this request — the ranking engine returned an empty pool.'

export function useMissionCore(): MissionCore {
  const [state, setState] = useState<MissionCore>({
    health: pending<SystemHealthResponse>(),
    demo: pending<DemoStatusResponse>(),
    sources: pending<TwinSourceRegistry>(),
    disagreement: pending<DisagreementMap>(),
    candidates: pending<TideCandidate[]>(),
    validation: pending<TideValidationStatus>(),
  })

  useEffect(() => {
    let alive = true
    const put = (patch: Partial<MissionCore>) => {
      if (alive) setState((prev) => ({ ...prev, ...patch }))
    }
    void load('System health', fetchSystemHealth).then((health) => put({ health }))
    void load('Observation ledger', fetchDemoStatus).then((demo) => put({ demo }))
    void load('Data-source registry', fetchDataSources).then((sources) => put({ sources }))
    void load('Model ⇄ observation comparison', () => fetchTwinDisagreement()).then((disagreement) =>
      put({ disagreement }),
    )
    void loadEnvelope<TideCandidate[]>(
      'TIDE candidate ranking',
      EMPTY_CANDIDATES,
      () => fetchTideCandidates(),
    ).then((candidates) => put({ candidates }))
    void loadEnvelope<TideValidationStatus>('TIDE validation status', '', () =>
      fetchTideValidationStatus(),
    ).then((validation) => put({ validation }))
    return () => {
      alive = false
    }
  }, [])

  return state
}

/* ------------------------------------------------------------------ */
/* Deferred payloads — only requested once their section is on screen  */
/* ------------------------------------------------------------------ */

/**
 * The reference benchmark runs the whole ranking engine across every strategy
 * and variable (seconds, not milliseconds), so it must not sit on the critical
 * path of the first paint. `enabled` is driven by IntersectionObserver.
 */
export function useBenchmark(enabled: boolean): Resource<TideBenchmarkReport> {
  const [state, setState] = useState<Resource<TideBenchmarkReport>>(pending<TideBenchmarkReport>())

  useEffect(() => {
    if (!enabled) return
    let alive = true
    void loadEnvelope<TideBenchmarkReport>('Reference benchmark', '', () =>
      fetchTideBenchmarks({ budget: 1, seed: 42 }),
    ).then((result) => {
      if (alive) setState(result)
    })
    return () => {
      alive = false
    }
  }, [enabled])

  return state
}

/**
 * Decision Replay for the first detected event. Read-only: the replay engine
 * never writes to the observation store and never modifies historical events.
 */
export function useDecisionReplay(enabled: boolean): Resource<DecisionReplay> {
  const [state, setState] = useState<Resource<DecisionReplay>>(pending<DecisionReplay>())

  useEffect(() => {
    if (!enabled) return
    let alive = true
    void loadEnvelope<{ events: TideEventIndexItem[] }>(
      'Detected-event index',
      'No ocean event is currently detected, so there is nothing to replay.',
      () => fetchTideEventIndex(),
    ).then(async (index) => {
      if (!alive) return
      if (!index.data) {
        setState({ data: null, reason: index.reason, loading: false })
        return
      }
      const first = index.data.events[0]
      if (!first) {
        setState({
          data: null,
          reason: 'No ocean event is currently detected, so there is nothing to replay.',
          loading: false,
        })
        return
      }
      const replay = await loadEnvelope<DecisionReplay>('Decision replay', '', () =>
        fetchDecisionReplay({ eventId: first.event_id }),
      )
      if (alive) setState(replay)
    })
    return () => {
      alive = false
    }
  }, [enabled])

  return state
}

/* ------------------------------------------------------------------ */
/* Presentation helpers — formatting only, never invention             */
/* ------------------------------------------------------------------ */

export function formatMetric(value: number | null | undefined, decimals = 2): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return value.toFixed(decimals)
}

export function formatPercent(fraction: number | null | undefined, decimals = 0): string {
  if (fraction == null || !Number.isFinite(fraction)) return '—'
  return `${(fraction * 100).toFixed(decimals)}%`
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '—'
  return parsed.toLocaleString('en-GB', {
    timeZone: 'Asia/Kolkata',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

/** The project's band vocabulary → a tone that matches the globe layer. */
export function bandTone(band: string | null | undefined): 'ok' | 'warn' | 'crit' | 'off' {
  switch (band) {
    case 'green':
      return 'ok'
    case 'yellow':
      return 'warn'
    case 'orange':
    case 'red':
      return 'crit'
    default:
      return 'off'
  }
}
