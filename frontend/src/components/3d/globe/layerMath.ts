/**
 * Pure layer math for the real-data globe layers (ERSST SST + satellite Chl).
 *
 * Zero dependencies (no Cesium/React imports) so it can run under the plain
 * Node 24 test runner (`node --test`) — see tests/layerMath.test.ts.
 */

/** A minimal grid-cell shape; real layers use {latitude, longitude, sst|chlor_a}. */
export interface DegCell {
  latitude: number
  longitude: number
}

/** ERSST temperature ramp: cold #22d3ee -> hot #ff8a28, k=(temp-20)/11. */
export function tempColorCss(temp: number): string {
  const cold = [0x22, 0xd3, 0xee]
  const hot = [0xff, 0x8a, 0x28]
  const k = clamp((temp - 20) / 11, 0, 1)
  return lerpHex(cold, hot, k)
}

/** Ocean-colour ramp log10 over 0.04-20 mg/m3: blue -> green -> yellow. */
export function chlorColorCss(chl: number): string {
  const low = [0x1d, 0x4e, 0xd8]
  const mid = [0x16, 0xa3, 0x4a]
  const high = [0xea, 0xb3, 0x08]
  const k = clamp((Math.log10(chl <= 0 ? 0.04 : chl) + 1.4) / 2.7, 0, 1)
  if (k < 0.5) return lerpHex(low, mid, k * 2)
  return lerpHex(mid, high, (k - 0.5) * 2)
}

/* ------------------------------------------------------------------ *
 * Data-driven, dynamic continuous colour scale (SIH items 8/9/10).    *
 * The globe + colorbar rescale to the real ingested grid's min/max    *
 * instead of a hard-coded window, with a Linear/Log toggle.           *
 * ------------------------------------------------------------------ */

export type ScaleMode = 'linear' | 'log'

export interface ScaleDomain {
  min: number
  max: number
}

/** Default ERSST SST window kept for legacy calls with no stats yet. */
export const TEMP_DEFAULT_DOMAIN: ScaleDomain = { min: 20, max: 31 }

/** Default ocean-colour log window kept for legacy calls with no stats yet. */
export const CHL_LEGACY_DOMAIN: ScaleDomain = { min: 0.04, max: 20 }

/** Data-driven domain from real cells: NaN/undefined are skipped; empty -> null. */
export function domainFrom(values: readonly (number | null | undefined)[]): ScaleDomain | null {
  let min = Infinity
  let max = -Infinity
  for (const v of values) {
    if (v === null || v === undefined || !Number.isFinite(v)) continue
    if (v < min) min = v
    if (v > max) max = v
  }
  return Number.isFinite(min) && Number.isFinite(max) ? { min, max } : null
}

/** Normalised [0,1] position of a value on the scale (log uses log10 spacing). */
export function kForValue(value: number, domain: ScaleDomain, mode: ScaleMode): number {
  if (!Number.isFinite(value)) return 0
  const lo = mode === 'log' ? Math.log10(domain.min > 0 ? domain.min : 1e-4) : domain.min
  const hi = mode === 'log' ? Math.log10(domain.max > 0 ? domain.max : 1e-2) : domain.max
  const v = mode === 'log' ? Math.log10(Math.max(value, 10 ** lo)) : value
  if (!(hi > lo)) return 0
  return clamp((v - lo) / (hi - lo), 0, 1)
}

/** SST heat ramp over a live data-driven domain (Linear or Log). */
export function tempColorCssFrom(
  temp: number,
  domain: ScaleDomain | null = null,
  mode: ScaleMode = 'linear',
): string {
  const d = domain ?? TEMP_DEFAULT_DOMAIN
  const cold = [0x22, 0xd3, 0xee]
  const hot = [0xff, 0x8a, 0x28]
  return lerpHex(cold, hot, kForValue(temp, d, mode))
}

/** Ocean-colour ramp over a live data-driven domain (Linear by default). */
export function chlorColorCssFrom(
  chl: number,
  domain: ScaleDomain | null = null,
  mode: ScaleMode = 'linear',
): string {
  const d = domain ?? CHL_LEGACY_DOMAIN
  const low = [0x1d, 0x4e, 0xd8]
  const mid = [0x16, 0xa3, 0x4a]
  const high = [0xea, 0xb3, 0x08]
  const k = kForValue(chl, d, mode)
  if (k < 0.5) return lerpHex(low, mid, k * 2)
  return lerpHex(mid, high, (k - 0.5) * 2)
}

/** Default Indian-Ocean salinity window kept for legacy calls with no stats yet. */
export const SAL_DEFAULT_DOMAIN: ScaleDomain = { min: 32, max: 37 }

/** Haline ramp over 32-37 PSU: indigo blue -> cyan (fresh -> salty). */
export function salColorCss(sal: number): string {
  const low = [0x1e, 0x40, 0xaf]
  const high = [0x22, 0xd3, 0xee]
  const k = clamp((sal - 32) / 5, 0, 1)
  return lerpHex(low, high, k)
}

/** Salinity ramp over a live data-driven domain (Linear or Log). */
export function salColorCssFrom(
  sal: number,
  domain: ScaleDomain | null = null,
  mode: ScaleMode = 'linear',
): string {
  const d = domain ?? SAL_DEFAULT_DOMAIN
  return lerpHex([0x1e, 0x40, 0xaf], [0x22, 0xd3, 0xee], kForValue(sal, d, mode))
}

/** Depth ramp for glider/Argo samples: surface cyan -> abyss violet. */
export function depthColorCss(depth: number, min: number, max: number): string {
  const lo = [0x67, 0xe8, 0xf9] // #67e8f9 surface
  const mid = [0x34, 0x39, 0x99] // #343999 mid-water
  const hi = [0x4c, 0x1d, 0x95] // #4c1d95 abyss
  const span = max - min
  const k = clamp(span > 0 ? (depth - min) / span : 0, 0, 1)
  if (k < 0.5) return lerpHex(lo, mid, k * 2)
  return lerpHex(mid, hi, (k - 0.5) * 2)
}

/** Indian-Ocean box used for the "INDIA-BOX" coverage chips on the globe cards. */
export function inIndiaBox(lat: number, lon: number): boolean {
  return lat >= 5 && lat <= 24 && lon >= 62 && lon <= 97
}

export interface NearestHit<T extends DegCell> {
  cell: T
  /** Deg distance (cos-latitude weighted) between the point and the cell. */
  dist: number
}

/** Nearest grid cell within maxDistDeg, else null (used by the region readouts). */
export function nearestCell<T extends DegCell>(
  lat: number,
  lon: number,
  samples: readonly T[],
  maxDistDeg: number,
): NearestHit<T> | null {
  let best: T | null = null
  let bestD = Infinity
  const cosLat = Math.cos(lat * (Math.PI / 180))
  for (const s of samples) {
    const dLat = s.latitude - lat
    const dLon = (s.longitude - lon) * cosLat
    const d = Math.sqrt(dLat * dLat + dLon * dLon)
    if (d < bestD) {
      bestD = d
      best = s
    }
  }
  return best && bestD <= maxDistDeg ? { cell: best, dist: bestD } : null
}

/* ------------------------------------------------------------------ *
 * Isosurface contours (feature #11): marching squares over the real   *
 * ERSST grid, returning line segments in degrees. Pure + testable.    *
 * ------------------------------------------------------------------ */

export interface Sample2 {
  latitude: number
  longitude: number
  value: number
}

export interface LatLonField {
  lat0: number
  lon0: number
  dlat: number
  dlon: number
  nLat: number
  nLon: number
  /** Row-major (nLat × nLon); null = no data cell (contours skip it). */
  values: (number | null)[]
}

/** Reconstruct a regular lat/lon field from irregular cell samples. */
export function buildLatLonField(samples: Sample2[]): LatLonField | null {
  const lats = [...new Set(samples.map((s) => s.latitude))].sort((a, b) => a - b)
  const lons = [...new Set(samples.map((s) => s.longitude))].sort((a, b) => a - b)
  if (lats.length < 2 || lons.length < 2) return null
  const dlat = medianDiff(lats)
  const dlon = medianDiff(lons)
  if (!(dlat > 0) || !(dlon > 0)) return null
  const field: LatLonField = {
    lat0: lats[0],
    lon0: lons[0],
    dlat,
    dlon,
    nLat: lats.length,
    nLon: lons.length,
    values: new Array(lats.length * lons.length).fill(null),
  }
  for (const s of samples) {
    const i = Math.round((s.latitude - field.lat0) / dlat)
    const j = Math.round((s.longitude - field.lon0) / dlon)
    if (i < 0 || i >= field.nLat || j < 0 || j >= field.nLon) continue
    field.values[i * field.nLon + j] = s.value
  }
  return field
}

export interface IsoSegment {
  lat0: number
  lon0: number
  lat1: number
  lon1: number
}

/** Marching-squares contour segments for one iso-level (degrees space). */
export function isoLines(field: LatLonField, level: number): IsoSegment[] {
  const out: IsoSegment[] = []
  const vals = field.values
  const nLon = field.nLon
  for (let i = 0; i < field.nLat - 1; i++) {
    for (let j = 0; j < nLon - 1; j++) {
      const tl = vals[i * nLon + j]
      const tr = vals[i * nLon + j + 1]
      const br = vals[(i + 1) * nLon + j + 1]
      const bl = vals[(i + 1) * nLon + j]
      // A cell touching any no-data corner is a real data gap — skip it,
      // leaving an honest gap in the contour instead of a guessed line.
      if (tl === null || tr === null || br === null || bl === null) continue
      const pTop = crosses(tl, tr, level) // on y = 0
      const pRight = crosses(tr, br, level) // on x = 1
      const pBottom = crosses(bl, br, level) // on y = 1
      const pLeft = crosses(tl, bl, level) // on x = 0
      const pts: { x: number; y: number }[] = []
      if (pTop !== null) pts.push({ x: pTop, y: 0 })
      if (pRight !== null) pts.push({ x: 1, y: pRight })
      if (pBottom !== null) pts.push({ x: pBottom, y: 1 })
      if (pLeft !== null) pts.push({ x: 0, y: pLeft })
      if (pts.length === 0 || pts.length % 2 !== 0) continue
      if (pts.length === 2) {
        const [a, b] = pts
        if (oppositeEdges(a, b)) {
          const c = { x: 0.5, y: 0.5 }
          pushSeg(out, field, i, j, a, c)
          pushSeg(out, field, i, j, c, b)
        } else {
          pushSeg(out, field, i, j, a, b)
        }
      } else {
        // Saddle (4 crossings): connect opposite edge pairs through the centre.
        const c = { x: 0.5, y: 0.5 }
        pushSeg(out, field, i, j, pts[0], c)
        pushSeg(out, field, i, j, c, pts[2])
        pushSeg(out, field, i, j, pts[1], c)
        pushSeg(out, field, i, j, c, pts[3])
      }
    }
  }
  return out
}

export function isoLevelsFor(domain: ScaleDomain, count = 6): number[] {
  const lo = domain.min
  const hi = domain.max
  if (!(hi > lo) || !(count > 0)) return []
  const levels: number[] = []
  for (let k = 1; k <= count; k++) {
    levels.push(Number((lo + (hi - lo) * (k / (count + 1))).toFixed(2)))
  }
  return levels
}

/* ------------------------------------------------------------------ *
 * Current-velocity arrows (feature #14): true u/v per cell → a small  *
 * lat/lon arrow geometry. Pure + testable.                            *
 * ------------------------------------------------------------------ */

export interface CurrentVectorCell {
  latitude: number
  longitude: number
  u: number
  v: number
}

export interface ArrowPts {
  tail: { latitude: number; longitude: number }
  head: { latitude: number; longitude: number }
  fins: { latitude: number; longitude: number }[]
}

export function arrowFor(
  v: CurrentVectorCell,
  opts: { degPerMs?: number; maxDeg?: number; minDeg?: number } = {},
): ArrowPts | null {
  const { degPerMs = 0.9, maxDeg = 1.4, minDeg = 0.18 } = opts
  if (!Number.isFinite(v.u) || !Number.isFinite(v.v)) return null
  const cosLat = Math.max(0.2, Math.cos((v.latitude * Math.PI) / 180))
  const speed = Math.hypot(v.u, v.v)
  if (speed === 0) return null // measured-but-stationary: no arrow to imply direction
  const len = Math.max(minDeg, Math.min(maxDeg, speed * degPerMs))
  const theta = Math.atan2(v.v, v.u)
  const tail = { latitude: v.latitude, longitude: v.longitude }
  const head = {
    latitude: v.latitude + Math.sin(theta) * len,
    longitude: v.longitude + (Math.cos(theta) * len) / cosLat,
  }
  const splay = Math.PI / 6
  return {
    tail,
    head,
    fins: [finPoint(head, tail, splay, cosLat), finPoint(head, tail, -splay, cosLat)],
  }
}

function finPoint(
  head: { latitude: number; longitude: number },
  tail: { latitude: number; longitude: number },
  splay: number,
  cosLat: number,
): { latitude: number; longitude: number } {
  const dx = tail.longitude - head.longitude
  const dy = tail.latitude - head.latitude
  const L = Math.hypot(dx, dy) || 1e-9
  const ux = dx / L
  const uy = dy / L
  const ca = Math.cos(splay)
  const sa = Math.sin(splay)
  const rx = ux * ca - uy * sa
  const ry = ux * sa + uy * ca
  const finLen = Math.min(L * 0.4, 0.18)
  return {
    latitude: head.latitude + ry * finLen,
    longitude: head.longitude + (rx * finLen) / cosLat,
  }
}

function crosses(v0: number, v1: number, level: number): number | null {
  const above0 = v0 >= level
  const above1 = v1 >= level
  if (above0 === above1) return null
  return (level - v0) / (v1 - v0)
}

function oppositeEdges(a: { x: number; y: number }, b: { x: number; y: number }): boolean {
  return (
    (a.y === 0 && b.y === 1) ||
    (b.y === 0 && a.y === 1) ||
    (a.x === 0 && b.x === 1) ||
    (b.x === 0 && a.x === 1)
  )
}

function pushSeg(
  out: IsoSegment[],
  field: LatLonField,
  i: number,
  j: number,
  a: { x: number; y: number },
  b: { x: number; y: number },
): void {
  out.push({
    lat0: field.lat0 + (i + a.y) * field.dlat,
    lon0: field.lon0 + (j + a.x) * field.dlon,
    lat1: field.lat0 + (i + b.y) * field.dlat,
    lon1: field.lon0 + (j + b.x) * field.dlon,
  })
}

function medianDiff(sorted: number[]): number {
  if (sorted.length < 2) return 0
  const diffs: number[] = []
  for (let i = 1; i < sorted.length; i++) {
    diffs.push(sorted[i] - sorted[i - 1])
  }
  diffs.sort((a, b) => a - b)
  const mid = Math.floor(diffs.length / 2)
  return diffs.length % 2 === 1 ? diffs[mid] : (diffs[mid - 1] + diffs[mid]) / 2
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v))
}

function lerpHex(a: number[], b: number[], k: number): string {
  const r = Math.round((a[0] + (b[0] - a[0]) * k))
  const g = Math.round((a[1] + (b[1] - a[1]) * k))
  const bl = Math.round((a[2] + (b[2] - a[2]) * k))
  return `#${to2(r)}${to2(g)}${to2(bl)}`
}

function to2(v: number): string {
  return v.toString(16).padStart(2, '0')
}