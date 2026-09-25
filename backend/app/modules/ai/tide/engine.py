"""Orchestrates existing Twin, Forensics, observations, and APEX into TIDE."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.modules.ai.tide import adapters
from app.modules.ai.tide.scoring import METHOD_COSTS, calculate_observation_value, unit
from app.modules.ai.tide.verdicts import classify_verdict
from app.modules.ai.tide.explanations import confidence_context, decision_context, recommendation_explanation, trace_evidence, verdict_summary
from app.modules.ai.forensics.fingerprint import fingerprint


def _method(platforms: list[str]) -> str:
    text = " ".join(platforms).lower()
    if "argo" in text: return "ARGO_FLOAT"
    if "buoy" in text or "mooring" in text or "wave rider" in text: return "BUOY"
    if "drone" in text or "satellite" in text: return "DRONE"
    if "auv" in text or "glider" in text or "autonomous" in text: return "AUTONOMOUS_VEHICLE"
    if "ship" in text or "vessel" in text: return "RESEARCH_VESSEL"
    return "MANUAL_SAMPLE"


def _level(score: float) -> str:
    return "CRITICAL" if score >= .75 else "HIGH" if score >= .5 else "MEDIUM" if score >= .25 else "LOW"


# ---------------------------------------------------------------------------
# Pure primitives (no database access).
#
# Phase 8 extracts the documented Phase 5 before/after heuristic into these
# module-level functions so the validation/benchmark framework can evaluate a
# candidate outcome WITHOUT re-querying the ranking engine and without
# duplicating any scoring logic.  ``TideEngine.virtual_observation`` uses the
# exact same functions, so the what-if and the benchmark can never diverge.
# ---------------------------------------------------------------------------

def decision_for(decision_impact: float, data_gap: float) -> str:
    """Documented TIDE decision rule (mirrored in replay.DECISION_RULES)."""
    impact = unit(decision_impact)
    gap = unit(data_gap)
    return "INVESTIGATE_ANOMALY" if impact >= .65 else "INCREASE_MONITORING" if gap >= .5 else "CONTINUE_MONITORING"


def calculate_anomaly_risk(candidate: dict, *, support_model: bool) -> float:
    """Anomaly risk from the candidate's disagreement severity + persistence."""
    disagreement = candidate.get("_disagreement", {})
    risk = unit(disagreement.get("severity", 0) * .7 + candidate.get("anomaly_persistence", 0) * .3)
    return unit(risk * (.5 if support_model else .92))


def supports_model(candidate: dict, simulated_value: float | None) -> bool:
    """True when the simulated reading sits within tolerance of the model value."""
    model_value = (candidate.get("_disagreement") or {}).get("model_value")
    return simulated_value is not None and model_value is not None and abs(simulated_value - model_value) <= max(abs(model_value) * .05, .1)


def simulate_candidate(candidate: dict, *, simulated_value: float | None = None,
                       observation_type: str = "VIRTUAL_SENSOR",
                       quality: float = 1.0,
                       fallback_value: float | None = None) -> dict:
    """Deterministic, non-persisted before/after simulation for a ranked candidate.

    Pure: performs no database access and writes nothing.  The simulated reading
    always carries ``SIMULATED`` semantics and every value is derived from the
    candidate's existing factors.  This is the single source of truth for the
    Phase 5 heuristic.
    """
    disagreement = candidate.get("_disagreement", {})
    value = simulated_value
    if value is None:
        value = disagreement.get("observed_value")
        if value is None:
            value = disagreement.get("model_value")
    if value is None:
        value = fallback_value
    value = None if value is None else round(float(value), 3)
    quality = unit(quality)

    surrogate = {k: candidate.get(k) for k in (
        "decision_impact", "uncertainty", "data_gap", "anomaly_persistence", "observation_cost")}
    before = calculate_observation_value(surrogate)
    support = quality >= .5 and supports_model(candidate, value)
    risk_before = calculate_anomaly_risk(candidate, support_model=False)

    effective_reduction = _quality_scaled_uncertainty(surrogate, quality)
    remaining_uncertainty = unit(before["uncertainty"] - effective_reduction)
    remaining_gap = unit(before["data_gap"] * (1 - .55 * quality))
    post_impact = unit(before["decision_impact"] + (.06 if before["data_gap"] >= .5 else 0))
    after = calculate_observation_value({
        "decision_impact": post_impact, "uncertainty": remaining_uncertainty,
        "data_gap": remaining_gap, "anomaly_persistence": before["anomaly_persistence"],
        "observation_cost": METHOD_COSTS.get(observation_type, METHOD_COSTS["VIRTUAL_SENSOR"]),
    })
    confidence_before = unit(candidate.get("confidence", 0))
    confidence_after = unit(confidence_before + quality * (.04 + .03 * (1 - remaining_gap)))
    risk_after = calculate_anomaly_risk(candidate, support_model=support) if quality >= .5 else risk_before
    decision_before = candidate.get("affected_decision") or decision_for(before["decision_impact"], before["data_gap"])
    decision_after = decision_for(after["decision_impact"], after["data_gap"])

    notes = [
        "SIMULATED OBSERVATION - DEMONSTRATION ONLY: this reading was not collected by a real sensor and was not written to the observation store.",
        "The simulated reading is derived from existing TIDE comparison inputs at this location so the what-if remains grounded in real data.",
        "After-state values are a transparent heuristic estimate of the effect a confirmed reading would have; they are not a measured outcome.",
        f"Assumed quality is {quality:.0%}; uncertainty and confidence changes are scaled by this quality setting.",
    ]
    if value is None:
        notes.append("No modelled or observed reference value was available; a simulated value could not be derived.")

    return {
        "simulated_value": value,
        "observation_type": observation_type,
        "before": {
            "uncertainty": before["uncertainty"],
            "anomaly_risk": risk_before,
            "decision": decision_before,
            "confidence": confidence_before,
            "observation_value": before["observation_value"],
            "data_gap": before["data_gap"],
            "decision_impact": before["decision_impact"],
            "anomaly_persistence": before["anomaly_persistence"],
            "observation_cost": before["observation_cost"],
            "expected_uncertainty_reduction": before["expected_uncertainty_reduction"],
        },
        "after": {
            "uncertainty": after["uncertainty"],
            "anomaly_risk": risk_after,
            "decision": decision_after,
            "confidence": confidence_after,
            "observation_value": after["observation_value"],
            "data_gap": after["data_gap"],
            "decision_impact": after["decision_impact"],
            "anomaly_persistence": after["anomaly_persistence"],
            "observation_cost": after["observation_cost"],
            "expected_uncertainty_reduction": round(effective_reduction, 4),
        },
        "uncertainty_change": {"before": before["uncertainty"], "after": after["uncertainty"],
                               "delta": round(after["uncertainty"] - before["uncertainty"], 4)},
        "relative_uncertainty_reduction": (round((before["uncertainty"] - after["uncertainty"]) / before["uncertainty"], 4)
                                           if before["uncertainty"] > 0 else None),
        "risk_change": {"before": risk_before, "after": risk_after, "delta": round(risk_after - risk_before, 4)},
        "confidence_change": {"before": confidence_before, "after": confidence_after,
                              "delta": round(confidence_after - confidence_before, 4)},
        "decision_changed": decision_before != decision_after,
        "decision_result": "DECISION_CHANGED" if decision_before != decision_after else "DECISION_UNCHANGED",
        "supports_model_hypothesis": support,
        "notes": notes,
    }


def _quality_scaled_uncertainty(candidate: dict, quality: float) -> float:
    """Expose expected reduction at a given quality for direct unit testing."""
    base = calculate_observation_value(candidate)["expected_uncertainty_reduction"]
    return round(base * unit(quality), 4)



class TideEngine:
    """Request-scoped TIDE decision layer; no recommendation persistence in Phase 3."""

    def __init__(self, db: Session):
        self.db = db

    def _context(self):
        return adapters.uncertainty_inputs(self.db), adapters.event_inputs(self.db), adapters.apex_candidates(self.db)

    def _candidate(self, location: OceanLocation, apex: dict, uncertainty_row: dict, events: list[dict], variable: str, depth_m: float) -> dict:
        lat, lon = adapters.location_coordinates(location)
        gaps = adapters.gap_inputs(self.db, location.id, depth_m)
        gap = max(item["score"] for item in gaps)
        disagreement = adapters.disagreement_input(self.db, location, variable, depth_m, events)
        platforms = next((need.get("platforms", []) for need in apex.get("needs", []) if need.get("variable") == variable), [])
        method = _method(platforms)
        persistence = disagreement["persistence"]
        impact = unit((apex.get("decision_impact") or 0) / 100)
        impact = max(impact, unit(disagreement["severity"] * .65 + persistence * .35))
        score = calculate_observation_value({"decision_impact": impact, "uncertainty": uncertainty_row.get("score", 0),
                                             "data_gap": gap, "anomaly_persistence": persistence,
                                             "observation_cost": METHOD_COSTS[method]})
        evidence = []
        if disagreement["severity"] > .15:
            evidence.append({"type": "MODEL_OBSERVATION_MISMATCH", "strength": disagreement["severity"], "variable": variable,
                             "description": "Existing Twin comparison reports model-observation disagreement."})
        if persistence > .15:
            evidence.append({"type": "PERSISTENT_ANOMALY", "strength": persistence,
                             "description": "Existing Twin event stream contains active evidence at this location."})
        for item in gaps:
            if item["score"] > .05:
                evidence.append({"type": item["type"], "strength": item["score"], "description": item["description"]})
        confidence = unit(.25 + .30 * disagreement["spatial_consistency"] + .25 * persistence + .20 * min(1, len(evidence) / 3))
        factors = [{"name": "Existing comparison support", "score": disagreement["spatial_consistency"], "description": "Twin comparison confidence used as a proxy for support."},
                   {"name": "Evidence coverage", "score": min(1, len(evidence) / 3), "description": "Number of independently available TIDE evidence signals."}]
        decision = "INVESTIGATE_ANOMALY" if impact >= .65 else "INCREASE_MONITORING" if gap >= .5 else "CONTINUE_MONITORING"
        limitations = ["Scores are transparent heuristics, not a validated value-of-information model."]
        if disagreement["observed_value"] is None: limitations.append("No supported observed value was available for this variable/depth comparison.")
        if disagreement["observed_value"] is not None and disagreement.get("representativeness_km") is not None:
            limitations.append(
                "Observed reference is the nearest real in-situ Argo float (~{:.0f} km from the {} coast centroid); the comparison is basin-scale, not co-located.".format(
                    disagreement["representativeness_km"], location.name))
        return {"candidate_id": f"tide-{location.id}-{variable}-{int(depth_m)}-{method.lower()}", "location_id": location.id,
                "location": location.name, "latitude": lat, "longitude": lon, "depth_m": depth_m, "variable": variable,
                "observation_type": method, "status": "MODEL_DERIVED", **score, "affected_decision": decision,
                "reason": f"{location.name}: {_level(score['uncertainty'])} uncertainty, {max(gaps, key=lambda x: x['score'])['type'].replace('_', ' ').lower()}, and {method.replace('_', ' ').lower()} cost profile.",
                "evidence": evidence, "confidence": confidence, "confidence_factors": factors, "limitations": limitations,
                "_gaps": gaps, "_disagreement": disagreement, "_apex": apex}

    def rankings(self, *, location_id: int | None = None, variable: str = "temperature", depth_m: float = 0.0) -> list[dict]:
        uncertainty, events, apex = self._context()
        locations = self.db.query(OceanLocation).all()
        if location_id is not None:
            locations = [loc for loc in locations if loc.id == location_id]
        rows = []
        for location in locations:
            rows.append(self._candidate(location, apex.get(location.id, {}), uncertainty.get(location.id, {"score": 0}), events.get(location.id, []), variable, depth_m))
        return sorted(rows, key=lambda row: (-row["observation_value"], row["candidate_id"]))

    def uncertainty(self, **filters) -> list[dict]:
        return [{"location_id": r["location_id"], "location": r.get("location"), "score": r["score"], "level": _level(r["score"]),
                 "factors": [{"name": "Existing Forensics uncertainty", "score": r["score"], "description": "Normalized from the existing 0-100 uncertainty output."}]}
                for r in self._context()[0].values() if filters.get("location_id") in (None, r["location_id"])]

    def gaps(self, **filters) -> list[dict]:
        candidates = self.rankings(**filters)
        return [{"location_id": c["location_id"], "location": c["location"], "gaps": c["_gaps"]} for c in candidates]

    def disagreements(self, **filters) -> list[dict]:
        candidates = self.rankings(**filters)
        return [{"location_id": c["location_id"], "location": c["location"], "depth_m": c["depth_m"], "variable": c["variable"],
                 "model_value": c["_disagreement"]["model_value"], "observed_value": c["_disagreement"]["observed_value"],
                 "difference": c["_disagreement"]["difference"], "normalized_severity": c["_disagreement"]["severity"],
                 "temporal_persistence": c["_disagreement"]["persistence"], "spatial_consistency": c["_disagreement"]["spatial_consistency"], "evidence": c["evidence"]}
                for c in candidates]

    def verdict(self, **filters) -> dict | None:
        rows = self.rankings(**filters)
        if not rows: return None
        candidate = rows[0]
        d = candidate["_disagreement"]
        verdict = classify_verdict(severity=d["severity"], persistence=d["persistence"], spatial_consistency=d["spatial_consistency"], observation_count=len(candidate["evidence"]))
        evidence = trace_evidence(candidate)
        confidence = confidence_context(candidate, evidence)
        return {**verdict, "summary": verdict_summary(verdict["verdict"], verdict["confidence"]),
                "evidence": evidence, "candidate_id": candidate["candidate_id"],
                "recommended_observation": {"candidate_id": candidate["candidate_id"], "observation_type": candidate["observation_type"],
                                            "variable": candidate["variable"], "depth_m": candidate["depth_m"], "location": candidate["location"]},
                "limitations": confidence["limiting_factors"]}

    def explanation(self, **filters) -> dict | None:
        rows = self.rankings(**filters)
        if not rows:
            return None
        candidate = rows[0]
        extra = []
        if candidate.get("_apex"):
            extra.append({"type": "APEX_RECOMMENDATION", "strength": candidate["decision_impact"],
                          "description": "APEX generated this location as an observation candidate."})
        evidence = trace_evidence(candidate, extra)
        confidence = confidence_context(candidate, evidence)
        return {"candidate_id": candidate["candidate_id"], "explanation": recommendation_explanation(candidate, evidence, confidence),
                "decision_context": decision_context(candidate)}

    def _decision_for(self, impact: float, gap: float) -> str:
        return decision_for(impact, gap)

    def _anomaly_risk(self, candidate: dict, support_model: bool) -> float:
        return calculate_anomaly_risk(candidate, support_model=support_model)

    def _rank_position(self, candidate_id: str, rows: list[dict]) -> int:
        for index, row in enumerate(rows, 1):
            if row["candidate_id"] == candidate_id:
                return index
        return len(rows) + 1

    def _rankings_with_observed(self, candidate: dict, variable: str, depth_m: float) -> list[dict]:
        """Re-rank all candidates as if the simulated reading existed at this location."""
        rows = self.rankings(variable=variable, depth_m=depth_m)
        post = dict(candidate)
        for key in ("_gaps", "_disagreement", "_apex"):
            post.pop(key, None)
        inserted = False
        updated = []
        for row in rows:
            if row["candidate_id"] == candidate["candidate_id"]:
                updated.append(post)
                inserted = True
            else:
                updated.append(row)
        if not inserted:
            updated.append(post)
        return sorted(updated, key=lambda row: (-row["observation_value"], row["candidate_id"]))

    def virtual_observation(self, *, location_id: int, variable: str = "temperature", depth_m: float = 0.0,
                            observation_type: str = "VIRTUAL_SENSOR", value: float | None = None,
                            quality: float = 1.0, observed_at: datetime | None = None) -> dict | None:
        """Deterministic, non-persisted what-if simulation of an observation.

        The simulated reading is never written to OceanObservation or any other
        store and always carries ``SIMULATED`` status.  Before/after values come
        from the shared pure :func:`simulate_candidate` primitive, so the what-if
        and the Phase 8 benchmark cannot diverge.
        """
        rows = self.rankings(location_id=location_id, variable=variable, depth_m=depth_m)
        if not rows:
            return None
        candidate = rows[0]

        fallback = None
        if value is None and (candidate.get("_disagreement") or {}).get("observed_value") is None \
                and (candidate.get("_disagreement") or {}).get("model_value") is None:
            latest = adapters.latest_observation(self.db, location_id)
            if latest is not None and candidate["variable"] == "temperature":
                fallback = latest.sea_surface_temperature

        sim = simulate_candidate(candidate, simulated_value=value, observation_type=observation_type, quality=quality,
                                 fallback_value=fallback)
        simulated_value = sim["simulated_value"]
        before, after = sim["before"], sim["after"]
        ranking_before = self._rank_position(candidate["candidate_id"], self.rankings(variable=variable, depth_m=depth_m))
        updated_dim = {**candidate, "observation_type": observation_type, "status": "SIMULATED",
                       "uncertainty": after["uncertainty"], "data_gap": after["data_gap"],
                       "decision_impact": after["decision_impact"], "confidence": after["confidence"],
                       "observation_value": after["observation_value"],
                       "anomaly_persistence": after["anomaly_persistence"],
                       "observation_cost": after["observation_cost"]}
        ranking_after = self._rank_position(candidate["candidate_id"], self._rankings_with_observed(updated_dim, variable, depth_m))

        return {
            "candidate_id": candidate["candidate_id"],
            "location_id": candidate["location_id"],
            "location": candidate["location"],
            "variable": candidate["variable"],
            "depth_m": candidate["depth_m"],
            "observation_type": observation_type,
            "before": {
                "uncertainty": before["uncertainty"],
                "anomaly_risk": before["anomaly_risk"],
                "ranking": ranking_before,
                "decision": before["decision"],
                "confidence": before["confidence"],
                "observation_value": before["observation_value"],
            },
            "simulated_observation": {
                "value": simulated_value,
                "variable": candidate["variable"],
                "depth_m": candidate["depth_m"],
                "location": candidate["location"],
                "location_id": candidate["location_id"],
                "observation_type": observation_type,
                "status": "SIMULATED",
                "quality": unit(quality),
                "observed_at": (observed_at or datetime.now(timezone.utc)).isoformat(),
            },
            "after": {
                "uncertainty": after["uncertainty"],
                "anomaly_risk": after["anomaly_risk"],
                "ranking": ranking_after,
                "decision": after["decision"],
                "confidence": after["confidence"],
                "observation_value": after["observation_value"],
            },
            "uncertainty_change": sim["uncertainty_change"],
            "risk_change": sim["risk_change"],
            "confidence_change": sim["confidence_change"],
            "decision_changed": sim["decision_changed"],
            "decision_result": sim["decision_result"],
            "supports_model_hypothesis": sim["supports_model_hypothesis"],
            "notes": sim["notes"],
            "method": "deterministic_heuristic",
        }

    def event_context(self, event_id: str) -> dict | None:
        """Compose an existing event, its existing fingerprint, and TIDE context."""
        events = adapters.detect_events(self.db).get("events", [])
        try:
            index = int(event_id.removeprefix("event-"))
        except ValueError:
            return None
        if index < 0 or index >= len(events):
            return None
        event = events[index]
        variable = {"strong_current_event": "current_speed", "coastal_flooding_risk": "wave_height"}.get(event.get("event_type"), "temperature")
        rows = self.rankings(location_id=event.get("location_id"), variable=variable)
        if not rows:
            return {"event_id": f"event-{index}", "event": event, "event_dna": fingerprint(event), "top_candidates": [],
                    "message": "The event is available, but no TIDE candidate can be derived for its location."}
        candidate = rows[0]
        dna = fingerprint(event)
        dna_evidence = [{"type": "EVENT_DNA_FEATURE", "strength": candidate["anomaly_persistence"],
                         "description": f"Existing Ocean Event DNA: {', '.join(dna.get('tags', [])) or 'no categorical DNA tags available'}."}]
        evidence = trace_evidence(candidate, dna_evidence)
        confidence = confidence_context(candidate, evidence)
        verdict = self.verdict(location_id=event.get("location_id"), variable=variable)
        return {"event_id": f"event-{index}", "event": event, "event_dna": dna,
                "uncertainty": {"score": candidate["uncertainty"], "level": _level(candidate["uncertainty"])},
                "data_gaps": candidate["_gaps"], "disagreement": self.disagreements(location_id=event.get("location_id"), variable=variable)[0],
                "top_candidates": [candidate], "evidence": evidence, "confidence": confidence, "verdict": verdict,
                "decision_context": decision_context(candidate), "evidence_chain": ["EVENT", "OCEAN_EVENT_DNA", "TWIN_DISAGREEMENT", "FORENSICS_UNCERTAINTY", "DATA_GAP", "APEX_CANDIDATE", "TIDE_RECOMMENDATION"]}

    def hypotheses(self, location_id: int, *, variable: str = "temperature", depth_m: float = 0.0) -> dict:
        """Build cautious competing explanations from available measurements only."""
        from datetime import datetime, timezone

        rows = (self.db.query(OceanObservation)
                .filter(OceanObservation.location_id == location_id)
                .order_by(OceanObservation.timestamp.desc()).limit(250).all())
        # Never use synthetic, simulated, or model-derived rows as measured
        # support for a scientific explanation.
        rows = [row for row in rows if adapters.observation_status(row) in ("REAL", "HISTORICAL")]
        latest_by_depth: dict[float, float] = {}
        for row in rows:
            if row.sea_surface_temperature is not None:
                latest_by_depth.setdefault(float(row.depth_m or 0), float(row.sea_surface_temperature))
        profile = sorted(latest_by_depth.items())
        salinity_rows = [r for r in rows if r.salinity is not None]
        current_rows = [r for r in rows if r.current_speed is not None and r.current_direction is not None]
        measured_temp = [r for r in reversed(rows) if r.sea_surface_temperature is not None and (r.depth_m or 0) <= 10]
        residuals: list[float] = []
        if variable == "temperature" and len(measured_temp) >= 6:
            for index in range(5, len(measured_temp)):
                history = [float(item.sea_surface_temperature) for item in measured_temp[:index]]
                residuals.append(float(measured_temp[index].sea_surface_temperature) - sum(history) / len(history))
        mean_recent_residual = sum(residuals[-5:]) / len(residuals[-5:]) if len(residuals) >= 3 else None

        def assessment(name: str, explanation: str, supports: list[dict], contradicts: list[dict], missing: list[str],
                       coverage: float, sources: list[str]) -> dict:
            positive = sum(float(item["strength"]) for item in supports)
            negative = sum(float(item["strength"]) for item in contradicts)
            direction_support = positive / max(positive + negative, .01) if positive else 0.0
            coverage = min(1.0, max(0.0, coverage))
            confidence = round(coverage * direction_support * 100)
            status = ("INSUFFICIENT_EVIDENCE" if not supports and not contradicts else
                      "CONSISTENT_WITH_AVAILABLE_EVIDENCE" if positive > negative else
                      "CONTRADICTED_BY_AVAILABLE_EVIDENCE" if negative > positive else "MIXED_EVIDENCE")
            return {"name": name, "status": status, "supporting_evidence": supports,
                    "contradicting_evidence": contradicts, "missing_evidence": missing,
                    "confidence": confidence,
                    "confidence_factors": [
                        {"name": "Evidence direction", "score": round(direction_support, 3), "description": "Supporting evidence strength divided by total supporting plus contradicting strength."},
                        {"name": "Required-signal coverage", "score": round(coverage, 3), "description": "Coverage proxy based on which required input families are available."},
                    ],
                    "confidence_basis": "Confidence = 100 × evidence-direction support × required-signal coverage; heuristic, not a calibrated probability.",
                    "data_sources": sources, "last_updated": datetime.now(timezone.utc).isoformat(),
                    "explanation": explanation}

        supports_heat: list[dict] = []
        contradicts_heat: list[dict] = []
        if mean_recent_residual is not None and len(residuals[-5:]) >= 3 and abs(mean_recent_residual) >= .2:
            residual = mean_recent_residual
            target = supports_heat if residual > 0 else contradicts_heat
            target.append({"description": f"The mean of at least three recent temperature departures from the preceding local-history mean is {residual:+.2f} °C; this is compatible with surface heating but does not identify its source.",
                           "strength": min(1, abs(residual) / 2), "source": "; ".join(sorted({r.source or adapters.observation_status(r) for r in measured_temp[-5:]}))})
        heat_coverage = .3 if mean_recent_residual is not None else 0

        supports_mixing: list[dict] = []
        contradicts_mixing: list[dict] = []
        gradient = None
        if len(profile) >= 2:
            shallow = profile[0]
            deep = profile[-1]
            gradient = shallow[1] - deep[1]
            item = {"description": f"Temperature differs by {gradient:+.2f} °C between {shallow[0]:g} m and {deep[0]:g} m; stratification alone does not establish reduced mixing.",
                    "strength": min(1, abs(gradient) / 2), "source": "Depth-resolved OceanObservation records"}
            if gradient >= .5:
                supports_mixing.append(item)
            elif gradient < .2:
                contradicts_mixing.append(item)
        mix_coverage = .5 if len(profile) >= 2 else 0

        supports_advection: list[dict] = []
        contradicts_advection: list[dict] = []
        advection_coverage = 0
        if current_rows and salinity_rows:
            max_current = max(float(r.current_speed) for r in current_rows)
            if max_current < .02:
                contradicts_advection.append({"description": f"Recorded current speed is below 0.02 m/s at the selected location; a single-site record cannot rule out advection elsewhere.",
                                              "strength": .2, "source": "OceanObservation current-speed records"})
            advection_coverage = .5

        updated = datetime.now(timezone.utc).isoformat()
        items = [
            assessment("Surface heat accumulation", "A possible explanation involving net surface heat input. The available temperature comparison can indicate a persistent residual, but heat flux and wind forcing are needed to test this mechanism.", supports_heat, contradicts_heat,
                       ["Surface heat flux or radiation", "Wind stress and mixed-layer depth", "A matched historical baseline"], heat_coverage,
                       ["Real/historical surface temperature observations", "No direct surface heat-flux source is currently included"]),
            assessment("Reduced vertical mixing", "A possible explanation involving a more strongly stratified upper ocean. A temperature profile is only a proxy; wind and turbulence measurements are needed before interpreting mixing changes.", supports_mixing, contradicts_mixing,
                       ["Wind stress or turbulence measurements", "Repeated profiles through the event", "Matched historical depth profiles"], mix_coverage,
                       ["Depth-resolved OceanObservation records" if profile else "No depth-resolved temperature profile available"]),
            assessment("Horizontal advection", "A possible explanation involving transport by currents. Current speed at one site is not enough to diagnose heat transport; spatial temperature and salinity gradients plus current direction are required.", supports_advection, contradicts_advection,
                       ["Co-located current direction and speed", "Spatial temperature and salinity gradients", "Repeated observations along the current path"], advection_coverage,
                       ["OceanObservation current and salinity records" if current_rows and salinity_rows else "No co-located current and salinity evidence available"]),
        ]
        return {"location_id": location_id, "variable": variable, "depth_m": depth_m,
                "assessment_note": "These are competing hypotheses, not causal findings. Confidence is traceable to the listed evidence and coverage and is not a probability.",
                "hypotheses": items, "last_updated": updated}
