/**
 * TidalTwin - TIDE shared contracts
 * ===================================
 * Frontend mirrors of the backend TIDE-Loop payloads (app/schemas/tide.py).
 * Every data field displayed on the TIDE Command Center must come from the
 * real backend; these types only describe the shapes of that data.
 */

export type TideStatus = 'REAL' | 'HISTORICAL' | 'SIMULATED' | 'SYNTHETIC' | 'MODEL_DERIVED'

export type TideObservationType =
  | 'BUOY'
  | 'ARGO_FLOAT'
  | 'RESEARCH_VESSEL'
  | 'DRONE'
  | 'AUTONOMOUS_VEHICLE'
  | 'MANUAL_SAMPLE'
  | 'VIRTUAL_SENSOR'

export type TideDecision = 'INVESTIGATE_ANOMALY' | 'INCREASE_MONITORING' | 'CONTINUE_MONITORING'

export type TideVerdictKind =
  | 'LIKELY_SENSOR_ISSUE'
  | 'LIKELY_MODEL_ISSUE'
  | 'LIKELY_MISSING_PHENOMENON'
  | 'INSUFFICIENT_EVIDENCE'

export interface TideFactor {
  name: string
  score: number
  description: string
}

export interface TideEvidence {
  evidence_id?: string
  type: string
  strength: number
  description: string
  variable?: string | null
  source_system?: string | null
  location_id?: number | null
  depth_m?: number | null
  timestamp?: string | null
  data_status?: TideStatus | null
}

export interface TideCandidate {
  candidate_id: string
  location_id: number
  location: string
  latitude: number | null
  longitude: number | null
  depth_m: number
  variable: string
  observation_type: TideObservationType
  status: TideStatus
  decision_impact: number
  uncertainty: number
  data_gap: number
  anomaly_persistence: number
  observation_cost: number
  observation_value: number
  expected_uncertainty_reduction: number
  affected_decision: TideDecision
  reason: string
  evidence: TideEvidence[]
  confidence: number
  confidence_factors: TideFactor[]
  limitations: string[]
}

export interface TideGap {
  type: string
  severity: number
  score: number
  description: string
  affected_depth_m?: number | null
  affected_time_range?: string | null
}

export interface TideDisagreement {
  location_id: number
  location: string
  depth_m: number
  variable: string
  model_value: number | null
  observed_value: number | null
  difference: number | null
  normalized_severity: number
  temporal_persistence: number
  spatial_consistency: number
  evidence: TideEvidence[]
}

export interface TideUncertainty {
  location_id: number
  location: string
  score: number
  level: string
  factors: TideFactor[]
}

export interface TideConfidenceContext {
  overall_confidence: number
  level: string
  supporting_factors: string[]
  limiting_factors: string[]
  evidence_count: number
  data_coverage: string
}

export interface TideExplanation {
  candidate_id: string
  explanation: {
    summary: string
    reasons: string[]
    expected_benefit: string
    affected_decision: TideDecision
    confidence: TideConfidenceContext
    evidence: TideEvidence[]
  }
  decision_context: {
    current_decision: string
    affected_decision: TideDecision
    decision_impact_score: number
    possible_decision_change: string
    why_it_matters: string
  }
}

export interface TideVerdict {
  verdict: TideVerdictKind
  confidence: number
  alternative_explanation: string
  summary: string
  evidence: TideEvidence[]
  candidate_id: string
  recommended_observation: {
    candidate_id: string
    observation_type: TideObservationType
    variable: string
    depth_m: number
    location: string
  }
  limitations: string[]
}

export interface TideEvent {
  event_type: string
  location_id?: number
  location?: string
  severity?: string
  confidence?: number
  model?: number | null
  observed?: number | null
  model_observed_diff?: number | null
  persistence?: number
  status?: string
  [k: string]: unknown
}

export interface TideEventDNA {
  id?: string
  tags: string[]
  features?: Record<string, number>
  [k: string]: unknown
}

export interface TideEventContext {
  event_id: string
  event: TideEvent
  event_dna: TideEventDNA
  uncertainty: { score: number; level: string }
  data_gaps: TideGap[]
  disagreement: TideDisagreement
  top_candidates: TideCandidate[]
  evidence: TideEvidence[]
  confidence: TideConfidenceContext
  verdict: TideVerdict | null
  decision_context: TideExplanation['decision_context']
  evidence_chain: string[]
  message?: string
}

export interface VirtualObservationState {
  uncertainty: number
  anomaly_risk: number
  ranking: number
  decision: TideDecision
  confidence: number
  observation_value: number
}

export interface VirtualObservationReading {
  value: number | null
  variable: string
  depth_m: number
  location: string
  location_id: number
  observation_type: TideObservationType
  status: TideStatus
}

export interface VirtualObservationChange {
  before: number
  after: number
  delta: number
}

export interface VirtualObservationSimulation {
  candidate_id: string
  location_id: number
  location: string
  variable: string
  depth_m: number
  observation_type: TideObservationType
  before: VirtualObservationState
  simulated_observation: VirtualObservationReading
  after: VirtualObservationState
  uncertainty_change: VirtualObservationChange
  risk_change: VirtualObservationChange
  confidence_change: VirtualObservationChange
  decision_changed: boolean
  decision_result: 'DECISION_CHANGED' | 'DECISION_UNCHANGED'
  supports_model_hypothesis: boolean
  notes: string[]
  method: string
}

// ---------------------------------------------------------------------------
// Phase 6 — TIDE Decision Replay & Validation contracts
// ---------------------------------------------------------------------------

export interface ReplayState {
  decision: TideDecision
  uncertainty: number | null
  anomaly_risk: number | null
  confidence: number | null
  evidence_count: number
  observation_status: TideStatus | null
  observation_value: number | null
  data_gap: number | null
  persistence: number | null
  model_value: number | null
  observed_value: number | null
  difference: number | null
  ranking: number | null
  expected_uncertainty_reduction: number | null
}

export interface ReplayStep {
  id: string
  label: string
  description: string
  sources: string[]
  model_only: ReplayState
  tide_assisted: ReplayState
}

export interface ReplayModeSummary {
  decision: TideDecision
  uncertainty: number | null
  anomaly_risk: number | null
  confidence: number | null
  evidence_count: number
  observation_available: boolean
  observation_value: number | null
  detection_time_h: number | null
}

export interface ReplayMetric {
  model_only: number | string | null
  tide_assisted: number | string | null
  delta: number | null
  calculated: boolean
  detail: string | null
  changed?: boolean | null
}

export interface ReplayComparison {
  uncertainty: ReplayMetric
  confidence: ReplayMetric
  anomaly_risk: ReplayMetric
  decision: ReplayMetric
  detection_time: ReplayMetric
}

export interface ReplayDecision {
  decision_changed: boolean
  decision_result: 'DECISION_CHANGED' | 'DECISION_UNCHANGED'
  before: TideDecision
  after: TideDecision
  why: string[]
  explanation: string
}

export interface ReplayRegret {
  available: boolean
  value: number
  label: string
  definition: string
  caveat: string
  explanation: string
}

export interface ReplayValidationBlock {
  predicted: number | null
  observed: number | null
  difference: number | null
  difference_pct: number | null
  evidence_status: number | null
  quality_status: TideStatus | null
  simulated: boolean
}

export interface ReplayValidation {
  available: boolean
  message: string
  variable: string | null
  depth_m: number
  location: string | null
  data_status: TideStatus | null
  model_only: ReplayValidationBlock
  tide_assisted: ReplayValidationBlock
}

export interface ReplayJourneyPoint {
  step: string
  label: string
  uncertainty_model_only: number | null
  uncertainty_tide_assisted: number | null
  anomaly_risk_model_only: number | null
  anomaly_risk_tide_assisted: number | null
}

export interface ReplayEvidence {
  step: string
  type: string
  description: string
  source_system: string | null
  strength: number | null
  data_status: TideStatus | null
  mode: 'both' | 'tide_assisted' | string
}

export interface ReplayLoopStatus {
  key: string
  label: string
  reached: boolean
  detail: string
  data_status: TideStatus | null
}

export interface ReplayEventItem {
  event_id: string
  event_type: string
  label: string
  icon: string
  intensity: string
  confidence: number
  location_id: number
  location: string
  variable: string
  began_hours_ago: number | null
  data_status: string | null
}

export interface DecisionReplay {
  event_id: string
  event: TideEvent & Record<string, unknown>
  event_dna: TideEventDNA
  variable: string
  depth_m: number
  location_id: number
  location: string
  candidate_id: string
  labels: Record<string, string>
  rules: Record<string, string>
  steps: ReplayStep[]
  model_only: ReplayModeSummary
  tide_assisted: ReplayModeSummary
  comparison: ReplayComparison
  decision: ReplayDecision
  regret: ReplayRegret
  validation: ReplayValidation
  uncertainty_journey: ReplayJourneyPoint[]
  evidence_journey: ReplayEvidence[]
  tide_loop: ReplayLoopStatus[]
  simulated_observation: VirtualObservationReading
  notes: string[]
  data_status: Record<string, TideStatus | null>
  method: string
}

// ---------------------------------------------------------------------------
// Phase 8 — Scientific Validation, Benchmarking & Reliability contracts
// ---------------------------------------------------------------------------

export type TideMaturityState =
  | 'IMPLEMENTED'
  | 'DEMONSTRATED'
  | 'TESTED'
  | 'EMPIRICALLY_VALIDATED'

export interface TideMaturity {
  IMPLEMENTED: string[]
  DEMONSTRATED: string[]
  TESTED: string[]
  EMPIRICALLY_VALIDATED: string[]
  empirical_note: string
}

export interface TideGroundTruth {
  available: boolean
  reason: string
  false_alarm: string
  missed_event: string
}

export interface TideSensitivityFactor {
  factor: string
  low_score: number
  high_score: number
  delta: number | null
  expected_direction: string
  consistent: boolean
}

export interface TideSensitivity {
  label: string
  caveat: string
  base_vector: Record<string, number | null>
  factors: TideSensitivityFactor[]
  all_consistent: boolean
}

export interface TideRankingSensitivity {
  available: boolean
  reason?: string
  target_candidate_id?: string
  pool_size?: number
  factors?: { factor: string; rank_at_low: number; rank_at_high: number; rank_moved: boolean }[]
  label?: string
}

export interface TideEdgeCase {
  case: string
  observation_value: number
  finite_nonnegative: boolean
  expected_uncertainty_reduction: number
}

export interface TideEdgeCases {
  label: string
  results: TideEdgeCase[]
  all_finite: boolean
}

export interface TideScientificBoundary {
  can_show: string[]
  cannot_show: string[]
  statement: string
}

export interface TideValidationStatus {
  algorithm_version: string
  generated_at: string
  maturity: TideMaturity
  dataset: {
    id: string
    version: string
    status: string
    locations: number
    observations: number
    events: number
    source: string
  }
  ground_truth: TideGroundTruth
  cost_assumption: string
  candidate_pool: { variable: string; size: number; nonzero_observation_value: number }
  reproducibility: {
    algorithm_version: string
    dataset_id: string
    dataset_version: string
    default_seed: number
    default_budget: number
    cost_assumption: string
  }
  sensitivity: TideSensitivity
  ranking_sensitivity: TideRankingSensitivity
  edge_cases: TideEdgeCases
  scientific_boundary: TideScientificBoundary
  limitations: string[]
}

export interface TideBenchmarkStats {
  N: number
  status?: string
  mean?: number | null
  median?: number | null
  min?: number | null
  max?: number | null
  values?: (number | null)[]
}

export interface TideBenchmarkValidationError {
  available: boolean
  reason: string
  model_value: number | null
  observed_value: number | null
  difference: number | null
  absolute_error: number | null
}

export interface TideBenchmarkRow {
  case_id: string
  case_label: string
  event_id: string | null
  strategy: string
  budget: number
  selected: {
    candidate_id: string
    location_id: number
    location: string
    variable: string
    depth_m: number
    observation_type: string
    observation_cost: number | null
    status: TideStatus | null
  }
  initial_uncertainty: number | null
  final_uncertainty: number | null
  uncertainty_reduction: number | null
  relative_uncertainty_reduction: number | null
  decision_before: TideDecision
  decision_after: TideDecision
  decision_changed: boolean
  validation_error: TideBenchmarkValidationError
  detection_time: { available: boolean; value_h: number | null; reason: string }
  evidence_count: number
  observation_cost: number | null
  cost_label: string
  data_status: { candidate: TideStatus | null; observation: string }
  supports_model_hypothesis: boolean
  simulated: boolean
  notes: string[]
}

export interface TideBenchmarkAggregate {
  strategy: string
  strategy_label: string
  N: number
  cases_with_selection: number
  decision_changes: number
  decision_change_rate: number | null
  uncertainty_reduction: TideBenchmarkStats
  validation_error: TideBenchmarkStats
  detection_time: TideBenchmarkStats
  observation_cost: TideBenchmarkStats
}

export interface TideBenchmarkReport {
  algorithm_version: string
  generated_at: string
  dataset: TideValidationStatus['dataset']
  configuration: {
    budget: number
    strategies: string[]
    cases: string[]
    seed: number
    cost_assumption: string
    ground_truth_available: boolean
  }
  fairness: {
    same_pool_per_strategy: boolean
    budget_uniform: number
    pool_size_by_case: Record<string, number>
    note: string
  }
  selection: {
    pool_size_by_case: Record<string, number>
    nonzero_observation_value_by_case: Record<string, number>
    pool_is_degenerate: boolean
    note: string
  }
  rows: TideBenchmarkRow[]
  aggregates: TideBenchmarkAggregate[]
  ground_truth: TideGroundTruth
  timing_ms: Record<string, number>
  scientific_boundary: TideScientificBoundary
  limitations: string[]
}

export interface TideBenchmarkCaseDetail {
  algorithm_version: string
  generated_at: string
  case: {
    case_id: string
    label: string
    variable: string
    depth_m: number
    event_id: string | null
    location_id?: number
    began_hours_ago?: number | null
  }
  candidate_pool_size: number
  rows: TideBenchmarkRow[]
  ground_truth: TideGroundTruth
  cost_assumption: string
  note: string
}