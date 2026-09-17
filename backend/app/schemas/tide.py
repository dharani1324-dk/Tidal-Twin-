"""Typed API contracts for the TIDE decision layer.

These objects are domain responses, not database models.  Phase 3 deliberately
keeps recommendations request-derived so it does not require a migration.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ObservationStatus = Literal["REAL", "HISTORICAL", "SIMULATED", "SYNTHETIC", "MODEL_DERIVED"]
ObservationMethod = Literal[
    "BUOY", "ARGO_FLOAT", "RESEARCH_VESSEL", "DRONE", "AUTONOMOUS_VEHICLE", "MANUAL_SAMPLE", "VIRTUAL_SENSOR",
]


class TideObservation(BaseModel):
    id: str
    location_id: int
    latitude: float | None = None
    longitude: float | None = None
    depth_m: float = 0.0
    timestamp: datetime | None = None
    variable: str
    value: float | None = None
    observation_type: str = "UNKNOWN"
    status: ObservationStatus
    quality: float | None = Field(default=None, ge=0, le=1)
    source: str | None = None


class TideFactor(BaseModel):
    name: str
    score: float = Field(ge=0, le=1)
    description: str


class TideEvidence(BaseModel):
    evidence_id: str | None = None
    type: str
    strength: float = Field(ge=0, le=1)
    description: str
    variable: str | None = None
    source_system: str | None = None
    location_id: int | None = None
    depth_m: float | None = None
    timestamp: datetime | None = None
    data_status: ObservationStatus | None = None


class TideGap(BaseModel):
    type: str
    severity: float = Field(ge=0, le=1)
    score: float = Field(ge=0, le=1)
    description: str
    affected_depth_m: float | None = None
    affected_time_range: str | None = None


class TideDisagreement(BaseModel):
    location_id: int
    location: str
    depth_m: float = 0.0
    variable: str
    model_value: float | None = None
    observed_value: float | None = None
    difference: float | None = None
    normalized_severity: float = Field(ge=0, le=1)
    temporal_persistence: float = Field(ge=0, le=1)
    spatial_consistency: float = Field(ge=0, le=1)
    evidence: list[TideEvidence] = []


class TideCandidate(BaseModel):
    candidate_id: str
    location_id: int
    location: str
    latitude: float | None = None
    longitude: float | None = None
    depth_m: float = 0.0
    variable: str
    observation_type: ObservationMethod
    status: ObservationStatus = "MODEL_DERIVED"
    decision_impact: float = Field(ge=0, le=1)
    uncertainty: float = Field(ge=0, le=1)
    data_gap: float = Field(ge=0, le=1)
    anomaly_persistence: float = Field(ge=0, le=1)
    observation_cost: float = Field(ge=0, le=1)
    observation_value: float = Field(ge=0)
    expected_uncertainty_reduction: float = Field(ge=0, le=1)
    affected_decision: str
    reason: str
    evidence: list[TideEvidence] = []
    confidence: float = Field(ge=0, le=1)
    confidence_factors: list[TideFactor] = []
    limitations: list[str] = []


class TideVerdict(BaseModel):
    verdict: Literal["LIKELY_SENSOR_ISSUE", "LIKELY_MODEL_ISSUE", "LIKELY_MISSING_PHENOMENON", "INSUFFICIENT_EVIDENCE"]
    confidence: float = Field(ge=0, le=1)
    evidence: list[TideEvidence]
    alternative_explanation: str
    recommended_observation: str


class VirtualObservationRequest(BaseModel):
    location_id: int = Field(ge=0)
    variable: str = "temperature"
    depth_m: float = Field(default=0.0, ge=0)
    observation_type: ObservationMethod = "VIRTUAL_SENSOR"
    value: float | None = None


class VirtualObservationState(BaseModel):
    uncertainty: float = Field(ge=0, le=1)
    anomaly_risk: float = Field(ge=0, le=1)
    ranking: int = Field(ge=1)
    decision: str
    confidence: float = Field(ge=0, le=1)
    observation_value: float = Field(ge=0)


class VirtualObservationReading(BaseModel):
    value: float | None = None
    variable: str
    depth_m: float = 0.0
    location: str
    location_id: int
    observation_type: ObservationMethod
    status: ObservationStatus = "SIMULATED"


class VirtualObservationChange(BaseModel):
    before: float = Field(ge=0, le=1)
    after: float = Field(ge=0, le=1)
    delta: float


class VirtualObservationSimulation(BaseModel):
    candidate_id: str
    location_id: int
    location: str
    variable: str
    depth_m: float = 0.0
    observation_type: ObservationMethod
    before: VirtualObservationState
    simulated_observation: VirtualObservationReading
    after: VirtualObservationState
    uncertainty_change: VirtualObservationChange
    risk_change: VirtualObservationChange
    confidence_change: VirtualObservationChange
    decision_changed: bool
    decision_result: Literal["DECISION_CHANGED", "DECISION_UNCHANGED"]
    supports_model_hypothesis: bool
    notes: list[str] = []
    method: str = "deterministic_heuristic"


# ---------------------------------------------------------------------------
# Phase 6 — TIDE Decision Replay & Validation contracts.
# Read-only session-scoped reconstruction; never persisted.
# ---------------------------------------------------------------------------


class ReplayState(BaseModel):
    decision: str
    uncertainty: float | None = Field(default=None, ge=0, le=1)
    anomaly_risk: float | None = Field(default=None, ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence_count: int = 0
    observation_status: ObservationStatus | None = None
    observation_value: float | None = None
    data_gap: float | None = Field(default=None, ge=0, le=1)
    persistence: float | None = Field(default=None, ge=0, le=1)
    model_value: float | None = None
    observed_value: float | None = None
    difference: float | None = None
    ranking: int | None = Field(default=None, ge=1)
    expected_uncertainty_reduction: float | None = Field(default=None, ge=0, le=1)


class ReplayStep(BaseModel):
    id: str
    label: str
    description: str
    sources: list[str] = []
    model_only: ReplayState
    tide_assisted: ReplayState


class ReplayModeSummary(BaseModel):
    decision: str
    uncertainty: float | None = Field(default=None, ge=0, le=1)
    anomaly_risk: float | None = Field(default=None, ge=0, le=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence_count: int = 0
    observation_available: bool = False
    observation_value: float | None = None
    detection_time_h: float | None = None


class ReplayMetric(BaseModel):
    model_only: float | str | None = None
    tide_assisted: float | str | None = None
    delta: float | None = None
    calculated: bool = True
    detail: str | None = None
    changed: bool | None = None


class ReplayComparison(BaseModel):
    uncertainty: ReplayMetric
    confidence: ReplayMetric
    anomaly_risk: ReplayMetric
    decision: ReplayMetric
    detection_time: ReplayMetric


class ReplayDecision(BaseModel):
    decision_changed: bool
    decision_result: Literal["DECISION_CHANGED", "DECISION_UNCHANGED"]
    before: str
    after: str
    why: list[str] = []
    explanation: str


class ReplayRegret(BaseModel):
    available: bool = True
    value: float = Field(ge=0, le=1)
    label: str
    definition: str
    caveat: str
    explanation: str


class ReplayValidationBlock(BaseModel):
    predicted: float | None = None
    observed: float | None = None
    difference: float | None = None
    difference_pct: float | None = None
    evidence_status: float | None = None
    quality_status: ObservationStatus | None = None
    simulated: bool = False


class ReplayValidation(BaseModel):
    available: bool
    message: str
    variable: str | None = None
    depth_m: float = 0.0
    location: str | None = None
    data_status: ObservationStatus | None = None
    model_only: ReplayValidationBlock
    tide_assisted: ReplayValidationBlock


class ReplayJourneyPoint(BaseModel):
    step: str
    label: str
    uncertainty_model_only: float | None = None
    uncertainty_tide_assisted: float | None = None
    anomaly_risk_model_only: float | None = None
    anomaly_risk_tide_assisted: float | None = None


class ReplayEvidence(BaseModel):
    step: str
    type: str
    description: str = ""
    source_system: str | None = None
    strength: float | None = Field(default=None, ge=0, le=1)
    data_status: ObservationStatus | None = None
    mode: str = "both"


class ReplayLoopStatus(BaseModel):
    key: str
    label: str
    reached: bool
    detail: str
    data_status: ObservationStatus | None = None


class DecisionReplay(BaseModel):
    event_id: str
    event: dict
    event_dna: dict
    variable: str
    depth_m: float = 0.0
    location_id: int
    location: str
    candidate_id: str
    labels: dict
    rules: dict
    steps: list[ReplayStep]
    model_only: ReplayModeSummary
    tide_assisted: ReplayModeSummary
    comparison: ReplayComparison
    decision: ReplayDecision
    regret: ReplayRegret
    validation: ReplayValidation
    uncertainty_journey: list[ReplayJourneyPoint]
    evidence_journey: list[ReplayEvidence]
    tide_loop: list[ReplayLoopStatus]
    simulated_observation: VirtualObservationReading
    notes: list[str] = []
    data_status: dict
    method: str = "deterministic_heuristic"
