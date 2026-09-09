/**
 * OceanVerse AI - 3D Math Utilities
 * =================================
 * Helpers for converting geographic coordinates (lat/lon)
 * into 3D positions on a sphere. This is the core math
 * behind every 3D globe.
 */

import * as THREE from 'three'

export const EARTH_RADIUS = 1

/**
 * Convert latitude/longitude to a 3D position on a sphere
 * of given radius.
 */
export function latLonToVector3(
  lat: number,
  lon: number,
  radius: number = EARTH_RADIUS,
): THREE.Vector3 {
  const phi = (90 - lat) * (Math.PI / 180)
  const theta = (lon + 180) * (Math.PI / 180)

  const x = -(radius * Math.sin(phi) * Math.cos(theta))
  const z = radius * Math.sin(phi) * Math.sin(theta)
  const y = radius * Math.cos(phi)

  return new THREE.Vector3(x, y, z)
}

/** A location marker: name + its position on the globe */
export interface GlobeMarker {
  id: number
  name: string
  lat: number
  lon: number
  temp?: number | null
  wave?: number | null
  position: THREE.Vector3
}

export function buildMarkers(
  locations: { id: number; name: string; latitude: number | null; longitude: number | null }[],
): GlobeMarker[] {
  return locations
    .filter((l) => l.latitude != null && l.longitude != null)
    .map((l) => ({
      id: l.id,
      name: l.name,
      lat: l.latitude!,
      lon: l.longitude!,
      position: latLonToVector3(l.latitude!, l.longitude!, EARTH_RADIUS * 1.008),
    }))
}