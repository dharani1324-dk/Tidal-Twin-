"""TIDE-Loop Phase 3 APIs: request-derived, explainable observation ranking."""

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.ai.tide import adapters, validation
from app.modules.ai.tide.engine import TideEngine
from app.modules.ai.tide.replay import ReplayEngine
from app.modules.ai.tide.scoring import unit
from app.schemas.tide import DecisionReplay, TideCandidate, VirtualObservationRequest, VirtualObservationSimulation

router = APIRouter(prefix="/api/v1/tide", tags=["TIDE-Loop"])

# TIDE accepts the full Phase 3 domain vocabulary. The adapter reports a
# limitation when the existing Twin has no comparison support for a variable.
TIDE_VARIABLES = ("temperature", "salinity", "oxygen", "chlorophyll", "current_speed", "wave_height", "pressure", "nutrients", "ph", "density")


def _payload(data):
    return {"success": True, "data": data, "error": None}


def _engine(db: Session) -> TideEngine:
    return TideEngine(db)


def _candidate_payload(rows: list[dict]) -> list[dict]:
    """Validate and omit internal adapter fields from public candidate JSON."""
    return [TideCandidate.model_validate(row).model_dump() for row in rows]


def _filters(location_id: int | None, variable: str, depth_m: float) -> dict:
    if variable not in TIDE_VARIABLES:
        raise HTTPException(422, detail={"code": "TIDE_INVALID_REQUEST", "message": f"variable must be one of {list(TIDE_VARIABLES)}"})
    if depth_m < 0:
        raise HTTPException(422, detail={"code": "TIDE_INVALID_REQUEST", "message": "depth_m must be zero or greater"})
    return {"location_id": location_id, "variable": variable, "depth_m": depth_m}


@router.get("/candidates")
def get_candidates(location_id: int | None = Query(None), variable: str = Query("temperature"), depth_m: float = Query(0.0), db: Session = Depends(get_db)):
    return _payload(_candidate_payload(_engine(db).rankings(**_filters(location_id, variable, depth_m))))


@router.get("/rankings")
def get_rankings(location_id: int | None = Query(None), variable: str = Query("temperature"), depth_m: float = Query(0.0), db: Session = Depends(get_db)):
    rows = _engine(db).rankings(**_filters(location_id, variable, depth_m))
    return _payload({"formula": "decision_impact * uncertainty * data_gap * anomaly_persistence / max(observation_cost, 0.05)", "rankings": _candidate_payload(rows)})


@router.get("/uncertainty")
def get_uncertainty(location_id: int | None = Query(None), db: Session = Depends(get_db)):
    return _payload(_engine(db).uncertainty(location_id=location_id))


@router.get("/data-gaps")
def get_data_gaps(location_id: int | None = Query(None), variable: str = Query("temperature"), depth_m: float = Query(0.0), db: Session = Depends(get_db)):
    return _payload(_engine(db).gaps(**_filters(location_id, variable, depth_m)))


@router.get("/disagreements")
def get_disagreements(location_id: int | None = Query(None), variable: str = Query("temperature"), depth_m: float = Query(0.0), db: Session = Depends(get_db)):
    return _payload(_engine(db).disagreements(**_filters(location_id, variable, depth_m)))


@router.get("/evidence")
def get_evidence(location_id: int | None = Query(None), variable: str = Query("temperature"), depth_m: float = Query(0.0), db: Session = Depends(get_db)):
    engine = _engine(db)
    filters = _filters(location_id, variable, depth_m)
    result = engine.explanation(**filters)
    if result is None:
        raise HTTPException(404, detail={"code": "TIDE_NO_CANDIDATE", "message": "No TIDE evidence is available for this request."})
    return _payload(result)


@router.get("/explanation")
def get_explanation(location_id: int | None = Query(None), variable: str = Query("temperature"), depth_m: float = Query(0.0), db: Session = Depends(get_db)):
    result = _engine(db).explanation(**_filters(location_id, variable, depth_m))
    if result is None:
        raise HTTPException(404, detail={"code": "TIDE_NO_CANDIDATE", "message": "No TIDE explanation is available for this request."})
    return _payload(result)


@router.get("/verdict")
def get_verdict(location_id: int = Query(...), variable: str = Query("temperature"), depth_m: float = Query(0.0), db: Session = Depends(get_db)):
    result = _engine(db).verdict(**_filters(location_id, variable, depth_m))
    if result is None:
        raise HTTPException(404, detail={"code": "TIDE_NO_CANDIDATE", "message": "No TIDE candidate is available for this location."})
    return _payload(result)


@router.get("/events/{event_id}")
def get_event_context(event_id: str, db: Session = Depends(get_db)):
    result = _engine(db).event_context(event_id)
    if result is None:
        raise HTTPException(404, detail={"code": "TIDE_EVENT_NOT_FOUND", "message": "The requested existing event was not found."})
    if result.get("top_candidates"):
        result["top_candidates"] = _candidate_payload(result["top_candidates"])
    return _payload(result)


@router.get("/events")
def get_event_index(db: Session = Depends(get_db)):
    """Index of playable TIDE events, in the same order event-N is resolved."""
    events = []
    for index, ev in enumerate(adapters.detect_events(db).get("events", [])):
        severity = float(ev.get("confidence") or 0) / 100
        events.append({
            "event_id": f"event-{index}",
            "event_type": ev.get("event_type"),
            "label": ev.get("label"),
            "icon": ev.get("icon"),
            "intensity": ev.get("intensity"),
            "confidence": unit(severity),
            "location_id": ev.get("location_id"),
            "location": ev.get("location"),
            "variable": ev.get("variable"),
            "began_hours_ago": ev.get("began_hours_ago"),
            "data_status": ev.get("data_status"),
        })
    return _payload({"events": events})


@router.get("/events/{event_id}/replay")
def get_event_replay(event_id: str, location_id: int | None = Query(None),
                     variable: str | None = Query(None), depth_m: float = Query(0.0),
                     observation_type: str = Query("VIRTUAL_SENSOR"), value: float | None = Query(None),
                     db: Session = Depends(get_db)):
    """Read-only, session-scoped TIDE Decision Replay for an existing event.

    Composes the Phase 3/4/5 engines (candidates, evidence, verdict,
    event context, virtual observation) into a two-mode step-by-step replay.
    Nothing is written to the observation store and historical events are
    never modified.
    """
    if variable is not None and variable not in TIDE_VARIABLES:
        raise HTTPException(422, detail={"code": "TIDE_INVALID_REQUEST", "message": f"variable must be one of {list(TIDE_VARIABLES)}"})
    if depth_m < 0:
        raise HTTPException(422, detail={"code": "TIDE_INVALID_REQUEST", "message": "depth_m must be zero or greater"})
    result = ReplayEngine(db).build(event_id, location_id=location_id, variable=variable,
                                    depth_m=depth_m, observation_type=observation_type, value=value)
    if result is None:
        raise HTTPException(404, detail={"code": "TIDE_EVENT_NOT_FOUND", "message": "The requested event replay could not be built."})
    return _payload(DecisionReplay.model_validate(result).model_dump())


@router.get("/validation")
def get_validation(db: Session = Depends(get_db)):
    """Phase 8 validation status: maturity, dataset, ground truth, boundary, consistency.

    Reports implementation maturity honestly (tested, not empirically validated),
    the available dataset, and algorithm-consistency / edge-case testing.
    """
    return _payload(validation.validation_status(db))


def _benchmark_params(budget: int, variables: str | None, strategies: str | None, depth_m: float, seed: int):
    if budget < 1 or budget > 10:
        raise HTTPException(422, detail={"code": "TIDE_INVALID_REQUEST", "message": "budget must be between 1 and 10"})
    if depth_m < 0:
        raise HTTPException(422, detail={"code": "TIDE_INVALID_REQUEST", "message": "depth_m must be zero or greater"})
    variable_list = tuple(v.strip() for v in variables.split(",") if v.strip()) if variables else ("temperature", "wave_height", "salinity", "current_speed")
    invalid_vars = [v for v in variable_list if v not in TIDE_VARIABLES]
    if invalid_vars:
        raise HTTPException(422, detail={"code": "TIDE_INVALID_REQUEST", "message": f"unknown variables {invalid_vars}; allowed {list(TIDE_VARIABLES)}"})
    strategy_list = tuple(s.strip().upper() for s in strategies.split(",") if s.strip()) if strategies else validation.STRATEGIES
    invalid_strats = [s for s in strategy_list if s not in validation.STRATEGIES]
    if invalid_strats:
        raise HTTPException(422, detail={"code": "TIDE_INVALID_REQUEST", "message": f"unknown strategies {invalid_strats}; allowed {list(validation.STRATEGIES)}"})
    return variable_list, strategy_list


@router.get("/benchmarks")
def get_benchmarks(budget: int = Query(1), variables: str | None = Query(None), strategies: str | None = Query(None),
                   depth_m: float = Query(0.0), seed: int = Query(42), db: Session = Depends(get_db)):
    """Machine-readable TIDE benchmark report (fair, budget-configurable, reproducible)."""
    variable_list, strategy_list = _benchmark_params(budget, variables, strategies, depth_m, seed)
    report = validation.run_database_benchmark(db, variables=variable_list, depth_m=depth_m,
                                               budget=budget, strategies=strategy_list, seed=seed)
    return _payload(report)


@router.get("/benchmarks/{case_id}")
def get_benchmark_case(case_id: str, variable: str = Query("temperature"), depth_m: float = Query(0.0),
                       budget: int = Query(1), seed: int = Query(42), db: Session = Depends(get_db)):
    """Case/event-level drill-down behind a benchmark number."""
    if budget < 1 or budget > 10:
        raise HTTPException(422, detail={"code": "TIDE_INVALID_REQUEST", "message": "budget must be between 1 and 10"})
    if variable not in TIDE_VARIABLES:
        raise HTTPException(422, detail={"code": "TIDE_INVALID_REQUEST", "message": f"variable must be one of {list(TIDE_VARIABLES)}"})
    if depth_m < 0:
        raise HTTPException(422, detail={"code": "TIDE_INVALID_REQUEST", "message": "depth_m must be zero or greater"})
    result = validation.benchmark_case_detail(db, case_id, variable=variable, depth_m=depth_m, budget=budget, seed=seed)
    if result is None:
        raise HTTPException(404, detail={"code": "TIDE_BENCHMARK_CASE_NOT_FOUND", "message": "The requested benchmark case could not be resolved."})
    return _payload(result)


@router.post("/virtual-observation")
def create_virtual_observation(payload: VirtualObservationRequest = Body(...), db: Session = Depends(get_db)):
    """Deterministic what-if observation simulation.

    The simulated reading is never persisted and always carries SIMULATED status.
    """
    if payload.variable not in TIDE_VARIABLES:
        raise HTTPException(422, detail={"code": "TIDE_INVALID_REQUEST", "message": f"variable must be one of {list(TIDE_VARIABLES)}"})
    result = _engine(db).virtual_observation(location_id=payload.location_id, variable=payload.variable,
                                             depth_m=payload.depth_m, observation_type=payload.observation_type,
                                             value=payload.value)
    if result is None:
        raise HTTPException(404, detail={"code": "TIDE_NO_CANDIDATE", "message": "No TIDE candidate is available for this location."})
    return _payload(VirtualObservationSimulation.model_validate(result).model_dump())
