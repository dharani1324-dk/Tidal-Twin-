/**
 * OceanVerse AI - API Client
 * ==========================
 * This is how our frontend talks to the backend.
 * We use axios to make HTTP requests to the FastAPI server.
 */

import axios from 'axios'

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

/** Ask the OceanVerse Copilot a natural-language question (multi-turn context) */
export const askAssistant = async (question: string, context: Record<string, unknown> = {}) => {
  const { data } = await api.post('/api/v1/assistant/ask', { question, context })
  return data
}

/** Get the copilot capability/affordance list for the UI */
export const fetchAssistantCapabilities = async () => {
  const { data } = await api.get('/api/v1/assistant/capabilities')
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
  temperature_delta?: number
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