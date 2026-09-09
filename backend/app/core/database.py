"""
OceanVerse AI - Database Connection
===================================
This module creates the connection between our backend and the
PostgreSQL + PostGIS database.

Think of this as a bridge: our Python code sends questions here,
and it carries them to the database and brings back answers.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

# Create the database engine (the actual connection manager)
# `pool_pre_ping` keeps connections healthy.
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=False,  # set True to see all SQL in terminal (good for debugging!)
)

# SessionLocal is a "stamp" we use to create database sessions.
# A session = one conversation with the database.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base is the blueprint foundation for all our database tables/models.
# Every model we create later will inherit from this.
Base = declarative_base()


def get_db():
    """
    FastAPI dependency that provides a database session.
    Each request gets its own session and it's always closed after.

    This is a standard, safe pattern recommended by FastAPI.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
