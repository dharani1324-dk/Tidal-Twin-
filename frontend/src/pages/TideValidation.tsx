import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  BarChart3, Loader2, ShieldCheck, ShieldAlert, Database, FlaskConical,
  ChevronRight, AlertTriangle, CheckCircle2, XCircle, Activity, Info, Target,
} from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, CartesianGrid } from 'recharts'
import TrustBadge from '../components/workspace/TrustBadge'
import { fetchTideValidationStatus, fetchTideBenchmarks } from '../api/client'
import type {
  TideValidationStatus, TideBenchmarkReport, TideBenchmarkRow,
} from '../types/tide'
import './TideValidation.css'

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: (i: number) => ({
    opacity: 1, y: 0,
    transition: { delay: i * 0.06, duration: 0.45, ease: 'easeOut' as const },
  }),
}

const STRATEGY_COLOR: Record<string, string> = {
  RANDOM: '#94a3b8',
  UNIFORM: '#38bdf8',
  UNCERTAINTY_ONLY: '#22d3ee',
  ANOMALY_ONLY: '#f43f5e',
  DATA_GAP_ONLY: '#f59e0b',
  TIDE: '#10b981',
}

const BUDGETS = [1, 3, 5, 10]

const fmt = (v: number | null | undefined, d = 3): string => (v == null ? '—' : v.toFixed(d))
const pct = (v: number | null | undefined): string => (v == null ? '—' : `${(v * 100).toFixed(0)}%`)

export default function TideValidation() {
  const navigate = useNavigate()
  const [status, setStatus] = useState<TideValidationStatus | null>(null)
  const [statusError, setStatusError] = useState<string | null>(null)
  const [report, setReport] = useState<TideBenchmarkReport | null>(null)
  const [reportLoading, setReportLoading] = useState(true)
  const [budget, setBudget] = useState(1)
  const [selected, setSelected] = useState<TideBenchmarkRow | null>(null)

  useEffect(() => {
    let alive = true
    fetchTideValidationStatus()
      .then((d) => { if (alive) setStatus(d?.data ?? null) })
      .catch(() => { if (alive) setStatusError('Validation status is unavailable right now.') })
    return () => { alive = false }
  }, [])

  useEffect(() => {
    let alive = true
    setReportLoading(true)
    fetchTideBenchmarks({ budget })
      .then((d) => { if (alive) setReport(d?.data ?? null) })
      .catch(() => { if (alive) setReport(null) })
      .finally(() => { if (alive) setReportLoading(false) })
    return () => { alive = false }
  }, [budget])

  const chartData = useMemo(
    () => (report?.aggregates ?? []).map((a) => ({
      strategy: a.strategy,
      reduction: a.uncertainty_reduction.mean ?? null,
      N: a.uncertainty_reduction.N,
      status: a.uncertainty_reduction.status ?? null,
    })),
    [report],
  )

  return (
    <div className="page tidev-page">
      <motion.div variants={fadeUp} initial="hidden" animate="show" custom={0} className="page-header">
        <div>
          <h1 className="page-title text-gradient">TIDE Validation Center</h1>
          <p className="page-subtitle">
            Phase 8 — scientific validation status, baseline benchmarks and reliability evidence for TIDE.
            TIDE is <b>tested and benchmarked, not scientifically validated</b>.
          </p>
        </div>
        <div className="tidev-header-actions">
          <button className="tide-btn" onClick={() => navigate('/tide')}>
            <Target size={14} /> TIDE Command Center
          </button>
          <button className="tide-btn" onClick={() => navigate('/tide/replay')}>
            <Activity size={14} /> Decision Replay
          </button>
        </div>
      </motion.div>

      {statusError && (
        <div className="glass-card tidev-banner tidev-banner-warn">
          <ShieldAlert size={16} /> {statusError}
        </div>
      )}

      {!status && !statusError && (
        <div className="glass-card tidev-loading"><Loader2 className="spin" size={18} /> Loading validation status…</div>
      )}

      {status && (
        <>
          <motion.div variants={fadeUp} initial="hidden" animate="show" custom={1} className="glass-card tidev-callout">
            <ShieldCheck size={18} />
            <div>
              <b>{status.scientific_boundary.statement}</b>
              <p>
                Algorithm version <code>{status.algorithm_version}</code> · Dataset{' '}
                <code>{status.dataset.id}</code> / <code>{status.dataset.version}</code>
              </p>
            </div>
          </motion.div>

          <motion.div variants={fadeUp} initial="hidden" animate="show" custom={2} className="tidev-grid">
            <div className="glass-card tidev-maturity">
              <h3><FlaskConical size={15} /> Implementation maturity</h3>
              {(['IMPLEMENTED', 'DEMONSTRATED', 'TESTED'] as const).map((key) => (
                <div className="tidev-maturity-block" key={key}>
                  <span className={`tidev-maturity-tag tidev-${key.toLowerCase()}`}>{key}</span>
                  <ul>
                    {status.maturity[key].map((item) => <li key={item}>{item}</li>)}
                  </ul>
                </div>
              ))}
              <div className="tidev-maturity-block">
                <span className="tidev-maturity-tag tidev-notvalidated">EMPIRICALLY VALIDATED</span>
                <p className="tidev-empty">NONE — {status.maturity.empirical_note}</p>
              </div>
            </div>

            <div className="tidev-side">
              <div className="glass-card">
                <h3><Database size={15} /> Dataset</h3>
                <TrustBadge status="MODEL_DERIVED" title="TIDE inputs come from the live store + model-derived candidates" />
                <ul className="tidev-kv">
                  <li><span>Locations</span><b>{status.dataset.locations}</b></li>
                  <li><span>Observations</span><b>{status.dataset.observations}</b></li>
                  <li><span>System-derived events</span><b>{status.dataset.events}</b></li>
                  <li><span>Candidate pool ({status.candidate_pool.variable})</span><b>{status.candidate_pool.size}</b></li>
                  <li><span>Non-zero observation value</span><b>{status.candidate_pool.nonzero_observation_value}</b></li>
                </ul>
                <p className="tidev-note">{status.dataset.status}</p>
              </div>

              <div className="glass-card tidev-groundtruth">
                <h3><AlertTriangle size={15} /> Ground truth</h3>
                <span className="tidev-na">GROUND TRUTH UNAVAILABLE</span>
                <p className="tidev-note">{status.ground_truth.reason}</p>
                <ul className="tidev-kv">
                  <li><span>False alarm</span><b>{status.ground_truth.false_alarm}</b></li>
                  <li><span>Missed event</span><b>{status.ground_truth.missed_event}</b></li>
                </ul>
              </div>
            </div>
          </motion.div>

          <motion.div variants={fadeUp} initial="hidden" animate="show" custom={3} className="glass-card tidev-boundary">
            <h3><Info size={15} /> Scientific claim boundary</h3>
            <div className="tidev-boundary-cols">
              <div>
                <span className="tidev-can"><CheckCircle2 size={13} /> What this validation CAN show</span>
                <ul>{status.scientific_boundary.can_show.map((c) => <li key={c}>{c}</li>)}</ul>
              </div>
              <div>
                <span className="tidev-cannot"><XCircle size={13} /> What it CANNOT show</span>
                <ul>{status.scientific_boundary.cannot_show.map((c) => <li key={c}>{c}</li>)}</ul>
              </div>
            </div>
          </motion.div>

          <motion.div variants={fadeUp} initial="hidden" animate="show" custom={4} className="tidev-grid">
            <div className="glass-card">
              <h3><BarChart3 size={15} /> {status.sensitivity.label}</h3>
              <p className="tidev-note">{status.sensitivity.caveat}</p>
              <table className="tidev-table">
                <thead><tr><th>Factor</th><th>Low</th><th>High</th><th>Direction</th><th>Consistent</th></tr></thead>
                <tbody>
                  {status.sensitivity.factors.map((f) => (
                    <tr key={f.factor}>
                      <td>{f.factor.replace(/_/g, ' ')}</td>
                      <td>{fmt(f.low_score)}</td>
                      <td>{fmt(f.high_score)}</td>
                      <td>{f.expected_direction}</td>
                      <td>{f.consistent ? <CheckCircle2 size={14} color="#10b981" /> : <XCircle size={14} color="#f43f5e" />}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="glass-card">
              <h3><ShieldCheck size={15} /> {status.edge_cases.label}</h3>
              <p className="tidev-note">
                {status.edge_cases.all_finite
                  ? 'All boundary inputs produce finite, non-negative scores.'
                  : 'At least one boundary input produced an invalid score.'}
              </p>
              <table className="tidev-table">
                <thead><tr><th>Input case</th><th>Score</th><th>Finite</th></tr></thead>
                <tbody>
                  {status.edge_cases.results.map((r) => (
                    <tr key={r.case}>
                      <td>{r.case.replace(/_/g, ' ')}</td>
                      <td>{fmt(r.observation_value)}</td>
                      <td>{r.finite_nonnegative ? <CheckCircle2 size={14} color="#10b981" /> : <XCircle size={14} color="#f43f5e" />}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </motion.div>

          <motion.div variants={fadeUp} initial="hidden" animate="show" custom={5} className="glass-card">
            <h3><Activity size={15} /> Reproducibility</h3>
            <div className="tidev-chips">
              <span className="tidev-chip">algorithm <b>{status.reproducibility.algorithm_version}</b></span>
              <span className="tidev-chip">dataset <b>{status.reproducibility.dataset_id}</b></span>
              <span className="tidev-chip">version <b>{status.reproducibility.dataset_version}</b></span>
              <span className="tidev-chip">seed <b>{status.reproducibility.default_seed}</b></span>
              <span className="tidev-chip">budget <b>{status.reproducibility.default_budget}</b></span>
            </div>
            <p className="tidev-note">Cost model: {status.reproducibility.cost_assumption}</p>
          </motion.div>

          <motion.div variants={fadeUp} initial="hidden" animate="show" custom={6} className="glass-card">
            <h3><AlertTriangle size={15} /> Known limitations</h3>
            <ul className="tidev-limits">{status.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
          </motion.div>
        </>
      )}

      <motion.div variants={fadeUp} initial="hidden" animate="show" custom={7} className="glass-card tidev-bench">
        <div className="tidev-bench-head">
          <h3><BarChart3 size={15} /> Benchmark — observed uncertainty reduction by strategy</h3>
          <div className="tidev-budget">
            <span>Observation budget</span>
            {BUDGETS.map((b) => (
              <button
                key={b}
                className={`tidev-budget-pill ${budget === b ? 'tidev-budget-on' : ''}`}
                onClick={() => setBudget(b)}
              >
                {b}
              </button>
            ))}
          </div>
        </div>

        {reportLoading && <div className="tidev-loading"><Loader2 className="spin" size={16} /> Running benchmark…</div>}

        {!reportLoading && report && (
          <>
            <div className="tidev-bench-tags">
              <span className="tidev-na">SIMULATED OBSERVATION — DEMONSTRATION ONLY</span>
              <span className="tidev-chip">{report.configuration.cost_assumption}</span>
              <span className="tidev-chip">seed <b>{report.configuration.seed}</b></span>
              <span className="tidev-chip">cases <b>{report.configuration.cases.length}</b></span>
              <span className="tidev-chip">selections <b>{report.rows.length}</b></span>
            </div>

            {report.selection.pool_is_degenerate && (
              <div className="tidev-banner tidev-banner-warn">
                <AlertTriangle size={15} /> {report.selection.note}
              </div>
            )}

            <div className="tidev-chart">
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="strategy" tick={{ fill: '#94a3b8', fontSize: 11 }} interval={0} angle={-12} textAnchor="end" height={54} />
                  <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} tickFormatter={(v) => `${(Number(v) * 100).toFixed(0)}%`} />
                  <Tooltip
                    contentStyle={{ background: '#0b1120', border: '1px solid #1e293b', borderRadius: 10 }}
                    formatter={(value) => [pct(Number(value)), 'Mean uncertainty reduction']}
                    labelFormatter={(label) => String(label)}
                  />
                  <Bar dataKey="reduction" radius={[6, 6, 0, 0]}>
                    {chartData.map((d) => <Cell key={d.strategy} fill={STRATEGY_COLOR[d.strategy] ?? '#22d3ee'} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            <table className="tidev-table tidev-agg-table">
              <thead>
                <tr><th>Strategy</th><th>N</th><th>Mean reduction</th><th>Median</th><th>Min</th><th>Max</th><th>Decision changes</th><th>Validation error</th><th>Detection time</th></tr>
              </thead>
              <tbody>
                {report.aggregates.map((a) => (
                  <tr key={a.strategy}>
                    <td>
                      <span className="tidev-strategy-dot" style={{ background: STRATEGY_COLOR[a.strategy] ?? '#22d3ee' }} />
                      {a.strategy}
                    </td>
                    <td>{a.N}</td>
                    <td>{a.uncertainty_reduction.mean != null ? pct(a.uncertainty_reduction.mean) : <em>INSUFFICIENT DATA</em>}</td>
                    <td>{a.uncertainty_reduction.median != null ? pct(a.uncertainty_reduction.median) : '—'}</td>
                    <td>{a.uncertainty_reduction.min != null ? pct(a.uncertainty_reduction.min) : '—'}</td>
                    <td>{a.uncertainty_reduction.max != null ? pct(a.uncertainty_reduction.max) : '—'}</td>
                    <td>{a.decision_changes} / {a.N}</td>
                    <td>{a.validation_error.status ?? pct(a.validation_error.mean)}</td>
                    <td>{a.detection_time.status ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="tidev-note">
              No winner is declared. Aggregates are shown with their sample size (N); values below the minimum
              sample are reported as INSUFFICIENT DATA rather than averaged.
            </p>

            <h4 className="tidev-subhead">Event-level inspection — drill down into every selection</h4>
            <div className="tidev-rows">
              <table className="tidev-table">
                <thead>
                  <tr><th>Case</th><th>Strategy</th><th>Selected candidate</th><th>Uncertainty</th><th>Decision</th><th></th></tr>
                </thead>
                <tbody>
                  {report.rows.map((r, i) => (
                    <tr key={`${r.case_id}-${r.strategy}-${i}`} className="tidev-row" onClick={() => setSelected(r)}>
                      <td>{r.case_label}</td>
                      <td>{r.strategy}</td>
                      <td>{r.selected.location} · {r.selected.variable} @ {r.selected.depth_m} m</td>
                      <td>{pct(r.initial_uncertainty)} → {pct(r.final_uncertainty)}</td>
                      <td>{r.decision_before.replace(/_/g, ' ')} → {r.decision_after.replace(/_/g, ' ')}</td>
                      <td><ChevronRight size={14} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {selected && (
              <div className="tidev-drill">
                <div className="tidev-drill-head">
                  <b>{selected.case_label} — {selected.strategy}</b>
                  <button className="tide-btn" onClick={() => setSelected(null)}>Close</button>
                </div>
                <div className="tidev-kv-grid">
                  <div><span>Event</span><b>{selected.event_id ?? 'none (variable case)'}</b></div>
                  <div><span>Location</span><b>{selected.selected.location} (#{selected.selected.location_id})</b></div>
                  <div><span>Depth</span><b>{selected.selected.depth_m} m</b></div>
                  <div><span>Variable</span><b>{selected.selected.variable}</b></div>
                  <div><span>Observation</span><b>{selected.selected.observation_type} · {selected.selected.observation_cost ?? '—'} cost</b></div>
                  <div><span>Evidence count</span><b>{selected.evidence_count}</b></div>
                  <div><span>Initial uncertainty</span><b>{pct(selected.initial_uncertainty)}</b></div>
                  <div><span>Final uncertainty</span><b>{pct(selected.final_uncertainty)}</b></div>
                  <div><span>Uncertainty reduction</span><b>{pct(selected.uncertainty_reduction)} ({pct(selected.relative_uncertainty_reduction)} relative)</b></div>
                  <div><span>Decision change</span><b>{selected.decision_changed ? 'YES' : 'NO'}</b></div>
                  <div><span>Validation error</span><b>{selected.validation_error.available ? fmt(selected.validation_error.absolute_error) : 'NOT AVAILABLE'}</b></div>
                  <div><span>Detection time</span><b>{selected.detection_time.available ? `${selected.detection_time.value_h} h` : 'UNAVAILABLE'}</b></div>
                </div>
                <p className="tidev-note">{selected.validation_error.reason}</p>
                <p className="tidev-note">{selected.detection_time.reason}</p>
                <div className="tidev-chips">
                  <TrustBadge status={selected.data_status.candidate} />
                  <TrustBadge status={selected.data_status.observation} />
                  <span className="tidev-chip">{selected.cost_label}</span>
                </div>
              </div>
            )}
          </>
        )}

        {!reportLoading && !report && (
          <div className="tidev-banner tidev-banner-warn"><AlertTriangle size={15} /> The benchmark report is unavailable right now.</div>
        )}
      </motion.div>
    </div>
  )
}
