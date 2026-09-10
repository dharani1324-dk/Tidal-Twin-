"""OceanVerse AI - Intelligence + Forensics API (all new endpoints).

One router covering: data gaps, priorities, uncertainty heatmap, health,
threat chain, impact bridge, relationship graph, causal chain, thermocline,
multi-variable what-if, counterfactual, future windows, forensic events,
investigation, similar events, fingerprint, autopsy, and scientific reports.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.ai.forensics import intelligence as intel
from app.modules.ai.forensics.forensics import investigate, autopsy
from app.modules.ai.forensics.fingerprint import similar_events, fingerprint as build_fp
from app.modules.ai.forensics.report import report_json, report_csv, report_pdf
from app.modules.ai.validation.engine import (
    classify_events, difference_engine, model_skill,
    scenario_projection_multi, counterfactual, future_windows,
)
from app.modules.physics.ocean_profiles import depth_profile, thermocline as thermo_engine
from app.models.location import OceanLocation

router = APIRouter(prefix="/api/v1/intelligence", tags=["Intelligence + Forensics"])


# ── Coverage / Gaps / Priority ─────────────────────────────────────────────

@router.get("/coverage")
def get_coverage(db: Session = Depends(get_db)):
    return intel.region_coverage(db)


@router.get("/priority")
def get_priority(db: Session = Depends(get_db)):
    return intel.priority_map(db)


@router.get("/uncertainty")
def get_uncertainty(db: Session = Depends(get_db)):
    return intel.uncertainty_map(db)


@router.get("/coverage-sim")
def coverage_sim(location_id: int = Query(...), delta_pct: float = Query(30),
                 db: Session = Depends(get_db)):
    return intel.coverage_simulator(db, location_id, delta_pct)


# ── Health / Threat / Impact ───────────────────────────────────────────────

@router.get("/health")
def get_health(location_id: int | None = Query(None), db: Session = Depends(get_db)):
    return intel.health_score(db, location_id)


@router.get("/threat-chain")
def get_threat_chain(db: Session = Depends(get_db)):
    return intel.threat_chain(db)


@router.get("/impact")
def get_impact(db: Session = Depends(get_db)):
    return intel.impact_bridge(db)


# ── Relationship Graph / Causal Chain ──────────────────────────────────────

@router.get("/relationships")
def get_relationships(db: Session = Depends(get_db)):
    return intel.relationship_graph(db)


@router.get("/causal")
def get_causal(location_id: int = Query(...), db: Session = Depends(get_db)):
    return intel.causal_chain(db, location_id)


# ── Thermocline ────────────────────────────────────────────────────────────

@router.get("/thermocline")
def get_thermocline(location_id: int = Query(...), db: Session = Depends(get_db)):
    loc = db.query(OceanLocation).filter(OceanLocation.id == location_id).first()
    if not loc:
        raise HTTPException(404, "Location not found")
    return thermo_engine(db, loc)


@router.get("/depth-profile")
def get_depth_profile(location_id: int = Query(...), db: Session = Depends(get_db)):
    loc = db.query(OceanLocation).filter(OceanLocation.id == location_id).first()
    if not loc:
        raise HTTPException(404, "Location not found")
    from app.models.observation import OceanObservation
    o = (db.query(OceanObservation)
         .filter(OceanObservation.location_id == loc.id)
         .order_by(OceanObservation.timestamp.desc()).first())
    if not o:
        return {"error": "No observations"}
    return depth_profile(loc, o.sea_surface_temperature, o.salinity, o.wave_height, o.current_speed)


# ── What-If / Counterfactual / Future ──────────────────────────────────────

class ScenarioRequest(BaseModel):
    location_id: int
    wind_percent: float = 0.0
    temp_delta: float = 0.0
    salinity_delta: float = 0.0
    mixing_factor: float = 1.0


@router.post("/whatif")
def whatif(req: ScenarioRequest, db: Session = Depends(get_db)):
    return scenario_projection_multi(db, req.location_id, req.wind_percent,
                                     req.temp_delta, req.salinity_delta, req.mixing_factor)


@router.post("/counterfactual")
def counterfactual_ep(req: ScenarioRequest, db: Session = Depends(get_db)):
    return counterfactual(db, req.location_id, req.wind_percent,
                          req.temp_delta, req.salinity_delta)


@router.get("/future")
def get_future(location_id: int = Query(...), db: Session = Depends(get_db)):
    return future_windows(db, location_id)


# ── Forensics ──────────────────────────────────────────────────────────────

@router.get("/events")
def get_events(db: Session = Depends(get_db)):
    events = classify_events(db)["events"]
    enriched = []
    for e in events:
        fp = build_fp(e)
        enriched.append({**e, "fingerprint": fp})
    return {"events": enriched}


@router.get("/investigate")
def investigate_region(location_id: int = Query(...), db: Session = Depends(get_db)):
    return investigate(db, location_id)


@router.get("/similar")
def similar(event_index: int = Query(0), db: Session = Depends(get_db)):
    events = classify_events(db)["events"]
    if event_index >= len(events):
        raise HTTPException(404, "Event index out of range")
    fp = build_fp(events[event_index])
    return {"similar": similar_events(db, fp, limit=5), "fingerprint": fp}


@router.get("/fingerprint")
def get_fingerprint(event_index: int = Query(0), db: Session = Depends(get_db)):
    events = classify_events(db)["events"]
    if event_index >= len(events):
        raise HTTPException(404, "Event index out of range")
    return build_fp(events[event_index])


@router.get("/timeline")
def get_timeline(location_id: int = Query(...), db: Session = Depends(get_db)):
    """Event timeline (Normal → Observed → Intensifying → Severe → Turning → Recovery)."""
    from app.models.observation import OceanObservation
    loc = db.query(OceanLocation).filter(OceanLocation.id == location_id).first()
    if not loc:
        raise HTTPException(404, "Location not found")
    rows = (db.query(OceanObservation)
            .filter(OceanObservation.location_id == location_id)
            .order_by(OceanObservation.timestamp.asc()).all())
    if not rows:
        return {"location": loc.name, "timeline": []}

    base_temp = rows[0].sea_surface_temperature or 28.0
    stages = []
    for i, o in enumerate(rows):
        t = o.sea_surface_temperature or base_temp
        anom = t - base_temp
        if i == 0 or abs(anom) < 0.2:
            stage = "Normal"
        elif i == len(rows) - 1 and abs(anom) < 0.5:
            stage = "Recovery"
        elif anom > 2.0:
            stage = "Severe"
        elif anom > 1.0:
            stage = "Intensifying"
        elif anom > 0.5:
            stage = "Observed"
        else:
            stage = "Turning point"
        stages.append({
            "time": o.timestamp.isoformat(),
            "sst": round(t, 2),
            "anomaly": round(anom, 2),
            "stage": stage,
        })

    return {"location": loc.name, "location_id": location_id, "timeline": stages}


@router.get("/autopsy")
def autopsy_report(location_id: int = Query(...), db: Session = Depends(get_db)):
    return autopsy(db, location_id)


# ── Scientific Report Export ───────────────────────────────────────────────

@router.get("/report/{location_id}.json")
def report_json_ep(location_id: int, db: Session = Depends(get_db)):
    return report_json(db, location_id)


@router.get("/report/{location_id}.csv")
def report_csv_ep(location_id: int, db: Session = Depends(get_db)):
    content = report_csv(db, location_id)
    return PlainTextResponse(content, media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename=report_{location_id}.csv"})


@router.get("/report/{location_id}.pdf")
def report_pdf_ep(location_id: int, db: Session = Depends(get_db)):
    pdf_bytes = report_pdf(db, location_id)
    if pdf_bytes is None:
        raise HTTPException(501, "PDF generation requires 'reportlab' package.")
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=report_{location_id}.pdf"})
