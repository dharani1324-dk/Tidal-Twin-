/**
 * TIDE Voice Agent - shared types (pure, dependency-free).
 */

export type VoicePhase =
  | 'idle'
  | 'ready'
  | 'connecting'
  | 'listening'
  | 'thinking'
  | 'speaking'
  | 'paused'
  | 'error'
  | 'fallback'

export type VoiceAuthor = 'user' | 'assistant' | 'system'

export interface VoiceMessage {
  id: string
  role: VoiceAuthor
  text: string
  time: number
  sources?: string[]
  kind?: 'user' | 'assistant' | 'tool' | 'error' | 'sys'
}

export interface VoiceToolInvocation {
  id: string
  name: string
  args: Record<string, unknown>
  status: 'executing' | 'ok' | 'error'
  feedback?: string
  time: number
}

export interface VoiceToolSpec {
  type: 'function'
  name: string
  description: string
  parameters: Record<string, unknown>
}

/** Immutable snapshot of what the model needs about the page the user is on.
 * Published by pages (DigitalTwin etc.) via the voice context registry. */
export interface VoiceContextData {
  page: string
  locationId?: number
  focusName?: string
  latitude?: number
  longitude?: number
  depth?: number | null
  variable?: string
  cursor?: number | null
  timeLabel?: string
  layers?: string[]
  selectedEventId?: string
  tideRecommendation?: { location: string; variable: string; observationType: string } | null
  locations?: {
    id: number
    name: string
    country?: string | null
    regionType?: string | null
    latitude?: number | null
    longitude?: number | null
  }[]
  lastAnomaly?: {
    location: string
    variable: string
    label: string
    severity: string
    confidence: number
    model: number | null
    observed: number | null
  } | null
  selectedAnomalyId?: string | null
  lastEvent?: { eventId: string; type: string; location: string } | null
  missionNote?: string
}

/** Payload returned by the backend session endpoint. */
export interface VoiceSessionBundle {
  model: string
  voice: string
  session_id: string | null
  ephemeral_key: { value: string; expires_at: number | null }
  instructions_bytes: number
  tools: VoiceToolSpec[]
  includes_context: boolean
  setup: Record<string, unknown> | null
}

export interface VoiceApiStatus {
  enabled: boolean
  model: string
  voice: string
  tool_count?: number
  tool_names: string[]
  ui_layers: string[]
  ui_pages: string[]
  provenance: string[]
  limitations: string[]
}

/** UI command event flowing over the voice command bus. */
export interface VoiceUiEvent {
  type: string
  payload: Record<string, unknown>
  time: number
}

export type VoiceUiCommand =
  | 'voice:focus'
  | 'voice:set-depth'
  | 'voice:set-time'
  | 'voice:set-variable'
  | 'voice:toggle-layer'
  | 'voice:navigate'
  | 'voice:reveal-panel'
  | 'voice:set-tide-visible'

export const VOICE_UI_COMMANDS: readonly VoiceUiCommand[] = [
  'voice:focus',
  'voice:set-depth',
  'voice:set-time',
  'voice:set-variable',
  'voice:toggle-layer',
  'voice:navigate',
  'voice:reveal-panel',
  'voice:set-tide-visible',
]

export const PAGE_ROUTES: Record<string, string> = {
  home: '/',
  globe: '/globe',
  monitoring: '/monitoring',
  classic: '/classic',
  assistant: '/assistant',
  validate: '/validate',
  anomalies: '/anomalies',
  forensics: '/forensics',
  intelligence: '/intelligence',
  tide: '/tide',
  replay: '/tide/replay',
  validation: '/tide/validation',
  oceanvision: '/oceanvision',
  coastal: '/coastal',
  scenarios: '/scenarios',
  safety: '/safety',
  risk: '/risk',
  stories: '/stories',
  reports: '/reports',
}

// A fade hint attached to every assistant message so the UI can style it.
export const VOICE_MAX_FALLBACK_WORDS = 260