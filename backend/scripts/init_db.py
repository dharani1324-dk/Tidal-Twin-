"""
OceanVerse AI - Database Schema Setup / Migration Helper
=======================================================
Run this to create all database tables from our models.

Usage:
    .venv\\Scripts\\python -m scripts.init_db

This imports our models (so SQLAlchemy knows about them),
then creates any tables that don't exist yet.
Safe to run multiple times.
"""

from app.core.database import Base, engine
import app.models  # noqa: F401  (ensures all models are registered)


def init_db():
    print("Creating database tables (if they don't exist)...")
    Base.metadata.create_all(bind=engine)
    print("Done. Tables are ready.")


if __name__ == "__main__":
    init_db()
