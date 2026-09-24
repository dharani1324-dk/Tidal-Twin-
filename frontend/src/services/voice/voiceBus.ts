/**
 * TIDE Voice Agent - UI command bus (pure, dependency-free).
 *
 * A tiny publish/subscribe channel with a short replay buffer. Pages publish
 * UI commands (focus/depth/time/layer/...) and the agent publishes intent
 * results. Replay lets a page that mounts AFTER a command was issued (e.g.
 * the Digital Twin page loads lazily) still receive the latest command.
 *
 * `voice:context` events are handled by the context registry, not the bus.
 */

import type { VoiceUiEvent, VoiceUiCommand } from './types.ts'

export const VOICE_REPLAY_TTL_MS = 6000
export const VOICE_CONTEXT_EVENT = 'voice:context' as const

type Listener = (event: VoiceUiEvent) => void

interface BusState {
  events: VoiceUiEvent[]
  listeners: Set<Listener>
}

/** A short-lived command bus. Configurable TTL for tests/telemetry. */
export class VoiceBus {
  readonly replayTtlMs: number
  private state: BusState = { events: [], listeners: new Set() }

  constructor(replayTtlMs: number = VOICE_REPLAY_TTL_MS) {
    this.replayTtlMs = replayTtlMs
  }

  /** Publish a command + payload to every current subscriber. */
  publish(type: VoiceUiCommand | string, payload: Record<string, unknown> = {}): VoiceUiEvent {
    const event: VoiceUiEvent = { type, payload, time: Date.now() }
    const state = this.state
    state.events.push(event)
    this.prune()
    for (const listener of Array.from(state.listeners)) {
      try {
        listener(event)
      } catch (err) {
        // A failing subscriber must never break the bus.
        console.error('[voice-bus] subscriber error', err)
      }
    }
    return event
  }

  /**
   * Subscribe to commands. Returns an unsubscribe function.
   * Fresh subscribers immediately receive commands issued within the TTL.
   */
  subscribe(listener: Listener): () => void {
    const state = this.state
    this.prune()
    for (const event of state.events) {
      if (Date.now() - event.time <= this.replayTtlMs) {
        try {
          listener(event)
        } catch (err) {
          console.error('[voice-bus] replay listener error', err)
        }
      }
    }
    state.listeners.add(listener)
    return () => {
      state.listeners.delete(listener)
    }
  }

  /** Drop all buffered events (leaves live subscribers intact). */
  clear(): void {
    this.state.events = []
  }

  private prune(): void {
    const now = Date.now()
    this.state.events = this.state.events.filter((e) => now - e.time <= this.replayTtlMs)
  }

  /** Serialisable snapshot (telemetry/testing). */
  snapshot(): VoiceUiEvent[] {
    this.prune()
    return [...this.state.events]
  }
}

/** The app-wide bus. */
export const voiceBus = new VoiceBus()

/**
 * Convenience sender. `voice:focus` is the most used command.
 */
export function publishVoiceCommand(
  type: VoiceUiCommand,
  payload: Record<string, unknown> = {},
): VoiceUiEvent {
  return voiceBus.publish(type, payload)
}