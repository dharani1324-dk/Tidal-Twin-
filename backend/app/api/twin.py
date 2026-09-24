"""TidalTwin - Ocean Digital Twin API.

One router exposing the AI-powered digital-twin intelligence layer:

    GET /api/v1/twin/compare          model-vs-observation comparison for one region
    GET /api/v1/twin/disagreement      disagreement map (per region, for the globe layer)
    GET /api/v1/twin/profile           model-vs-observation depth profile
    GET /api/v1/twin/anomalies         ranked anomaly intelligence
    GET /api/v1/twin/events            detected ocean events (enriched)
    GET /api/v1/twin/confidence       confidence scoring for one region+variable
    GET /api/v1/twin/explain          evidence-driven explanation
    GET /api/v1/twin/sources           data-source registry / health
    GET /api/v1/twin/situation         aggregated decision-support situation
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.location import OceanLocation
from app.modules.ai.twin import anomalies, confidence as conf_mod, events, explain
from app.modules.ai.twin.compare import VARIABLES, compare
from app.modules.ai.twin.profiles import profile
from app.modules.ai.twin.situation import situation
from app.modules.ai.twin.sources import data_sources
from app.modules.ai.twin.transect import TRANSECT_VARIABLES, transect

router = APIRouter(prefix="/api/v1/twin", tags=["Ocean Digital Twin"])

VALID_VARIABLES = list(VARIABLES.keys())


def _loc(db: Session, location_id: int) -> OceanLocation:
    loc = db.query(OceanLocation).filter(OceanLocation.id == location_id).first()
    if not loc:
        raise HTTPException(404, "Location not found")
    return loc


@router.get("/compare")
def get_compare(location_id: int = Query(...), variable: str = Query("temperature"), depth_m: float = Query(0.0),
                db: Session = Depends(get_db)):
    if variable not in VALID_VARIABLES:
        raise HTTPException(422, f"variable must be one of {VALID_VARIABLES}")
    return compare(db, _loc(db, location_id), variable=variable, depth_m=depth_m)


@router.get("/disagreement")
def get_disagreement(variable: str = Query("temperature"), depth_m: float = Query(0.0),
                     db: Session = Depends(get_db)):
    if variable not in VALID_VARIABLES:
        raise HTTPException(422, f"variable must be one of {VALID_VARIABLES}")
    from app.modules.ai.twin.compare import disagreement_map

    return disagreement_map(db, variable=variable, depth_m=depth_m)


@router.get("/profile")
def get_profile(location_id: int = Query(...), variable: str = Query("temperature"),
                db: Session = Depends(get_db)):
    if variable not in list(anomalies.RANK_VARIABLES) + ["salinity"]:
        raise HTTPException(422, f"variable must be one of {list(anomalies.RANK_VARIABLES) + ['salinity']}")
    return profile(db, _loc(db, location_id), variable=variable)


@router.get("/anomalies")
def get_anomalies(variable: str | None = Query(None), severity: str | None = Query(None),
                  region: str | None = Query(None), min_confidence: int = Query(0),
                  sort: str = Query("severity"), db: Session = Depends(get_db)):
    if variable and variable not in VALID_VARIABLES:
        raise HTTPException(422, f"variable must be one of {VALID_VARIABLES}")
    if sort not in ("severity", "magnitude", "confidence", "recency"):
        raise HTTPException(422, "sort must be one of severity, magnitude, confidence, recency")
    return anomalies.rank_anomalies(db, variable=variable, severity=severity,
                                    region=region, min_confidence=min_confidence, sort=sort)


@router.get("/events")
def get_events(location_id: int | None = Query(None), db: Session = Depends(get_db)):
    if location_id is not None:
        _loc(db, location_id)
    return events.detect_events(db, location_id=location_id)


@router.get("/confidence")
def get_confidence(location_id: int = Query(...), variable: str = Query("temperature"),
                   db: Session = Depends(get_db)):
    if variable not in VALID_VARIABLES:
        raise HTTPException(422, f"variable must be one of {VALID_VARIABLES}")
    loc = _loc(db, location_id)
    res = compare(db, loc, variable=variable)
    if res.get("error"):
        raise HTTPException(404, str(res["error"]))
    return {
        "location_id": loc.id,
        "location": loc.name,
        "variable": variable,
        "label": VARIABLES[variable]["label"],
        "score": res.get("confidence"),
        "level": res.get("confidence_level"),
        "factors": res.get("confidence_factors", []),
        "reasons": res.get("confidence_reasons", []),
    }


@router.get("/explain")
def get_explain(location_id: int = Query(...), variable: str = Query("temperature"), depth_m: float = Query(0.0),
                db: Session = Depends(get_db)):
    if variable not in VALID_VARIABLES:
        raise HTTPException(422, f"variable must be one of {VALID_VARIABLES}")
    tag = explain.explain(db, _loc(db, location_id), variable=variable, depth_m=depth_m)
    return tag


@router.get("/sources")
def get_sources(db: Session = Depends(get_db)):
    return data_sources(db)


@router.get("/situation")
def get_situation(db: Session = Depends(get_db)):
    return situation(db)


@router.get("/transect")
def get_transect(lat1: float = Query(...), lon1: float = Query(...),
                 lat2: float = Query(...), lon2: float = Query(...),
                 variable: str = Query("temperature"), depth_max: float = Query(2000),
                 n_samples: int = Query(48), db: Session = Depends(get_db)):
    """3D vertical transect 'curtain' between two picked ocean points."""
    if variable not in TRANSECT_VARIABLES:
        raise HTTPException(422, f"variable must be one of {list(TRANSECT_VARIABLES)}")
    for la, lo, nm in ((lat1, lon1, "lat1/lon1"), (lat2, lon2, "lat2/lon2")):
        if not (-90 <= la <= 90) or not (-180 <= lo <= 180):
            raise HTTPException(422, f"{nm} out of range")
    return transect(db, lat1, lon1, lat2, lon2,
                    variable=variable, depth_max=int(depth_max), n_samples=int(n_samples))