/**
 * TransectHUD - 2D Depth-vs-Distance Cross-Section Panel
 * =======================================================
 * Synchronized bottom overlay that renders the ocean vertical transect
 * curtain as a procedural canvas heatmap with the thermocline layer
 * and Argo in-situ profile markers overlaid.  Rendered inside the
 * .twin-globe-wrap when a transect is active.
 */
import { useEffect, useRef } from 'react'
import type { TransectData } from '../../components/3d/globe/CesiumGlobe'

const DEPTH_LABELS = [0, 50, 100, 200, 500, 1000, 1500, 2000]
const CSS_BG = '#020b14'
const CSS_CYAN = '#22d3ee'
const CSS_GOLD = '#f59e0b'

function tempRgb(t01: number) {
  const k = Math.max(0, Math.min(1, t01))
  const stops: [number, number, number, number][] = [
    [0.0, 10, 20, 45],
    [0.22, 23, 163, 199],
    [0.45, 45, 212, 191],
    [0.6, 125, 211, 252],
    [0.75, 251, 191, 36],
    [0.9, 249, 115, 22],
    [1.0, 244, 63, 94],
  ]
  for (let i = 1; i < stops.length; i++) {
    if (k <= stops[i][0]) {
      const [t0, r0, g0, b0] = stops[i - 1]
      const [t1, r1, g1, b1] = stops[i]
      const f = (k - t0) / (t1 - t0)
      return [Math.round(r0 + (r1 - r0) * f), Math.round(g0 + (g1 - g0) * f), Math.round(b0 + (b1 - b0) * f)]
    }
  }
  return [244, 63, 94]
}

export default function TransectHUD({ data }: { data: TransectData | null }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !data) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const rect = canvas.parentElement!.getBoundingClientRect()
    const W = Math.max(480, Math.floor(rect.width))
    const H = 200
    canvas.width = W
    canvas.height = H

    const samples = data.samples ?? []
    const depths = data.depths ?? []
    const nS = samples.length
    const nD = depths.length
    if (nS < 2 || nD < 2) return

    const marginLeft = 48
    const marginBottom = 22
    const marginTop = 8
    const marginRight = 8
    const plotW = W - marginLeft - marginRight
    const plotH = H - marginTop - marginBottom
    const depthMax = data.depth_max_m || 2000

    // Background
    ctx.fillStyle = CSS_BG
    ctx.fillRect(0, 0, W, H)

    // Find value range
    let vMin = Infinity
    let vMax = -Infinity
    for (const s of samples) {
      for (const v of s.values ?? []) {
        if (v == null) continue
        if (v < vMin) vMin = v
        if (v > vMax) vMax = v
      }
    }
    if (!isFinite(vMin) || vMax - vMin < 0.5) {
      vMin = data.variable === 'salinity' ? 34 : 4
      vMax = data.variable === 'salinity' ? 37 : 30
    }

    // Draw the gradient cells
    const cellW = plotW / (nS - 1 || 1)
    const cellH = plotH / (nD - 1 || 1)
    for (let si = 0; si < nS; si++) {
      const values = samples[si].values ?? []
      const x = marginLeft + (si / (nS - 1)) * plotW
      for (let di = 0; di < nD; di++) {
        const v = values[di]
        if (v == null) continue
        const [r, g, b] = tempRgb((v - vMin) / (vMax - vMin))
        const y = marginTop + (di / (nD - 1)) * plotH
        ctx.fillStyle = `rgb(${r},${g},${b})`
        ctx.fillRect(x - cellW / 2, y - cellH / 2, cellW + 1, cellH + 1)
      }
    }

    // Thermocline line (cyan)
    ctx.strokeStyle = CSS_CYAN
    ctx.lineWidth = 2.2
    ctx.shadowColor = CSS_CYAN
    ctx.shadowBlur = 6
    ctx.beginPath()
    let thermoStarted = false
    for (let si = 0; si < nS; si++) {
      const tDepth = samples[si].thermocline?.thermocline_depth ?? 0
      if (tDepth <= 0 || tDepth > depthMax) continue
      const x = marginLeft + (si / (nS - 1)) * plotW
      const y = marginTop + (tDepth / depthMax) * plotH
      if (!thermoStarted) {
        ctx.moveTo(x, y)
        thermoStarted = true
      } else {
        ctx.lineTo(x, y)
      }
    }
    ctx.stroke()
    ctx.shadowBlur = 0

    // Thermocline legend
    ctx.fillStyle = CSS_CYAN
    ctx.font = '600 10px Inter, sans-serif'
    ctx.fillText('--- Thermocline (max \u2202T/\u2202z)', marginLeft + 4, marginTop + 12)

    // Argo float in-situ markers (gold dots at discrete depths)
    for (const f of data.argos ?? []) {
      const inSitu = f.in_situ?.temperature ?? []
      const argoDepths = f.in_situ?.depths ?? []
      if (inSitu.length === 0) continue
      // Map the float's position to the nearest transect sample index
      let bestSi = 0
      let bestD = Infinity
      for (let si = 0; si < nS; si++) {
        const dx = (samples[si].distance_km - f.distance_km)
        if (Math.abs(dx) < bestD) {
          bestD = Math.abs(dx)
          bestSi = si
        }
      }
      const x = marginLeft + (bestSi / (nS - 1)) * plotW
      for (let i = 0; i < argoDepths.length; i++) {
        const d = argoDepths[i]
        const v = inSitu[i]
        if (v == null || d > depthMax) continue
        const y = marginTop + (d / depthMax) * plotH
        ctx.fillStyle = CSS_GOLD
        ctx.shadowColor = CSS_GOLD
        ctx.shadowBlur = 4
        ctx.beginPath()
        ctx.arc(x, y, 3, 0, Math.PI * 2)
        ctx.fill()
      }
      ctx.shadowBlur = 0
    }

    // Depth axis labels (left side)
    ctx.fillStyle = '#94a3b8'
    ctx.font = '10px monospace'
    ctx.textAlign = 'right'
    for (const d of DEPTH_LABELS) {
      if (d > depthMax) continue
      const y = marginTop + (d / depthMax) * plotH
      ctx.fillText(`${d}m`, marginLeft - 4, y + 3)
      ctx.strokeStyle = 'rgba(148,163,184,0.12)'
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(marginLeft, y)
      ctx.lineTo(W - marginRight, y)
      ctx.stroke()
    }
    ctx.textAlign = 'start'

    // Distance axis labels (top)
    ctx.fillStyle = '#64748b'
    ctx.font = '9px monospace'
    const totalKm = data.distance_km || samples[samples.length - 1]?.distance_km || 1
    for (let t = 0; t <= 5; t++) {
      const km = (t / 5) * totalKm
      const x = marginLeft + (t / 5) * plotW
      ctx.fillText(`${Math.round(km)} km`, x - 8, marginTop + plotH + 14)
    }

    // Title
    ctx.fillStyle = '#ffffff'
    ctx.font = '600 11px Inter, sans-serif'
    ctx.fillText(`Depth vs Distance \u2022 ${data.label} (${data.unit})`, marginLeft, 16)
  }, [data])

  return (
    <div className="transect-hud">
      <canvas
        ref={canvasRef}
        style={{ width: '100%', height: 200, borderRadius: '0 0 var(--r-lg) var(--r-lg)' }}
      />
    </div>
  )
}
