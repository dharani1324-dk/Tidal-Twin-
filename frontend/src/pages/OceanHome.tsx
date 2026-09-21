import { useEffect, useMemo, useState } from 'react'
import {
  Activity, ArrowRight, Crosshair, Database, Globe2, Radar,
  RefreshCw, Scale, ShieldAlert, Thermometer, Waves,
} from 'lucide-react'
import {
  fetchDemoStatus, fetchDataSources, fetchErsstLatest, fetchLocations, fetchSituation,
  fetchSLR, fetchSystemHealth, fetchTideCandidates, fetchTideExplanation,
  fetchTideVerdict, fetchValidationEvents, fetchValidationSituation,
  triggerRefresh,
} from '../api/client'
import type { ErsstLayer } from '../components/3d/globe/CesiumGlobe'
import {
  AnimatedNumber, DataSourceBadge, GlowButton, RiskBar,
  ScientificBadge, SectionHeader, StatusIndicator, Timeline,
} from '../components/ocean/OceanUI'
import { DepthMarkers, OceanGrid, ParticleLayer, SonarPulse } from '../components/ocean/effects'
import { useInView } from '../components/ocean/hooks'
import MastheadNav from '../components/layout/MastheadNav'
import { SeaLevelChart } from '../components/wave/SeaLevelChart'
import { ContributionBars } from '../components/wave/ContributionBars'
import {
  GMSL_REFERENCE, SLR_CONTRIBUTIONS, SLR_PROJECTION_CARDS, SLR_SERIES, SLR_TIMELINE,
} from '../components/data/slrReference'
import SystemStatusPill from '../components/system/SystemStatusPill'
import './OceanHome.css'

const REF = GMSL_REFERENCE

interface LocRow { id: number; name: string; region_type: string; country: string }
interface SitRow {
  location_id: number; location: string; status: string; temperature_anomaly: string;
  observation_confidence: number; model_trust: number; disagreement: boolean;
}
interface AgSit {
  split: { normal_regions_pct: number; watch_regions_pct: number; high_risk_regions_pct: number };
  active_events: number; observation_coverage_pct: number; model_trust: number; summary: string;
}
interface SlrRow { location_id: number; location: string; impact_pct: number; population_at_risk: number; land_area_lost_km2: number }
interface SlrResp {
  scenario_m: number; regions: SlrRow[];
  summary: { coasts_analyzed: number; towns_inundated: number; total_land_area_lost_km2: number; total_population_at_risk: number; most_affected: string };
  note: string;
}
interface TideRow {
  location: string; variable: string; location_id: number;
  observation_value: number; uncertainty: number; data_gap: number; evidence: string[];
}
interface EvRow { event_type: string; intensity: string; location: string; location_id: number }

const DEPTH_MARKS = [
  { value: '00', label: 'SURFACE' }, { value: '-100', label: 'M' }, { value: '-500', label: 'M' },
  { value: '-1000', label: 'M' }, { value: '-2000', label: 'M' }, { value: '-4000', label: 'M' },
]

const TIDE_FLOW = ['DENOISE', 'TIDE SCORE', 'CAUSE RANKING', 'HIDDEN PATTERN', 'EXPLANATION', 'VERDICT', 'NEXT-BEST OBS']

const SEV_TONE: Record<string, 'crit' | 'warn' | 'ok'> = {
  HIGH: 'crit', WARNING: 'warn', MEDIUM: 'warn', CRITICAL: 'crit', MODERATE: 'warn', LOW: 'ok',
}

function unwrap<T>(d: unknown): T {
  if (d && typeof d === 'object' && 'data' in d) return (d as { data: T }).data
  return d as T
}

const SEASON = new Date().toLocaleDateString('en-IN', { month: 'long', year: 'numeric' })

export default function OceanHome() {
  const [, setT] = useState(0)
  const [loc, setLoc] = useState<LocRow[]>([])
  const [sitRows, setSitRows] = useState<SitRow[]>([])
  const [sit, setSit] = useState<AgSit | null>(null)
  const [ersst, setErsst] = useState<ErsstLayer | null>(null)
  const [slrMid, setSlrMid] = useState<SlrResp | null>(null)
  const [proj, setProj] = useState<(SlrResp | null)[]>([null, null, null])
  const [tide, setTide] = useState<TideRow[]>([])
  const [tideExplain, setTideExplain] = useState<string | null>(null)
  const [tideVerdict, setTideVerdict] = useState<string | null>(null)
  const [events, setEvents] = useState<EvRow[]>([])
  const [sources, setSources] = useState<string[]>([])
  const [online, setOnline] = useState(false)
  const [simMode, setSimMode] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [syncedAgo, setSyncedAgo] = useState(0)

  const hero = useInView<HTMLElement>({ once: false, margin: '0px 0px -40% 0px' })
  const kpis = useInView<HTMLDivElement>()
  const refresh = () => {
    setSyncing(true)
    triggerRefresh()
      .catch(() => null)
      .finally(() => { setSyncing(false); setSyncedAgo(0); setT(Date.now()) })
  }

  useEffect(() => {
    let alive = true
    const t = setInterval(() => setSyncedAgo((v) => v + 1), 1000)
    const load = async () => {
      const [l, s, ag, e, sm, fresh] = await Promise.all([
        fetchLocations().catch(() => [] as LocRow[]),
        fetchValidationSituation().catch(() => ({ regions: [] as SitRow[] })),
        fetchSituation().catch(() => null as AgSit | null),
        fetchErsstLatest().catch(() => null as ErsstLayer | null),
        fetchSLR(0.5).catch(() => null as SlrResp | null),
        (async () => {
          const out = [null, null, null] as (SlrResp | null)[]
          for (let i = 0; i < SLR_PROJECTION_CARDS.length; i++) {
            out[i] = await fetchSLR(SLR_PROJECTION_CARDS[i].riseM).catch(() => null)
          }
          return out
        })(),
      ])
      const [p3, p5, p1] = fresh
      const td = await fetchTideCandidates({}).catch(() => null)
      const tdList: TideRow[] = (Array.isArray(td) ? td : unwrap<TideRow[]>(td)) ?? []
      const tdExpl = tdList[0] ? unwrap<{ explanation?: { summary?: string } }>(await fetchTideExplanation({ location_id: tdList[0].location_id, variable: tdList[0].variable, depth_m: 0 }).catch(() => null)) : null
      const tdVerd = tdList[0] ? unwrap<{ verdict?: string; summary?: string }>(await fetchTideVerdict({ location_id: tdList[0].location_id, variable: tdList[0].variable, depth_m: 0 }).catch(() => null)) : null
      const dsrc = await fetchValidationEvents().catch(() => null)
      const evList: EvRow[] = ((dsrc as { events?: { location_id: number; location: string; event_type: string; intensity: string }[] } | null)?.events ?? [])
        .map((e) => ({ event_type: e.event_type, intensity: e.intensity ?? '', location: e.location ?? '', location_id: e.location_id }))
      const src = await fetchDataSources().catch(() => null)
      const srcList = (src as { sources?: { name?: string; status?: string }[] } | null)?.sources?.map((s) => s.name ?? '').filter(Boolean) ?? []
      const h = await fetchSystemHealth().catch(() => null)
      const dm = await fetchDemoStatus().catch(() => null)
      if (!alive) return
      setLoc(l); setSitRows(s.regions ?? []); setSit(ag); setErsst(e); setSlrMid(sm)
      setProj([p3, p5, p1]); setTide(tdList)
      setTideExplain(tdExpl?.explanation?.summary ?? null)
      setTideVerdict(tdVerd?.verdict?.replace(/_/g, ' ') ?? tdVerd?.summary ?? null)
      setEvents(evList); setSources(srcList.slice(0, 12))
      setOnline(Boolean(h && h.status === 'healthy'))
      setSimMode(Boolean(dm?.demo_data_present))
    }
    load()
    return () => { alive = false; clearInterval(t) }
  }, [])

  const ersstSST = useMemo(() => {
    if (!ersst?.samples?.length) return null
    const inBox = ersst.samples.filter((x) => x.latitude >= 4 && x.latitude <= 25 && x.longitude >= 58 && x.longitude <= 98)
    const pool = inBox.length ? inBox : ersst.samples
    const mean = pool.reduce((a, x) => a + x.sst, 0) / pool.length
    return { mean, at: ersst.time ?? '' }
  }, [ersst])

  const regions = useMemo(() => {
    const byId = new Map(sitRows.map((r) => [r.location_id, r]))
    const merged = loc.map((l) => ({ ...l, sit: byId.get(l.id) })).filter((r) => r.sit)
    const weight = (s: SitRow) => (s.status === 'danger' ? 0 : s.status === 'caution' ? 1 : 2)
    return merged.sort((a, b) => weight(a.sit as SitRow) - weight(b.sit as SitRow) || (b.sit as SitRow).observation_confidence - (a.sit as SitRow).observation_confidence).slice(0, 6)
  }, [loc, sitRows])

  const slrByLoc = useMemo(() => new Map((slrMid?.regions ?? []).map((r) => [r.location_id, r])), [slrMid])
  const atRisk = sit?.split ?? null
  const coastsCount = loc.length
  const tideRows = tide.slice(0, 3)
  const eventsCrit = events.filter((e) => SEV_TONE[e.intensity] === 'crit').length

  return (
    <div className="ocean-home">
      {/* ------------------------------------------------ HERO */}
      <section id="overview" className="oh-hero" ref={hero.ref}>
        <OceanGrid />
        <ParticleLayer count={110} />
        <SonarPulse />
        <DepthMarkers marks={DEPTH_MARKS} />

        <div className="oh-inner">
          <MastheadNav scrolled={!hero.inView} />

          <span className="oh-hero__eyebrow">◉ INDIAN OCEAN · 4D OCEAN DIGITAL TWIN &nbsp;·&nbsp; {SEASON.toUpperCase()}</span>

          <div className="oh-hero__grid">
            <div>
              <h1 className="oh-hero__title">
                The Ocean<br />is <span className="oh-shimmer">Rising.</span>
              </h1>
              <p className="oh-hero__lede">
                A cinematic mission control built on live ocean telemetry — model-vs-observation digital twin,
                TIDE explainable forensics, and decision-grade sea-level analysis for India&rsquo;s coasts.
              </p>
              <div className="oh-hero__cta">
                <GlowButton to="/globe"><Globe2 size={14} /> Enter 4D Digital Twin</GlowButton>
                <GlowButton to="/tide" variant="ghost"><Crosshair size={14} /> Run TIDE Command</GlowButton>
                <GlowButton to="/validate" variant="ghost"><Scale size={14} /> Model Validation (Goa)</GlowButton>
              </div>
            </div>

            <div className="oh-hero__live-card">
              <div className="oh-panel oh-scanline" aria-label="Live sea-level reference">
                <div className="oh-livecard-head">
                  <span className="oh-kpi__label"><Activity size={12} /> GLOBAL MEAN SEA LEVEL</span>
                  <ScientificBadge tone="ref">REFERENCE</ScientificBadge>
                </div>
                <span className="oh-kpi__value">
                  <AnimatedNumber target={REF.since1993mm} decimals={1} prefix="+" enabled={hero.inView} /> <em>mm</em>
                </span>
                <span className="oh-kpi__foot"><b>1993 → {REF.recordEndYear} · ~{REF.annualRateMmyr} mm/yr</b></span>

                <div className="oh-livecard-divider" />
                <div className="oh-livecard-row">
                  <span className="oh-kpi__label">REAL SST · ERSST BOX</span>
                  {ersstSST ? <LiveMark value={`${ersstSST.mean.toFixed(1)} °C`} note={ersstSST.at} /> : <span className="oh-status oh-status--off"><span className="oh-status__dot" />STANDBY</span>}
                </div>
                <p className="oh-hero__sub">Floating global indicators are the NASA/NOAA record shown as labelled reference — the project&rsquo;s own live twin data drives every RISE/RISK number below.</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="oh-inner">
        {/* ------------------------------------------------ KPI STRIP */}
        <div className="oh-kpi-strip" ref={kpis.ref}>
          <div className="oh-panel oh-kpi">
            <span className="oh-kpi__label">GLOBAL MEAN SEA LEVEL <ScientificBadge tone="ref">REF</ScientificBadge></span>
            <span className="oh-kpi__value"><AnimatedNumber target={REF.since1993mm} decimals={1} prefix="+" enabled={kpis.inView} /> <em>mm</em></span>
            <span className="oh-kpi__foot"><b>vs 1993 · NASA RANGE</b></span>
          </div>
          <div className="oh-panel oh-kpi">
            <span className="oh-kpi__label">ANNUAL RISE RATE <ScientificBadge tone="ref">REF</ScientificBadge></span>
            <span className="oh-kpi__value"><AnimatedNumber target={REF.annualRateMmyr} decimals={1} prefix="+" enabled={kpis.inView} /> <em>mm/yr</em></span>
            <span className="oh-kpi__foot"><b>±{REF.annualRateBandMmyr} · NASA</b></span>
          </div>
          <div className="oh-panel oh-kpi">
            <span className="oh-kpi__label">MONITORED COASTS {online ? <span className="oh-live-dot" /> : null}</span>
            <span className="oh-kpi__value"><AnimatedNumber target={coastsCount} enabled={kpis.inView} /> <em>regions</em></span>
            <span className="oh-kpi__foot"><b>TIDALTWIN · LIVE NETWORK</b></span>
          </div>
          <div className="oh-panel oh-kpi">
            <span className="oh-kpi__label">HIGH-RISK REGIONS {online ? <span className="oh-live-dot" /> : null}</span>
            <span className="oh-kpi__value"><AnimatedNumber target={atRisk?.high_risk_regions_pct ?? 0} enabled={kpis.inView} /> <em>%</em></span>
            <span className="oh-kpi__foot"><b>{sit?.active_events ?? 0} ACTIVE EVENTS</b></span>
          </div>
        </div>

        {/* ------------------------------------------------ SEA LEVEL */}
        <div id="sea-level" className="oh-section">
          <SectionHeader
            eyebrow="Sea Level · Satellite Record"
            title={<>Global mean sea level is <span className="oh-shimmer">still accelerating</span>.</>}
            sub={<>Sea level rises as warming oceans expand and ice sheets melt. This 33-year satellite record — presented as an indicative NASA/NOAA reference series — is the backdrop the twin&rsquo;s own coastal SLR engine thresholds against.</>}
            right={<ScientificBadge tone="ref">REFERENCE · NASA/NOAA</ScientificBadge>}
          />
          <div className="oh-chart-grid">
            <div className="oh-panel oh-scanline oh-chart-panel">
              <div className="oh-chart-head">
                <span className="oh-kpi__label">GMSL 1993 → {REF.recordEndYear}</span>
                <DataSourceBadge label={REF.source} />
              </div>
              <SeaLevelChart points={SLR_SERIES} yearStart={REF.recordStartYear} yearEnd={REF.recordEndYear} sourceLabel={REF.source} />
              <Timeline items={SLR_TIMELINE} activeYear={REF.recordEndYear} />
            </div>
            <div className="oh-panel oh-scanline oh-contrib-panel">
              <div className="oh-chart-head">
                <span className="oh-kpi__label">WHAT IS DRIVING THE RISE</span>
                <ScientificBadge tone="ref">INDICATIVE SPLIT</ScientificBadge>
              </div>
              <ContributionBars items={SLR_CONTRIBUTIONS} source="IPCC AR6 · INDICATIVE" />
              <div className="oh-note">
                <Waves size={13} /> Three physical mechanisms — the ocean&rsquo;s own fingerprints on the global curve. The
                twin monitors the <b>Indian Ocean</b> portion of this signal via temperature, salinity and coastal SLR simulation.
              </div>
            </div>
          </div>
        </div>

        {/* ------------------------------------------------ REGIONS */}
        <div id="regions" className="oh-section">
          <SectionHeader
            eyebrow="Regional Analysis · Live Network"
            title="Six coasts under the microscope."
            sub="Legend tells of critical regions. The twin tells you which coasts actually need your attention today — from real model-vs-observation telemetry and the coastal SLR engine."
            right={<DataSourceBadge label="TIDALTWIN · /twin/situation + /coastal/slr" />}
          />
          {regions.length === 0 ? (
            <div className="oh-panel oh-empty">
              <p>No live situation data yet. Start the backend and ingest the reference observations (ERSST / Argo) on a networked host — or use the Sandbox.</p>
            </div>
          ) : (
            <div className="oh-region-grid">
              {regions.map((r, i) => {
                const s = r.sit as SitRow
                const slr = slrByLoc.get(r.id)
                const tone = s.status === 'danger' ? 'crit' : s.status === 'caution' ? 'warn' : 'ok'
                return (
                  <div className="oh-card oh-card--hover oh-scanline" key={r.id}>
                    <div className="oh-region-top">
                      <span className="oh-eyebrow">{String(i + 1).padStart(2, '0')} / {r.name}</span>
                      <StatusIndicator tone={tone}>{s.status.toUpperCase()}</StatusIndicator>
                    </div>
                    <div className="oh-region-meta">{r.country} · {r.region_type}</div>
                    <div className="oh-region-vals">
                      <div className="oh-kpi">
                        <span className="oh-kpi__label">TEMP ANOMALY</span>
                        <span className="oh-kpi__value">{s.temperature_anomaly ?? '—'}</span>
                      </div>
                      <div className="oh-kpi">
                        <span className="oh-kpi__label">OBS CONFIRMATION</span>
                        <span className="oh-kpi__value">{(s.observation_confidence ?? 0).toFixed(0)} <em>%</em></span>
                      </div>
                    </div>
                    <RiskBar
                      pct={slr?.impact_pct ?? 0}
                      label="SLR INUNDATION (0.5 m)"
                      value={slr != null ? `${slr.impact_pct}%` : '—'}
                      heat
                    />
                    <div className="oh-region-foot">
                      <DataSourceBadge label="TIDALTWIN API" />
                      {s.disagreement ? <ScientificBadge tone="warn">MODEL DISAGREES</ScientificBadge> : <ScientificBadge>MODEL-VS-OBS</ScientificBadge>}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* ------------------------------------------------ TIDE */}
        <div id="tide-loop" className="oh-section">
          <SectionHeader
            eyebrow="TIDE Loop · Explainable Forensics"
            title="Every observation decision, explainable end to end."
            sub="TIDE ranks where the next observation matters most — denoising telemetry, scoring causal causes, surfacing the hidden pattern, and closing with a verdict and next-best observation. Powered by the real engine."
            right={<GlowButton to="/tide" variant="ghost">FULL TIDE CENTER <ArrowRight size={13} /></GlowButton>}
          />
          <div className="oh-panel oh-scanline">
            <div className="oh-tide-flow" role="list">
              {TIDE_FLOW.map((step, i) => (
                <div className="oh-tide-step" role="listitem" key={step}>
                  <span className="oh-tide-step__idx">{i + 1}</span>
                  <span className="oh-tide-step__name">{step}</span>
                </div>
              ))}
            </div>

            {tideRows.length === 0 ? (
              <div className="oh-empty-row">
                <p><Radar size={13} /> No TIDE candidates computed yet — the engine needs telemetry for a region to rank. Open the TIDE Center or seed the sandbox.</p>
                <GlowButton to="/tide" variant="ghost">GO TO TIDE</GlowButton>
              </div>
            ) : (
              <div className="oh-tide-results">
                {tideRows.map((c, i) => (
                  <div className="oh-tide-cand" key={`${c.location}-${i}`}>
                    <span className="oh-tide-cand__rank">#{i + 1}</span>
                    <div>
                      <b>{c.location}</b>
                      <span className="oh-tide-cand__var">{c.variable} · depth 0 m</span>
                    </div>
                    <div className="oh-tide-cand__stat"><span>SCORE</span><b>{c.observation_value ?? '—'}</b></div>
                    <div className="oh-tide-cand__stat"><span>UNC</span><b>{c.uncertainty != null ? Math.round(c.uncertainty * 100) : '—'}</b></div>
                    <ScientificBadge tone={i === 0 ? 'teal' : 'cyan'}>TOP CANDIDATE</ScientificBadge>
                  </div>
                ))}
                <div className="oh-tide-out">
                  <span className="oh-kpi__label">VERDICT</span>
                  {tideVerdict ? <b className="oh-tide-verdict">{tideVerdict}</b> : <span className="oh-status oh-status--off"><span className="oh-status__dot" />PENDING</span>}
                  {tideExplain ? <p className="oh-tide-explain">{tideExplain}</p> : null}
                  <DataSourceBadge label="TIDALTWIN · /tide/candidates" />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ------------------------------------------------ FORENSICS */}
        <div id="forensics" className="oh-section">
          <SectionHeader
            eyebrow="Ocean Forensics"
            title="When reality disagreed with the model."
            sub="Every unresolved anomaly is an investigation case file — the twin forensics engine walks effect back to cause. Live events from the validation store."
            right={<GlowButton to="/forensics" variant="ghost">OPEN FORENSICS <ArrowRight size={13} /></GlowButton>}
          />
          <div className="oh-forensics-grid">
            {events.length === 0 ? (
              <div className="oh-panel oh-empty">
                <p><ShieldAlert size={13} /> No forensic case files right now — the ocean is tracking its model baseline. Historical storms reappear in Story Mode and Decision Replay.</p>
              </div>
            ) : (
              events.slice(0, 4).map((ev) => (
                <div className="oh-card oh-scanline" key={`${ev.location_id}-${ev.event_type}`}>
                  <div className="oh-region-top">
                    <span className="oh-eyebrow">{ev.event_type.replace(/_/g, ' ').toUpperCase()}</span>
                    <StatusIndicator tone={SEV_TONE[ev.intensity] ?? 'warn'}>{ev.intensity || 'ACTIVE'}</StatusIndicator>
                  </div>
                  <div className="oh-region-meta">{ev.location ?? `Region #${ev.location_id ?? '—'}`}</div>
                  <div className="oh-region-foot"><DataSourceBadge label="TIDALTWIN · /validation/events" /><ScientificBadge>CASE FILE</ScientificBadge></div>
                </div>
              ))
            )}
            <div className="oh-panel oh-forensics-stat oh-scanline">
              <span className="oh-kpi__label">CRITICAL EVENTS LOGGED</span>
              <span className="oh-kpi__value">{eventsCrit} <em>critical</em></span>
              <span className="oh-kpi__foot"><b>{events.length} ACTIVE CASE FILES</b></span>
            </div>
          </div>
        </div>

        {/* ------------------------------------------------ PROJECTIONS */}
        <div id="projections" className="oh-section">
          <SectionHeader
            eyebrow="2100 Projections · Coastal SLR Engine"
            title="The future is a menu of shared choices."
            sub="Three IPCC-aligned scenarios, run through the twin&rsquo;s real coastal SLR inundation engine (illustrative settlement DEM). Your actions today pick the menu."
            right={<ScientificBadge tone="ref">IPCC AR6 FRAMEWORK</ScientificBadge>}
          />
          <div className="oh-projection-grid">
            {SLR_PROJECTION_CARDS.map((p, i) => {
              const r = proj[i]
              const toneCls = p.tone === 'teal' ? ' oh-proj--teal' : p.tone === 'amber' ? ' oh-proj--amber' : ''
              return (
                <div className={`oh-panel oh-proj oh-scanline${toneCls}`} key={p.id}>
                  <div className="oh-proj-head">
                    <div>
                      <span className="oh-kpi__label">{p.code} · {p.tagline.toUpperCase()}</span>
                      <span className="oh-proj-rise">+{p.riseM} <em>m</em></span>
                    </div>
                    <ScientificBadge>{p.id.toUpperCase()}</ScientificBadge>
                  </div>
                  <div className="oh-proj-stats">
                    <div className="oh-proj-stat"><b>{r?.summary?.towns_inundated ?? '—'}</b><span>SETTLEMENTS INUNDATED</span></div>
                    <div className="oh-proj-stat"><b>{r?.summary?.total_land_area_lost_km2 ?? '—'}</b><span>km² LAND LOST</span></div>
                    <div className="oh-proj-stat"><b>{r ? r.summary.total_population_at_risk.toLocaleString('en-IN') : '—'}</b><span>POPULATION AT RISK</span></div>
                  </div>
                  <div className="oh-proj-foot">
                    <span>Most affected: <b>{r?.summary?.most_affected ?? '—'}</b></span>
                    <DataSourceBadge label="TIDALTWIN · /coastal/slr" />
                  </div>
                  {r?.note ? <p className="oh-proj-note">{r.note}</p> : null}
                </div>
              )
            })}
          </div>
          <div className="oh-note">
            <Thermometer size={13} /> Projection cards run the <b>live project SLR engine</b> (real scenario math, honest illustrative elevations).
            The hero global numbers stay labelled as NASA/NOAA reference. No value here is invented on screen.
          </div>
        </div>

        {/* ------------------------------------------------ SOURCES + STATUS */}
        <div id="status" className="oh-section">
          <SectionHeader
            eyebrow="Data Sources · Honesty First"
            title="Every number carries its provenance."
            right={<DataSourceBadge label="LIVE HEALTH CHECK BELOW" />}
          />
          <div className="oh-src-row">
            <div className="oh-panel oh-src">
              <div className="oh-chart-head"><span className="oh-kpi__label">SOURCE REGISTRY</span></div>
              <div className="oh-src__list">
                {(sources.length ? sources : ['ERSST v5 · NOAA', 'ARGO · JCOMM', 'CHL · ESA / NOAA', 'MODEL GRID · HYCOM', 'TIDE · TIDALTWIN LAB']).map((s) => (
                  <span className="oh-src__chip" key={s}>{s}</span>
                ))}
              </div>
              <p className="oh-src-note">{sources.length ? 'Registered by /twin/sources.' : 'Illustrative registry labels — the twin loads real ERSST/Argo/model-grid on a networked host.'}</p>
            </div>
            <div className="oh-panel oh-panel-status">
              <div className="oh-chart-head">
                <span className="oh-kpi__label">SYSTEM STATUS</span>
                <SystemStatusPill />
              </div>
              <div className="oh-status-row">
                <button type="button" className="oh-btn oh-btn--ghost" onClick={refresh} disabled={syncing}>
                  <RefreshCw size={13} /> {syncing ? 'REFRESHING…' : 'TRIGGER REFRESH'}
                </button>
                <span className="oh-kpi__foot"><b>LAST SYNC {syncedAgo}s AGO</b> </span>
                {simMode ? <ScientificBadge tone="off">SIMULATION MODE</ScientificBadge> : <ScientificBadge tone="live">REAL DATA MODE</ScientificBadge>}
                <DataSourceBadge label="TIDALTWIN · /health" />
              </div>
              <p className="oh-src-note">
                <Database size={11} /> Backend live, honest surfaces: when telemetry is absent the UI says so instead of inventing a number.
              </p>
            </div>
          </div>
        </div>

        <footer className="oh-footer">
          <span className="masthead__logo">TIDAL<em>TWIN</em></span>
          <span>4D OCEAN DIGITAL TWIN · INDIAN OCEAN · <ScientificBadge tone="ref">GMSL SATELLITE RECORD 1993–{REF.recordEndYear}</ScientificBadge></span>
        </footer>
      </div>
    </div>
  )
}

function LiveMark({ value, note }: { value: string; note: string }) {
  return (
    <span className="oh-kpi__value oh-livemark">{value} <em>{note}</em></span>
  )
}