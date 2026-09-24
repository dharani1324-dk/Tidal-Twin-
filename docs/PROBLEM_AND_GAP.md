# Problem and Gap

> The system-level decision question this project is built around, and the gap
> it addresses. This document does not claim that existing scientific systems
> are incapable of these functions.

## 1. Context

Coastal management, fisheries safety, and marine operations depend on an
understanding of the ocean that is derived from two imperfect things: **models**
(numerical or AI estimates of ocean state) and **observations** (in-situ and
remote measurements). The two rarely agree perfectly. The disagreement, its
persistence, and what to do about it are the practical problem.

An observation system typically makes four things possible:

1. **Observe** ocean conditions (temperature, waves, currents, …).
2. **Visualise** multidimensional ocean data across space and time (4D).
3. **Detect anomalies** and investigate events.
4. **Compare model and observations** to characterise disagreement.

These capabilities exist widely in ocean science and operational
oceanography. TidalTwin implements its own versions of them.

## 2. The additional decision question

Beyond those four capabilities, TidalTwin is organised around a further
decision-support question:

> **Given uncertainty, model–observation disagreement, data gaps, event
> persistence, decision impact, and observation cost — where should the next
> observation be prioritised?**

This is a *resource-allocation* question. Observations are expensive and finite;
not every location, variable or depth can be sampled continuously. The question
of *where to look next*, given what is already known and how much each option
costs, is the central decision-support problem the project addresses.

## 3. The gap this project addresses

The gap is one of **integration and decision focus**, not of missing science:

| Capability | Typically available | TidalTwin adds |
|-----------|---------------------|----------------|
| Observation & visualisation | Yes (many systems) | A single integrated twin |
| Anomaly detection & event naming | Yes | Detection bound to events and Event DNA |
| Model–observation comparison | Yes | Explainable confidence + cautious verdicts |
| Next-observation prioritisation | Domain-dependent | An explicit, transparent formula + baselines |

Existing monitoring and intelligence workflows can *observe, visualise, detect
and compare*. The project integrates these capabilities into a unified
**decision-aware observation loop** whose explicit output is a prioritised next
observation, together with the evidence and trust status behind it.

## 4. Why the question is hard

- **Uncertainty is not uniform.** Some locations/variables are well observed;
  others have sparse, stale or absent coverage.
- **Disagreement is ambiguous.** A model–observation mismatch could indicate a
  sensor issue, a model issue, or a real unrepresented phenomenon. The system
  must not pretend to know which.
- **Data gaps distort confidence.** Absence of data is itself information, and
  must be represented, not silently treated as "no problem".
- **Events persist or decay.** A short spike and a long, coherent anomaly carry
  different decision weight.
- **Observations cost time and money.** The value of a measurement depends on
  its cost, and different platforms have very different costs.
- **Decisions must be defensible.** A recommendation that cannot be inspected is
  hard to trust.

## 5. Scope and non-goals

**In scope (implemented):** a 4D digital twin, model–observation comparison,
anomaly/event detection, Event DNA, evidence-carrying prioritisation, cautious
verdicts, what-if simulation, decision replay, and an honest validation and
benchmark framework.

**Not claimed:** scientifically validated optimal control; prediction accuracy;
verified causal attribution of sensor/model/phenomenon; operational deployment
performance. This project does not claim that existing scientific systems cannot
perform observation prioritisation — many can. It claims to implement a
specific, transparent, inspectable integration and to report its behaviour
honestly.
