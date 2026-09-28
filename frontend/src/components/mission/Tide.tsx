/**
 * Mission Intro — Sections 06 & 07
 * ================================
 * 06  TIDE: the five factors, the formula, and the live ranking.
 * 07  The data-honesty contract: the full provenance vocabulary, and what
 *     happens when the system genuinely does not know.
 *
 * The formula and the cost table below are the project's own
 * `modules/ai/tide/scoring.py`, reproduced so the ranking is auditable rather
 * than a black box.
 */
import { Link } from 'react-router-dom'
import { ArrowRight, Calculator, CircleSlash, Scale, Sigma } from 'lucide-react'
import { Absence, Caveat, Loading, MissionSection, OriginTag, Reveal, SchematicTag } from './Primitives'
import { PROVENANCE_STATES, formatMetric, formatPercent } from './missionData'
import type { MissionCore } from './missionData'
import type { TideCandidate } from '../../types/tide'

/* ------------------------------------------------------------------ */
/* 06 — TIDE                                                           */
/* ------------------------------------------------------------------ */

const FACTORS = [
  { key: 'decision_impact', k: 'DECISION IMPACT', d: 'How much a new reading would move the operational call.' },
  { key: 'uncertainty', k: 'UNCERTAINTY', d: 'Disagreement between model and observation, plus evidence age.' },
  { key: 'data_gap', k: 'DATA GAP', d: 'Depth, region or variable that has never been properly sampled.' },
  { key: 'anomaly_persistence', k: 'ANOMALY PERSISTENCE', d: 'Whether the anomaly survives across time and space.' },
  { key: 'observation_cost', k: 'OBSERVATION COST', d: 'Deployed in the denominator — effort discounts the score.' },
] as const

/** `scoring.METHOD_COSTS` — the relative cost the formula divides by. */
const COSTS: Record<string, number> = {
  BUOY: 0.35,
  ARGO_FLOAT: 0.42,
  RESEARCH_VESSEL: 0.92,
  DRONE: 0.28,
  AUTONOMOUS_VEHICLE: 0.62,
  MANUAL_SAMPLE: 0.48,
  VIRTUAL_SENSOR: 0.08,
}

function CandidateRow({ c, rank }: { c: TideCandidate; rank: number }) {
  return (
    <li className="mi-cand">
      <span className="mi-cand__rank">{String(rank).padStart(2, '0')}</span>
      <div className="mi-cand__main">
        <div className="mi-cand__top">
          <b>{c.location}</b>
          <span className="mi-cand__var">
            {c.variable} · {c.depth_m} m
          </span>
          <OriginTag status={c.status} />
        </div>
        <p className="mi-cand__reason">{c.reason}</p>
        <div className="mi-cand__bars">
          {FACTORS.map((f) => {
            const raw = c[f.key] as number
            const value = Number.isFinite(raw) ? raw : 0
            return (
              <div className="mi-factor" key={f.key} title={`${f.k}: ${value.toFixed(3)}`}>
                <span>{f.k}</span>
                <i data-invert={f.key === 'observation_cost' ? 'true' : 'false'}>
                  <b style={{ width: `${Math.min(100, Math.max(0, value * 100)).toFixed(1)}%` }} />
                </i>
                <em>{value.toFixed(2)}</em>
              </div>
            )
          })}
        </div>
        <div className="mi-cand__foot">
          <span>
            value <b>{formatMetric(c.observation_value, 4)}</b>
          </span>
          <span>
            exp. uncertainty reduction <b>{formatMetric(c.expected_uncertainty_reduction, 4)}</b>
          </span>
          <span>
            confidence <b>{formatPercent(c.confidence)}</b>
          </span>
          <span>
            via <b>{c.observation_type.replace(/_/g, ' ')}</b>
          </span>
          <span className="mi-cand__decision">{c.affected_decision.replace(/_/g, ' ')}</span>
        </div>
        {c.limitations.length ? (
          <p className="mi-cand__limits">
            <CircleSlash size={12} aria-hidden="true" /> {c.limitations.join(' · ')}
          </p>
        ) : null}
      </div>
    </li>
  )
}

export function TideSection({ core }: { core: MissionCore }) {
  const candidates = core.candidates.data ?? []
  const lead = candidates[0]

  return (
    <MissionSection
      id="tide"
      index="06"
      eyebrow="TIDE · TRUST-AWARE INFORMATION FOR DECISION AND EXPLORATION"
      title="Five factors. One auditable number. No hidden model."
      sub="TIDE asks a different question: not only what is happening, but where the next observation matters most. Trust-aware Information for Decision and Exploration is a transparent heuristic, not a learned ranker; every candidate carries the evidence and limitations behind its score."
      aside={
        core.candidates.loading ? (
          <Loading label="scoring candidates" />
        ) : (
          <span className="oh-badge oh-badge--teal">{candidates.length} CANDIDATES RANKED</span>
        )
      }
    >
      <Reveal className="mi-formula">
        <div className="mi-formula__top">
          <span className="oh-eyebrow">
            <Calculator size={12} /> OBSERVATION VALUE
          </span>
          <span className="mi-formula__tag">ALGORITHM v1.0 · scoring.py · epsilon 0.05</span>
        </div>
        <p className="mi-formula__eq">
          <span className="mi-formula__num">value</span>
          <span className="mi-formula__op">=</span>
          <span className="mi-formula__frac">
            <span className="mi-formula__prod">
              decision_impact × uncertainty × data_gap × anomaly_persistence
            </span>
            <span className="mi-formula__bar" aria-hidden="true" />
            <span className="mi-formula__den">max( observation_cost , 0.05 )</span>
          </span>
        </p>
        <Caveat>
          The 0.05 floor is a guard: without it, a zero-cost candidate would divide by zero and
          dominate every ranking. Cost is a discount, not a bonus.
        </Caveat>
      </Reveal>

      <div className="mi-factors">
        {FACTORS.map((f, i) => {
          const leadValue = lead ? (lead[f.key] as number) : null
          return (
            <Reveal className="mi-factorcard" key={f.key} delay={i * 0.06}>
              <b>{f.k}</b>
              <p>{f.d}</p>
              <span className="mi-factorcard__val">
                {leadValue == null || !Number.isFinite(leadValue) ? (
                  '—'
                ) : (
                  <>
                    lead candidate <em>{leadValue.toFixed(2)}</em>
                  </>
                )}
              </span>
            </Reveal>
          )
        })}
      </div>

      <Reveal className="mi-costs" delay={0.3}>
        <span className="oh-eyebrow">
          <Scale size={12} /> RELATIVE COST BY METHOD
        </span>
        <ul>
          {Object.entries(COSTS)
            .sort((a, b) => a[1] - b[1])
            .map(([method, cost]) => (
              <li key={method}>
                <i>
                  <b style={{ width: `${(cost * 100).toFixed(0)}%` }} />
                </i>
                <span>{method.replace(/_/g, ' ')}</span>
                <em>{cost.toFixed(2)}</em>
              </li>
            ))}
        </ul>
        <Caveat>
          A cheaper method does not make a site more valuable — it lowers the divisor, which raises the
          score. The trade-off is deliberate and is meant to be argued with.
        </Caveat>
      </Reveal>

      <Reveal className="mi-ranking" delay={0.36}>
        <div className="mi-ranking__head">
          <span className="oh-eyebrow">
            <Sigma size={12} /> LIVE RANKING — /api/v1/tide/candidates
          </span>
          <SchematicTag>SCHEMATIC RANK — NOT A NAVIGATION CHART</SchematicTag>
        </div>

        {core.candidates.loading ? (
          <Loading label="requesting a fresh ranking" />
        ) : !candidates.length ? (
          <Absence reason={core.candidates.reason} />
        ) : (
          <>
            <ul className="mi-cands">
              {candidates.slice(0, 4).map((c, i) => (
                <CandidateRow c={c} rank={i + 1} key={c.candidate_id} />
              ))}
            </ul>
            {candidates.length > 4 ? (
              <Caveat>
                {candidates.length} candidates were scored; the top {Math.min(4, candidates.length)} are
                shown. The Command Center holds the full pool with per-candidate explanations.
              </Caveat>
            ) : null}
            <div className="mi-ranking__foot">
              <Link className="oh-btn oh-btn--solid" to="/tide">
                OPEN THE TIDE COMMAND CENTER <ArrowRight size={14} />
              </Link>
              <p>
                Ranking is reproducible: fixed dataset version, fixed seed, fixed budget. Re-running it
                gives the same order.
              </p>
            </div>
          </>
        )}
      </Reveal>
    </MissionSection>
  )
}

/* ------------------------------------------------------------------ */
/* 07 — The data-honesty contract                                      */
/* ------------------------------------------------------------------ */

export function Provenance({ core }: { core: MissionCore }) {
  const ledger = core.demo.data

  return (
    <MissionSection
      id="honesty"
      index="07"
      eyebrow="THE DATA-HONESTY CONTRACT"
      title="When data doesn't exist, return a structured absence with a reason — never a plausible-looking number."
      sub="This is the single rule every TidalTwin surface obeys. It is also the hardest one to keep, because a blank looks like a bug and a confident wrong number looks like a product."
    >
      <Reveal className="mi-absence-demo">
        <div className="mi-absence-flow" aria-label="Missing data handling">
          <span>NO DATA</span><b aria-hidden="true">↓</b><span>STRUCTURED ABSENCE</span><b aria-hidden="true">↓</b><span>REASON</span>
          <i>NO DATA <s aria-hidden="true">→</s> FAKE NUMBER</i>
        </div>
        <div className="mi-absence-demo__side">
          <span className="oh-eyebrow">THE ONLY PERMITTED SHAPE FOR “I DON'T KNOW”</span>
          <pre className="mi-code" aria-label="Structured absence response shape">
{`{
  "available": false,
  "reason": "No observation exists
              for this site, depth
              and variable."
}`}
          </pre>
          <p className="mi-absence-demo__note">
            This is a first-class response. The UI renders it as a labelled absence, the API returns it
            with a machine-readable code, and the ranking engine treats the site as unranked rather
            than assuming a neutral value.
          </p>
        </div>

        <div className="mi-absence-demo__states">
          <span className="oh-eyebrow">PROVENANCE VOCABULARY · {PROVENANCE_STATES.length} STATES</span>
          <ul className="mi-states">
            {PROVENANCE_STATES.map((s) => (
              <li key={s.status}>
                <OriginTag status={s.status} title={s.means} />
                <span>{s.means}</span>
              </li>
            ))}
          </ul>
          <Caveat tone="edge">
            SIMULATED is never blended into an aggregate alongside REAL. The observation ledger keeps
            them counted separately, which is why the headline figures on this page are reported as a
            pair rather than a single number.
          </Caveat>
        </div>
      </Reveal>

      <Reveal className="mi-ledger" delay={0.12}>
        <div className="mi-ledger__head">
          <span className="oh-eyebrow">OBSERVATION LEDGER · COUNTED BY ORIGIN</span>
          {core.demo.loading ? <Loading label="counting" /> : null}
        </div>
        {core.demo.loading ? null : !ledger ? (
          <Absence reason={core.demo.reason} />
        ) : (
          <div className="mi-ledger__grid">
            <div className="mi-ledger__cell mi-ledger__cell--total">
              <b>{ledger.total_observations}</b>
              <span>TOTAL ROWS</span>
            </div>
            <div className="mi-ledger__cell">
              <b>{ledger.real_observations}</b>
              <span>REAL</span>
            </div>
            <div className="mi-ledger__cell">
              <b>{ledger.historical_records ?? '—'}</b>
              <span>HISTORICAL</span>
            </div>
            <div className="mi-ledger__cell">
              <b>{ledger.model_derived_records ?? '—'}</b>
              <span>MODEL DERIVED</span>
            </div>
            <div className="mi-ledger__cell mi-ledger__cell--sim">
              <b>{ledger.simulated_observations}</b>
              <span>SIMULATED</span>
            </div>
            <div className="mi-ledger__cell">
              <b>{ledger.detected_events}</b>
              <span>DETECTED EVENTS</span>
            </div>
          </div>
        )}
        {ledger?.notes?.length ? <Caveat>{ledger.notes.join(' ')}</Caveat> : null}
      </Reveal>
    </MissionSection>
  )
}
