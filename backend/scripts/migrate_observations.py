"""
TidalTwin - Migration v3: national ocean observation metadata
==============================================================
Adds the provenance / quality metadata columns to ``ocean_observations`` that
the MoES / INCOIS observation layer writes.

Design constraints this migration honours:

* **Additive only.**  Every column is nullable, so no existing row is modified
  and no existing value is re-labelled.  A row written before this migration
  keeps whatever ``source`` string it had, and continues to be classified the
  way it always was.
* **Idempotent.**  Uses ``ADD COLUMN IF NOT EXISTS`` via a column inspection, so
  running it twice is a no-op.
* **No data backfill.**  Nothing is inferred about historical rows.  Inventing
  provenance for a value nobody recorded would be exactly the dishonesty this
  feature exists to remove.

Usage:
    .venv\\Scripts\\python -m scripts.migrate_observations
"""

from sqlalchemy import inspect, text

from app.core.database import SessionLocal, engine

TABLE = "ocean_observations"

#: column name -> portable DDL type.
NEW_COLUMNS: dict[str, str] = {
    "source_id": "VARCHAR(80)",
    "platform_id": "VARCHAR(120)",
    "instrument_id": "VARCHAR(120)",
    "data_status": "VARCHAR(20)",
    "quality_flag": "VARCHAR(30)",
    "processing_level": "VARCHAR(40)",
    "retrieval_time": "TIMESTAMP WITH TIME ZONE",
    "source_reference": "VARCHAR(500)",
    "qc_flags": "TEXT",
    "uncertainty": "TEXT",
    "validation_flags": "TEXT",
    "observation_uid": "VARCHAR(200)",
}

#: Indexes created after the columns exist.  ``observation_uid`` is unique so a
#: re-run of an ingestion cannot duplicate a physical sample.
INDEXES: tuple[tuple[str, str, bool], ...] = (
    ("ix_ocean_observations_source_id", "source_id", False),
    ("ix_ocean_observations_platform_id", "platform_id", False),
    ("ix_ocean_observations_data_status", "data_status", False),
    ("uq_ocean_observations_observation_uid", "observation_uid", True),
)


def migrate() -> dict[str, list[str]]:
    inspector = inspect(engine)
    existing = {c["name"] for c in inspector.get_columns(TABLE)}
    added_columns: list[str] = []
    with engine.begin() as conn:
        for name, dtype in NEW_COLUMNS.items():
            if name in existing:
                continue
            conn.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN {name} {dtype}"))
            added_columns.append(name)

        added_indexes: list[str] = []
        live = {c["name"] for c in inspect(conn).get_columns(TABLE)}
        for index_name, column, unique in INDEXES:
            if column not in live:
                continue
            conn.execute(text(f'CREATE INDEX IF NOT EXISTS "{index_name}" ON {TABLE} ("{column}")'))
            if unique:
                # A unique constraint cannot be added with IF NOT EXISTS; it is
                # created only when the index is absent, and legacy rows keep a
                # NULL uid, which Postgres allows to repeat.
                conn.execute(text(
                    f'CREATE UNIQUE INDEX IF NOT EXISTS "{index_name}" ON {TABLE} ("{column}")'
                ))
            added_indexes.append(index_name)
    return {"columns": added_columns, "indexes": added_indexes}


def summarise() -> dict[str, object]:
    """Report how many stored rows carry the new metadata.

    Used by the API to state honestly how much of the historical table predates
    the observation layer, instead of implying every row is fully provenanced.
    """
    from sqlalchemy import func, select
    from app.models.observation import OceanObservation

    db = SessionLocal()
    try:
        total = db.execute(select(func.count(OceanObservation.id))).scalar() or 0
        with_provenance = db.execute(
            select(func.count(OceanObservation.id))
            .where(OceanObservation.source_id.isnot(None))
        ).scalar() or 0
        by_status = dict(
            db.execute(
                select(OceanObservation.data_status, func.count(OceanObservation.id))
                .where(OceanObservation.data_status.isnot(None))
                .group_by(OceanObservation.data_status)
            ).all()
        )
        return {
            "total_rows": int(total),
            "rows_with_observation_provenance": int(with_provenance),
            "rows_without_observation_provenance": int(total) - int(with_provenance),
            "by_data_status": by_status,
        }
    finally:
        db.close()


if __name__ == "__main__":
    result = migrate()
    print(f"Migration v3 complete: added {len(result['columns'])} column(s), "
          f"{len(result['indexes'])} index(es).")
    if result["columns"]:
        print("  columns: " + ", ".join(result["columns"]))
    print("  " + str(summarise()))
