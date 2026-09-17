"""TidalTwin - export a machine-readable TIDE benchmark artifact.

Writes the real output of the existing Phase 8 benchmark framework to a
timestamped JSON file under ``docs/benchmark-results/``. It never overwrites a
previous artifact: the timestamp plus a numeric suffix guarantee uniqueness.

Usage (from ``backend/``):
    python -m scripts.export_benchmark                      # budget 1, seed 42
    python -m scripts.export_benchmark --budget 3 --seed 42
    python -m scripts.export_benchmark --use-events         # event-based cases

The artifact contains the dataset description, configuration, fairness note,
per-strategy aggregates, raw rows, timing and the scientific-boundary /
limitations blocks produced by the framework itself. No value is fabricated.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from app.core.database import SessionLocal
from app.modules.ai.tide import validation


def _output_dir() -> Path:
    root = Path(__file__).resolve().parents[2]
    out = root / "docs" / "benchmark-results"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _unique_path(out_dir: Path, stem: str) -> Path:
    candidate = out_dir / f"{stem}.json"
    counter = 1
    while candidate.exists():
        candidate = out_dir / f"{stem}-{counter}.json"
        counter += 1
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a timestamped TIDE benchmark JSON artifact.")
    parser.add_argument("--budget", type=int, default=1, help="Observation budget per case (1-10).")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible baselines.")
    parser.add_argument("--depth-m", type=float, default=0.0, help="Depth in metres for the cases.")
    parser.add_argument("--use-events", action="store_true", help="Use detected events as cases when available.")
    args = parser.parse_args()

    if args.budget < 1 or args.budget > 10:
        parser.error("--budget must be between 1 and 10")

    db = SessionLocal()
    try:
        report = validation.run_database_benchmark(
            db,
            depth_m=args.depth_m,
            budget=args.budget,
            seed=args.seed,
            use_events=args.use_events,
        )
        # Attach the algorithm-consistency and edge-case evidence alongside the
        # benchmark so a single file is self-contained and auditable.
        report["consistency"] = {
            "sensitivity": validation.sensitivity_report(),
            "edge_cases": validation.edge_case_report(),
        }
    finally:
        db.close()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = f"tide-benchmark_{stamp}_budget{args.budget}_seed{args.seed}"
    path = _unique_path(_output_dir(), stem)
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print(f"[tidaltwin] Benchmark artifact written: {path}")
    print(f"[tidaltwin] algorithm={report['algorithm_version']} budget={args.budget} "
          f"seed={args.seed} cases={len(report['configuration']['cases'])}")
    degenerate = report["selection"]["pool_is_degenerate"]
    print(f"[tidaltwin] pool_is_degenerate={degenerate} (selection differentiation may be unavailable)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
