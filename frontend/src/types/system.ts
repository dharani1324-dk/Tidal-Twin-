/**
 * Phase 9 — system health + demonstration mode contracts.
 * Mirrors backend `app/api/health.py` and `app/api/demo.py`.
 */

export type SubsystemStatus = 'AVAILABLE' | 'LIMITED' | 'UNAVAILABLE' | 'OPTIONAL / UNAVAILABLE'
export type OverallStatus = 'healthy' | 'degraded' | 'unavailable'

export interface HealthCheck {
  status: SubsystemStatus
  detail: string
  [key: string]: unknown
}

export interface SystemHealthResponse {
  status: OverallStatus
  service: string
  version: string
  release?: string
  environment?: string
  simulation_mode?: boolean
  checked_at: string
  checks: Record<string, HealthCheck>
}

export interface DemoGuideStep {
  step: number
  title: string
  route: string
  description: string
}

export interface DemonstrationEvent {
  available: boolean
  event_id: string | null
  location_id?: number | null
  location?: string | null
  event_type?: string | null
  label?: string | null
  data_status?: string | null
  completeness_score?: number
  criteria?: string[]
  candidate_count?: number
  reason: string
  candidates_considered?: number
}

export interface DemoSource {
  source: string
  count: number
  status: string
  is_simulated: boolean
}

export interface DemoStatusResponse {
  generated_at: string
  demo_data_present: boolean
  labels: { dataset: string; simulated_observation: string }
  total_observations: number
  simulated_observations: number
  real_observations: number
  sources: DemoSource[]
  detected_events: number
  demonstration_event: DemonstrationEvent
  guide_steps: DemoGuideStep[]
  notes: string[]
}

export interface DemoSeedResponse {
  created: number
  replaced?: number
  skipped: boolean
  reason?: string
  location?: string
  kind?: string
  alerts_created?: number
  simulated_observations?: number
  detected_events?: number
  label: string
  note?: string
}

export interface DemoResetResponse {
  deleted: number
  simulated_before: number
  simulated_after: number
  real_observations_untouched: number
  label: string
  note: string
}
