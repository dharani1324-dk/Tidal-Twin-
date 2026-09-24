/**
 * TIDE Voice Agent - tool executors (browser side).
 *
 * Maps the tool names registered by the backend (see
 * backend/app/modules/voice/tools.py) onto the EXISTING TidalTwin API client
 * and the UI command bus. Every result is tagged as REAL / HISTORICAL /
 * SIMULATED / SYNTHETIC / MODEL_DERIVED by the underlying endpoints; the voice
 * model reads those tags and never invents numbers.
 *
 * No duplicate endpoints, no parallel data access: these are thin, validated
 * adapters over `src/api/client.ts`.
 */

import {
  fetchAnomalies,
  fetchDataSources,
  fetchDecisionReplay,
  fetchDepthProfile,
  fetchHealth,
  fetchModelGridProfile,
  fetchObservations,
  fetchRealArgoFloats,
  fetchSituation,
  fetchErsstLatest,
  fetchErsstNear,
  fetchChlorLatest,
  fetchChlorNear,
  fetchTideCandidates,
  fetchTideDataGaps,
  fetchTideDisagreements,
  fetchTideEvidence,
  fetchTideExplanation,
  fetchTideEventContext,
  fetchTideUncertainty,
  fetchTideVerdict,
  fetchTideValidationStatus,
  fetchTimeline,
  fetchTwinCompare,
  fetchTwinConfidence,
  fetchTwinDisagreement,
  fetchTwinEvents,
  fetchTwinProfile,
  investigateEvent,
runWhatIf as runWhatIfApi,
  voiceWebSearch,
} from '../../api/client'
import { resolveFromContext } from './voiceContext.ts'
import { isPlainObject, validateToolArgs } from './jsonSchema.ts'
import { publishVoiceCommand } from './voiceBus.ts'
import { PAGE_ROUTES, type VoiceToolSpec } from './types.ts'

export interface ToolExecutionResult {
  status: 'ok' | 'error' | 'no_data'
  source: string
  feedback: string
  data: unknown
  confidence?: number
  limitations: string[]
}

type Args = Record<string, unknown>

/** Unwrap FastAPI {success, data, error} style envelopes defensively. */
function unwrap<T>(value: unknown): T {
  if (isPlainObject(value) && 'data' in value) {
    const inner = (value as Record<string, unknown>).data
    if (inner !== undefined && inner !== null) return inner as T
  }
  return value as T
}

function ok(source: string, feedback: string, data: unknown, opts: Partial<ToolExecutionResult> = {}): ToolExecutionResult {
  return { status: 'ok', source, feedback, data, limitations: [], ...opts }
}

function err(feedback: string, data: unknown = {}, opts: Partial<ToolExecutionResult> = {}): ToolExecutionResult {
  return { status: 'error', source: 'voice', feedback, data, limitations: [], ...opts }
}

function num(v: unknown): number | undefined {
  return typeof v === 'number' && Number.isFinite(v) ? v : undefined
}

function str(v: unknown): string | undefined {
  return typeof v === 'string' ? v : undefined
}

function int(v: unknown): number | undefined {
  return typeof v === 'number' && Number.isInteger(v) ? v : undefined
}

export interface ExecutorContext {
  tools: VoiceToolSpec[]
}

/** Pull a canonical where-set from args (backed by the current page context). */
function whereSet(args: Args) {
  const region = str(args.region) ?? str(args.location) ?? undefined
  return resolveFromContext({
    location_id: int(args.location_id),
    region,
    latitude: num(args.latitude),
    longitude: num(args.longitude),
  })
}

function variableOf(args: Args, fallback?: string): string {
  const v = str(args.variable)
  return v ?? fallback ?? 'temperature'
}

function depthOf(args: Args): number {
  return num(args.depth_m) ?? 0
}

// ---------------------------------------------------------------------------
// Executor implementations
// ---------------------------------------------------------------------------

async function getProjectStatus(): Promise<ToolExecutionResult> {
  const health = await fetchHealth()
  const checks = (health as { checks?: Record<string, { status?: string; detail?: string }> }).checks ?? {}
  const voice = checks.voice?.status ?? 'UNAVAILABLE'
  const tide = checks.tide?.status ?? 'UNAVAILABLE'
  const data = checks.ocean_data?.status ?? 'UNAVAILABLE'
  return ok(
    'health',
    `TidalTwin ${health.version ?? ''} (${health.release ?? ''}) is ${health.status ?? 'unknown'}. Ocean data ${data?.toLowerCase()}, TIDE ${tide?.toLowerCase()}, voice agent ${voice?.toLowerCase()}.`,
    health,
    { limitations: ['Status reflects backend subsystems, not scientific claims.'] },
  )
}

function getUiContext(): ToolExecutionResult {
  return ok(
    'ui-context',
    'Returned the current page context to resolve here/this-region references.',
    resolveFromContext({}),
  )
}

async function getDataSources(): Promise<ToolExecutionResult> {
  const payload = unwrap<unknown>(await fetchDataSources())
  return ok('data-sources', 'Returned registered data sources and provenance entries.', payload, {
    limitations: ['Provenance reflects what the platform loaded, not an exhaustive registry.'],
  })
}

async function getRegionOverview(args: Args): Promise<ToolExecutionResult> {
  const where = whereSet(args)
  if (!where.locationId) {
    return err('No region was specified and none is focused on screen. Ask for a place like "Bay of Bengal" or select a region on the globe.', {})
  }
  const variable = variableOf(args)
  const depth = depthOf(args)
  const [compare, observations, profile] = await Promise.allSettled([
    fetchTwinCompare(where.locationId, variable, depth),
    fetchObservations(where.locationId, 12),
    fetchTwinProfile(where.locationId, variable),
  ])
  const data = {
    location: where.name,
    location_id: where.locationId,
    variable,
    comparison: compare.status === 'fulfilled' ? unwrap(compare.value) : null,
    observations: observations.status === 'fulfilled' ? unwrap(observations.value) : null,
    profile: profile.status === 'fulfilled' ? unwrap(profile.value) : null,
  }
  const cmp = isPlainObject(data.comparison) ? data.comparison : {}
  const observed = num(cmp.observed)
  const model = num(cmp.model)
  const ds = str(cmp.data_status) ?? 'unknown'
  const feedback = observed != null && model != null
    ? `${where.name}: ${variable} model ${model} vs observed ${observed} (difference ${str(cmp.difference) ?? 'n/a'}), data_status ${ds}.`
    : `${where.name}: ${variable} comparison unavailable (${str(cmp.note) ?? 'no data'}), data_status ${ds}.`
  return ok('twin', feedback, data, {
    confidence: num(cmp.confidence),
    limitations: [str(cmp.note) ?? 'Model estimate = history-conditioned normal.'],
  })
}

async function getOceanField(args: Args): Promise<ToolExecutionResult> {
  const variable = variableOf(args)
  const depth = depthOf(args)
  const where = whereSet(args)

  // Depth or coordinate queries use the REAL ocean-model grid profile.
  if ((depth > 0 || (where.latitude != null && where.longitude != null)) && where.latitude != null && where.longitude != null) {
    const profile = await fetchModelGridProfile(
      variable as 'temperature' | 'salinity' | 'current_speed',
      where.latitude,
      where.longitude,
    )
    const p = unwrap<Record<string, unknown>>(profile)
    if (p.found === false) {
      return ok('modelgrid', `No real ${variable} model cell within range of ${where.name ?? 'that point'}.`, p, {
        limitations: [str(p.reason) ?? 'Real grid not ingested at this location.'],
      })
    }
    const levels = Array.isArray(p.levels) ? (p.levels as Record<string, unknown>[]) : []
    const valueAtDepth = depth > 0
      ? levels.find((l) => Math.abs((num(l.depth_m) ?? 0) - depth) < 1e-6) ?? null
      : levels[levels.length - 1] ?? null
    const shown = valueAtDepth ?? levels.slice(0, 4)
    return ok('modelgrid', `Returned the real model ${variable} profile near ${p.latitude}, ${p.longitude} (month ${str(p.month) ?? 'n/a'}).`, {
      found: true,
      variable,
      latitude: p.latitude,
      longitude: p.longitude,
      unit: p.unit,
      source: p.source,
      value: valueAtDepth != null ? num(valueAtDepth.value) : undefined,
      value_at_depth_m: num(valueAtDepth?.depth_m),
      levels: shown,
    }, { limitations: ['Values are the real ocean-model grid (MODEL_DERIVED), not observations.'] })
  }

  const where2 = whereSet(args)
  if (!where2.locationId) {
    return err('No region or coordinates given and none focused. Say a place or "here".', {})
  }
  const compare = await fetchTwinCompare(where2.locationId, variable, depth)
  const payload = unwrap<Record<string, unknown>>(compare)
  return ok('twin', `${payload.location ?? where2.name} ${variable}: observed ${str(payload.observed) ?? 'n/a'} (${str(payload.data_status) ?? 'unknown'}), model ${str(payload.model) ?? 'n/a'}.`, payload, {
    limitations: [str(payload.note) ?? ''],
  })
}

async function getDepthProfile(args: Args): Promise<ToolExecutionResult> {
  const where = whereSet(args)
  if (!where.locationId) return err('No region focused or named for a depth profile.', {})
  const variable = variableOf(args)
  const profile = await fetchDepthProfile(where.locationId)
  const p = unwrap<Record<string, unknown>>(profile)
  return ok('twin', `Vertical profile for ${where.name} (${variable}).`, p, {
    limitations: [str(p.note) ?? 'Profile reflects the twin model depth structure.'],
  })
}

async function getObservations(args: Args): Promise<ToolExecutionResult> {
  const where = whereSet(args)
  if (!where.locationId) return err('No region focused or named for observations.', {})
  const limit = int(args.limit)
  const payload = unwrap<Record<string, unknown>>(await fetchObservations(where.locationId, limit ?? 10))
  const rows = Array.isArray(payload.observations ?? payload.rows ?? payload.data)
    ? (payload.observations ?? payload.rows ?? payload.data) as Record<string, unknown>[]
    : []
  const simulated = rows.filter((r) => {
    const s = str(r.data_status) ?? str(r.source) ?? ''
    return /sim|demo|synthetic/i.test(s)
  }).length
  const status = rows.length === 0 ? 'no_data' : 'ok'
  return ok('observations', `${rows.length} observation row(s) (${simulated} labelled simulated/demo).`, payload, {
    limitations: ['Per-row data_status values are the honest REAL/SIMULATED label set.'],
    ...(status === 'no_data' ? {} : {}),
  })
}

async function getSatelliteObservations(args: Args): Promise<ToolExecutionResult> {
  const [ersst, chlor] = await Promise.allSettled([fetchErsstLatest(), fetchChlorLatest()])
  const where = whereSet(args)
  let nearest = null
  if (where.latitude != null && where.longitude != null) {
    const [n1, n2] = await Promise.allSettled([
      fetchErsstNear(where.latitude, where.longitude).catch(() => null),
      fetchChlorNear(where.latitude, where.longitude).catch(() => null),
    ])
    nearest = {
      ersst: n1.status === 'fulfilled' ? unwrap(n1.value) : null,
      chlorophyll: n2.status === 'fulfilled' ? unwrap(n2.value) : null,
    }
  }
  return ok('satellite', 'Returned NOAA ERSST SST and VIIRS chlorophyll availability.', {
    ersst: ersst.status === 'fulfilled' ? unwrap(ersst.value) : null,
    chlorophyll: chlor.status === 'fulfilled' ? unwrap(chlor.value) : null,
    nearest,
  }, { limitations: ['ERSST is a 2° analysis grid; VIIRS is 5 km satellite imagery - both are gridded, not in-situ.'] })
}

async function getArgoObservations(): Promise<ToolExecutionResult> {
  const payload = unwrap<Record<string, unknown>>(await fetchRealArgoFloats())
  const raw = payload.floats ?? payload.items ?? payload.data
  const floats = Array.isArray(raw) ? raw : []
  return ok('argo', `${floats.length} real Argo float(s) registered.`, payload, {
    limitations: ["Argo float list reflects the floats India-Ocean dataset currently loaded."],
  })
}

async function getAnomalies(args: Args): Promise<ToolExecutionResult> {
  const where = whereSet(args)
  const params: Record<string, string | number | undefined> = {
    variable: variableOf(args),
    severity: str(args.severity),
    limit: typeof args.limit === 'number' ? String(args.limit) : '8',
    location_id: where.locationId,
  }
  for (const key of Object.keys(params)) if (params[key] == null) delete params[key]
  const payload = unwrap<Record<string, unknown>>(await fetchAnomalies(params))
  const rows = Array.isArray(payload.anomalies ?? payload.data ?? payload.points)
    ? (payload.anomalies ?? payload.data ?? payload.points) as Record<string, unknown>[]
    : []
  return ok('anomalies', `${rows.length} anomaly row(s) for ${str(args.severity) ?? 'any severity'}.`, payload, {
    limitations: ['Anomalies are model-vs-observation alerts; inspect data_status per row.'],
  })
}

async function getAnomalyStatistics(args: Args): Promise<ToolExecutionResult> {
  const rows = (await getAnomalies({ ...args, limit: 50 })).data as Record<string, unknown> | null
  const list = Array.isArray(rows?.anomalies ?? rows?.data ?? rows?.points)
    ? (rows?.anomalies ?? rows?.data ?? rows?.points) as Record<string, unknown>[]
    : []
  const bySeverity: Record<string, number> = {}
  const byVariable: Record<string, number> = {}
  for (const r of list) {
    const s = str(r.severity) ?? 'unknown'
    bySeverity[s] = (bySeverity[s] ?? 0) + 1
    byVariable[str(r.variable) ?? 'unknown'] = (byVariable[str(r.variable) ?? 'unknown'] ?? 0) + 1
  }
  list.sort((a, b) => (num(b.confidence) ?? 0) - (num(a.confidence) ?? 0))
  return ok('anomalies', `${list.length} anomalies; by severity ${JSON.stringify(bySeverity)}; strongest ${str(list[0]?.location) ?? 'n/a'}.`, {
    total: list.length,
    current_context: {
      last_anomaly: list[0] ? {
        location: str(list[0].location) ?? str(list[0].location_id),
        variable: str(list[0].variable),
        label: str(list[0].label),
        severity: str(list[0].severity),
        confidence: num(list[0].confidence),
        model: num(list[0].model_value) ?? num(list[0].model),
        observed: num(list[0].observed_value) ?? num(list[0].observed),
        data_status: str(list[0].data_status),
      } : null,
    },
    by_severity: bySeverity,
    by_variable: byVariable,
  })
}

async function getEvents(): Promise<ToolExecutionResult> {
  const payload = unwrap<Record<string, unknown>>(await fetchTwinEvents())
  const events = Array.isArray(payload.events) ? payload.events as Record<string, unknown>[] : []
  const active = events.filter((e) => {
    const status = str(e.current_status) ?? ''
    return /active|developing|observed|intensifying/i.test(status) || status === ''
  })
  return ok('twin-events', `${events.length} detected event(s), ${active.length} active/developing.`, payload, {
    limitations: ['Events are detected from the loaded model-vs-observation data (data_status per event).'],
  })
}

async function getInvestigateEvent(args: Args): Promise<ToolExecutionResult> {
  const where = whereSet(args)
  if (!where.locationId) return err('No region named/focused for an event investigation.', {})
  const payload = unwrap<Record<string, unknown>>(await investigateEvent(where.locationId))
  const factors = Array.isArray(payload.factors) ? (payload.factors as { name?: string }[]) : []
  return ok('forensics', `Investigation for ${where.name}: ${factors.map((f) => f.name).filter(Boolean).join(', ') || 'no isolated factors'}.`, payload, {
    limitations: ['Forensic factors are derived from the existing intelligence engine, not confirmed causes.'],
  })
}

async function getEventTimeline(args: Args): Promise<ToolExecutionResult> {
  const where = whereSet(args)
  if (!where.locationId) return err('No region named/focused for a timeline.', {})
  const payload = unwrap<Record<string, unknown>>(await fetchTimeline(where.locationId))
  return ok('forensics', `Stage timeline for ${where.name}.`, payload, {
    limitations: ['Timeline is the existing event-stage walkthrough, not a measured record.'],
  })
}

async function getTideCandidates(args: Args): Promise<ToolExecutionResult> {
  const where = whereSet(args)
  const candidates = unwrap<Record<string, unknown>>(await fetchTideCandidates({
    location_id: where.locationId,
    variable: variableOf(args),
    depth_m: depthOf(args),
  }))
  const rows = Array.isArray(candidates.candidates ?? candidates.data ?? candidates)
    ? (candidates.candidates ?? candidates.data ?? candidates) as Record<string, unknown>[]
    : []
  const top = rows[0]
  return ok('tide-candidates', `${rows.length} ranked candidate(s); top: ${str(top?.location) ?? 'n/a'} → ${str(top?.observation_type) ?? 'n/a'} (score ${num(top?.observation_value)}).`, { candidates: rows.slice(0, 8) }, {
    confidence: num(top?.confidence),
    limitations: ['TIDE scores are transparent heuristics (MODEL_DERIVED), not a validated value-of-information model.'],
  })
}

async function getTideExplanation(args: Args): Promise<ToolExecutionResult> {
  const where = whereSet(args)
  if (!where.locationId) return err('No region named/focused for a TIDE explanation.', {})
  const payload = unwrap<Record<string, unknown>>(await fetchTideExplanation({
    location_id: where.locationId,
    variable: variableOf(args),
    depth_m: depthOf(args),
  }))
  return ok('tide-explanation', str(payload.summary) ?? 'TIDE explanation returned.', payload, {
    limitations: ((payload.limitations ?? []) as string[]).length ? ((payload.limitations ?? []) as string[]) : ['MODEL_DERIVED; see evidence field for transparency.'],
  })
}

async function getTideEvidence(args: Args): Promise<ToolExecutionResult> {
  const where = whereSet(args)
  if (!where.locationId) return err('No region named/focused for TIDE evidence.', {})
  const payload = unwrap<Record<string, unknown>>(await fetchTideEvidence({
    location_id: where.locationId,
    variable: variableOf(args),
    depth_m: depthOf(args),
  }))
  const evidence = Array.isArray(payload.evidence) ? payload.evidence as Record<string, unknown>[] : []
  const sources = evidence.map((e) => str(e.source_system) ?? 'tide').filter(Boolean)
  return ok('tide-evidence', `${evidence.length} evidence record(s).`, payload, {
    limitations: (payload.limitations ?? []) as string[],
    ...(sources.length ? { data_status: sources.join(',') } : {}),
  })
}

async function getTideVerdict(args: Args): Promise<ToolExecutionResult> {
  const where = whereSet(args)
  if (!where.locationId) return err('A location is required to read a TIDE verdict.', {})
  const payload = unwrap<Record<string, unknown>>(await fetchTideVerdict({
    location_id: where.locationId,
    variable: variableOf(args),
    depth_m: depthOf(args),
  }))
  return ok('tide-verdict', `Verdict at ${where.name}: ${str(payload.verdict) ?? 'n/a'} (confidence ${str(payload.confidence) ?? 'n/a'}). ${str(payload.summary) ?? ''}`, payload, {
    confidence: num(payload.confidence),
    limitations: (payload.limitations ?? []) as string[],
  })
}

async function getTideUncertainty(args: Args): Promise<ToolExecutionResult> {
  const where = whereSet(args)
  const [uncertainty, gaps, disagreements] = await Promise.allSettled([
    fetchTideUncertainty({ location_id: where.locationId }),
    fetchTideDataGaps({ location_id: where.locationId }),
    fetchTideDisagreements({ location_id: where.locationId }),
  ])
  return ok('tide-uncertainty', 'Returned uncertainty, data gaps and disagreements.', {
    uncertainty: uncertainty.status === 'fulfilled' ? unwrap(uncertainty.value) : null,
    data_gaps: gaps.status === 'fulfilled' ? unwrap(gaps.value) : null,
    disagreements: disagreements.status === 'fulfilled' ? unwrap(disagreements.value) : null,
  }, { limitations: ['Uncertainty scores are TIDE heuristics over existing inputs (MODEL_DERIVED).'] })
}

async function recommendNextObservation(args: Args): Promise<ToolExecutionResult> {
  const where = whereSet(args)
  const candidates = unwrap<Record<string, unknown>>(await fetchTideCandidates({
    location_id: where.locationId,
    variable: variableOf(args),
    depth_m: depthOf(args),
  }))
  const rows = Array.isArray(candidates.candidates ?? candidates.data ?? candidates)
    ? (candidates.candidates ?? candidates.data ?? candidates) as Record<string, unknown>[]
    : []
  const top = rows[0]
  if (!top) return ok('tide-candidates', 'TIDE returned no candidates for this request.', {}, {})
  let explanation: unknown = null
  if (top.location_id != null) {
    explanation = await fetchTideExplanation({ location_id: num(top.location_id)!, variable: str(top.variable) ?? 'temperature', depth_m: num(top.depth_m) ?? 0 })
      .then((d) => unwrap(d)).catch(() => null)
  }
  return ok('tide-candidates', `Recommended: ${str(top.observation_type)?.replace(/_/g, ' ')} at ${str(top.location) ?? 'n/a'} for ${str(top.variable) ?? 'n/a'}. Reason: ${str(top.reason) ?? 'n/a'}.`, {
    recommendation: top,
    explanation: explanation ? { summary: (explanation as Record<string, unknown>).summary, limitations: (explanation as Record<string, unknown>).limitations } : null,
  }, {
    confidence: num(top.confidence),
    limitations: [
      'MODEL_DERIVED - a simulated recommendation for study, never persisted as an observation.',
      ...((top.limitations ?? []) as string[]),
    ],
  })
}

async function getEventContext(args: Args): Promise<ToolExecutionResult> {
  const eventId = str(args.event_id)
  if (!eventId) return err('A TIDE event id is required (e.g. "event-2").', {})
  const payload = unwrap<Record<string, unknown>>(await fetchTideEventContext(eventId))
  const event = isPlainObject(payload.event) ? payload.event : null
  return ok('tide-event', `Event ${eventId}: ${str(event?.event_type) ?? 'unknown'} at ${str(event?.location) ?? 'n/a'}.`, payload, {
    limitations: ['Event context reuses the existing event DNA + TIDE composition.'],
  })
}

async function getReplay(args: Args): Promise<ToolExecutionResult> {
  const eventId = str(args.event_id)
  if (!eventId) return err('A TIDE event id is required to replay (e.g. "event-1").', {})
  const where = whereSet(args)
  const payload = unwrap<Record<string, unknown>>(await fetchDecisionReplay({
    eventId,
    location_id: where.locationId,
    variable: variableOf(args, 'temperature'),
    depth_m: depthOf(args),
  }))
  return ok('tide-replay', `Replay for ${eventId}: model-only vs TIDE-assisted walkthrough. ${str(payload.decision_summary) ?? str(payload.summary) ?? ''}`, payload, {
    limitations: ['The replay is a read-only comparison of decision-making; nothing is written to the store.'],
  })
}

async function getValidationStatus(): Promise<ToolExecutionResult> {
  const payload = unwrap<Record<string, unknown>>(await fetchTideValidationStatus())
  const stages = payload.maturity ?? payload.stages ?? []
  const stageNames = Array.isArray(stages)
    ? (stages as Record<string, unknown>[]).map((s) => str(s.name) ?? str(s.stage)).filter(Boolean).join(', ')
    : ''
  return ok('tide-validation', `TIDE validation: ${str(payload.status) ?? str(payload.verdict) ?? 'tested'}. Stages: ${stageNames || 'IMPLEMENTED→DEMONSTRATED→TESTED'}.`, payload, {
    limitations: ['TIDE is tested and benchmarked on this dataset, not scientifically field-validated.'],
  })
}

async function runWhatIf(args: Args): Promise<ToolExecutionResult> {
  const where = whereSet(args)
  if (!where.locationId) return err('A focused/named region is required to run a what-if scenario.', {})
  const payload = unwrap<Record<string, unknown>>(await runWhatIfApi({
    location_id: where.locationId,
    wind_percent: num(args.wind_percent),
    temp_delta: num(args.temp_delta),
    salinity_delta: num(args.salinity_delta),
    mixing_factor: num(args.mixing_factor),
  }))
  return ok('whatif', `What-if scenario ran at ${where.name} (wind ${str(args.wind_percent) ?? '0'}%, ΔT ${str(args.temp_delta) ?? '0'}°C).`, payload, {
    limitations: ['SIMULATED scenario for study - never persisted, not a measured outcome.'],
  })
}

async function compareScenarios(args: Args): Promise<ToolExecutionResult> {
  const where = whereSet(args)
  if (!where.locationId) return err('A focused/named region is required to compare scenarios.', {})
  const deltas = {
    wind_percent: num(args.wind_percent),
    temp_delta: num(args.temp_delta),
    salinity_delta: num(args.salinity_delta),
    mixing_factor: num(args.mixing_factor),
  }
  const [baseline, scenario] = await Promise.allSettled([
    runWhatIf({ location_id: where.locationId }),
    runWhatIf({ location_id: where.locationId, ...deltas }),
  ])
  return ok('whatif', `Baseline vs scenario comparison at ${where.name}.`, {
    baseline: baseline.status === 'fulfilled' ? baseline.value.data : null,
    scenario: scenario.status === 'fulfilled' ? scenario.value.data : null,
  }, { limitations: ['Both legs are SIMULATED what-if outputs (never persisted).'] })
}

async function getModelComparison(args: Args): Promise<ToolExecutionResult> {
  const where = whereSet(args)
  if (!where.locationId) {
    const [disagreement, situation] = await Promise.allSettled([
      fetchTwinDisagreement(variableOf(args), depthOf(args)),
      fetchSituation(),
    ])
    return ok('twin', 'Returned an all-region disagreement overview plus the ocean situation.', {
      disagreement: disagreement.status === 'fulfilled' ? unwrap(disagreement.value) : null,
      situation: situation.status === 'fulfilled' ? unwrap(situation.value) : null,
    }, { limitations: ['All-region overview; ask for a specific region for full comparison detail.'] })
  }
  const variable = variableOf(args)
  const [compare, confidence] = await Promise.allSettled([
    fetchTwinCompare(where.locationId, variable, depthOf(args)),
    fetchTwinConfidence(where.locationId, variable),
  ])
  const cmp = compare.status === 'fulfilled' ? unwrap<Record<string, unknown>>(compare.value) : {}
  return ok('twin', `Model vs observation at ${where.name}: observed ${str(cmp.observed) ?? 'n/a'} vs model ${str(cmp.model) ?? 'n/a'} (${str(cmp.status) ?? 'n/a'} disagreement), data_status ${str(cmp.data_status) ?? 'unknown'}.`, {
    comparison: cmp,
    confidence: confidence.status === 'fulfilled' ? unwrap(confidence.value) : null,
  }, {
    confidence: num(cmp.confidence),
    limitations: [str(cmp.note) ?? ''],
  })
}

async function doWebSearch(args: Args): Promise<ToolExecutionResult> {
  const query = str(args.query) ?? ''
  const max = Math.min(int(args.max_results) ?? 3, 5)
  const payload = await voiceWebSearch(query, max)
  if (payload.status === 'error') return err(`Web search failed.`, payload)
  if (payload.status === 'no_results') return ok('web', 'The web search returned nothing useful.', payload, { limitations: payload.limitations })
  const top = payload.results[0]
  return ok('web', `Web result: ${payload.answer ?? top?.snippet ?? 'no summary'}.`, payload, {
    limitations: payload.limitations,
  })
}

// ---------------------------------------------------------------------------
// UI control executors (thin command-bus adapters)
// ---------------------------------------------------------------------------

async function uiFocusRegion(args: Args): Promise<ToolExecutionResult> {
  const where = whereSet(args)
  if (!where.locationId && where.latitude == null && where.longitude == null) {
    return err('Could not resolve that place. Try a monitored region name, a gazetteer place, or coordinates.', {})
  }
  publishVoiceCommand('voice:focus', {
    locationId: where.locationId,
    name: where.name,
    latitude: where.latitude,
    longitude: where.longitude,
  })
  return ok('ui_focus_region', `Focused the globe on ${where.name ?? `${where.latitude}, ${where.longitude}`}.`, where)
}

async function uiSetDepth(args: Args): Promise<ToolExecutionResult> {
  const depth = num(args.depth_m)
  if (depth == null) return err('A numeric depth is required (metres).', {})
  publishVoiceCommand('voice:set-depth', { depthM: depth })
  return ok('ui_set_depth', `Set the globe depth slice to ${depth} metres (snapped to the nearest model level).`, { depth_m: depth })
}

async function uiSetTime(args: Args): Promise<ToolExecutionResult> {
  const label = str(args.label) ?? 'now'
  const hoursAgo = int(args.hours_ago)
  publishVoiceCommand('voice:set-time', { label, hoursAgo })
  const text = hoursAgo != null ? `${hoursAgo} hours before now` : label
  return ok('ui_set_time', `Moved the time cursor to ${text}.`, { label, hoursAgo })
}

async function uiSetVariable(args: Args): Promise<ToolExecutionResult> {
  const variable = str(args.variable) ?? 'temperature'
  publishVoiceCommand('voice:set-variable', { variable })
  return ok('ui_set_variable', `Selected ${variable} on the globe comparison.`, { variable })
}

async function uiToggleLayer(args: Args): Promise<ToolExecutionResult> {
  const layer = str(args.layer)
  if (!layer) return err('A layer key is required (e.g. "anomalies", "tide", "realArgo").', {})
  const on = args.on === undefined ? undefined : Boolean(args.on)
  publishVoiceCommand('voice:toggle-layer', { layer, on })
  const text = on === true ? 'activated' : on === false ? 'deactivated' : 'toggled'
  return ok('ui_toggle_layer', `${text === 'toggled' ? 'Toggled' : `${text.charAt(0).toUpperCase()}${text.slice(1)}`} the ${layer} layer.`, { layer, on })
}

async function uiNavigate(args: Args): Promise<ToolExecutionResult> {
  const page = str(args.page)
  if (!page) return err('A target page is required.', {})
  const route = PAGE_ROUTES[page]
  const locationId = int(args.location_id)
  const variable = str(args.variable)
  if (!route) return err(`Unknown page '${page}'.`, {})
  publishVoiceCommand('voice:navigate', { page, route, locationId, variable })
  return ok('ui_navigate', `Opening the ${page} page.`, { page, route, locationId, variable })
}

async function uiRevealPanel(args: Args): Promise<ToolExecutionResult> {
  const panel = str(args.panel)
  if (!panel) return err('A panel id is required.', {})
  publishVoiceCommand('voice:reveal-panel', { panel })
  return ok('ui_reveal_panel', `Revealing the ${panel} panel on the globe.`, { panel })
}

// ---------------------------------------------------------------------------
// Registry
// ---------------------------------------------------------------------------

type Executor = (args: Args) => Promise<ToolExecutionResult> | ToolExecutionResult

export const TOOL_EXECUTORS: Record<string, Executor> = {
  'tidetwin_get_project_status': getProjectStatus,
  'tidetwin_get_ui_context': getUiContext,
  'tidetwin_get_data_sources': getDataSources,
  'tidetwin_get_region_overview': getRegionOverview,
  'tidetwin_get_ocean_field': getOceanField,
  'tidetwin_get_depth_profile': getDepthProfile,
  'tidetwin_get_observations': getObservations,
  'tidetwin_get_satellite_observations': getSatelliteObservations,
  'tidetwin_get_argo_observations': getArgoObservations,
  'tidetwin_get_anomalies': getAnomalies,
  'tidetwin_get_anomaly_statistics': getAnomalyStatistics,
  'tidetwin_get_events': getEvents,
  'tidetwin_investigate_event': getInvestigateEvent,
  'tidetwin_get_event_timeline': getEventTimeline,
  'tidetwin_get_tide_candidates': getTideCandidates,
  'tidetwin_get_tide_explanation': getTideExplanation,
  'tidetwin_get_tide_evidence': getTideEvidence,
  'tidetwin_get_tide_verdict': getTideVerdict,
  'tidetwin_get_tide_uncertainty': getTideUncertainty,
  'tidetwin_recommend_next_observation': recommendNextObservation,
  'tidetwin_get_event_context': getEventContext,
  'tidetwin_get_replay': getReplay,
  'tidetwin_get_validation_status': getValidationStatus,
  'tidetwin_run_whatif': runWhatIf,
  'tidetwin_compare_scenarios': compareScenarios,
  'tidetwin_get_model_comparison': getModelComparison,
  'web_search': doWebSearch,
  'ui_focus_region': uiFocusRegion,
  'ui_set_depth': uiSetDepth,
  'ui_set_time': uiSetTime,
  'ui_set_variable': uiSetVariable,
  'ui_toggle_layer': uiToggleLayer,
  'ui_navigate': uiNavigate,
  'ui_reveal_panel': uiRevealPanel,
}

/** Validate arguments against the session tool schemas, then execute. */
export async function executeTool(
  tools: VoiceToolSpec[],
  name: string,
  args: unknown,
): Promise<ToolExecutionResult> {
  const exec = TOOL_EXECUTORS[name]
  if (!exec) return err(`Unknown tool '${name}'.`, {})
  const validation = validateToolArgs(tools, name, args)
  if (!validation.ok) {
    return {
      status: 'error',
      source: 'voice',
      feedback: `Tool argument error for ${name}: ${validation.errors.join('; ')}`,
      data: { tool: name, errors: validation.errors },
      limitations: [],
    }
  }
  try {
    const result = await exec(args as Args)
    return result
  } catch (e) {
    const message = e instanceof Error ? e.message : String(e)
    return {
      status: 'error',
      source: 'voice',
      feedback: `${name} failed: ${message}`,
      data: { tool: name, error: message },
      limitations: [],
    }
  }
}

export const TOOL_COUNT = Object.keys(TOOL_EXECUTORS).length