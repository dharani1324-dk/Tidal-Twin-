/**
 * Unit tests for the TIDE Voice Agent - PURE modules only.
 *
 * Runs with the built-in Node test runner (Node >=24 type-strips TS):
 *   npm test  (runs node --test on the tests directory, matching *.test.ts).
 *
 * The modules here are dependency-free by design (no axios, no React, no DOM),
 * so every rule can be verified hermeticly: bus replay, JSON-schema argument
 * validation, place resolution and the F/B category router.
 */

import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  findGazetteerEntry,
  haversineKm,
  matchMonitoredLocations,
  normalizePlace,
  resolvePlace,
} from '../src/services/voice/gazetteer.ts'
import { isPlainObject, validateAgainst, validateToolArgs } from '../src/services/voice/jsonSchema.ts'
import { classifyCategory, routeFeedback, CATEGORY_LABELS, type VoiceCategory } from '../src/services/voice/router.ts'
import { VoiceBus, VOICE_REPLAY_TTL_MS, publishVoiceCommand, voiceBus } from '../src/services/voice/voiceBus.ts'
import {
  getVoiceContext,
  resolveFromContext,
  resetVoiceContext,
  setVoiceContext,
} from '../src/services/voice/voiceContext.ts'
import { PAGE_ROUTES, type VoiceToolSpec } from '../src/services/voice/types.ts'

/* ================= gazetteer ================= */

const MONITORED = [
  { id: 1, name: 'North Bay of Bengal', country: 'India', latitude: 16.0, longitude: 89.0 },
  { id: 2, name: 'West Arabian Sea', country: 'India', latitude: 15.0, longitude: 69.5 },
  { id: 3, name: 'Tamil Nadu Coast', country: 'India', latitude: 11.9, longitude: 79.9 },
]

test('normalizePlace strips region suffixes and case', () => {
  assert.equal(normalizePlace('BAY OF BENGAL'), 'of bengal')
  assert.equal(normalizePlace('Tamil Nadu Coast Region'), 'tamil nadu')
})

test('matchMonitoredLocations ranks exact matches highest', () => {
  const ranked = matchMonitoredLocations('Tamil Nadu', MONITORED)
  assert.ok(ranked.length > 0)
  assert.equal(ranked[0].id, 3)
  assert.ok(ranked[0].score >= 70)
})

test('findGazetteerEntry finds built-in entries by keyword', () => {
  const gz = findGazetteerEntry('Bay of Bengal')
  assert.ok(gz)
  assert.equal(gz?.name, 'Bay of Bengal')
  assert.ok(Math.abs(gz.latitude - 14) < 0.1)
})

test('haversineKm computes a plausible distance', () => {
  const km = haversineKm(13.08, 80.28, 13.08, 80.28)
  assert.equal(km, 0)
  const goaToChennai = haversineKm(15.3, 73.8, 13.08, 80.28)
  assert.ok(goaToChennai > 600 && goaToChennai < 750, `got ${goaToChennai}`)
})

test('resolvePlace prioritises id -> monitored name -> gazetteer -> coords -> context', () => {
  assert.deepEqual(resolvePlace({ location_id: 2, locations: MONITORED }), {
    locationId: 2,
    name: 'West Arabian Sea',
    latitude: 15.0,
    longitude: 69.5,
    source: 'location',
  })

  const byName = resolvePlace({ region: 'North Bay of Bengal', locations: MONITORED })
  assert.equal(byName.source, 'location')
  assert.equal(byName.locationId, 1)

  const byGaz = resolvePlace({ region: 'Andaman sea', locations: MONITORED })
  assert.equal(byGaz.source, 'gazetteer')
  assert.ok(byGaz.latitude != null && byGaz.longitude != null)

  const byCoords = resolvePlace({ latitude: 13.0, longitude: 80.3, locations: MONITORED })
  assert.equal(byCoords.source, 'location') // within 300 km → snaps to Tamil Nadu Coast

  const byContext = resolvePlace({ contextFocus: 3, contextName: 'Tamil Nadu Coast', locations: MONITORED })
  assert.equal(byContext.source, 'context')
  assert.equal(byContext.locationId, 3)

  assert.equal(resolvePlace({}).source, null)
})

/* ================= json schema ================= */

const WEB_SEARCH_SPEC: VoiceToolSpec = {
  type: 'function',
  name: 'web_search',
  description: 'search',
  parameters: {
    type: 'object',
    properties: {
      query: { type: 'string', minLength: 1, maxLength: 250 },
      max_results: { type: 'integer', minimum: 1, maximum: 5 },
    },
    required: ['query'],
    additionalProperties: false,
  },
}

const FOCUS_SPEC: VoiceToolSpec = {
  type: 'function',
  name: 'ui_focus_region',
  description: 'focus',
  parameters: {
    type: 'object',
    properties: {
      location_id: { type: 'integer' },
      latitude: { type: 'number' },
      longitude: { type: 'number' },
      region: { type: 'string' },
    },
    additionalProperties: false,
  },
}

const TOOL_SPECS = [WEB_SEARCH_SPEC, FOCUS_SPEC]

test('validateToolArgs accepts valid args and rejects bad ones', () => {
  assert.deepEqual(validateToolArgs(TOOL_SPECS, 'web_search', { query: 'cyclone news' }), { ok: true, errors: [] })
  assert.deepEqual(validateToolArgs(TOOL_SPECS, 'web_search', { query: 'x', max_results: 10 }), {
    ok: false,
    errors: ['max_results: must be <= 5'],
  })
  const missing = validateToolArgs(TOOL_SPECS, 'web_search', {})
  assert.equal(missing.ok, false)
  assert.ok(missing.errors[0].includes('query'))
  const extra = validateToolArgs(TOOL_SPECS, 'web_search', { query: 'goa', api_key: 'nope' })
  assert.equal(extra.ok, false)
  assert.ok(extra.errors[0].includes('unexpected argument'))
  assert.deepEqual(validateToolArgs(TOOL_SPECS, 'ui_focus_region', {}), { ok: true, errors: [] })
})

test('validateToolArgs rejects unknown tools and non-object args', () => {
  assert.equal(validateToolArgs(TOOL_SPECS, 'nope.tool', {}).ok, false)
  assert.equal(validateToolArgs(TOOL_SPECS, 'web_search', 'not an object').ok, false)
})

test('validateAgainst enforces enums and limits', () => {
  assert.deepEqual(validateAgainst('a', { type: 'string', minLength: 2 }), ['value: shorter than minLength'])
  assert.deepEqual(validateAgainst('red', { type: 'string', enum: ['green', 'blue'] }), ['value: must be one of green, blue'])
  assert.deepEqual(validateAgainst(0.5, { type: 'integer' }), ['value: expected integer'])
  assert.equal(isPlainObject({ a: 1 }), true)
  assert.equal(isPlainObject(null), false)
  assert.equal(isPlainObject([]), false)
})

/* ================= router ================= */

test('classifyCategory routes the six documented categories', () => {
  assert.equal(classifyCategory('What is TidalTwin?').category, 'A')
  assert.equal(classifyCategory('tell me the latest news about the election').category, 'D')
  assert.equal(classifyCategory('recommend the next observation for the tide').category, 'C')
  assert.equal(classifyCategory('what is the temperature at Goa?').category, 'B')
  assert.equal(classifyCategory('what is an upwelling?').category, 'E')
  assert.equal(classifyCategory('go to the tide page').category, 'F')
  assert.equal(classifyCategory('next').category, 'F')
})

test('classifyCategory does not misfire on data words', () => {
  assert.equal(classifyCategory('show me the anomaly at Goa').category, 'F')
  assert.notEqual(classifyCategory('what happened at the anomaly site?').category, 'F')
  assert.equal(classifyCategory('what is the current speed near Chennai?').category, 'B')
  assert.equal(routeFeedback({ category: 'B', reasons: ['test'] }), `Category B - ${CATEGORY_LABELS.B} (test)`)
})

test('every category has a label', () => {
  for (const c of ['A', 'B', 'C', 'D', 'E', 'F'] as VoiceCategory[]) {
    assert.ok(CATEGORY_LABELS[c].length > 0)
  }
})

/* ================= voice bus ================= */

test('bus publishes to subscribers and replays within the TTL', () => {
  const bus = new VoiceBus()
  const seen: string[] = []
  const unsub = bus.subscribe((e) => seen.push(e.type))
  bus.publish('voice:focus', { locationId: 1 })
  bus.publish('voice:set-depth', { depthM: 0 })
  unsub()
  // A late subscriber must hear the buffered commands.
  const late: string[] = []
  const unsub2 = bus.subscribe((e) => late.push(e.type))
  assert.ok(late.includes('voice:focus'))
  assert.deepEqual(seen, ['voice:focus', 'voice:set-depth'])
  unsub2()
})

test('bus clear() drops the replay buffer but keeps live subscribers', () => {
  const bus = new VoiceBus()
  bus.publish('voice:focus', { locationId: 2 }) // stale, pre-test noise
  bus.clear()
  const live: string[] = []
  const unsub = bus.subscribe((e) => live.push(e.type))
  assert.deepEqual(live, []) // replay buffer was cleared
  bus.publish('voice:focus', { locationId: 2 })
  bus.clear()
  const late: string[] = []
  const unsub2 = bus.subscribe((e) => late.push(e.type))
  bus.publish('voice:navigate', { page: 'tide' })
  assert.deepEqual(late, ['voice:navigate'])
  assert.deepEqual(live, ['voice:focus', 'voice:navigate'])
  unsub()
  unsub2()
})

test('tiny-TTL bus stops replaying expired events', async () => {
  const tiny = new VoiceBus(5)
  tiny.publish('voice:focus', {})
  await new Promise((r) => setTimeout(r, 20))
  const late: string[] = []
  tiny.subscribe((e) => late.push(e.type))
  assert.deepEqual(late, [])
})

test('publishVoiceCommand helper reaches the global bus', () => {
  voiceBus.clear()
  const got: string[] = []
  const unsub = voiceBus.subscribe((e) => got.push(e.type))
  publishVoiceCommand('voice:focus', {})
  publishVoiceCommand('voice:set-tide-visible', {})
  assert.deepEqual(got, ['voice:focus', 'voice:set-tide-visible'])
  unsub()
  voiceBus.clear()
})

/* ================= voice context ================= */

test('context registry merges, snapshots and resolves place references', () => {
  resetVoiceContext()
  const snapshot = setVoiceContext({
    page: 'globe',
    locationId: 1,
    focusName: 'North Bay of Bengal',
    latitude: 16,
    longitude: 89,
    depth: 0,
    variable: 'temperature',
    locations: [
      { id: 1, name: 'North Bay of Bengal', latitude: 16, longitude: 89 },
      { id: 2, name: 'West Arabian Sea', latitude: 15, longitude: 69.5 },
    ],
  })
  assert.equal(snapshot.page, 'globe')
  assert.equal(getVoiceContext().focusName, 'North Bay of Bengal')

  const here = resolveFromContext({})
  assert.equal(here.source, 'context')
  assert.equal(here.locationId, 1)

  const byName = resolveFromContext({ region: 'West Arabian Sea' })
  assert.equal(byName.source, 'location')
  assert.equal(byName.locationId, 2)

  resetVoiceContext()
  assert.equal(getVoiceContext().page, 'home')
  assert.equal(resolveFromContext({}).source, null)
})

/* ================= shared constants ================= */

test('PAGE_ROUTES and replay TTL are stable', () => {
  assert.equal(PAGE_ROUTES.tide, '/tide')
  assert.equal(PAGE_ROUTES.globe, '/globe')
  assert.equal(PAGE_ROUTES.replay, '/tide/replay')
  assert.ok(VOICE_REPLAY_TTL_MS === 6000)
})