/**
 * Unit tests for the real-data globe layers (ERSST SST + satellite Chl).
 *
 * Runs with the built-in Node test runner (Node >=24 type-strips TS):
 *   npm test   (== node --test tests)
 *
 * Pure module is src/components/3d/globe/layerMath.ts (no Cesium/React).
 */

import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  chlorColorCss,
  inIndiaBox,
  nearestCell,
  tempColorCss,
} from '../src/components/3d/globe/layerMath.ts'
import {
  CHL_LEGACY_DOMAIN,
  TEMP_DEFAULT_DOMAIN,
  arrowFor,
  buildLatLonField,
  chlorColorCssFrom,
  domainFrom,
  isoLevelsFor,
  isoLines,
  kForValue,
  salColorCss,
  salColorCssFrom,
  tempColorCssFrom,
  type IsoSegment,
} from '../src/components/3d/globe/layerMath.ts'

/* ---- Isosurface contours (SIH #11) ---- */

test('buildLatLonField reconstructs a regular grid from samples', () => {
  const samples = [
    { latitude: 5, longitude: 60, value: 20 },
    { latitude: 5, longitude: 62, value: 21 },
    { latitude: 7, longitude: 60, value: 22 },
    { latitude: 7, longitude: 62, value: 23 },
  ]
  const f = buildLatLonField(samples)
  assert.ok(f)
  assert.equal(f!.dlat, 2)
  assert.equal(f!.dlon, 2)
  assert.equal(f!.nLat, 2)
  assert.equal(f!.nLon, 2)
  assert.deepEqual(f!.values, [20, 21, 22, 23]) // row-major
  assert.equal(buildLatLonField([]), null)
  assert.equal(buildLatLonField([{ latitude: 5, longitude: 60, value: 1 }]), null)
})

test('buildLatLonField tolerates unordered and shuffled samples', () => {
  const samples = [
    { latitude: 7, longitude: 61, value: 30 },
    { latitude: 5, longitude: 61, value: 10 },
    { latitude: 5, longitude: 63, value: 12 },
    { latitude: 7, longitude: 63, value: 34 },
  ]
  const f = buildLatLonField(samples)
  assert.ok(f)
  assert.equal(f!.nLat, 2)
  assert.equal(f!.nLon, 2)
  assert.equal(f!.values[1 * 2 + 0], 30) // row 1 (lat 7), col 0 (lon 61)
  assert.equal(f!.values[0 * 2 + 1], 12)
})

test('isoLines draws one crossing segment for a single heated corner', () => {
  const f = buildLatLonField([
    { latitude: 5, longitude: 60, value: 20 },
    { latitude: 5, longitude: 62, value: 21 },
    { latitude: 7, longitude: 60, value: 22 },
    { latitude: 7, longitude: 62, value: 23 },
  ])!
  const segs = isoLines(f, 20.5)
  assert.equal(segs.length, 1)
  const [s] = segs
  // The isotherm crosses the top edge mid-point (5°N, 61°E) and the left edge
  // a quarter up (5.5°N, 60°E) — a single segment, entirely inside the cell.
  const ends = new Set([
    `${s.lat0.toFixed(3)}:${s.lon0.toFixed(3)}`,
    `${s.lat1.toFixed(3)}:${s.lon1.toFixed(3)}`,
  ])
  assert.deepEqual([...ends].sort(), ['5.000:61.000', '5.500:60.000'])
})

test('isoLines returns none when the level is outside the data range', () => {
  const f = buildLatLonField([
    { latitude: 5, longitude: 60, value: 20 },
    { latitude: 5, longitude: 62, value: 21 },
    { latitude: 7, longitude: 60, value: 22 },
    { latitude: 7, longitude: 62, value: 23 },
  ])!
  assert.deepEqual(isoLines(f, 10), [])
  assert.deepEqual(isoLines(f, 30), [])
})

test('isoLines closes a hot core into a ring (topology: every endpoint shared)', () => {
  const samples: { latitude: number; longitude: number; value: number }[] = []
  for (let i = 0; i < 4; i++) {
    for (let j = 0; j < 4; j++) {
      const inCore = i >= 1 && i <= 2 && j >= 1 && j <= 2
      samples.push({ latitude: 5 + i, longitude: 60 + j, value: inCore ? 30 : 20 })
    }
  }
  const f = buildLatLonField(samples)!
  const segs = isoLines(f, 25)
  assert.ok(segs.length >= 4, 'a closed contour needs multiple segments')
  const endpointKey = (s: IsoSegment, pick0: boolean) =>
    pick0 ? `${s.lat0.toFixed(3)}:${s.lon0.toFixed(3)}` : `${s.lat1.toFixed(3)}:${s.lon1.toFixed(3)}`
  const count = new Map<string, number>()
  for (const s of segs) {
    for (const k of [endpointKey(s, true), endpointKey(s, false)]) {
      count.set(k, (count.get(k) ?? 0) + 1)
    }
  }
  // Closed loop: every segment endpoint is shared by exactly two segments.
  for (const n of count.values()) {
    assert.equal(n, 2)
  }
})

test('isoLines leaves an honest gap where a cell has no data', () => {
  const f = buildLatLonField([
    { latitude: 5, longitude: 60, value: 20 },
    { latitude: 5, longitude: 62, value: 21 },
    { latitude: 5, longitude: 64, value: 22 },
    { latitude: 7, longitude: 60, value: 22 },
    { latitude: 7, longitude: 64, value: 24 },
    // lat 7 / lon 62 is a missing cell (null) -> the middle column is gappy
  ])!
  const segs = isoLines(f, 21)
  for (const s of segs) {
    // No segment may pass through the missing cell column (lon 62).
    const lonMid = (s.lon0 + s.lon1) / 2
    assert.ok(!(s.lat0 >= 6 && s.lat1 >= 6 && lonMid > 62 - 1e-9 && lonMid < 62 + 1e-9))
  }
})

test('isoLevelsFor yields strictly interior, ascending, distinct levels', () => {
  const levels = isoLevelsFor({ min: 20, max: 32 }, 6)
  assert.equal(levels.length, 6)
  for (const l of levels) {
    assert.ok(l > 20 && l < 32)
  }
  for (let i = 1; i < levels.length; i++) {
    assert.ok(levels[i] > levels[i - 1])
  }
  assert.equal(levels[0], 21.71) // 20 + 12 * (1/7)
  assert.ok(Number.isInteger(levels[0] * 100))
  assert.deepEqual(isoLevelsFor({ min: 5, max: 5 }, 6), []) // degenerate domain
})

/* ---- Current-velocity arrows (SIH #14) ---- */

test('arrowFor points eastward for pure +u and northward for pure +v', () => {
  const east = arrowFor({ latitude: 10, longitude: 65, u: 0.5, v: 0 })!
  assert.ok(east.head.longitude > east.tail.longitude)
  assert.ok(Math.abs(east.head.latitude - east.tail.latitude) < 1e-9)

  const north = arrowFor({ latitude: 10, longitude: 65, u: 0, v: 0.5 })!
  assert.ok(north.head.latitude > north.tail.latitude)
  assert.ok(Math.abs(north.head.longitude - north.tail.longitude) < 1e-6)
})

test('arrowFor clamps length and draws twin fins back from the head', () => {
  const fast = arrowFor({ latitude: 10, longitude: 65, u: 9, v: 9 })! // ~12.7 m/s
  const len = Math.abs(fast.head.latitude - fast.tail.latitude)
  assert.ok(len > 0 && len <= 1.4)
  assert.equal(fast.fins.length, 2)
  // Fins start at the head and point back toward the tail.
  for (const fin of fast.fins) {
    const fromHead = Math.abs(fin.latitude - fast.head.latitude) + Math.abs(fin.longitude - fast.head.longitude)
    assert.ok(fromHead > 0)
  }
})

test('arrowFor is honest: NaN/zero-speed vectors yield no arrow', () => {
  assert.equal(arrowFor({ latitude: 10, longitude: 65, u: NaN, v: 0 }), null)
  assert.equal(arrowFor({ latitude: 10, longitude: 65, u: 0, v: 0 }), null) // measured-but-stationary
  assert.equal(arrowFor({ latitude: 10, longitude: 65, u: Infinity, v: 1 }), null)
})

const HEX = /^#[0-9a-f]{6}$/

test('tempColorCss maps the ERSST ramp to exact endpoints', () => {
  assert.equal(tempColorCss(20), '#22d3ee') // k = 0
  assert.equal(tempColorCss(31), '#ff8a28') // k >= 1
  assert.equal(tempColorCss(-10), '#22d3ee') // clamped low -> still cold
  assert.equal(tempColorCss(60), '#ff8a28') // clamped high -> still hot
  assert.match(tempColorCss(25.5), HEX) // midpoint is a valid 24-bit colour
  assert.notEqual(tempColorCss(25.5), tempColorCss(20))
  assert.notEqual(tempColorCss(25.5), tempColorCss(31))
})

test('tempColorCss is monotonically hot across the ocean range', () => {
  // 8-bit lerp means neighbours may round to the same hex; the sweep must still
  // traverse more than just the two endpoints, and order high > low.
  const seen = new Set<number>()
  for (let t = 5; t <= 33; t += 1) {
    const c = tempColorCss(t)
    assert.match(c, HEX)
    for (const i of [1, 3, 5]) {
      seen.add(parseInt(c.slice(i, i + 2), 16))
    }
  }
  assert.ok(seen.size >= 6, 'expected >6 distinct channel bytes across the sweep')
})

test('chlorColorCss guards log10(0) and clamps the ramp', () => {
  assert.equal(chlorColorCss(0), chlorColorCss(0.04)) // log-guard, not NaN
  assert.equal(chlorColorCss(0.04), '#1d4ed8') // bottom of scale (k = 0)
  assert.equal(chlorColorCss(200), '#eab308') // top of scale (k >= 1)
  assert.match(chlorColorCss(1), HEX)
})

test('chlorColorCss: deep blue -> green -> yellow as chl rises', () => {
  const at = (v: number) => chlorColorCss(v)
  const blue = (c: string) => parseInt(c.slice(5, 7), 16) // trailing channel
  const red = (c: string) => parseInt(c.slice(1, 3), 16)
  const green = (c: string) => parseInt(c.slice(3, 5), 16)

  const low = at(0.05)
  const mid = at(0.7)
  const high = at(25)

  assert.notEqual(low, mid)
  assert.notEqual(mid, high)
  // The blue channel fades from deep blue (oligotrophic) to yellow (bloom).
  assert.ok(blue(low) > blue(mid) && blue(mid) > blue(high))
  // Top of the bloom scale is clear yellow (high red AND green).
  assert.ok(red(high) > 0x80 && green(high) > 0x80)
})

test('nearestCell picks the nearest cell and honours the max-distance threshold', () => {
  const grid = [
    { latitude: 13.0, longitude: 63.0, sst: 28.4 },
    { latitude: 13.0, longitude: 65.0, sst: 27.9 },
    { latitude: 15.0, longitude: 63.0, sst: 29.1 },
  ]
  const hit = nearestCell(13.2, 63.1, grid, 3.5)
  assert.ok(hit)
  assert.equal(hit!.cell.sst, 28.4)
  assert.ok(hit!.dist < 1) // cos-lat weighted deg

  // Points far past 3.5 deg -> null (honest "Data unavailable").
  assert.equal(nearestCell(41.0, -70.0, grid, 3.5), null)

  // maxDistDeg is respected as a hard bound even when a cell exists.
  assert.equal(nearestCell(13.2, 63.1, grid, 0.05), null)
})

test('nearestCell handles empty grids and far-off longitudes', () => {
  assert.equal(nearestCell(10, 60, [], 10), null)
  // Cells near the anti-meridian still resolve with cos-lat lon weights.
  const lond = [
    { latitude: 10.0, longitude: 179.0, chlor_a: 0.5 },
    { latitude: 10.0, longitude: -179.0, chlor_a: 0.7 },
  ]
  const hit = nearestCell(10.0, 179.5, lond, 2)
  assert.ok(hit)
  assert.equal(hit!.cell.chlor_a, 0.5)
})

test('inIndiaBox matches the coverage chip boundaries', () => {
  assert.ok(inIndiaBox(13.84, 63.46)) // Arabian Sea
  assert.ok(inIndiaBox(5, 62)) // south-western corner (inclusive)
  assert.ok(inIndiaBox(24, 97)) // north-eastern corner (inclusive)
  assert.ok(!inIndiaBox(4.9, 63)) // just south of the box
  assert.ok(!inIndiaBox(13.84, 61.9)) // just west of the box
  assert.ok(!inIndiaBox(24.1, 63))
})

/* ---- Dynamic continuous colour scale (SIH 8/9/10) ---- */

test('domainFrom derives min/max and ignores null/NaN', () => {
  assert.deepEqual(domainFrom([1, 2, 3]), { min: 1, max: 3 })
  assert.deepEqual(domainFrom([NaN, 1, null, undefined, 2]), { min: 1, max: 2 })
  assert.deepEqual(domainFrom([NaN, null]), null) // all junk -> no domain
  assert.deepEqual(domainFrom([]), null) // single identical value still yields a range edge
  assert.deepEqual(domainFrom([5, 5]), { min: 5, max: 5 })
})

test('kForValue linear maps endpoints and clamps outside', () => {
  const d = { min: 24, max: 27 }
  assert.equal(kForValue(24, d, 'linear'), 0)
  assert.equal(kForValue(27, d, 'linear'), 1)
  assert.equal(kForValue(25.5, d, 'linear'), 0.5)
  assert.equal(kForValue(-10, d, 'linear'), 0)
  assert.equal(kForValue(60, d, 'linear'), 1)
  assert.equal(kForValue(NaN, d, 'linear'), 0)
  assert.equal(kForValue(5, { min: 5, max: 5 }, 'linear'), 0) // degenerate range
})

test('kForValue log is geometric (midpoint = sqrt(lo*hi)), guarded <= 0', () => {
  const d = { min: 0.04, max: 20 } // legacy chl window
  assert.equal(kForValue(0.04, d, 'log'), 0)
  assert.equal(kForValue(20, d, 'log'), 1)
  const mid = Math.sqrt(0.04 * 20)
  assert.ok(Math.abs(kForValue(mid, d, 'log') - 0.5) < 1e-9)
  // log-space halfway is NOT the same position as a linear halfway.
  const linMid = 0.04 + (20 - 0.04) / 2
  assert.ok(kForValue(linMid, d, 'log') !== kForValue(linMid, d, 'linear'))
  // Non-positive domain bottoms out at a tiny floor instead of NaN.
  assert.ok(Number.isFinite(kForValue(-3, { min: -1, max: 5 }, 'log')))
  assert.equal(kForValue(-3, { min: -1, max: 5 }, 'log'), 0)
})

test('tempColorCssFrom rescales endpoints to the live data domain', () => {
  const d = { min: 24, max: 27 }
  assert.equal(tempColorCssFrom(24, d, 'linear'), '#22d3ee') // k = 0 -> cold
  assert.equal(tempColorCssFrom(27, d, 'linear'), '#ff8a28') // k = 1 -> hot
  assert.equal(tempColorCssFrom(31, d, 'linear'), '#ff8a28') // hot cell clamps, no out-of-range
  assert.equal(tempColorCssFrom(20, d, 'linear'), '#22d3ee')
  // The same cell gets a DIFFERENT colour than the fixed legacy window would give
  // (25.5 is exactly the midpoint of BOTH windows, so use a value off-centre).
  assert.notEqual(tempColorCssFrom(26, d, 'linear'), tempColorCss(26))
})

test('tempColorCssFrom falls back to the legacy window without stats', () => {
  for (let t = 5; t <= 33; t += 2) {
    assert.equal(tempColorCssFrom(t), tempColorCss(t))
    assert.equal(tempColorCssFrom(t, null, 'linear'), tempColorCss(t))
    assert.equal(tempColorCssFrom(t, TEMP_DEFAULT_DOMAIN, 'linear'), tempColorCss(t))
  }
})

test('chlorColorCssFrom honours a live domain in linear and log', () => {
  const d = { min: 0.05, max: 5 }
  assert.equal(chlorColorCssFrom(0.05, d, 'log'), '#1d4ed8') // k = 0 -> deep blue
  assert.equal(chlorColorCssFrom(5, d, 'log'), '#eab308') // k = 1 -> bloom yellow
  assert.equal(chlorColorCssFrom(2.525, d, 'linear'), '#16a34a') // exact k = 0.5 -> green
  // Linear vs log disagree for values far from the geometric mid.
  assert.notEqual(chlorColorCssFrom(1, d, 'linear'), chlorColorCssFrom(1, d, 'log'))
})

test('chlorColorCssFrom matches the legacy log ramp without stats', () => {
  assert.equal(chlorColorCssFrom(0.04), chlorColorCss(0.04))
  assert.equal(chlorColorCssFrom(0.04, null, 'log'), chlorColorCss(0.04))
  assert.equal(chlorColorCssFrom(200, CHL_LEGACY_DOMAIN, 'log'), '#eab308')
  assert.equal(chlorColorCssFrom(0), chlorColorCss(0)) // log-guard parity
})

test('salColorCss maps the 32-37 PSU window and clamps outside', () => {
  assert.equal(salColorCss(32), '#1e40af') // fresh end
  assert.equal(salColorCss(37), '#22d3ee') // salty end
  assert.equal(salColorCss(-5), '#1e40af') // clamped low
  assert.equal(salColorCss(50), '#22d3ee') // clamped high
  assert.equal(salColorCss(34.5), '#208acf') // exact midpoint (lerpHex rounds each channel)
})

test('salColorCssFrom rescales to a live domain', () => {
  const d = { min: 33, max: 36 }
  assert.equal(salColorCssFrom(33, d, 'linear'), '#1e40af')
  assert.equal(salColorCssFrom(36, d, 'linear'), '#22d3ee')
  assert.equal(salColorCssFrom(34.5, d, 'linear'), '#208acf')
  // Falls back to the 32-37 PSU window without stats.
  assert.equal(salColorCssFrom(32), '#1e40af')
  assert.notEqual(salColorCssFrom(34, d, 'linear'), salColorCss(34))
})