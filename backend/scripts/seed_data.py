"""
OceanVerse AI - Seed Script
===========================
Adds starter data to the database so the app has something to show.

Currently seeds a set of ocean locations around India's coastline
(e.g. Arabian Sea, Bay of Bengal, Gulf of Mannar, etc.).

Usage:
    .venv\\Scripts\\python -m scripts.seed_data
Safe to run multiple times (won't duplicate locations with same name).
"""

from sqlalchemy.orm import Session
from geoalchemy2.shape import from_shape
from shapely.geometry import Point

from app.core.database import SessionLocal, engine
import app.models  # noqa: F401
from app.models.location import OceanLocation

# A helper to build a small polygon around a point (a simple square "zone")
def make_zone(lat, lon, half_deg=1.0):
    return from_shape(
        Point(lon, lat).buffer(half_deg),
        srid=4326,
    )


# List of initial ocean locations (focused on India for the SIH theme)
LOCATIONS = [
    # name, latitude, longitude, region_type, country
    ("Arabian Sea (Mumbai Coast)", 18.9, 72.0, "sea", "India"),
    ("Bay of Bengal (Chennai Coast)", 13.0, 80.3, "bay", "India"),
    ("Gulf of Mannar", 9.0, 78.5, "gulf", "India"),
    ("Kerala Coast (Kochi)", 9.9, 76.3, "coastal", "India"),
    ("Goa Coast (Panaji)", 15.5, 73.8, "coastal", "India"),
    ("Andaman Sea", 11.5, 92.5, "sea", "India"),
    ("Lakshadweep Sea", 10.5, 72.5, "sea", "India"),
    ("Odisha Coast (Puri)", 19.8, 85.8, "coastal", "India"),
]


def seed_locations(db: Session):
    count = 0
    for name, lat, lon, rtype, country in LOCATIONS:
        exists = db.query(OceanLocation).filter(OceanLocation.name == name).first()
        if exists:
            continue
        loc = OceanLocation(
            name=name,
            region_type=rtype,
            country=country,
            geom=make_zone(lat, lon),
        )
        db.add(loc)
        count += 1
    db.commit()
    print(f"Seeded {count} new ocean locations.")


def seed_all():
    db = SessionLocal()
    try:
        seed_locations(db)
    finally:
        db.close()


if __name__ == "__main__":
    seed_all()
