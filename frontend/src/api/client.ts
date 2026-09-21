/**
 * TidalTwin - API Client
 * ==========================
 * This is how our frontend talks to the backend.
 * We use axios to make HTTP requests to the FastAPI server.
 */

import axios from 'axios'
import type {
  DemoResetResponse,
  DemoSeedResponse,
  DemoStatusResponse,
  SystemHealthResponse,
} from '../types/system'

// The backend runs here in development
const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
})

/** Get a friendly backend health status */
export const fetchHealth = async () => {
  const { data } = await api.get('/api/v1/health')
  return data
}

/** Get all ocean locations from the database */
export const fetchLocations = async () => {
  const { data } = await api.get('/api/v1/ocean/locations')
  return data
}

/** Get recent observations for one location */
export const fetchObservations = async (locationId: number, limit = 50) => {
  const { data } = await api.get(
    `/api/v1/ocean/locations/${locationId}/observations`,
    { params: { limit } },
  )
  return data
}

/** Trigger a refresh of real ocean data from the API */
export const triggerRefresh = async () => {
  const { data } = await api.post('/api/v1/ocean/refresh')
  return data
}

/** Ask the TidalTwin Copilot a natural-language question (multi-turn context) */
export const askAssistant = async (question: string, context: Record<string, unknown> = {}) => {
  const { data } = await api.post('/api/v1/assistant/ask', { question, context })
  return data
}

/** Get the copilot capability/affordance list for the UI */
export const fetchAssistantCapabilities = async () => {
  const { data } = await api.get('/api/v1/assistant/capabilities')
  return data
}

/** Multimodal Ocean AI: fuse a pasted document/news/NetCDF summary with live sensors */
export const askMultimodal = async (text: string, media?: Record<string, unknown>) => {
  const { data } = await api.post('/api/v1/assistant/multimodal', { text, media })
  return data
}

/** Get monitoring alerts (active/resolved/all) */
export const fetchAlerts = async (status = 'all') => {
  const { data } = await api.get('/api/v1/monitoring/alerts', { params: { status } })
  return data
}

/** Run the AI anomaly-detection radar */
export const runAnomalyScan = async () => {
  const { data } = await api.post('/api/v1/monitoring/scan')
  return data
}

/** Get AI 12h forecasts for all regions */
export const fetchForecasts = async () => {
  const { data } = await api.get('/api/v1/monitoring/forecast')
  return data
}

/** Get all interactive ocean stories with live data hooks */
export const fetchStories = async () => {
  const { data } = await api.get('/api/v1/stories')
  return data.stories
}

/** Get AI forecast-vs-reality comparisons for all locations */
export const fetchComparisons = async () => {
  const { data } = await api.get('/api/v1/comparison')
  return data.comparisons
}

/** Get AI forecast-vs-reality comparison for one location */
export const fetchComparison = async (locationId: number) => {
  const { data } = await api.get(`/api/v1/comparison/${locationId}`)
  return data
}

/** Get national ocean risk index (composite ranking) */
export const fetchRiskIndex = async () => {
  const { data } = await api.get('/api/v1/reports/index')
  return data
}

/** Get auto-generated executive summary + risk index */
export const fetchSummary = async () => {
  const { data } = await api.get('/api/v1/reports/summary')
  return data
}

/** Download all observations as CSV (browser download) */
export const downloadCsv = () => {
  window.open(`${API_BASE}/api/v1/reports/csv`, '_blank')
}

/** Get per-coast fishing safety advisories (safe window + status) */
export const fetchSafetyAdvisory = async () => {
  const { data } = await api.get('/api/v1/safety/advisory')
  return data
}

/** Get the simulated storm-track layer for the globe */
export const fetchStormTrack = async () => {
  const { data } = await api.get('/api/v1/safety/storm')
  return data
}

/** Get per-coast model trust scores + rolling MAE sparklines */
export const fetchModelTrust = async () => {
  const { data } = await api.get('/api/v1/safety/trust')
  return data
}

/** Get merged observation + forecast timelines for the globe time-scrubber */
export const fetchSafetyTimeseries = async () => {
  const { data } = await api.get('/api/v1/safety/timeseries')
  return data
}

/** Get per-coast observation confidence + model agreement */
export const fetchValidationConfidence = async () => {
  const { data } = await api.get('/api/v1/validation/confidence')
  return data
}

/** Get MODEL | OBSERVED | DEVIATION fields per coast (optionally one) */
export const fetchValidationDifference = async (locationId?: number) => {
  const { data } = await api.get('/api/v1/validation/difference', {
    params: locationId != null ? { location_id: locationId } : {},
  })
  return data
}

/** Get the operational situation panel for all coasts */
export const fetchValidationSituation = async () => {
  const { data } = await api.get('/api/v1/validation/situation')
  return data
}

/** Get per-variable model skill score (MAE / RMSE / bias / skill %) */
export const fetchValidationSkill = async () => {
  const { data } = await api.get('/api/v1/validation/skill')
  return data
}

/** Get classified ocean events (heatwave, flood risk, mismatch...) */
export const fetchValidationEvents = async () => {
  const { data } = await api.get('/api/v1/validation/events')
  return data
}

/** Get scientific traceability per coast (source / dataset / model run) */
export const fetchValidationProvenance = async () => {
  const { data } = await api.get('/api/v1/validation/provenance')
  return data
}

/** Run an illustrative what-if projection (labelled simulation, not a forecast) */
export const runScenario = async (locationId: number, windPercent: number) => {
  const { data } = await api.post('/api/v1/validation/scenario', {
    location_id: locationId,
    wind_percent: windPercent,
  })
  return data
}

// --- Intelligence & Forensics API ---

/** Get region coverage (observation density per coastal region) */
export const fetchCoverage = async () => {
  const { data } = await api.get('/api/v1/intelligence/coverage')
  return data
}

/** Get priority map (which regions need most attention) */
export const fetchPriority = async () => {
  const { data } = await api.get('/api/v1/intelligence/priority')
  return data
}

/** Get uncertainty map (data gaps & confidence per region) */
export const fetchUncertainty = async () => {
  const { data } = await api.get('/api/v1/intelligence/uncertainty')
  return data
}

/** Simulate what adding more observations would do to coverage */
export const simulateCoverage = async (locationId: number, deltaPct: number) => {
  const { data } = await api.get('/api/v1/intelligence/coverage-sim', {
    params: { location_id: locationId, delta_pct: deltaPct },
  })
  return data
}

/** Get composite ocean health score (0-100) for all or one region */
export const fetchHealthScore = async (locationId?: number) => {
  const { data } = await api.get('/api/v1/intelligence/health', {
    params: locationId != null ? { location_id: locationId } : {},
  })
  return data
}

/** Get threat escalation chain (Normal→Watch→Warning→Critical) */
export const fetchThreatChain = async () => {
  const { data } = await api.get('/api/v1/intelligence/threat-chain')
  return data
}

/** Get impact bridge (event → consequence mapping) */
export const fetchImpact = async () => {
  const { data } = await api.get('/api/v1/intelligence/impact')
  return data
}

/** Get variable relationship graph (correlations) */
export const fetchRelationships = async () => {
  const { data } = await api.get('/api/v1/intelligence/relationships')
  return data
}

/** Get causal chain for a specific region */
export const fetchCausalChain = async (locationId: number) => {
  const { data } = await api.get('/api/v1/intelligence/causal', {
    params: { location_id: locationId },
  })
  return data
}

/** Get thermocline analysis for a region */
export const fetchThermocline = async (locationId: number) => {
  const { data } = await api.get('/api/v1/intelligence/thermocline', {
    params: { location_id: locationId },
  })
  return data
}

/** Get full depth profile (temperature/salinity/density/oxygen) for a region */
export const fetchDepthProfile = async (locationId: number) => {
  const { data } = await api.get('/api/v1/intelligence/depth-profile', {
    params: { location_id: locationId },
  })
  return data
}

/** Get classified ocean events */
export const fetchEvents = async () => {
  const { data } = await api.get('/api/v1/intelligence/events')
  return data
}

/** Investigate a specific event (contributing factors, evidence, confidence) */
export const investigateEvent = async (locationId: number) => {
  const { data } = await api.get('/api/v1/intelligence/investigate', {
    params: { location_id: locationId },
  })
  return data
}

/** Get ocean fingerprint/DNA for an event */
export const fetchFingerprint = async (eventIndex: number) => {
  const { data } = await api.get('/api/v1/intelligence/fingerprint', {
    params: { event_index: eventIndex },
  })
  return data
}

/** Find similar historical events via cosine similarity */
export const fetchSimilar = async (eventIndex: number) => {
  const { data } = await api.get('/api/v1/intelligence/similar', {
    params: { event_index: eventIndex },
  })
  return data
}

/** Get event timeline for a region */
export const fetchTimeline = async (locationId: number) => {
  const { data } = await api.get('/api/v1/intelligence/timeline', {
    params: { location_id: locationId },
  })
  return data
}

/** Get full autopsy report (comprehensive post-event analysis) */
export const fetchAutopsy = async (locationId: number) => {
  const { data } = await api.get('/api/v1/intelligence/autopsy', {
    params: { location_id: locationId },
  })
  return data
}

/** Run what-if scenario with full parameter control */
export const runWhatIf = async (payload: {
  location_id: number
  wind_percent?: number
  temp_delta?: number
  salinity_delta?: number
  mixing_factor?: number
}) => {
  const { data } = await api.post('/api/v1/intelligence/whatif', payload)
  return data
}

/** Run counterfactual (actual vs scenario side-by-side) */
export const runCounterfactual = async (locationId: number, scenario: Record<string, number>) => {
  const { data } = await api.post('/api/v1/intelligence/counterfactual', {
    location_id: locationId,
    ...scenario,
  })
  return data
}

/** Get future projection windows (3/7/14/30 day horizons) */
export const fetchFuture = async (locationId: number) => {
  const { data } = await api.get('/api/v1/intelligence/future', {
    params: { location_id: locationId },
  })
  return data
}

// --- Apex Intelligence API (advanced decision-support engines) ---

/** Get adaptive identification (self-calibrating detection thresholds) */
export const fetchAdaptive = async (locationId?: number) => {
  const { data } = await api.get('/api/v1/apex/adaptive', {
    params: locationId != null ? { location_id: locationId } : {},
  })
  return data
}

/** Get marine carbon monitoring (CO2 fluxes & blue-carbon potential) */
export const fetchCarbon = async () => {
  const { data } = await api.get('/api/v1/apex/carbon')
  return data
}

/** Get light pollution & artificial-light-at-night impact */
export const fetchLightPollution = async () => {
  const { data } = await api.get('/api/v1/apex/light-pollution')
  return data
}

/** Get remote-sensing harmonization & multi-source fusion */
export const fetchRemoteSensing = async () => {
  const { data } = await api.get('/api/v1/apex/remote-sensing')
  return data
}

/** Get ranked observation recommendations (what to sample next, where, why) */
export const fetchRecommendations = async (minPriority = 0) => {
  const { data } = await api.get('/api/v1/apex/recommendations', {
    params: { min_priority: minPriority },
  })
  return data
}

/** Get simulated Argo float trajectories (paths + T/S profiles) */
export const fetchArgo = async (locationId?: number, nFloats = 3) => {
  const { data } = await api.get('/api/v1/apex/argo', {
    params: { location_id: locationId, n_floats: nFloats },
  })
  return data
}

/** Get real Argo floats in the database (latest position per float). */
export const fetchRealArgoFloats = async () => {
  const { data } = await api.get('/api/v1/argo/floats')
  return data
}

/** Get the real vertical profile (temperature & salinity vs depth) of one float. */
export const fetchArgoFloatProfile = async (floatId: string) => {
  const { data } = await api.get(`/api/v1/argo/floats/${floatId}/profile`)
  return data
}

/** Get the latest real NOAA ERSST v5 SST month grid (from /api/v1/ersst/latest). */
export const fetchErsstLatest = async () => {
  const { data } = await api.get('/api/v1/ersst/latest')
  return data
}

/** Get the nearest real ERSST grid cell to a point (from /api/v1/ersst/near). */
export const fetchErsstNear = async (latitude: number, longitude: number, maxDistDeg = 3.5) => {
  const { data } = await api.get('/api/v1/ersst/near', {
    params: { latitude, longitude, max_dist_deg: maxDistDeg },
  })
  return data
}

/** Real NOAA CoastWatch satellite Chl-a month grid (from /api/v1/chlor/latest). */
export const fetchChlorLatest = async () => {
  const { data } = await api.get('/api/v1/chlor/latest')
  return data
}

/** Nearest real satellite Chl-a cell to a point (from /api/v1/chlor/near). */
export const fetchChlorNear = async (latitude: number, longitude: number, maxDistDeg = 0.2) => {
  const { data } = await api.get('/api/v1/chlor/near', {
    params: { latitude, longitude, max_dist_deg: maxDistDeg },
  })
  return data
}

/**
 * True u/v current-velocity vectors of the real ocean-model 3D grid.
 * Honest availability: when the grid was never ingested, the payload carries
 * `available:false` with the exact reason, and no vectors are returned.
 */
export const fetchModelGridVectors = async (depthM = 0) => {
  const { data } = await api.get('/api/v1/modelgrid/vectors', {
    params: { depth_m: depthM },
  })
  return data
}

/** 3D-field overview: which model variables exist + their real depth levels (feature #7). */
export const fetchModelGridSummary = async () => {
  const { data } = await api.get('/api/v1/modelgrid/summary')
  return data
}

/**
 * One horizontal depth slice of the latest real model month (feature #7):
 * every real cell at that depth, optionally evaluated for salinity.
 */
export const fetchModelGridSlice = async (
  variable: 'temperature' | 'salinity' | 'current_speed',
  depthM: number,
) => {
  const { data } = await api.get('/api/v1/modelgrid/latest', {
    params: { variable, depth_m: depthM },
  })
  return data
}

/** Real glider deployments with their extents + which BGC sensors were carried (feature #16/#17). */
export const fetchGliderDeployments = async () => {
  const { data } = await api.get('/api/v1/glider/deployments')
  return data
}

/** Real sample transect (position/depth/time + measured fields) of one deployment. */
export const fetchGliderSamples = async (deploymentId: string, limit = 2000) => {
  const { data } = await api.get(`/api/v1/glider/${encodeURIComponent(deploymentId)}/samples`, {
    params: { limit },
  })
  return data
}

/** Real biogeochemical traces of a glider deployment (feature #17): dissolved
 * oxygen / chlorophyll / nitrate vs depth — fields the payload didn't carry are
 * honestly reported as absent. */
export const fetchGliderBgc = async (deploymentId: string) => {
  const { data } = await api.get(`/api/v1/glider/${encodeURIComponent(deploymentId)}/bgc`)
  return data
}

/** Get fish-aggregation zones + seasonal fishing calendar */
export const fetchFisheries = async () => {
  const { data } = await api.get('/api/v1/coastal/fisheries')
  return data
}

/** Get coral bleaching thermal-stress risk index */
export const fetchCoral = async () => {
  const { data } = await api.get('/api/v1/coastal/coral')
  return data
}

/** Run an oil-spill / search-and-rescue drift simulation */
export const postDriftSim = async (payload: Record<string, unknown>) => {
  const { data } = await api.post('/api/v1/coastal/spill', payload)
  return data
}

/** Get sea-level-rise inundation estimate for a scenario (metres) */
export const fetchSLR = async (scenario = 1.0) => {
  const { data } = await api.get('/api/v1/coastal/slr', { params: { scenario } })
  return data
}

/** Get rip-current / beach safety flags */
export const fetchBeachSafety = async () => {
  const { data } = await api.get('/api/v1/coastal/beach')
  return data
}

/** Get economic impact estimate (INR) for active events */
export const fetchEconomicImpact = async () => {
  const { data } = await api.get('/api/v1/coastal/impact')
  return data
}

// --- Ocean Digital Twin API (model-vs-observation intelligence) ---

/** Model-vs-observation comparison for one region+variable. */
export const fetchTwinCompare = async (locationId: number, variable = 'temperature', depthM = 0) => {
  const { data } = await api.get('/api/v1/twin/compare', {
    params: { location_id: locationId, variable, depth_m: depthM },
  })
  return data
}

/** Per-region disagreement map (colors the globe patches). */
export const fetchTwinDisagreement = async (variable = 'temperature', depthM = 0) => {
  const { data } = await api.get('/api/v1/twin/disagreement', {
    params: { variable, depth_m: depthM },
  })
  return data
}

/** Model-vs-observation depth profile for one region. */
export const fetchTwinProfile = async (locationId: number, variable = 'temperature') => {
  const { data } = await api.get('/api/v1/twin/profile', {
    params: { location_id: locationId, variable },
  })
  return data
}

/** Ranked anomaly intelligence across the network. */
export const fetchAnomalies = async (params: Record<string, string | number | undefined> = {}) => {
  const { data } = await api.get('/api/v1/twin/anomalies', { params })
  return data
}

/** Detected ocean events (enriched with model-vs-observed evidence). */
export const fetchTwinEvents = async (locationId?: number) => {
  const { data } = await api.get('/api/v1/twin/events', {
    params: locationId != null ? { location_id: locationId } : {},
  })
  return data
}

/** Transparent confidence scoring for a region+variable. */
export const fetchTwinConfidence = async (locationId: number, variable = 'temperature') => {
  const { data } = await api.get('/api/v1/twin/confidence', {
    params: { location_id: locationId, variable },
  })
  return data
}

/** Evidence-driven AI explanation for a region+variable. */
export const fetchTwinExplain = async (locationId: number, variable = 'temperature', depthM = 0) => {
  const { data } = await api.get('/api/v1/twin/explain', {
    params: { location_id: locationId, variable, depth_m: depthM },
  })
  return data
}

/** Data-source registry + health. */
export const fetchDataSources = async () => {
  const { data } = await api.get('/api/v1/twin/sources')
  return data
}

/** Aggregated decision-support ocean situation. */
export const fetchSituation = async () => {
  const { data } = await api.get('/api/v1/twin/situation')
  return data
}

/** 3D vertical transect curtain between two picked ocean points. */
export const fetchTransect = async (params: {
  lat1: number; lon1: number; lat2: number; lon2: number;
  variable?: string; depth_max?: number; n_samples?: number;
}) => {
  const { data } = await api.get('/api/v1/twin/transect', {
    params: {
      lat1: params.lat1,
      lon1: params.lon1,
      lat2: params.lat2,
      lon2: params.lon2,
      variable: params.variable ?? 'temperature',
      depth_max: params.depth_max ?? 2000,
      n_samples: params.n_samples ?? 48,
    },
  })
  return data
}

// --- TIDE-Loop API (explainable, request-derived observation ranking) ---

/** Ranked TIDE observation candidates (scored + decision attached). */
export const fetchTideCandidates = async (params: {
  location_id?: number; variable?: string; depth_m?: number;
} = {}) => {
  const { data } = await api.get('/api/v1/tide/candidates', {
    params: {
      location_id: params.location_id,
      variable: params.variable ?? 'temperature',
      depth_m: params.depth_m ?? 0,
    },
  })
  return data
}

/** Transparent TIDE evidence chain + explanation for the top candidate. */
export const fetchTideExplanation = async (params: {
  location_id?: number; variable?: string; depth_m?: number;
} = {}) => {
  const { data } = await api.get('/api/v1/tide/explanation', {
    params: {
      location_id: params.location_id,
      variable: params.variable ?? 'temperature',
      depth_m: params.depth_m ?? 0,
    },
  })
  return data
}

/** TIDE hypothesis verdict (sensor / model / missing phenomenon). */
export const fetchTideVerdict = async (params: {
  location_id: number; variable?: string; depth_m?: number;
}) => {
  const { data } = await api.get('/api/v1/tide/verdict', {
    params: {
      location_id: params.location_id,
      variable: params.variable ?? 'temperature',
      depth_m: params.depth_m ?? 0,
    },
  })
  return data
}

/** Existing ocean event composed with its Event DNA + TIDE context. */
export const fetchTideEventContext = async (eventId: string) => {
  const { data } = await api.get(`/api/v1/tide/events/${eventId}`)
  return data
}

/** Per-region TIDE data gaps (sparse / stale / depth gaps). */
export const fetchTideDataGaps = async (params: {
  location_id?: number; variable?: string; depth_m?: number;
} = {}) => {
  const { data } = await api.get('/api/v1/tide/data-gaps', { params })
  return data
}

/** Per-region TIDE model-vs-observation disagreement. */
export const fetchTideDisagreements = async (params: {
  location_id?: number; variable?: string; depth_m?: number;
} = {}) => {
  const { data } = await api.get('/api/v1/tide/disagreements', { params })
  return data
}

/** Deterministic what-if observation simulation (never persisted). */
export const runVirtualObservation = async (payload: {
  location_id: number
  variable?: string
  depth_m?: number
  observation_type?: string
  value?: number | null
}) => {
  const { data } = await api.post('/api/v1/tide/virtual-observation', payload)
  return data
}

/** Phase 6 — index of playable TIDE events (same order event-N resolves). */
export const fetchTideEventIndex = async () => {
  const { data } = await api.get('/api/v1/tide/events')
  return data
}

/** Phase 6 — read-only two-mode TIDE Decision Replay for an existing event. */
export const fetchDecisionReplay = async (params: {
  eventId: string
  location_id?: number
  variable?: string
  depth_m?: number
  observation_type?: string
  value?: number | null
}) => {
  const { data } = await api.get(`/api/v1/tide/events/${params.eventId}/replay`, {
    params: {
      location_id: params.location_id,
      variable: params.variable,
      depth_m: params.depth_m ?? 0,
      observation_type: params.observation_type ?? 'VIRTUAL_SENSOR',
      value: params.value,
    },
  })
  return data
}

/** Phase 8 — TIDE validation status (maturity, dataset, ground truth, boundary). */
export const fetchTideValidationStatus = async () => {
  const { data } = await api.get('/api/v1/tide/validation')
  return data
}

/** Phase 8 — machine-readable TIDE benchmark report (fair, budget-configurable). */
export const fetchTideBenchmarks = async (params: {
  budget?: number
  variables?: string
  strategies?: string
  depth_m?: number
  seed?: number
} = {}) => {
  const { data } = await api.get('/api/v1/tide/benchmarks', {
    params: {
      budget: params.budget ?? 1,
      variables: params.variables,
      strategies: params.strategies,
      depth_m: params.depth_m ?? 0,
      seed: params.seed ?? 42,
    },
  })
  return data
}

/** Phase 8 — case/event-level drill-down behind a benchmark number. */
export const fetchTideBenchmarkCase = async (
  caseId: string,
  params: { variable?: string; depth_m?: number; budget?: number; seed?: number } = {},
) => {
  const { data } = await api.get(`/api/v1/tide/benchmarks/${encodeURIComponent(caseId)}`, {
    params: {
      variable: params.variable ?? 'temperature',
      depth_m: params.depth_m ?? 0,
      budget: params.budget ?? 1,
      seed: params.seed ?? 42,
    },
  })
  return data
}

/** Phase 9 — per-subsystem system health for the status indicator. */
export const fetchSystemHealth = async (): Promise<SystemHealthResponse> => {
  const { data } = await api.get('/api/v1/health')
  return data
}

/** Phase 9 — honest demonstration-data status + demonstration event. */
export const fetchDemoStatus = async (): Promise<DemoStatusResponse> => {
  const { data } = await api.get('/api/v1/demo/status')
  return data
}

/** Phase 9 — create the labelled SIMULATED demonstration dataset. */
export const seedDemoData = async (
  params: { location?: string; kind?: 'heatwave' | 'surge'; force?: boolean } = {},
): Promise<DemoSeedResponse> => {
  const { data } = await api.post('/api/v1/demo/seed', null, {
    params: {
      location: params.location ?? 'goa',
      kind: params.kind ?? 'heatwave',
      force: params.force ?? false,
    },
  })
  return data
}

/** Phase 9 — delete only simulation-labelled rows; real observations untouched. */
export const resetDemoData = async (): Promise<DemoResetResponse> => {
  const { data } = await api.post('/api/v1/demo/reset')
  return data
}