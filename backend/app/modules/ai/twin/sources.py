"""
TidalTwin - Data Source Registry & Health
=============================================
A normalised registry of the data streams feeding the twin. Every source
carries: status, last update, variables, coverage and a plain-language
note. If a source is unavailable it is shown as such - the system never
pretends a live feed exists where it does not.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.modules.ai.forecast.argo import get_argo_trajectories
from app.modules.ai.twin.compare import data_status_for

REAL_SOURCE = "Open-Meteo Marine"


def _parse_ts(ts_str):
    if ts_str is None:
        return None
    if isinstance(ts_str, datetime):
        return ts_str
    try:
        return datetime.fromisoformat(ts_str)
    except Exception:
        return None
MODEL_KIND = "Numerical model (history-conditioned estimate)"

# Order used by the UI.
SOURCE_ORDER = [
    "open_meteo",
    "model_estimate",
    "argo",
    "physics_engine",
    "satellite",
]


def _coverage(db: Session, cols: list[str]) -> float:
    locations = db.query(OceanLocation).count()
    if not locations:
        return 0.0
    with_rows = 0
    for loc in db.query(OceanLocation).all():
        obs = (
            db.query(OceanObservation)
            .filter(OceanObservation.location_id == loc.id)
            .limit(1)
            .all()
        )
        if obs:
            has_any = False
            row = obs[0]
            for c in cols:
                if getattr(row, c, None) is not None:
                    has_any = True
                    break
            if has_any:
                with_rows += 1
    return round(with_rows / locations * 100.0, 1)


def data_sources(db: Session) -> dict:
    now = datetime.now(timezone.utc)

    latest = (
        db.query(OceanObservation)
        .order_by(OceanObservation.timestamp.desc())
        .first()
    )
    latest_ts = latest.timestamp if latest else None

    argo = get_argo_trajectories(db, n_floats=1)
    argo_floats = argo.get("floats", [])
    argo_last = None
    if argo_floats:
        pts = argo_floats[0].get("points", [])
        if pts:
            argo_last = _parse_ts(pts[-1].get("timestamp"))

    sources = {
        "open_meteo": {
            "id": "open_meteo",
            "name": "Open-Meteo Marine",
            "kind": "observation",
            "status": "online" if latest_ts else "offline",
            "status_detail": data_status_for(REAL_SOURCE, latest_ts, now),
            "last_update": latest_ts.isoformat() if latest_ts else None,
            "variables": ["Sea temperature", "Wave height", "Wave direction"],
            "coverage_pct": _coverage(db, ["sea_surface_temperature", "wave_height"]),
            "note": (
                "Real ocean-model in-situ feed (MeteoFrance/Copernicus-derived), refreshed on demand. "
                "No API key required."
            ),
        },
        "model_estimate": {
            "id": "model_estimate",
            "name": "Ocean model estimate",
            "kind": "model",
            "status": "online" if latest_ts else "offline",
            "status_detail": "derived",
            "last_update": latest_ts.isoformat() if latest_ts else None,
            "variables": ["Sea temperature", "Wave height"],
            "coverage_pct": _coverage(db, ["sea_surface_temperature", "wave_height"]),
            "note": (
                "History-conditioned statistical model (validated trend/baseline), fit to the most recent "
                "observation window. Forecasting pipeline is explainable and evaluated by rolling MAE."
            ),
        },
        "argo": {
            "id": "argo",
            "name": "Argo floats",
            "kind": "observation",
            "status": "simulated",
            "status_detail": data_status_for("ARGO_SIM", argo_last, now),
            "last_update": argo_last,
            "variables": ["Sea temperature", "Salinity"],
            "coverage_pct": 0.0,
            "note": (
                "Trajectory simulator with synthetic WMO floats. Live Argo integration is pending "
                "(see integration_pending); values are simulated and labelled as such."
            ),
        },
        "physics_engine": {
            "id": "physics_engine",
            "name": "Physics engine (derived)",
            "kind": "derived",
            "status": "online",
            "status_detail": "derived",
            "last_update": latest_ts.isoformat() if latest_ts else None,
            "variables": ["Dissolved oxygen", "Chlorophyll", "pH", "Density", "Nutrients"],
            "coverage_pct": _coverage(db, ["dissolved_oxygen", "chlorophyll"]),
            "note": (
                "Local bio-physical derivation from surface state (oxygen/chlorophyll/pH/density). "
                "Derived estimates, not direct measurements."
            ),
        },
        "satellite": {
            "id": "satellite",
            "name": "Satellite products (SST/Chl)",
            "kind": "observation",
            "status": "integration pending",
            "status_detail": "unavailable",
            "last_update": None,
            "variables": ["Sea surface temperature", "Chlorophyll"],
            "coverage_pct": 0.0,
            "note": (
                "No satellite product connector configured yet. Architecture is ready; when a public "
                "source is added it appears here with its own status."
            ),
        },
    }

    order = [s["id"] for s in sources.values() if s["id"] in SOURCE_ORDER]
    ordered = [sources[oid] for oid in order if oid in sources]
    online = sum(1 for s in ordered if s["status"] == "online")
    return {
        "generated_at": now.isoformat(),
        "sources": ordered,
        "health": {
            "online": online,
            "total": len(ordered),
            "degraded": [s["name"] for s in ordered if s["status"] not in ("online",)],
        },
    }