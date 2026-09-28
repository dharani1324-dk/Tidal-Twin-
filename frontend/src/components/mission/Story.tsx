/**
 * Mission Intro — Sections 02 … 05
 * ================================
 * The argument, in four movements:
 *
 *   02  The ocean is not unobserved. It is *unevenly* observed.
 *   03  A 4D twin: what we have, what it covers, and how far we can trust it.
 *   04  The chain: what is observed, what changed, where to look next.
 *   05  Decision Intelligence: the question a viewer cannot answer.
 *
 * Every figure below is read from the live API. Where a request fails the
 * section says so and says why; it never substitutes an invented number.
 */
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Boxes,
  Clock3,
  Compass,
  Eye,
  GitBranch,
  Layers,
  Radar,
  ScanSearch,
  Waves,
} from 'lucide-react'
import { Absence, Caveat, Loading, MissionSection, OriginTag, Reveal, SchematicTag } from './Primitives'
import { bandTone, formatMetric, formatPercent, formatTimestamp } from './missionData'
import type { MissionCore } from './missionData'

/* ================================================================== */
/* 02 — The problem                                                    */
/* ================================================================== */

export function Problem({ core }: { core: MissionCore }) {
  const map = core.disagreement.data
  const points = map?.points ?? []
  const bands = points.reduce<Record<string, number>>((acc, p) => {
    acc[p.band] = (acc[p.band] ?? 0) + 1
    return acc
  }, {})
  const worst = [...points].sort(
    (a, b) => Math.abs(b.difference ?? 0) - Math.abs(a.difference ?? 0),
  )[0]

  return (
    <MissionSection
      id="problem"
      index="02"
      eyebrow="THE PROBLEM"
      title={
        <>
          The ocean is observable.
          <br />
          But never completely observed.
        </>
      }
      sub="Ocean observations are sparse, unevenly distributed and expensive to collect. Models provide continuous coverage, but can disagree with reality. TidalTwin turns that disagreement into a measurable decision signal."
    >
      <div className="mi-split">
        <Reveal className="mi-split__text">
          <p className="oh-lede">
            Coverage is not the same as understanding. A dense surface product can sit directly above a
            water column nobody has sampled, and nothing in a viewer will tell you so.
          </p>
          <ul className="mi-list">
            <li>
              <b>Surface bias.</b> Most remote sensing stops at the skin of the ocean. Below it, the
              thermocline and the deep basin are inferred, not measured.
            </li>
            <li>
              <b>Sampling bias.</b> A station that was convenient ten years ago is still the station
              the fleet visits.
            </li>
            <li>
              <b>Disagreement is invisible.</b> Where a model and an observation disagree, a viewer
              renders two layers and leaves the reader to guess which one to believe.
            </li>
          </ul>
          <p className="mi-split__kick">
            TidalTwin starts from that disagreement. It measures how far apart the model and the
            observation are, and treats that gap as the thing worth resolving.
            <br />
            Given what we do not know — where should we measure next?
          </p>
        </Reveal>

        <Reveal className="mi-split__panel" delay={0.1}>
          <div className="oh-panel mi-panel">
            <div className="oh-panel__head">
              <span className="oh-eyebrow">
                <GitBranch size={12} /> MODEL ⇄ OBSERVATION
              </span>
              {core.disagreement.loading ? <Loading label="comparing" /> : null}
            </div>

            <ol className="mi-signal-flow" aria-label="Model to next observation flow">
              {['MODEL', 'REALITY', 'DISAGREEMENT', 'UNCERTAINTY', 'NEXT OBSERVATION'].map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>

            {core.disagreement.loading ? null : !map ? (
              <Absence reason={core.disagreement.reason} />
            ) : (
              <>
                <p className="oh-panel__sub">
                  {points.length} reference location{points.length === 1 ? '' : 's'} carry a model value
                  and an observation for the same variable. The twin reports the gap rather than hiding
                  it.
                </p>

                <div className="mi-bands" role="list" aria-label="Disagreement bands">
                  {(['green', 'yellow', 'orange', 'red'] as const).map((band) => (
                    <div className="mi-band" key={band} role="listitem" data-tone={bandTone(band)}>
                      <b>{bands[band] ?? 0}</b>
                      <span>{band}</span>
                    </div>
                  ))}
                </div>

                {worst ? (
                  <div className="mi-worst">
                    <span className="oh-eyebrow">LARGEST REPORTED GAP</span>
                    <p>
                      <b>{worst.location}</b> · {worst.variable}
                    </p>
                    <div className="mi-worst__nums">
                      <span>
                        model <b>{formatMetric(worst.model)}</b>
                      </span>
                      <span>
                        observed <b>{formatMetric(worst.observed)}</b>
                      </span>
                      <span>
                        difference{' '}
                        <b className={bandTone(worst.band) === 'crit' ? 'is-crit' : ''}>
                          {formatMetric(worst.difference)}
                        </b>
                      </span>
                      <span>
                        confidence{' '}
                        <b>
                          {worst.confidence == null ? '—' : formatPercent(worst.confidence)}
                        </b>
                      </span>
                    </div>
                    <OriginTag status={worst.data_status} />
                  </div>
                ) : null}

                <ul className="mi-rows">
                  {points.slice(0, 6).map((p) => (
                    <li key={`${p.location_id}-${p.variable}`}>
                      <span className="mi-rows__name">{p.location}</span>
                      <span className="mi-rows__var">{p.variable}</span>
                      <span className="mi-rows__band" data-tone={bandTone(p.band)}>
                        {p.status}
                      </span>
                      <span className="mi-rows__val">
                        Δ {formatMetric(p.difference)} · {p.band}
                      </span>
                    </li>
                  ))}
                </ul>
                {points.length > 6 ? (
                  <Caveat>
                    Showing 6 of {points.length} compared locations. The full ledger is in the Digital
                    Twin.
                  </Caveat>
                ) : null}
              </>
            )}

            <div className="oh-panel__foot">
              <Link className="oh-btn oh-btn--ghost" to="/globe">
                OPEN THE DIGITAL TWIN <ArrowRight size={14} />
              </Link>
            </div>
          </div>
        </Reveal>
      </div>
    </MissionSection>
  )
}

/* ================================================================== */
/* 03 — The 4D twin                                                    */
/* ================================================================== */

export function FourDTwin({ core }: { core: MissionCore }) {
  const registry = core.sources.data
  const sources = registry?.sources ?? []

  return (
    <MissionSection
      id="twin"
      index="03"
      eyebrow="THE TWIN"
      title="One ocean. Four dimensions. Every reading labelled."
      sub="Three spatial dimensions give a volume; time makes it a record. What separates TidalTwin from a static model is that each layer keeps the origin of its own value — measured, modelled, derived, simulated or unknown."
      aside={
        registry ? (
          <span className="oh-badge oh-badge--src">
            {registry.health.online} / {registry.health.total} SOURCES ONLINE
          </span>
        ) : core.sources.loading ? (
          <Loading label="reading registry" />
        ) : null
      }
    >
      <Reveal className="mi-axes" as="div">
        {[
          { k: 'X', t: 'LONGITUDE', d: 'Geometry, bathymetry, distance to coast, shelf position.' },
          { k: 'Y', t: 'LATITUDE', d: 'Latitude band, upwelling regime, monsoon forcing.' },
          { k: 'Z', t: 'DEPTH', d: 'Surface skin, mixed layer, thermocline, deep basin.' },
          { k: 'T', t: 'TIME', d: 'Nowcast, forecast, and the archive that explains the nowcast.' },
        ].map((axis) => (
          <div className="mi-axis" key={axis.k}>
            <b>{axis.k}</b>
            <span className="oh-eyebrow">{axis.t}</span>
            <p>{axis.d}</p>
          </div>
        ))}
      </Reveal>

      <Reveal className="mi-ocean-column" delay={0.04}>
        <div className="mi-ocean-column__labels" aria-hidden="true">
          <span>0 m · SURFACE</span><span>THERMOCLINE</span><span>SUBSURFACE</span><span>1,000 m</span>
        </div>
        <div className="mi-ocean-column__water" role="img" aria-label="Schematic ocean column showing surface, thermocline and subsurface observation depths">
          <i className="mi-ocean-column__thermocline" />
          <i className="mi-ocean-column__point mi-ocean-column__point--one" />
          <i className="mi-ocean-column__point mi-ocean-column__point--two" />
          <i className="mi-ocean-column__point mi-ocean-column__point--three" />
          <span>DEPTH</span>
        </div>
        <div className="mi-ocean-column__time"><b>TIME</b><span>ARCHIVE</span><i /> <span>NOW</span><i /> <span>OBSERVATION</span></div>
        <p className="mi-ocean-column__caption">A 4D view follows a signal from surface through depth and time to the next observation. <SchematicTag compact>SCHEMATIC</SchematicTag></p>
      </Reveal>

      <Reveal className="mi-constellation" delay={0.08}>
        <div className="mi-constellation__head" id="sources">
          <span className="oh-eyebrow">ONE OCEAN. MANY SIGNALS.</span>
          <span className="mi-constellation__note">Source availability varies by dataset and time.</span>
        </div>
        <div className="mi-constellation__groups">
          <div><b>IN-SITU</b><span>Argo · BGC-Argo · CTD · IOOS Gliders</span></div>
          <div><b>SATELLITE / REMOTE</b><span>NOAA · VIIRS · ERSST</span></div>
          <div><b>MODELS</b><span>HYCOM · Copernicus Marine</span></div>
          <strong className="mi-constellation__core">TIDALTWIN</strong>
          <div><b>MARITIME</b><span>Global Fishing Watch AIS</span></div>
          <div><b>CARBON / CHEMISTRY</b><span>SOCAT · marine environmental datasets</span></div>
          <div><b>MARINE CONDITIONS</b><span>Open-Meteo Marine</span></div>
        </div>
        <p className="mi-constellation__caveat">Integrations, archives and model-derived products retain their own origin; this overview does not imply that every source is live.</p>
      </Reveal>

      <Reveal className="mi-registry" delay={0.1}>
        <div className="mi-registry__head">
          <span className="oh-eyebrow">
            <Radar size={12} /> DATA-SOURCE REGISTRY
          </span>
          <span className="mi-registry__meta">
            {registry ? `read ${formatTimestamp(registry.generated_at)} IST` : 'awaiting registry'}
          </span>
        </div>

        {core.sources.loading ? (
          <Loading label="asking the source registry" />
        ) : !registry ? (
          <Absence reason={core.sources.reason} />
        ) : (
          <ul className="mi-sources">
            {sources.map((s) => (
              <li key={s.id ?? s.name} className="mi-source" data-status={s.status}>
                <div className="mi-source__top">
                  <b>{s.name}</b>
                  <span className={`oh-status oh-status--${s.status === 'online' ? 'ok' : 'warn'}`}>
                    {s.status}
                  </span>
                </div>
                <div className="mi-source__mid">
                  <OriginTag status={s.origin_status} />
                  {s.kind ? <span className="mi-source__kind">{s.kind}</span> : null}
                  {s.coverage_pct != null ? (
                    <span className="mi-source__cov">{formatPercent(s.coverage_pct)} coverage</span>
                  ) : null}
                </div>
                {s.note ? <p className="mi-source__note">{s.note}</p> : null}
                {s.status_detail ? <p className="mi-source__detail">{s.status_detail}</p> : null}
                <div className="mi-source__foot">
                  {s.last_update ? <span>last update {formatTimestamp(s.last_update)}</span> : null}
                  {s.variables?.length ? (
                    <span className="mi-source__vars">{s.variables.join(' · ')}</span>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}

        {registry?.health.degraded.length ? (
          <Caveat tone="edge">
            Degraded sources: {registry.health.degraded.join(', ')}. Degraded does not mean absent — the
            registry still reports what each source can and cannot currently support.
          </Caveat>
        ) : null}
      </Reveal>
    </MissionSection>
  )
}

/* ================================================================== */
/* 04 — The chain                                                      */
/* ================================================================== */

const CHAIN = [
  {
    icon: Eye,
    k: 'OBSERVE',
    q: 'What do we actually have?',
    d: 'Ingested measurements, their data status, their depth, their age. Nothing promoted to a fact until its origin is known.',
    to: '/globe',
    cta: 'SEE THE LAYERS',
  },
  {
    icon: Radar,
    k: 'DETECT',
    q: 'What changed?',
    d: 'Model fields compared against observations. Persistent divergence becomes an event, with severity, persistence and the evidence behind it.',
    to: '/anomalies',
    cta: 'SEE THE EVENTS',
  },
  {
    icon: ScanSearch,
    k: 'INVESTIGATE',
    q: 'Is it the model, the sensor, or the ocean?',
    d: 'A verdict weighs sensor fault against model error and a genuinely missing phenomenon — and is allowed to answer "insufficient evidence".',
    to: '/tide',
    cta: 'SEE THE VERDICT',
  },
] as const

export function Chain() {
  return (
    <MissionSection
      id="chain"
      index="04"
      eyebrow="THE CHAIN"
      title="Observe. Detect. Investigate. Then — and only then — decide."
      sub="Each link is a separate surface with its own evidence. The intelligence layer is what reads across all three."
    >
      <div className="mi-chain">
        {CHAIN.map((link, i) => {
          const Icon = link.icon
          return (
            <Reveal className="mi-chain__item" key={link.k} delay={i * 0.09}>
              <span className="mi-chain__num">{String(i + 1).padStart(2, '0')}</span>
              <span className="mi-chain__icon">
                <Icon size={18} />
              </span>
              <b className="mi-chain__k">{link.k}</b>
              <p className="mi-chain__q">{link.q}</p>
              <p className="mi-chain__d">{link.d}</p>
              <Link className="mi-chain__cta" to={link.to}>
                {link.cta} <ArrowRight size={13} />
              </Link>
              {i < CHAIN.length - 1 ? (
                <span className="mi-chain__link" aria-hidden="true">
                  <GitBranch size={16} />
                </span>
              ) : null}
            </Reveal>
          )
        })}
      </div>

      <Reveal className="mi-chain__foot" delay={0.3}>
        <p>
          <Waves size={15} aria-hidden="true" />
          The loop is closed only when the chosen observation comes back into the store and the twin
          re-scores. Nothing in TidalTwin is write-once.
        </p>
      </Reveal>
    </MissionSection>
  )
}

/* ================================================================== */
/* 05 — Decision Intelligence                                          */
/* ================================================================== */

const INTELLIGENCE = [
  {
    icon: Compass,
    k: 'DECISION IMPACT',
    q: 'What decision would this change?',
    d: 'An observation that confirms what you already believe is worth less than one that flips an operational call — whether to re-task a survey, redeploy a mooring, or stand down.',
  },
  {
    icon: Layers,
    k: 'UNCERTAINTY',
    q: 'How unsure are we, honestly?',
    d: 'Uncertainty combines disagreement, data gaps and the age of the evidence. A stale confident field is not a low-uncertainty field; it is an unexamined one.',
  },
  {
    icon: Boxes,
    k: 'DATA GAP',
    q: 'What is structurally missing?',
    d: 'Depth with no profile. A region with no seasonal history. A variable nobody sampled. Gaps are first-class objects, not empty cells.',
  },
] as const

export function Understand() {
  return (
    <MissionSection
      id="intelligence"
      index="05"
      eyebrow="DECISION INTELLIGENCE"
      title="A viewer answers “what is there”. TidalTwin asks “what would change our mind”."
      sub="Three questions stand between a layer and a deployment. Answering them is not a dashboard feature — it is the TIDE score itself."
    >
      <div className="mi-intel">
        {INTELLIGENCE.map((item, i) => {
          const Icon = item.icon
          return (
            <Reveal className="mi-intel__card" key={item.k} delay={i * 0.09}>
              <span className="mi-intel__icon">
                <Icon size={17} />
              </span>
              <b>{item.k}</b>
              <p className="mi-intel__q">{item.q}</p>
              <p className="mi-intel__d">{item.d}</p>
            </Reveal>
          )
        })}
      </div>

      <Reveal className="mi-intel__foot" delay={0.28}>
        <p className="oh-lede">
          Read those three questions together with cost, and you get a ranking: not the most
          interesting place in the ocean, but the place where the next unit of observing effort buys
          the most.
        </p>
        <p className="mi-intel__hint">
          <Clock3 size={14} aria-hidden="true" /> The next section shows exactly how that ranking is
          computed — including the parts it cannot know.
        </p>
      </Reveal>
    </MissionSection>
  )
}
