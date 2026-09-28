/**
 * Mission Intro — Sections 08 … 10
 * ================================
 * 08  Observe Next — the recommendation, and how to reject it.
 * 09  What-if simulation — a *real* call to /tide/virtual-observation, so the
 *     interaction is genuine even though the reading is explicitly simulated.
 * 10  Decision Replay — the same event walked twice: model-only, then
 *     TIDE-assisted, with the deltas and the reasons.
 *
 * Section 10 is deferred behind IntersectionObserver because a replay composes
 * three engines (candidates, evidence, verdict) and is far too expensive to
 * fetch during first paint.
 */
import { useCallback, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  FlaskConical,
  History,
  MapPin,
  Scale,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'
import {
  Absence,
  Caveat,
  Loading,
  MissionSection,
  OriginTag,
  Reveal,
  SchematicTag,
  SimulatedTag,
} from './Primitives'
import {
  formatMetric,
  formatPercent,
  useDecisionReplay,
} from './missionData'
import { useInView } from '../ocean/hooks'
import { runVirtualObservation } from '../../api/client'
import type { MissionCore, Resource } from './missionData'
import type {
  DecisionReplay,
  TideCandidate,
  VirtualObservationSimulation,
} from '../../types/tide'

/* ================================================================== */
/* 08 — Observe Next                                                   */
/* ================================================================== */

export function ObserveNext({ core }: { core: MissionCore }) {
  const candidates = core.candidates.data ?? []
  const top = candidates.slice(0, 3)

  return (
    <MissionSection
      id="observe-next"
      index="08"
      eyebrow="OBSERVE NEXT"
      title="A recommendation is only useful if you can reject it."
      sub="TidalTwin does not hand over a location and call it a conclusion. Each recommendation carries the reason it ranked, the evidence behind it, and the limitations that should make a careful operator hesitate."
    >
      {core.candidates.loading ? (
        <Loading label="requesting a fresh ranking" />
      ) : !top.length ? (
        <Absence reason={core.candidates.reason} />
      ) : (
        <div className="mi-recos">
          {top.map((c, i) => (
            <Reveal className="mi-reco" key={c.candidate_id} delay={i * 0.08}>
              <div className="mi-reco__rank">
                <span>#{i + 1}</span>
                <OriginTag status={c.status} />
              </div>
              <h3>
                <MapPin size={15} aria-hidden="true" /> {c.location}
              </h3>
              <p className="mi-reco__meta">
                {c.variable} · {c.depth_m} m · via {c.observation_type.replace(/_/g, ' ').toLowerCase()}
              </p>
              <p className="mi-reco__reason">{c.reason}</p>
              <div className="mi-reco__nums">
                <div>
                  <b>{formatMetric(c.observation_value, 3)}</b>
                  <span>observation value</span>
                </div>
                <div>
                  <b>{formatMetric(c.expected_uncertainty_reduction, 3)}</b>
                  <span>exp. uncertainty reduction</span>
                </div>
                <div>
                  <b>{formatPercent(c.confidence)}</b>
                  <span>confidence</span>
                </div>
              </div>
              <p className="mi-reco__decision">
                would inform <b>{c.affected_decision.replace(/_/g, ' ').toLowerCase()}</b>
              </p>
              {c.limitations.length ? (
                <ul className="mi-reco__limits">
                  {c.limitations.map((l) => (
                    <li key={l}>{l}</li>
                  ))}
                </ul>
              ) : null}
            </Reveal>
          ))}
        </div>
      )}

      <Reveal className="mi-recos__foot" delay={0.26}>
        <div className="mi-recos__limits-block">
          <span className="oh-eyebrow">
            <Scale size={12} /> WHAT THIS RANKING DOES NOT KNOW
          </span>
          <ul>
            <li>Whether the modelled field is right where no observation exists to contradict it.</li>
            <li>Whether a cheap method can actually reach the site at the season it is needed.</li>
            <li>Whether the operator's real budget, vessel availability and safety constraints match the modelled cost.</li>
            <li>Whether the next observation changes the world, or only changes the field.</li>
          </ul>
          <Caveat tone="edge">
            The score is a prioritisation heuristic over five normalised factors. It is deliberately
            replaceable by a value-of-information or Bayesian formulation; until that is validated
            against outcomes, it is a starting point for a human decision, not the decision.
          </Caveat>
        </div>
        <Link className="oh-btn oh-btn--solid" to="/tide">
          SEE THE FULL RANKING <ArrowRight size={14} />
        </Link>
      </Reveal>
    </MissionSection>
  )
}

/* ================================================================== */
/* 09 — What-if simulation (real API, simulated reading)               */
/* ================================================================== */

export function Simulate({ core }: { core: MissionCore }) {
  // Stable reference: `?? []` would otherwise mint a new array every render and
  // invalidate the memo below on each one.
  const candidates = useMemo(() => core.candidates.data ?? [], [core.candidates.data])
  const [selected, setSelected] = useState<string | null>(null)
  const [result, setResult] = useState<Resource<VirtualObservationSimulation> | null>(null)
  const [busy, setBusy] = useState(false)

  const candidate = useMemo<TideCandidate | null>(
    () => candidates.find((c) => c.candidate_id === selected) ?? candidates[0] ?? null,
    [candidates, selected],
  )

  const run = useCallback(async () => {
    if (!candidate) return
    setBusy(true)
    setResult({ data: null, reason: null, loading: true })
    try {
      const payload = await runVirtualObservation({
        location_id: candidate.location_id,
        variable: candidate.variable,
        depth_m: candidate.depth_m,
        observation_type: candidate.observation_type,
      })
      const data = (payload as { data?: VirtualObservationSimulation } | null)?.data
      setResult(
        data
          ? { data, reason: null, loading: false }
          : {
              data: null,
              loading: false,
              reason: 'The simulation endpoint answered without a result — nothing is displayed in its place.',
            },
      )
    } catch {
      setResult({
        data: null,
        loading: false,
        reason: 'The what-if engine did not respond. No simulated values are shown.',
      })
    } finally {
      setBusy(false)
    }
  }, [candidate])

  return (
    <MissionSection
      id="simulate"
      index="09"
      eyebrow="WHAT-IF SIMULATION"
      title="Ask the counterfactual — and keep it labelled."
      sub="Pick a candidate, ask what a measurement there would do to the state of knowledge, and watch uncertainty, risk and confidence move. The reading is generated by the engine, never collected by a sensor, and never written to the ledger."
      aside={<SimulatedTag />}
    >
      <Reveal className="mi-sim">
        <div className="mi-sim__controls">
          <span className="oh-eyebrow">CHOOSE A SITE TO SIMULATE</span>
          {candidates.length === 0 ? (
            <p className="mi-sim__none">
              {core.candidates.loading
                ? 'Waiting for a candidate ranking…'
                : (core.candidates.reason ?? 'No candidate is available to simulate.')}
            </p>
          ) : (
            <>
              <div className="mi-sim__pills" role="group" aria-label="Candidate to simulate">
                {candidates.slice(0, 4).map((c) => (
                  <button
                    key={c.candidate_id}
                    type="button"
                    className={`mi-pill${candidate?.candidate_id === c.candidate_id ? ' is-on' : ''}`}
                    onClick={() => setSelected(c.candidate_id)}
                    aria-pressed={candidate?.candidate_id === c.candidate_id}
                  >
                    {c.location}
                    <em>{c.variable}</em>
                  </button>
                ))}
              </div>
              <button
                type="button"
                className="oh-btn oh-btn--solid"
                onClick={() => void run()}
                disabled={busy}
              >
                <FlaskConical size={15} />
                {busy ? 'SIMULATING…' : 'RUN WHAT-IF'}
              </button>
              <p className="mi-sim__warn">
                <SimulatedTag />
                <span>
                  This endpoint computes a deterministic what-if. The result is never persisted and never
                  counts as an observation.
                </span>
              </p>
            </>
          )}
        </div>

        <div className="mi-sim__out">
          {!result ? (
            <p className="mi-sim__placeholder">
              Run the simulation to see how this candidate would change the state of knowledge.
            </p>
          ) : result.loading ? (
            <Loading label="re-scoring the twin with a hypothetical reading" />
          ) : !result.data ? (
            <Absence reason={result.reason} />
          ) : (
            <SimResult sim={result.data} />
          )}
        </div>
      </Reveal>
    </MissionSection>
  )
}

function SimResult({ sim }: { sim: VirtualObservationSimulation }) {
  const dU = sim.uncertainty_change
  const improved = dU.delta < 0
  return (
    <div className="mi-simres">
      <div className="mi-simres__head">
        <span className="oh-eyebrow">
          {sim.location} · {sim.variable} · {sim.depth_m} m
        </span>
        <SimulatedTag>SIMULATED READING — NOT MEASURED</SimulatedTag>
      </div>

      <div className="mi-simres__read">
        <b>{formatMetric(sim.simulated_observation.value, 3)}</b>
        <span>
          hypothetical {sim.variable} at {sim.simulated_observation.depth_m} m, quality{' '}
          {formatPercent(sim.simulated_observation.quality)}
        </span>
        <OriginTag status={sim.simulated_observation.status} />
      </div>

      <div className="mi-deltas">
        <Delta
          label="UNCERTAINTY"
          before={dU.before}
          after={dU.after}
          delta={dU.delta}
          goodWhenDown={true}
          improved={improved}
        />
        <Delta
          label="ANOMALY RISK"
          before={sim.risk_change.before}
          after={sim.risk_change.after}
          delta={sim.risk_change.delta}
          goodWhenDown={true}
        />
        <Delta
          label="CONFIDENCE"
          before={sim.confidence_change.before}
          after={sim.confidence_change.after}
          delta={sim.confidence_change.delta}
          goodWhenDown={false}
        />
      </div>

      <div className={`mi-simres__decision${sim.decision_changed ? ' is-changed' : ''}`}>
        <span className="oh-eyebrow">DECISION</span>
        <p>
          {sim.before.decision.replace(/_/g, ' ').toLowerCase()} →{' '}
          <b>{sim.after.decision.replace(/_/g, ' ').toLowerCase()}</b>
        </p>
        <span>
          {sim.decision_result === 'DECISION_CHANGED'
            ? 'The hypothetical reading changes the recommended action.'
            : 'The hypothetical reading does not change the recommended action.'}
        </span>
      </div>

      {sim.notes.length ? (
        <ul className="mi-simres__notes">
          {sim.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      ) : null}
      <p className="mi-simres__method">method: {sim.method}</p>
    </div>
  )
}

function Delta({
  label,
  before,
  after,
  delta,
  goodWhenDown,
  improved,
}: {
  label: string
  before: number
  after: number
  delta: number
  goodWhenDown: boolean
  improved?: boolean
}) {
  const good = improved ?? (goodWhenDown ? delta < 0 : delta > 0)
  const Icon = delta < 0 ? TrendingDown : TrendingUp
  return (
    <div className="mi-delta" data-good={good ? 'true' : 'false'}>
      <span className="oh-eyebrow">{label}</span>
      <div className="mi-delta__nums">
        <span>{formatMetric(before, 3)}</span>
        <Icon size={13} aria-hidden="true" />
        <b>{formatMetric(after, 3)}</b>
      </div>
      <span className="mi-delta__tag">Δ {formatMetric(delta, 3)}</span>
    </div>
  )
}

/* ================================================================== */
/* 10 — Decision Replay                                                */
/* ================================================================== */

export function Replay() {
  const { ref, inView } = useInView<HTMLDivElement>({ margin: '0px 0px -20% 0px' })
  const replay = useDecisionReplay(inView)
  const data = replay.data

  return (
    <section className="mi-section" id="replay" aria-labelledby="replay-title" ref={ref}>
      <Reveal className="mi-section__head">
        <div className="mi-section__marker">
          <span className="mi-section__num">10</span>
          <span className="mi-section__rule" aria-hidden="true" />
          <span className="oh-eyebrow">DECISION REPLAY</span>
        </div>
        <div className="mi-section__headrow">
          <div className="mi-section__headtext">
            <h2 className="oh-title" id="replay-title">
              The same event, walked twice.
            </h2>
            <p className="oh-sub">
              A replay is read-only. It recomputes what the twin would have concluded with the model
              alone, and again with TIDE's evidence in the loop — then shows exactly which step moved.
              Nothing is written and no historical event is altered.
            </p>
          </div>
        </div>
      </Reveal>

      <div className="mi-section__body">
        {replay.loading ? (
          <Loading label="composing the replay" />
        ) : !data ? (
          <Absence reason={replay.reason} />
        ) : (
          <ReplayBody data={data} />
        )}
      </div>
    </section>
  )
}

function ReplayBody({ data }: { data: DecisionReplay }) {
  const cmp = data.comparison
  const decision = data.decision
  const validation = data.validation

  return (
    <>
      <Reveal className="mi-replay__head">
        <div className="mi-replay__id">
          <span className="oh-eyebrow">
            <History size={12} /> EVENT {data.event_id}
          </span>
          <b>
            {data.location} · {data.variable} · {data.depth_m} m
          </b>
          <span className="mi-replay__meta">
            detected {String(data.event?.event_type ?? 'event').replace(/_/g, ' ').toLowerCase()}
          </span>
        </div>
        <Link className="oh-btn oh-btn--ghost" to="/tide/replay">
          FULL REPLAY <ArrowRight size={14} />
        </Link>
      </Reveal>

      <Reveal className="mi-replay__modes" delay={0.08}>
        <div className="mi-mode" data-mode="model">
          <span className="oh-eyebrow">MODEL ONLY</span>
          <p className="mi-mode__decision">{data.model_only.decision.replace(/_/g, ' ').toLowerCase()}</p>
          <ul>
            <li>
              uncertainty <b>{formatMetric(data.model_only.uncertainty, 3)}</b>
            </li>
            <li>
              confidence <b>{formatPercent(data.model_only.confidence)}</b>
            </li>
            <li>
              evidence records <b>{data.model_only.evidence_count}</b>
            </li>
            <li>
              observation used{' '}
              <b>{data.model_only.observation_available ? 'yes' : 'no'}</b>
            </li>
          </ul>
        </div>
        <div className="mi-replay__vs" aria-hidden="true">
          vs
        </div>
        <div className="mi-mode" data-mode="tide">
          <span className="oh-eyebrow">TIDE ASSISTED</span>
          <p className="mi-mode__decision">{data.tide_assisted.decision.replace(/_/g, ' ').toLowerCase()}</p>
          <ul>
            <li>
              uncertainty <b>{formatMetric(data.tide_assisted.uncertainty, 3)}</b>
            </li>
            <li>
              confidence <b>{formatPercent(data.tide_assisted.confidence)}</b>
            </li>
            <li>
              evidence records <b>{data.tide_assisted.evidence_count}</b>
            </li>
            <li>
              observation used{' '}
              <b>{data.tide_assisted.observation_available ? 'yes' : 'no'}</b>
            </li>
          </ul>
        </div>
      </Reveal>

      <Reveal className="mi-replay__cmp" delay={0.14}>
        {(
          [
            ['UNCERTAINTY', cmp.uncertainty],
            ['CONFIDENCE', cmp.confidence],
            ['ANOMALY RISK', cmp.anomaly_risk],
            ['DETECTION TIME', cmp.detection_time],
          ] as const
        ).map(([label, metric]) => (
          <div className="mi-cmp" key={label}>
            <span className="oh-eyebrow">{label}</span>
            <div className="mi-cmp__pair">
              <span>
                model <b>{metric.model_only ?? '—'}</b>
              </span>
              <span>
                tide <b>{metric.tide_assisted ?? '—'}</b>
              </span>
            </div>
            <span className="mi-cmp__delta" data-moved={metric.changed ? 'true' : 'false'}>
              Δ {metric.delta ?? '—'}
            </span>
            {metric.detail ? <i>{metric.detail}</i> : null}
          </div>
        ))}
      </Reveal>

      <Reveal className="mi-replay__decision" delay={0.2}>
        <span className="oh-eyebrow">DECISION DELTA</span>
        <p className={decision.decision_changed ? 'is-changed' : ''}>
          {decision.before.replace(/_/g, ' ').toLowerCase()} →{' '}
          <b>{decision.after.replace(/_/g, ' ').toLowerCase()}</b>
        </p>
        <p className="mi-replay__why">{decision.explanation}</p>
        {decision.why.length ? (
          <ul className="mi-replay__reasons">
            {decision.why.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        ) : null}
      </Reveal>

      {!validation.available ? (
        <Reveal className="mi-replay__validation" delay={0.26}>
          <span className="oh-eyebrow">OUT-OF-SAMPLE CHECK</span>
          <Absence reason={validation.message} compact />
        </Reveal>
      ) : (
        <Reveal className="mi-replay__validation" delay={0.26}>
          <span className="oh-eyebrow">OUT-OF-SAMPLE CHECK</span>
          <p>
            {validation.location} · {validation.variable} at {validation.depth_m} m
          </p>
          <div className="mi-cmp__pair">
            <span>
              model-only predicted <b>{formatMetric(validation.model_only.predicted, 3)}</b>
            </span>
            <span>
              observed <b>{formatMetric(validation.tide_assisted.observed, 3)}</b>
            </span>
            <span>
              difference <b>{formatMetric(validation.tide_assisted.difference, 3)}</b>
            </span>
          </div>
          <Caveat>
            A single held-out case is a sanity check, not a validation set. It is reported because it
            is available, not because it settles the question.
          </Caveat>
        </Reveal>
      )}

      {data.notes.length ? (
        <Reveal className="mi-replay__notes" delay={0.3}>
          <ul>
            {data.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
          <p className="mi-replay__method">
            method: {data.method} <SchematicTag compact>READ-ONLY RECOMPUTATION</SchematicTag>
          </p>
        </Reveal>
      ) : null}
    </>
  )
}
