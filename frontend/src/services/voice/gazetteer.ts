/**
 * TIDE Voice Agent - place name gazetteer (pure, dependency-free).
 *
 * The live model rarely knows numeric location ids, so the voice layer maps a
 * human place name ("Bay of Bengal", "Goa", "Arabian Sea") to either a
 * monitored TidalTwin location (when the name matches what the platform loaded)
 * or a built-in oceanographic/coastal entry with approximate coordinates for
 * the globe to fly to.
 */

export interface GazetteerEntry {
  name: string
  keywords: string[]
  latitude: number
  longitude: number
  kind: 'sea' | 'city' | 'island' | 'strait' | 'gulf'
}

export const GAZETTEER: GazetteerEntry[] = [
  { name: 'Bay of Bengal', keywords: ['bay of bengal'], latitude: 14.0, longitude: 87.0, kind: 'sea' },
  { name: 'Arabian Sea', keywords: ['arabian sea'], latitude: 14.0, longitude: 65.0, kind: 'sea' },
  { name: 'North Indian Ocean', keywords: ['north indian ocean', 'indian ocean'], latitude: 5.0, longitude: 75.0, kind: 'sea' },
  { name: 'Andaman Sea', keywords: ['andaman sea'], latitude: 10.5, longitude: 95.0, kind: 'sea' },
  { name: 'Gulf of Mannar', keywords: ['gulf of mannar', 'mannar'], latitude: 8.5, longitude: 78.8, kind: 'gulf' },
  { name: 'Palk Bay', keywords: ['palk bay'], latitude: 9.7, longitude: 79.4, kind: 'sea' },
  { name: 'Strait of Malacca', keywords: ['malacca'], latitude: 3.0, longitude: 100.5, kind: 'strait' },
  { name: 'Persian Gulf', keywords: ['persian gulf'], latitude: 26.5, longitude: 52.5, kind: 'gulf' },
  { name: 'Red Sea', keywords: ['red sea'], latitude: 20.0, longitude: 38.0, kind: 'sea' },
  { name: 'Gulf of Aden', keywords: ['aden'], latitude: 12.0, longitude: 48.0, kind: 'gulf' },
  { name: 'Somali Coast', keywords: ['somalia', 'somalian'], latitude: 7.0, longitude: 50.5, kind: 'sea' },
  { name: 'Maldives', keywords: ['maldives'], latitude: 3.2, longitude: 73.2, kind: 'island' },
  { name: 'Sri Lanka South Coast', keywords: ['sri lanka', 'lanka', 'colombo'], latitude: 6.4, longitude: 80.2, kind: 'island' },
  { name: 'Mumbai Coast', keywords: ['mumbai', 'bombay'], latitude: 19.0, longitude: 72.8, kind: 'city' },
  { name: 'Goa Coast', keywords: ['goa', 'panaji', 'panjim'], latitude: 15.3, longitude: 73.8, kind: 'city' },
  { name: 'Kerala Coast', keywords: ['kochi', 'cochin', 'kerala'], latitude: 9.97, longitude: 76.27, kind: 'city' },
  { name: 'Tamil Nadu Coast', keywords: ['chennai', 'madras', 'tamil nadu'], latitude: 13.08, longitude: 80.28, kind: 'city' },
  { name: 'Gujarat Coast', keywords: ['gujarat', 'veraval', 'okha'], latitude: 20.9, longitude: 70.4, kind: 'city' },
  { name: 'Karnataka Coast', keywords: ['mangalore', 'karnataka', 'karwar'], latitude: 12.9, longitude: 74.85, kind: 'city' },
  { name: 'Andhra Coast', keywords: ['visakhapatnam', 'vishakha', 'andhra'], latitude: 17.7, longitude: 83.3, kind: 'city' },
  { name: 'Odisha Coast', keywords: ['paradeep', 'puri', 'odisha'], latitude: 20.3, longitude: 86.6, kind: 'city' },
  { name: 'West Bengal Sundarbans', keywords: ['kolkata', 'sundarban', 'hooghly'], latitude: 21.7, longitude: 88.3, kind: 'city' },
  { name: 'Kanyakumari Coast', keywords: ['kanyakumari', 'cape comorin'], latitude: 8.07, longitude: 77.55, kind: 'city' },
  { name: 'Andaman Islands', keywords: ['port blair', 'andaman'], latitude: 11.6, longitude: 92.7, kind: 'island' },
  { name: 'Nicobar Islands', keywords: ['nicobar'], latitude: 8.0, longitude: 93.5, kind: 'island' },
  { name: 'Lakshadweep', keywords: ['lakshadweep'], latitude: 10.5, longitude: 72.6, kind: 'island' },
]

export interface ResolvedPlace {
  locationId?: number
  name?: string
  latitude?: number
  longitude?: number
  source: 'location' | 'context' | 'gazetteer' | 'coords' | null
}

export interface PlaceLookupOptions {
  location_id?: number | null
  region?: string | null
  latitude?: number | null
  longitude?: number | null
  locations?: { id: number; name: string; latitude?: number | null; longitude?: number | null }[]
  contextFocus?: number | null
  contextName?: string | null
}

export interface RankedLocation {
  id: number
  name: string
  score: number
}

/** Case-insensitive, accent-light name match. */
export function normalizePlace(text: string): string {
  return (text || '')
    .toLowerCase()
    .replace(/[©®™]/g, '')
    .replace(/coast|region|coastal|basin|waters?|sea|bay|gulf/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

/** Rank monitored locations that plausibly match a spoken place name. */
export function matchMonitoredLocations(
  region: string,
  locations?: { id: number; name: string }[],
): RankedLocation[] {
  if (!region || !Array.isArray(locations) || locations.length === 0) return []
  const q = normalizePlace(region)
  if (!q) return []
  const ranked: RankedLocation[] = []
  for (const loc of locations) {
    const name = normalizePlace(loc.name)
    if (!name) continue
    let score = 0
    if (name === q) score = 100
    else if (name.includes(q)) score = 80
    else if (q.includes(name)) score = 75
    const qWords = q.split(' ')
    const nameWords = name.split(' ')
    for (const w of qWords) {
      if (nameWords.some((nw) => nw.includes(w) || w.includes(nw))) score += 10
    }
    if (score > 0) ranked.push({ id: loc.id, name: loc.name, score })
  }
  ranked.sort((a, b) => b.score - a.score)
  return ranked.slice(0, 5)
}

export function findGazetteerEntry(region: string): GazetteerEntry | null {
  const q = normalizePlace(region)
  if (!q) return null
  let best: GazetteerEntry | null = null
  let bestScore = 0
  for (const entry of GAZETTEER) {
    let score = 0
    for (const kw of entry.keywords) {
      const k = normalizePlace(kw)
      if (k && q.includes(k)) score = Math.max(score, 30 + k.length)
    }
    if (score > bestScore) {
      bestScore = score
      best = entry
    }
  }
  return best
}

export function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371
  const toRad = (d: number): number => (d * Math.PI) / 180
  const dLat = toRad(lat2 - lat1)
  const dLon = toRad(lon2 - lon1)
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(a))
}

/**
 * Resolve a "where" set provided by the model into a concrete place.
 * Priority: explicit numeric id -> named monitored location -> built-in
 * gazetteer -> explicit lat/lon -> current UI focus.
 */
export function resolvePlace(opts: PlaceLookupOptions): ResolvedPlace {
  const locations = opts.locations ?? []
  if (opts.location_id != null) {
    const loc = locations.find((l) => l.id === opts.location_id)
    return {
      locationId: opts.location_id,
      name: loc?.name,
      latitude: loc?.latitude ?? undefined,
      longitude: loc?.longitude ?? undefined,
      source: 'location',
    }
  }

  if (opts.region) {
    const ranked = matchMonitoredLocations(opts.region, locations)
    if (ranked.length > 0 && ranked[0].score >= 70) {
      return {
        locationId: ranked[0].id,
        name: ranked[0].name,
        source: 'location',
      }
    }
    const gaz = findGazetteerEntry(opts.region)
    if (gaz) return { name: gaz.name, latitude: gaz.latitude, longitude: gaz.longitude, source: 'gazetteer' }
  }

  if (opts.latitude != null && opts.longitude != null) {
    let nearest: { id: number; latitude: number; longitude: number } | null = null
    let bestKm = Infinity
    for (const loc of locations) {
      if (loc.latitude == null || loc.longitude == null) continue
      const km = haversineKm(opts.latitude, opts.longitude, loc.latitude, loc.longitude)
      if (km < bestKm) {
        bestKm = km
        nearest = { id: loc.id, latitude: loc.latitude, longitude: loc.longitude }
      }
    }
    if (nearest && bestKm <= 300) {
      const loc = locations.find((l) => l.id === nearest!.id)
      return { locationId: nearest.id, name: loc?.name, source: 'location' }
    }
    return {
      latitude: opts.latitude,
      longitude: opts.longitude,
      source: 'coords',
    }
  }

  if (opts.contextFocus != null) {
    const loc = locations.find((l) => l.id === opts.contextFocus)
    return {
      locationId: opts.contextFocus,
      name: loc?.name ?? opts.contextName ?? undefined,
      source: 'context',
    }
  }

  return { source: null }
}