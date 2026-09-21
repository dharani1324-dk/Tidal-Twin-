"""
TidalTwin - Data Source Registry & Health (plugin-driven)
=================================================================
A normalised registry of the data streams feeding the twin. Every source is
a `SensorPlugin` (feature #20, runtime plugin architecture) carrying: status,
last update, variables, coverage and a plain-language note. If a source is
unavailable it is shown as such - the system never pretends a live feed
exists where it does not.

`data_sources(db)` is a thin wrapper over `build_sources(db)` so the twin's
API and situational-awareness consumers keep the exact same contract
(generated_at / sources / health), while the set of sources itself is
discoverable and hot-swappable at runtime.
"""

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.models.argo import ArgoProfile
from app.models.glider import GliderProfile
from app.modules.ai.realdata import latest_for, location_center, near
from app.modules.ai.modelgrid import GRID_SOURCES, depths_for, latest_for as modelgrid_latest_for
from app.modules.ai.twin.compare import data_status_for
from app.modules.ai.twin.plugins import (
    SensorPlugin,
    SOURCE_ORDER,
    build_sources,
    register,
)

REAL_SOURCE = "Open-Meteo Marine"


MODEL_KIND = "Numerical model (history-conditioned estimate)"


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


def _argo_info(db: Session):
    """(latest time, n floats, n profile levels) from REAL ingested Argo rows."""
    latest = db.query(func.max(ArgoProfile.time)).scalar()
    if latest is None:
        return None, 0, 0
    n_floats = db.query(func.count(func.distinct(ArgoProfile.float_id))).scalar() or 0
    n_levels = db.query(func.count(ArgoProfile.id)).scalar() or 0
    return latest, n_floats, n_levels


def _grid_health(db: Session, variable: str, max_deg: float) -> tuple:
    """(latest time, coverage %) for one real ingested grid: the share of
    monitored locations whose centroid has a real cell within search range."""
    latest_t, _, _ = latest_for(db, variable)
    if latest_t is None:
        return None, 0.0
    locations = db.query(OceanLocation).all()
    if not locations:
        return latest_t, 0.0
    near_count = 0
    for loc in locations:
        center = location_center(loc)
        if center is None:
            continue
        if near(db, variable, center[0], center[1], max_deg)["found"]:
            near_count += 1
    return latest_t, round(near_count / len(locations) * 100.0, 1)


def _ersst_info(db: Session):
    """(latest time, coverage %) for the real NOAA ERSST grid we ingested."""
    return _grid_health(db, "sst", 3.5)


def _chlor_info(db: Session):
    """(latest time, coverage %) for the real satellite Chl grid we ingested."""
    return _grid_health(db, "chlor_a", 0.2)


def _glider_info(db: Session):
    """(latest time, n deployments, n samples, n BGC samples) from REAL ingested glider rows."""
    latest = db.query(func.max(GliderProfile.time)).scalar()
    if latest is None:
        return None, 0, 0, 0
    n_deployments = db.query(func.count(func.distinct(GliderProfile.deployment_id))).scalar() or 0
    n_samples = db.query(func.count(GliderProfile.id)).scalar() or 0
    n_bgc = (
        db.query(func.count(GliderProfile.id))
        .filter(GliderProfile.dissolved_oxygen.isnot(None)
                | GliderProfile.chlorophyll.isnot(None)
                | GliderProfile.nitrate.isnot(None))
        .scalar() or 0
    )
    return latest, n_deployments, n_samples, n_bgc


def _model_grid_info(db: Session):
    """(latest time, present variables, total depth levels) of the REAL 3D
    ocean-model grid (HYCOM via scripts.fetch_model + ingest_netcdf)."""
    present: list[str] = []
    latest_t = None
    total_levels = 0
    for var in GRID_SOURCES:
        t, _ = modelgrid_latest_for(db, var)
        if t is not None:
            present.append(var)
            total_levels += len(depths_for(db, var))
            if latest_t is None or t > latest_t:
                latest_t = t
    return latest_t, present, total_levels


def _latest_observation(db: Session):
    return (
        db.query(OceanObservation)
        .order_by(OceanObservation.timestamp.desc())
        .first()
    )


# ---------------------------------------------------------------------------
# Sensor plugins (feature #20). Each plugin computes its own honest status.
# ---------------------------------------------------------------------------


class OpenMeteoPlugin(SensorPlugin):
    source_id = "open_meteo"
    name = "Open-Meteo Marine"
    kind = "observation"
    variables = ["Sea temperature", "Wave height", "Wave direction"]

    def info(self, db, now):
        latest = _latest_observation(db)
        latest_ts = latest.timestamp if latest else None
        return {
            "id": self.source_id,
            "name": self.name,
            "kind": self.kind,
            "status": "online" if latest_ts else "offline",
            "status_detail": data_status_for(REAL_SOURCE, latest_ts, now),
            "last_update": latest_ts.isoformat() if latest_ts else None,
            "variables": self.variables,
            "coverage_pct": _coverage(db, ["sea_surface_temperature", "wave_height"]),
            "note": (
                "Real ocean-model in-situ feed (MeteoFrance/Copernicus-derived), refreshed on demand. "
                "No API key required."
            ),
        }


class ModelEstimatePlugin(SensorPlugin):
    source_id = "model_estimate"
    name = "Ocean model estimate"
    kind = "model"
    variables = ["Sea temperature", "Wave height"]

    def info(self, db, now):
        latest = _latest_observation(db)
        latest_ts = latest.timestamp if latest else None
        return {
            "id": self.source_id,
            "name": self.name,
            "kind": self.kind,
            "status": "online" if latest_ts else "offline",
            "status_detail": "derived",
            "last_update": latest_ts.isoformat() if latest_ts else None,
            "variables": self.variables,
            "coverage_pct": _coverage(db, ["sea_surface_temperature", "wave_height"]),
            "note": (
                "History-conditioned statistical model (validated trend/baseline), fit to the most recent "
                "observation window. Forecasting pipeline is explainable and evaluated by rolling MAE."
            ),
        }


class ArgoPlugin(SensorPlugin):
    source_id = "argo"
    name = "Argo floats"
    kind = "observation"
    variables = ["Sea temperature", "Salinity"]

    def info(self, db, now):
        argo_last, argo_floats, argo_levels = _argo_info(db)
        locations = max(len(db.query(OceanLocation).all()), 1)
        return {
            "id": self.source_id,
            "name": self.name,
            "kind": self.kind,
            "status": "online" if argo_last else "simulated",
            "status_detail": data_status_for("ARGO", argo_last, now) if argo_last
                            else data_status_for("ARGO_SIM", argo_last, now),
            "last_update": argo_last.isoformat() if argo_last else None,
            "variables": self.variables,
            "coverage_pct": round(argo_floats / locations * 100.0, 1) if argo_last else 0.0,
            "note": (
                f"Real Argo GDAC float profiles ingested ({argo_floats} floats, "
                f"{argo_levels} depth levels). Fetched by scripts.fetch_argo and "
                f"ingested with scripts.ingest_argo."
                if argo_last else
                "Trajectory simulator with synthetic WMO floats. Live Argo integration is pending "
                "(see integration_pending); values are simulated and labelled as such."
            ),
        }


class OceanModelGridPlugin(SensorPlugin):
    source_id = "ocean_model_grid"
    name = "Real ocean model (HYCOM 3D grid)"
    kind = "model"
    variables = ["Sea temperature", "Salinity", "Current speed"]

    def info(self, db, now):
        model_last, model_vars, _ = _model_grid_info(db)
        return {
            "id": self.source_id,
            "name": self.name,
            "kind": self.kind,
            "status": "online" if model_last else "integration pending",
            "status_detail": data_status_for("HYCOM", model_last, now) if model_last else "data not ingested yet",
            "last_update": model_last.isoformat() if model_last else None,
            "variables": model_vars or self.variables,
            "coverage_pct": round(len(model_vars) / len(GRID_SOURCES) * 100.0, 1),
            "note": (
                "Real US Navy HYCOM+NCODA GLBu0.08 (global 1/12°) 3D ocean-model grid — "
                "sea temperature, salinity and current speed at multiple depth levels "
                "(features #3/#5/#6/#7). Not ingested yet on this machine: run "
                "scripts.fetch_model + scripts.ingest_netcdf on a networked host to "
                "populate the depth slices."
            ),
        }


class PhysicsEnginePlugin(SensorPlugin):
    source_id = "physics_engine"
    name = "Physics engine (derived)"
    kind = "derived"
    variables = ["Dissolved oxygen", "Chlorophyll", "pH", "Density", "Nutrients"]

    def info(self, db, now):
        latest = _latest_observation(db)
        latest_ts = latest.timestamp if latest else None
        return {
            "id": self.source_id,
            "name": self.name,
            "kind": self.kind,
            "status": "online",
            "status_detail": "derived",
            "last_update": latest_ts.isoformat() if latest_ts else None,
            "variables": self.variables,
            "coverage_pct": _coverage(db, ["dissolved_oxygen", "chlorophyll"]),
            "note": (
                "Local bio-physical derivation from surface state (oxygen/chlorophyll/pH/density). "
                "Derived estimates, not direct measurements."
            ),
        }


class GliderPlugin(SensorPlugin):
    source_id = "gliders"
    name = "Glider deployments (IOOS NGDAC)"
    kind = "observation"
    variables = ["Sea temperature", "Salinity", "Dissolved oxygen", "Chlorophyll", "Nitrate"]

    def info(self, db, now):
        glider_last, glider_n, glider_samples, glider_bgc = _glider_info(db)
        locations = max(len(db.query(OceanLocation).all()), 1)
        return {
            "id": self.source_id,
            "name": self.name,
            "kind": self.kind,
            "status": "online" if glider_last else "integration pending",
            "status_detail": data_status_for("GLIDER", glider_last, now) if glider_last else "data not ingested yet",
            "last_update": glider_last.isoformat() if glider_last else None,
            "variables": self.variables,
            "coverage_pct": round(glider_n / locations * 100.0, 1) if glider_last else 0.0,
            "note": (
                f"Real IOOS National GliderDAC deployments ingested ({glider_n} deployments, "
                f"{glider_samples} samples, {glider_bgc} BGC samples) — features #16 glider "
                f"+ #17 CTD/BGC. Fetched by scripts.fetch_glider and ingested with "
                f"scripts.ingest_glider."
                if glider_last else
                "Glider deployments are not ingested yet on this machine: run scripts.fetch_glider "
                "+ scripts.ingest_glider on a networked host (feature #16, with BGC fields "
                "dissolved oxygen / chlorophyll / nitrate per feature #17)."
            ),
        }


class ErsstPlugin(SensorPlugin):
    source_id = "ersst"
    name = "NOAA ERSST v5 (real SST grid)"
    kind = "observation"
    variables = ["Sea surface temperature"]

    def info(self, db, now):
        ersst_last, ersst_coverage = _ersst_info(db)
        return {
            "id": self.source_id,
            "name": self.name,
            "kind": self.kind,
            "status": "online" if ersst_last else "offline",
            "status_detail": data_status_for("ERSST", ersst_last, now),
            "last_update": ersst_last.isoformat() if ersst_last else None,
            "variables": self.variables,
            "coverage_pct": ersst_coverage,
            "note": (
                "Real NOAA ERSST v5 gridded analysis (2-degree, monthly) built from in-situ "
                "ship/buoy observations. It is a historical archive (newest month: "
                f"{ersst_last.strftime('%Y-%m') if ersst_last else 'n/a'}) — not a live feed "
                "and not a satellite product."
            ),
        }


class SatellitePlugin(SensorPlugin):
    source_id = "satellite"
    name = "Satellite ocean colour (Chl)"
    kind = "observation"
    variables = ["Chlorophyll (chlor_a)"]

    def info(self, db, now):
        chlor_last, chlor_coverage = _chlor_info(db)
        return {
            "id": self.source_id,
            "name": self.name,
            "kind": self.kind,
            "status": "online" if chlor_last else "integration pending",
            "status_detail": data_status_for("CHLOROPHYLL", chlor_last, now) if chlor_last else "data not ingested yet",
            "last_update": chlor_last.isoformat() if chlor_last else None,
            "variables": self.variables,
            "coverage_pct": chlor_coverage,
            "note": (
                "Real satellite ocean colour: NOAA CoastWatch Geo-Polar Blended VIIRS-Himawari-NPP "
                "Chlorophyll-a (5 km), composited to a monthly mean over the Indian region by "
                "scripts.fetch_chlor. Not ingested yet on this machine: run fetch_chlor + "
                "ingest_netcdf on a networked host to populate it."
            ),
        }


# Register the built-in sources (feature #20 - at import time, runtime-swappable).
for _plugin_cls in (OpenMeteoPlugin, ModelEstimatePlugin, ArgoPlugin, GliderPlugin,
                    OceanModelGridPlugin, PhysicsEnginePlugin, ErsstPlugin, SatellitePlugin):
    register(_plugin_cls)


def data_sources(db: Session) -> dict:
    """Public entry point (unchanged contract) -> plugin-driven build."""
    return build_sources(db)


__all__ = ["data_sources", "SOURCE_ORDER", "MODEL_KIND", "REAL_SOURCE"]