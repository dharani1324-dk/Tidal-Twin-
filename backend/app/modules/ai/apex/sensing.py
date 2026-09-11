"""Remote-Sensing Harmonization — satellite data fusion layer.

Maps every monitored variable to its best satellite source and produces a
harmonized per-region view: primary sensor, spatial resolution, revisit,
latency and the multi-source confidence boost you get by fusing instruments
instead of trusting a single pixel.

Offline + explainable: capability tables are fixed constants; per-region
availability is derived from the live observation stream, so the answer
always reflects what the platform actually has.
"""

from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.modules.ai.validation.engine import _latest_rows, observation_confidence

# Satellite capability catalogue (name → payload → variables it serves).
CATALOGUE = [
    {"satellite": "NOAA AVHRR", "variable": "SST", "resolution_km": 4.0, "resolution_m": 4000.0,
     "revisit_h": 6, "latency_h": 3, "reliability": 0.90},
    {"satellite": "Sentinel-3 SLSTR", "variable": "SST", "resolution_km": 1.0, "resolution_m": 1000.0,
     "revisit_h": 12, "latency_h": 6, "reliability": 0.93},
    {"satellite": "Sentinel-2 MSI", "variable": "Chlorophyll", "resolution_km": 0.01, "resolution_m": 10.0,
     "revisit_h": 120, "latency_h": 24, "reliability": 0.85},
    {"satellite": "Copernicus GlobOcean", "variable": "Wave / Current", "resolution_km": 8.0, "resolution_m": 8000.0,
     "revisit_h": 3, "latency_h": 4, "reliability": 0.88},
    {"satellite": "VIIRS DNB", "variable": "Night Lights", "resolution_km": 0.75, "resolution_m": 750.0,
     "revisit_h": 24, "latency_h": 12, "reliability": 0.80},
    {"satellite": "OCO-2 / GOSAT", "variable": "XCO2", "resolution_km": 10.0, "resolution_m": 10000.0,
     "revisit_h": 192, "latency_h": 72, "reliability": 0.82},
]

VARIABLE_MAP = {
    "SST": ["sea_surface_temperature"],
    "Chlorophyll": ["chlorophyll"],
    "Wave / Current": ["wave_height", "current_speed"],
    "Night Lights": [],
    "XCO2": [],
}

# Primary (highest-reliability) source per variable for fusion.
PRIMARY = {c["variable"]: c for c in CATALOGUE}


def _sources_for(variable: str) -> list[dict]:
    return [dict(c) for c in CATALOGUE if c["variable"] == variable]


def remote_sensing_fusion(db: Session) -> dict:
    """Harmonized satellite view + multi-source confidence boost per region."""
    regions = []
    per_variable = {}

    for loc in db.query(OceanLocation).all():
        obs = _latest_rows(db, loc, window=96)
        present = set()
        if obs:
            latest = obs[-1]
            for var, cols in VARIABLE_MAP.items():
                if any(getattr(latest, c) is not None for c in cols):
                    present.add(var)

        variable_view = []
        for var in PRIMARY:
            src = PRIMARY[var]
            reliability = src["reliability"]
            # Availability fraction from the live stream for this variable class.
            cols = VARIABLE_MAP[var]
            n_have = sum(1 for o in obs if any(getattr(o, c) is not None for c in cols))
            availability = round(n_have / max(1, len(obs)), 3) if obs else 0.0
            active = var in present or (cols and availability > 0)
            variable_view.append({
                "variable": var,
                "primary_satellite": src["satellite"],
                "resolution": src["resolution_m"],
                "revisit_h": src["revisit_h"],
                "latency_h": src["latency_h"],
                "reliability": reliability,
                "availability": availability,
                "active": active,
            })

        # Fusion boost: incremental information gain over the best single
        # source — combining instruments reduces blind-spot probability,
        # but the headline gain over the primary sensor stays in single digits.
        good = [v for v in variable_view if v["active"]]
        if good:
            best = max(v["reliability"] for v in good)
            fused_miss = 1.0
            for v in good:
                fused_miss *= (1 - v["reliability"])
            boost = round(min(15.0, max(0.0, (1 - fused_miss - best) * 100)), 1)
        else:
            boost = 0.0

        conf = observation_confidence(db)
        base_conf = next((r for r in conf.get("regions", []) if r["location_id"] == loc.id), None)
        base = base_conf.get("observation_confidence", 70) if base_conf else 70

        regions.append({
            "location_id": loc.id,
            "location": loc.name,
            "variables": variable_view,
            "fused_confidence_boost_pct": boost,
            "single_source_confidence": base,
            "harmonized_confidence": round(min(100, base + boost * 0.5), 1),
            "sources_used": [v["primary_satellite"] for v in good],
        })

    per_variable = {
        var: _sources_for(var)
        for var in PRIMARY
    }
    return {
        "engine": "Remote-Sensing Harmonization & Data Fusion",
        "catalogue": CATALOGUE,
        "per_variable": per_variable,
        "regions": regions,
    }