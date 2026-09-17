"""
TidalTwin - Migration v2: Ocean variable columns
====================================================
Adds the bio-physical variable columns (deep profile foundation) to
ocean_observations so the 4D forensics features have a place to live.

Safe to run anytime (uses ADD COLUMN IF NOT EXISTS).

Usage:
    .venv\Scripts\python -m scripts.migrate_v2
"""

from sqlalchemy import inspect, text

from app.core.database import SessionLocal, engine
from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.modules.physics.ocean_profiles import derive_surface


NEW_COLUMNS = {
    "depth_m": "FLOAT",
    "dissolved_oxygen": "FLOAT",
    "chlorophyll": "FLOAT",
    "ph": "FLOAT",
    "pressure": "FLOAT",
    "density": "FLOAT",
    "nutrients": "FLOAT",
}


def migrate():
    insp = inspect(engine)
    existing = {c["name"] for c in insp.get_columns("ocean_observations")}
    added = 0
    with engine.begin() as conn:
        for name, dtype in NEW_COLUMNS.items():
            if name in existing:
                continue
            conn.execute(text(f"ALTER TABLE ocean_observations ADD COLUMN {name} {dtype}"))
            added += 1
    print(f"Migration v2 complete: added {added} new column(s).")


def backfill():
    """Fill derived bio-physical variables for rows written before v2."""
    db = SessionLocal()
    try:
        updated = 0
        for loc in db.query(OceanLocation).all():
            rows = (
                db.query(OceanObservation)
                .filter(OceanObservation.location_id == loc.id)
                .filter(OceanObservation.dissolved_oxygen.is_(None))
                .all()
            )
            for o in rows:
                surf = derive_surface(loc, o.sea_surface_temperature, o.salinity,
                                      o.wave_height, o.current_speed)
                o.depth_m = 0.0
                o.dissolved_oxygen = surf["dissolved_oxygen"]
                o.chlorophyll = surf["chlorophyll"]
                o.ph = surf["ph"]
                o.pressure = surf["pressure"]
                o.density = surf["density"]
                o.nutrients = surf["nutrients"]
                updated += 1
        db.commit()
        print(f"Backfilled derived variables for {updated} existing row(s).")
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
    backfill()