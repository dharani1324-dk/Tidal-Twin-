"""
OceanVerse AI - Ocean Data Refresh Script
=========================================
Fetches REAL ocean data from Open-Meteo Marine API
and stores it for every location in the database.

Usage:
    .venv\\Scripts\\python -m scripts.refresh_ocean_data
"""

from app.core.database import SessionLocal
from app.services.ocean_data import refresh_all_locations


def main():
    db = SessionLocal()
    try:
        summary = refresh_all_locations(db, forecast_days=2)
        print("Ocean data refresh complete:")
        print(summary)
    finally:
        db.close()


if __name__ == "__main__":
    main()
