"""
OceanVerse AI - Demo Anomaly Simulator
======================================
Simulates a realistic ocean event (e.g. a marine heat-wave / wave surge)
so judges can SEE the anomaly-detection AI fire an alert.

It writes a series of slightly-elevated observations to one location,
then runs the detector so it flags the event.

This is a legitimate demo technique: we engineer a known scenario to
prove the AI pipeline catches it. In production the detector runs
continuously on REAL data (it also works now, but the real sea is calm).

Usage:
    .venv\\Scripts\\python -m scripts.simulate_anomaly --location goa --kind heatwave
"""

import argparse
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.modules.ai.anomaly.detector import scan_all_locations
from app.modules.physics.ocean_profiles import derive_surface


LOCATION_ALIASES = {
    "mumbai": "Arabian Sea (Mumbai Coast)",
    "chennai": "Bay of Bengal (Chennai Coast)",
    "mannar": "Gulf of Mannar",
    "kochi": "Kerala Coast (Kochi)",
    "goa": "Goa Coast (Panaji)",
    "andaman": "Andaman Sea",
    "lakshadweep": "Lakshadweep Sea",
    "puri": "Odisha Coast (Puri)",
}


def _enrich(obs: OceanObservation, loc: OceanLocation):
    """Fill derived bio-physical variables from the physics engine."""
    surf = derive_surface(
        loc,
        obs.sea_surface_temperature,
        obs.salinity,
        obs.wave_height,
        obs.current_speed,
    )
    obs.depth_m = 0.0
    obs.dissolved_oxygen = surf["dissolved_oxygen"]
    obs.chlorophyll = surf["chlorophyll"]
    obs.ph = surf["ph"]
    obs.pressure = surf["pressure"]
    obs.density = surf["density"]
    obs.nutrients = surf["nutrients"]
    return obs


def simulate(db: Session, location_name: str, kind: str) -> int:
    loc = (
        db.query(OceanLocation)
        .filter(OceanLocation.name == location_name)
        .first()
    )
    if not loc:
        raise SystemExit(f"Location not found: {location_name}")

    base = (
        db.query(OceanObservation)
        .filter(OceanObservation.location_id == loc.id)
        .order_by(OceanObservation.timestamp.desc())
        .first()
    )
    if not base:
        raise SystemExit("No base observations — sync ocean data first.")

    # Find the latest timestamp to start simulating from
    t = base.timestamp

    # How many fake readings to inject (each hour)
    n_hours = 8
    if kind == "heatwave":
        # Start normal, then raise temperature ~2°C over 6 hours (anomaly)
        steps = [0.0, 0.4, 0.8, 1.3, 1.8, 2.2, 2.3, 2.2]  # delta from base temp
        for i in range(n_hours):
            t = t + timedelta(hours=1)
            obs = OceanObservation(
                location_id=loc.id,
                timestamp=t,
                sea_surface_temperature=(base.sea_surface_temperature or 28) + steps[i],
                wave_height=base.wave_height,
                source="SIMULATED_HEATWAVE",
                data_type="observation",
            )
            _enrich(obs, loc)
            db.add(obs)
        db.commit()
        print(f"Simulated a marine heat-wave at {loc.name} (+{steps[-1]}°C).")
    elif kind == "surge":
        # Sudden wave jump to 2.8m
        steps = [0.0, 0.6, 1.4, 2.1, 2.8, 2.6, 2.0, 1.5]
        for i in range(n_hours):
            t = t + timedelta(hours=1)
            obs = OceanObservation(
                location_id=loc.id,
                timestamp=t,
                sea_surface_temperature=base.sea_surface_temperature,
                wave_height=(base.wave_height or 1.0) + steps[i],
                source="SIMULATED_SURGE",
                data_type="observation",
            )
            _enrich(obs, loc)
            db.add(obs)
        db.commit()
        print(f"Simulated a wave surge at {loc.name} (peak {(base.wave_height or 1.0) + 2.8:.1f} m).")
    else:
        raise SystemExit("kind must be 'heatwave' or 'surge'")

    # Now run the AI radar to detect the event we just engineered
    summary = scan_all_locations(db)
    print(f"AI scan: {summary}")
    return summary["alerts_created"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--location", default="goa", help="city alias: goa, mumbai, chennai...")
    parser.add_argument("--kind", default="heatwave", choices=["heatwave", "surge"])
    args = parser.parse_args()

    db = SessionLocal()
    try:
        name = LOCATION_ALIASES.get(args.location.lower(), args.location)
        created = simulate(db, name, args.kind)
        print(f"Alerts created: {created}")
    finally:
        db.close()


if __name__ == "__main__":
    main()