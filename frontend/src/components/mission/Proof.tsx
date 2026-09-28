/**
 * Mission Intro — Sections 11 … 15
 * ================================
 * 11  Validation and the scientific boundary — including the things the
 *     system is explicitly forbidden from claiming.
 * 12  The complete intelligence loop, phase by phase, each phase wired to
 *     the route that implements it.
 * 13  Ocean domains — the real application surfaces, not a wishlist.
 * 14  Who it is for.
 * 15  The closing mission statement.
 *
 * Section 11's benchmark is requested only once the section is on screen. The
 * reference benchmark runs the full ranking engine across every strategy, which
 * is the wrong thing to do during first paint.
 */
import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  Ban,
  FlaskConical,
  GraduationCap,
  Landmark,
  Microscope,
  Recycle,
  Route,
  Ship,
  Waves,
} from 'lucide-react'
import {
  Absence,
  Caveat,
  Loading,
  MissionSection,
  Reveal,
  SchematicTag,
} from './Primitives'
import { useBenchmark, formatMetric, formatPercent, formatTimestamp } from './missionData'
import { useInView } from '../ocean/hooks'
import type { MissionCore } from './missionData'

/* ================================================================== */
/* 11 — Validation & the scientific boundary                           */
/* ================================================================== */

export function Validation({ core }: { core: MissionCore }) {
  const { ref, inView } = useInView<HTMLDivElement>({ margin: '0px 0px -15% 0px' })
  const benchmark = useBenchmark(inView)
  const v = core.validation.data

  // Derived from the report rather than asserted: which strategies actually
  // reached the best mean uncertainty reduction, and how many cases there were.
  const verdict = useMemo(() => {
    const rows = benchmark.data?.aggregates ?? []
    const usable = rows.filter(
      (a) => a.uncertainty_reduction.mean != null && a.cases_with_selection > 0,
    )
    if (usable.length === 0) return null
    const best = Math.max(...usable.map((a) => a.uncertainty_reduction.mean as number))
    const leaders = usable
      .filter((a) => Math.abs((a.uncertainty_reduction.mean as number) - best) < 1e-9)
      .map((a) => a.strategy)
    const n = Math.max(...rows.map((a) => a.N))
    return { leaders, best, n, strategies: rows.length }
  }, [benchmark.data])

  return (
    <section className="mi-section" id="validation" aria-labelledby="validation-title" ref={ref}>
      <Reveal className="mi-section__head">
        <div className="mi-section__marker">
          <span className="mi-section__num">11</span>
          <span className="mi-section__rule" aria-hidden="true" />
          <span className="oh-eyebrow">VALIDATION &amp; THE SCIENTIFIC BOUNDARY</span>
        </div>
        <div className="mi-section__headrow">
          <div className="mi-section__headtext">
            <h2 className="oh-title" id="validation-title">
              Here is what is implemented, and what still needs external evidence.
            </h2>
            <p className="oh-sub">
              Maturity is tracked per claim, not per product. A system that is fully implemented and
              heavily tested system still needs ground truth before scientific validation.
              <br />
              <span className="mi-validation-boundary">IMPLEMENTED · TESTED · DEMONSTRATED &nbsp; / &nbsp; SCIENTIFIC VALIDATION — NEXT MILESTONE</span>
            </p>
          </div>
        </div>
      </Reveal>

      <div className="mi-section__body">
        {core.validation.loading ? (
          <Loading label="reading validation status" />
        ) : !v ? (
          <Absence reason={core.validation.reason} />
        ) : (
          <>
            <Reveal className="mi-maturity">
              <div className="mi-maturity__col">
                <span className="oh-eyebrow">
                  <BadgeCheck size={12} /> IMPLEMENTED
                </span>
                <b>{v.maturity.IMPLEMENTED.length}</b>
                <p>capabilities that exist and run</p>
              </div>
              <div className="mi-maturity__col">
                <span className="oh-eyebrow">
                  <FlaskConical size={12} /> DEMONSTRATED
                </span>
                <b>{v.maturity.DEMONSTRATED.length}</b>
                <p>capabilities exercised end to end</p>
              </div>
              <div className="mi-maturity__col">
                <span className="oh-eyebrow">
                  <Microscope size={12} /> TESTED
                </span>
                <b>{v.maturity.TESTED.length}</b>
                <p>capabilities covered by the test suite</p>
              </div>
              <div className="mi-maturity__col mi-maturity__col--empty">
                <span className="oh-eyebrow">
                  <Ban size={12} /> EMPIRICALLY VALIDATED
                </span>
                <b>{v.maturity.EMPIRICALLY_VALIDATED.length}</b>
                <p>{v.maturity.empirical_note}</p>
              </div>
            </Reveal>

            <div className="mi-val-grid">
              <Reveal className="mi-val" delay={0.06}>
                <span className="oh-eyebrow">REFERENCE DATASET</span>
                <p className="mi-val__id">
                  {v.dataset.id} <em>{v.dataset.version}</em>
                </p>
                <ul>
                  <li>
                    locations <b>{v.dataset.locations}</b>
                  </li>
                  <li>
                    observations <b>{v.dataset.observations}</b>
                  </li>
                  <li>
                    events <b>{v.dataset.events}</b>
                  </li>
                  <li>
                    status <b>{v.dataset.status}</b>
                  </li>
                </ul>
                <Caveat>source: {v.dataset.source}</Caveat>
              </Reveal>

              <Reveal className="mi-val" delay={0.12}>
                <span className="oh-eyebrow">GROUND TRUTH</span>
                <p className="mi-val__flag" data-ok={v.ground_truth.available ? 'true' : 'false'}>
                  <AlertTriangle size={14} aria-hidden="true" />
                  {v.ground_truth.available ? 'available' : 'not available'}
                </p>
                <Absence reason={v.ground_truth.reason} compact />
                <ul>
                  <li>
                    false alarm <b>{v.ground_truth.false_alarm}</b>
                  </li>
                  <li>
                    missed event <b>{v.ground_truth.missed_event}</b>
                  </li>
                </ul>
              </Reveal>

              <Reveal className="mi-val" delay={0.18}>
                <span className="oh-eyebrow">ALGORITHM CONSISTENCY</span>
                <ul>
                  <li>
                    factor sensitivity{' '}
                    <b data-ok={v.sensitivity.all_consistent ? 'true' : 'false'}>
                      {v.sensitivity.all_consistent ? 'all factors behave as expected' : 'inconsistent factor found'}
                    </b>
                  </li>
                  <li>
                    edge cases{' '}
                    <b data-ok={v.edge_cases.all_finite ? 'true' : 'false'}>
                      {v.edge_cases.all_finite ? 'all outputs finite' : 'non-finite output found'}
                    </b>
                  </li>
                  <li>
                    cost assumption <b>{v.cost_assumption}</b>
                  </li>
                  <li>
                    seed / budget <b>{v.reproducibility.default_seed} / {v.reproducibility.default_budget}</b>
                  </li>
                </ul>
                <Caveat>
                  Internal consistency is not external validity. These checks catch implementation
                  errors; they cannot confirm the ocean behaves the way the model assumes.
                </Caveat>
              </Reveal>
            </div>

            <Reveal className="mi-boundary" delay={0.24}>
              <div className="mi-boundary__col" data-kind="can">
                <span className="oh-eyebrow">THIS PAGE MAY CLAIM</span>
                <ul>
                  {v.scientific_boundary.can_show.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
              </div>
              <div className="mi-boundary__col" data-kind="cannot">
                <span className="oh-eyebrow">THIS PAGE MUST NOT CLAIM</span>
                <ul>
                  {v.scientific_boundary.cannot_show.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
              </div>
              <p className="mi-boundary__statement">
                <Quote /> {v.scientific_boundary.statement}
              </p>
            </Reveal>

            {v.limitations.length ? (
              <Reveal className="mi-limits" delay={0.3}>
                <span className="oh-eyebrow">STATED LIMITATIONS</span>
                <ul>
                  {v.limitations.map((l) => (
                    <li key={l}>{l}</li>
                  ))}
                </ul>
              </Reveal>
            ) : null}
          </>
        )}

        {/* --- deferred benchmark ------------------------------------ */}
        <Reveal className="mi-bench" delay={0.34}>
          <div className="mi-bench__head">
            <span className="oh-eyebrow">REFERENCE BENCHMARK — BUDGET-CONSISTENT STRATEGY COMPARISON</span>
            <SchematicTag>N = {benchmark.data?.configuration.cases.length ?? '—'} CASES</SchematicTag>
          </div>

          {benchmark.loading ? (
            <Loading label="running the reference benchmark" />
          ) : !benchmark.data ? (
            <Absence reason={benchmark.reason} />
          ) : (
            <>
              <div className="mi-bench__meta">
                <span>
                  budget <b>{benchmark.data.configuration.budget}</b>
                </span>
                <span>
                  seed <b>{benchmark.data.configuration.seed}</b>
                </span>
                <span>
                  strategies <b>{benchmark.data.configuration.strategies.length}</b>
                </span>
                <span>
                  ground truth{' '}
                  <b>{benchmark.data.configuration.ground_truth_available ? 'yes' : 'no'}</b>
                </span>
                <span>
                  run at {formatTimestamp(benchmark.data.generated_at)}
                </span>
              </div>

              <div className="mi-bench__table" role="table" aria-label="Benchmark strategies">
                <div className="mi-bench__row mi-bench__row--head" role="row">
                  <span role="columnheader">STRATEGY</span>
                  <span role="columnheader">CASES</span>
                  <span role="columnheader">UNCERTAINTY REDUCTION (MEAN)</span>
                  <span role="columnheader">DECISION CHANGES</span>
                </div>
                {benchmark.data.aggregates.map((a) => (
                  <div
                    className={`mi-bench__row${
                      verdict?.leaders.includes(a.strategy) ? ' is-leader' : ''
                    }`}
                    key={a.strategy}
                    role="row"
                  >
                    <span role="cell">{a.strategy_label || a.strategy}</span>
                    <span role="cell">{a.N}</span>
                    <span role="cell">{formatMetric(a.uncertainty_reduction.mean, 4)}</span>
                    <span role="cell">{formatPercent(a.decision_change_rate)}</span>
                  </div>
                ))}
              </div>

              {verdict ? (
                <p className="mi-bench__verdict">
                  On this reference run, {verdict.leaders.join(' and ')} reached the highest mean
                  uncertainty reduction, across {verdict.n} case{verdict.n === 1 ? '' : 's'} and{' '}
                  {verdict.strategies} strategies.
                </p>
              ) : null}

              <Caveat tone="edge">
                {benchmark.data.ground_truth.reason} A tied or leading mean on {verdict?.n ?? 'a few'}{' '}
                cases with no ground truth is not evidence of superiority, and this page will not
                present it as such. {benchmark.data.fairness.note}
              </Caveat>
            </>
          )}
        </Reveal>
      </div>
    </section>
  )
}

function Quote() {
  return <span className="mi-quote" aria-hidden="true">“</span>
}

/* ================================================================== */
/* 12 — The complete loop                                              */
/* ================================================================== */

const LOOP = [
  { n: '01', k: 'OBSERVE', d: 'See the ocean through models, observations and spatial layers.', to: '/globe' },
  { n: '02', k: 'DETECT', d: 'Identify anomalies and model–observation deviations.', to: '/anomalies' },
  { n: '03', k: 'INVESTIGATE', d: 'Trace when, where and how an event changed.', to: '/forensics' },
  { n: '04', k: 'UNDERSTAND', d: 'Connect variables, threats and possible causal relationships.', to: '/intelligence' },
  { n: '05', k: 'PRIORITIZE', d: 'Rank where additional observation may provide the most value.', to: '/tide' },
  { n: '06', k: 'OBSERVE NEXT', d: 'Explore candidate observation locations.', to: '/oceanvision?tab=recommend' },
  { n: '07', k: 'SIMULATE', d: 'Test what-if observations without modifying real data.', to: '/scenarios' },
  { n: '08', k: 'DECIDE', d: 'Replay model-only and TIDE-assisted decision paths.', to: '/tide/replay' },
  { n: '09', k: 'VALIDATE', d: 'Inspect evidence, limitations, sensitivity and reproducibility.', to: '/validate' },
] as const

export function LoopDiagram() {
  return (
    <MissionSection
      id="loop"
      index="12"
      eyebrow="THE COMPLETE LOOP"
      title="From signal to decision. Then back to observation."
      sub="Nine connected phases carry evidence from the ocean into a decision, and validation returns the work to the next observation."
    >
      <Reveal className="mi-loop" as="div">
        {LOOP.map((p) => (
          <Link className="mi-loop__node" to={p.to} key={p.k}>
            <span className="mi-loop__n">{p.n}</span>
            <b>{p.k}</b>
            <p>{p.d}</p>
            <span className="mi-loop__go">
              <Route size={12} aria-hidden="true" /> {p.to}
            </span>
          </Link>
        ))}
      </Reveal>
      <Reveal className="mi-loop-return" delay={0.34}>
        <span>09 · VALIDATE</span><i aria-hidden="true">↶</i><span>01 · OBSERVE</span>
      </Reveal>
      <Reveal className="mi-loop__foot" delay={0.3}>
        <Recycle size={16} aria-hidden="true" />
        <p>
          Every phase writes back into the same observation ledger with the same provenance
          vocabulary. That is what makes the loop closed rather than decorative.
        </p>
      </Reveal>
    </MissionSection>
  )
}

/* ================================================================== */
/* 13 — Ocean domains                                                  */
/* ================================================================== */

const DOMAINS = [
  {
    to: '/coastal',
    icon: Waves,
    k: 'COASTAL INTELLIGENCE',
    signal: 'COASTAL RISK →',
    d: 'Shoreline, sediment and nearshore behaviour.',
  },
  {
    to: '/deoxygenation',
    icon: Microscope,
    k: 'DEOXYGENATION',
    signal: 'O₂ ↓',
    d: 'Dissolved oxygen trends and coastal dead zones.',
  },
  {
    to: '/acidification',
    icon: FlaskConical,
    k: 'ACIDIFICATION',
    signal: 'pH ↓ · Ω ↓',
    d: 'Carbon uptake, pH and saturation state.',
  },
  {
    to: '/microplastics',
    icon: Recycle,
    k: 'MICROPLASTICS',
    signal: 'MICROPLASTICS ↑',
    d: 'Particle distribution, transport and sinks.',
  },
  {
    to: '/safety',
    icon: AlertTriangle,
    k: 'MARITIME SAFETY',
    signal: 'MARITIME ·',
    d: 'Conditions that affect vessels and offshore work.',
  },
  {
    to: '/risk',
    icon: Ship,
    k: 'RISK',
    signal: 'EXPOSURE →',
    d: 'Where environmental signal becomes operational exposure.',
  },
] as const

export function Domains() {
  return (
    <MissionSection
      id="domains"
      index="13"
      eyebrow="OCEAN DOMAINS"
      title="The twin is general. These are the domains it is wired into today."
      sub="Each domain is an existing surface in TidalTwin, not a roadmap item. The same observation ledger and the same provenance rules serve all of them."
    >
      <div className="mi-domains">
        {DOMAINS.map((d, i) => {
          const Icon = d.icon
          return (
            <Reveal className="mi-domain" key={d.to} delay={i * 0.06}>
              <Link to={d.to}>
                <span className="mi-domain__icon">
                  <Icon size={17} />
                </span>
                <span className="mi-domain__signal">{d.signal}</span>
                <b>{d.k}</b>
                <p>{d.d}</p>
                <span className="mi-domain__go">
                  open <ArrowRight size={12} />
                </span>
              </Link>
            </Reveal>
          )
        })}
      </div>
    </MissionSection>
  )
}

/* ================================================================== */
/* 14 — Who it is for                                                  */
/* ================================================================== */

const USERS = [
  {
    icon: Landmark,
    k: 'RESEARCH INSTITUTIONS',
    q: '“Where should our next cruise spend its days?”',
    d: 'Turn a limited ship-time budget into a defensible sampling plan, with the evidence and the uncertainty attached to every site.',
  },
  {
    icon: Ship,
    k: 'COASTAL & PORT AUTHORITIES',
    q: '“What changes our operating decision this week?”',
    d: 'Fuse environmental signal with operational consequence, and see which observation would firm up a call before you make it.',
  },
  {
    icon: Microscope,
    k: 'NGOs & CONSERVATION BODIES',
    q: '“Can we defend this number?”',
    d: 'Every figure carries its origin, so a figure that cannot be sourced is visibly absent rather than quietly quoted.',
  },
  {
    icon: GraduationCap,
    k: 'STUDENTS & RESEARCHERS',
    q: '“Can I follow the reasoning?”',
    d: 'A complete, inspectable chain from observation to recommendation — the fastest way to understand how decision-support oceanography actually works.',
  },
] as const

export function Users() {
  return (
    <MissionSection
      id="users"
      index="14"
      eyebrow="WHO IT IS FOR"
      title="Four people who need to know why the system says so."
      sub="TidalTwin is built for readers who have to defend a decision, not just view a map."
    >
      <div className="mi-users">
        {USERS.map((u, i) => {
          const Icon = u.icon
          return (
            <Reveal className="mi-user" key={u.k} delay={i * 0.07}>
              <span className="mi-user__icon">
                <Icon size={16} />
              </span>
              <b>{u.k}</b>
              <p className="mi-user__q">{u.q}</p>
              <p className="mi-user__d">{u.d}</p>
            </Reveal>
          )
        })}
      </div>
    </MissionSection>
  )
}

/* ================================================================== */
/* 15 — Finale                                                         */
/* ================================================================== */

export function Finale({ core }: { core: MissionCore }) {
  const health = core.health.data
  const statusRows = [
    { label: 'SYSTEM HEALTH', value: health?.status.toUpperCase() ?? 'UNAVAILABLE' },
    {
      label: 'OBSERVATION SOURCES',
      value: core.sources.data
        ? `${core.sources.data.health.online} / ${core.sources.data.health.total} REPORTED ONLINE`
        : 'UNAVAILABLE',
    },
    { label: 'MODEL / REALITY COMPARISON', value: core.disagreement.data ? 'AVAILABLE' : 'UNAVAILABLE' },
    { label: 'TIDE', value: core.candidates.data ? 'ALGORITHM v1.0' : 'UNAVAILABLE' },
    { label: 'SIMULATION', value: 'ISOLATED' },
    { label: 'PROVENANCE', value: 'ENABLED' },
  ]
  return (
    <section className="mi-finale" id="finale" aria-labelledby="finale-title">
      <Reveal className="mi-finale__inner">
        <span className="oh-eyebrow">THE MISSION</span>
        <h2 className="mi-finale__title" id="finale-title">
          The ocean changes.
          <br />
          So should the way we observe it.
        </h2>
        <p className="mi-finale__lede">
          Explore the digital twin, investigate ocean events, and follow the evidence from observation
          to decision.
        </p>

        <div className="mi-finale__cta">
          <Link className="oh-btn oh-btn--solid" to="/globe">
            ENTER DIGITAL TWIN <ArrowRight size={15} />
          </Link>
          <Link className="oh-btn oh-btn--ghost" to="/tide">
            EXPLORE TIDE
          </Link>
        </div>

        <dl className="mi-system-status" aria-label="Mission system status">
          {statusRows.map((row) => (
            <div key={row.label}>
              <dt>{row.label}</dt>
              <dd data-available={row.value === 'UNAVAILABLE' ? 'false' : 'true'}>{row.value}</dd>
            </div>
          ))}
        </dl>

        <p className="mi-finale__foot">
          {health ? (
            <>
              <span className={`oh-status oh-status--${health.status === 'healthy' ? 'ok' : 'warn'}`}>
                {health.status}
              </span>
              <span>
                {health.service} v{health.version}
                {health.environment ? ` · ${health.environment}` : ''}
                {health.simulation_mode ? ' · simulation mode active' : ''}
              </span>
            </>
          ) : (
            <span>System status is not available right now — the rest of this page still works.</span>
          )}
        </p>
      </Reveal>
    </section>
  )
}
