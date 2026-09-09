/**
 * OceanVerse AI - API Client
 * ==========================
 * This is how our frontend talks to the backend.
 * We use axios to make HTTP requests to the FastAPI server.
 */

import axios from 'axios'

// The backend runs here in development
const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
})

/** Get a friendly backend health status */
export const fetchHealth = async () => {
  const { data } = await api.get('/api/v1/health')
  return data
}

/** Get all ocean locations from the database */
export const fetchLocations = async () => {
  const { data } = await api.get('/api/v1/ocean/locations')
  return data
}

/** Get recent observations for one location */
export const fetchObservations = async (locationId: number, limit = 50) => {
  const { data } = await api.get(
    `/api/v1/ocean/locations/${locationId}/observations`,
    { params: { limit } },
  )
  return data
}

/** Trigger a refresh of real ocean data from the API */
export const triggerRefresh = async () => {
  const { data } = await api.post('/api/v1/ocean/refresh')
  return data
}