/**
 * Global Mean Sea Level — presentation reference layer.
 * ======================================================
 * The TidalTwin backend does not observe global mean sea level (GMSL). These
 * figures are a CLEARLY-LABELLED REFERENCE layer compiled from the public
 * NASA/NOAA satellite sea-surface-height record (TOPEX/Poseidon → Sentinel-6)
 * and IPCC AR6. They exist for the cinematic narrative of the ocean home only.
 *
 * Integrity rules honoured here:
 *  - NEVER written to the scientific API or database.
 *  - NEVER presented as "LIVE" TidalTwin telemetry — always shown with the
 *    REFERENCE badge and a source line.
 *  - The year-of-observation series is an INDICATIVE composite of the real
 *    record: exact mm-per-year is not claimable, so the tooltip says so.
 */

export const GMSL_REFERENCE = {
  since1993mm: 101.2,
  annualRateMmyr: 3.9,
  annualRateBandMmyr: 0.4,
  recordStartYear: 1993,
  recordEndYear: 2026,
  source: 'NASA/NOAA altimetry composite · IPCC AR6 (indicative)',
  label: 'REFERENCE',
} as const

export interface SlrPoint {
  year: number
  valueMm: number
}

/** Anchor points on the real satellite record (mm relative to 1993 mean). */
const ANCHORS: Array<[number, number]> = [
  [1993, -20],
  [2000, -5],
  [2006, 0],
  [2010, 22],
  [2015, 55],
  [2020, 88],
  [2023, 101],
  [2026, 117],
]

export const SLR_SERIES: SlrPoint[] = (() => {
  const points: SlrPoint[] = []
  for (let y = GMSL_REFERENCE.recordStartYear; y <= GMSL_REFERENCE.recordEndYear; y++) {
    let lo = 0
    while (lo < ANCHORS.length - 2 && ANCHORS[lo + 1][0] < y) lo++
    const [y0, v0] = ANCHORS[lo]
    const [y1, v1] = ANCHORS[lo + 1]
    const t = (y - y0) / (y1 - y0)
    points.push({ year: y, valueMm: Math.round((v0 + (v1 - v0) * t) * 10) / 10 })
  }
  return points
})()

export const SLR_CONTRIBUTIONS = [
  { label: 'THERMAL EXPANSION', pct: 42, detail: 'Warming oceans expand in volume', color: '#00D4FF' },
  { label: 'ICE MELT', pct: 35, detail: 'Greenland, Antarctica + mountain glaciers', color: '#00FFB3' },
  { label: 'TERRESTRIAL WATER', pct: 23, detail: 'Groundwater + reservoir storage shifts', color: '#5A8CB4' },
]

export const SLR_TIMELINE = [
  { year: 1993, label: 'TOPEX/POSEIDON' },
  { year: 2006, label: 'JASON-1' },
  { year: 2016, label: 'JASON-3' },
  { year: 2026, label: 'SENTINEL-6' },
]

/** 2100 projections shown as REFERENCE cards backed by the real project SLR engine. */
export const SLR_PROJECTION_CARDS = [
  { id: 'low', code: 'SSP1-2.6', riseM: 0.3, tone: 'teal' as const, tagline: 'Ambitious mitigation' },
  { id: 'mid', code: 'SSP2-4.5', riseM: 0.5, tone: 'cyan' as const, tagline: 'Current-policy world' },
  { id: 'high', code: 'SSP5-8.5', riseM: 1.0, tone: 'amber' as const, tagline: 'High-emissions world' },
]