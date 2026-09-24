/**
 * TIDE Voice Agent - page context registry (runtime singleton).
 *
 * Pages publish an immutable context snapshot (focus location, depth, cursor,
 * variable, layers, selection, mission note) and the voice session reads it to
 * resolve "here / this region / current view" references. Pure dependency-free
 * (no React, no API client), so it can be unit-tested under `node --test`.
 */

import { resolvePlace } from './gazetteer.ts'
import type { PlaceLookupOptions, ResolvedPlace } from './gazetteer.ts'
import type { VoiceContextData } from './types.ts'

let current: VoiceContextData = { page: 'home', layers: [] }
const listeners = new Set<(ctx: VoiceContextData) => void>()

function clone(ctx: VoiceContextData): VoiceContextData {
  return {
    ...ctx,
    layers: ctx.layers ? [...ctx.layers] : undefined,
    locations: ctx.locations ? [...ctx.locations] : undefined,
  }
}

/** Replace (merge) the current page context and notify listeners. */
export function setVoiceContext(partial: Partial<VoiceContextData>): VoiceContextData {
  current = clone({ ...current, ...partial })
  for (const listener of Array.from(listeners)) {
    try {
      listener(current)
    } catch (err) {
      console.error('[voice-context] listener error', err)
    }
  }
  return current
}

/** Latest immutable snapshot. */
export function getVoiceContext(): VoiceContextData {
  return clone(current)
}

export function subscribeVoiceContext(listener: (ctx: VoiceContextData) => void): () => void {
  listeners.add(listener)
  listener(current)
  return () => listeners.delete(listener)
}

export function resetVoiceContext(): void {
  current = { page: 'home', layers: [] }
}

/** Resolve a model "where" set against the CURRENT page context. */
export function resolveFromContext(opts: Omit<PlaceLookupOptions, 'locations' | 'contextFocus' | 'contextName'>): ResolvedPlace {
  const ctx = getVoiceContext()
  return resolvePlace({
    ...opts,
    location_id: opts.location_id,
    region: opts.region,
    latitude: opts.latitude,
    longitude: opts.longitude,
    locations: ctx.locations,
    contextFocus: ctx.locationId,
    contextName: ctx.focusName,
  })
}

/** One-line mission note for the session instructions (never user data). */
export function missionNote(): string {
  const ctx = current
  const parts = [`page=${ctx.page}`]
  if (ctx.focusName) parts.push(`focus=${ctx.focusName}`)
  if (ctx.depth != null) parts.push(`depth=${ctx.depth}m`)
  if (ctx.variable) parts.push(`variable=${ctx.variable}`)
  if (ctx.selectedEventId) parts.push(`event=${ctx.selectedEventId}`)
  if (ctx.tideRecommendation) parts.push('tide-active')
  return parts.join('; ')
}