"""
TidalTwin - Microplastics Ingestion Script
=============================================
Pulls the NOAA NCEI global Marine Microplastics collection through the
microplastics connectors, normalises it, maps it onto the monitored coastal
regions and stores it.  Safe to run repeatedly: rows are upserted on
(source, source_record_id).

Usage:
    .venv\\Scripts\\python -m scripts.ingest_microplastics

Schedule it (cron, daily 04:00 IST):
    0 4 * * *  cd /srv/tidaltwin/backend && .venv/bin/python -m scripts.ingest_microplastics

The collection is an archive updated infrequently, so daily is generous; the
point is that new publications are picked up without a manual step.

Run scripts.init_db first if the microplastic_samples table does not yet exist.
"""

import json
import sys

from app.core.database import SessionLocal
from app.modules.ai.microplastics import engine
from app.modules.ai.microplastics import sources


def main() -> int:
    db = SessionLocal()
    try:
        print("Microplastics ingestion starting...")
        print(f"  endpoint: {sources.settings.MICROPLASTICS_NOAA_URL}")
        print(f"  window  : {sources.INDIA_BBOX}")

        summary = engine.ingest(db)
        engine.clear_cache()

        print(json.dumps(summary, indent=2, default=str))

        coverage = engine.coverage_report(db)
        print("\nCoverage:")
        print(json.dumps(coverage, indent=2, default=str))

        # Non-zero exit when nothing was retrieved, so a scheduler surfaces the
        # failure instead of silently recording a successful empty run.
        if summary["status"] != "OK":
            print("\n[!] No records were ingested. See connector reasons above.")
            return 1

        print(f"\n[ok] {summary['persistence']['total']} sample row(s) upserted.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
