"""
TidalTwin - Acidification: acidification zones
==============================================
Acidification zones are the plan-view companion to the depth layers: measured
pH levels aggregated onto a coarse 0.5-degree grid, so "where is the ocean
acidifying" reads off a map instead of a scatter plot.

Rules
-----
* A zone cell is only ever built from REAL stored samples; the cell carries
  ``n_samples`` and ``n_floats`` so thin evidence is visible rather than
  looking like a solid field.
* ``is_zone`` means the worst sample in the cell scored MODERATE or worse
  (pH < 8.00 on the 1-based ladder).  ``is_undersaturated`` is the separate,
  harder biological test: aragonite below 1.0 in any sample in the cell.
* Both thresholds come from ``units`` so the grid, the ingest classifier and the
  hotspot scorer cannot drift apart.
* The depth band filter lets the same grid be drawn per layer, which is what
  makes the depth-slider view honest rather than a single blended average.
"""

from __future__ import annotations

from app.modules.ai.acidification.units import (
    ARAGONITE_SATURATION,
    SEVERITY_ORDINALS,
    depth_band_for_depth,
    severity_label_for_ordinal,
)

ZONE_GRID_STEP = 0.5
# MODERATE on the 1-based severity ladder (units.SEVERITY_ORDINALS), i.e. the
# worst sample in the cell is below pH 8.00.
ZONE_THRESHOLD_ORDINAL = SEVERITY_ORDINALS["MODERATE"]


def _cell_key(latitude: float, longitude: float) -> tuple[int, int]:
    return (
        int((latitude + 0.0) // ZONE_GRID_STEP),
        int((longitude + 0.0) // ZONE_GRID_STEP),
    )


def _cell_center(row: int, col: int) -> tuple[float, float]:
    return (
        round(col * ZONE_GRID_STEP + ZONE_GRID_STEP / 2, 4),
        round(row * ZONE_GRID_STEP + ZONE_GRID_STEP / 2, 4),
    )


def build_zones(
    records: list[dict],
    min_depth: float | None = None,
    max_depth: float | None = None,
    band: str | None = None,
    threshold_ordinal: int = ZONE_THRESHOLD_ORDINAL,
) -> dict:
    """Aggregate measured pH onto the grid, per depth window.

    ``records`` are the normalised sample dicts (need ``latitude``,
    ``longitude``, ``depth_m``, ``ph_total``, ``severity_ordinal``).
    """
    cells: dict[tuple[int, int], list[dict]] = {}
    for rec in records:
        depth = rec.get("depth_m")
        if depth is None:
            continue
        if min_depth is not None and depth < min_depth:
            continue
        if max_depth is not None and depth > max_depth:
            continue
        if band and depth_band_for_depth(depth) != band:
            continue
        cells.setdefault(_cell_key(rec["latitude"], rec["longitude"]), []).append(rec)

    zones: list[dict] = []
    for key, recs in cells.items():
        center_lon, center_lat = _cell_center(*key)
        values = [r["ph_total"] for r in recs if r.get("ph_total") is not None]
        ordinals = [
            r["severity_ordinal"] for r in recs if r.get("severity_ordinal") is not None
        ]
        if not values:
            continue
        worst_ordinal = max(ordinals) if ordinals else None
        # Mean omega is reported only over samples that actually have one.
        # A cell of 40 samples where 4 have a derived aragonite must not report
        # a mean over the other 36 as if it were measured.
        omegas = [r["omega_arag"] for r in recs if r.get("omega_arag") is not None]
        zones.append(
            {
                "latitude": center_lat,
                "longitude": center_lon,
                "n_samples": len(recs),
                "n_floats": len({r.get("float_id") for r in recs if r.get("float_id")}),
                "mean_ph": round(sum(values) / len(values), 4),
                "min_ph": round(min(values), 4),
                "max_ph": round(max(values), 4),
                "mean_omega": round(sum(omegas) / len(omegas), 4) if omegas else None,
                "min_omega": round(min(omegas), 4) if omegas else None,
                "n_with_omega": len(omegas),
                "worst_ordinal": worst_ordinal,
                "worst_label": severity_label_for_ordinal(worst_ordinal),
                "is_zone": worst_ordinal is not None
                and worst_ordinal >= threshold_ordinal,
                "is_undersaturated": any(
                    o < ARAGONITE_SATURATION for o in omegas
                ),
                "depth_min": round(min(r["depth_m"] for r in recs), 1),
                "depth_max": round(max(r["depth_m"] for r in recs), 1),
            }
        )

    # Worst-first, then lowest pH: the cells that need attention lead.
    zones.sort(
        key=lambda z: (
            -z["worst_ordinal"] if z["worst_ordinal"] is not None else -1,
            z["mean_ph"],
        )
    )

    return {
        "grid_step_deg": ZONE_GRID_STEP,
        "band": band,
        "min_depth_m": min_depth,
        "max_depth_m": max_depth,
        "zone_count": sum(1 for z in zones if z["is_zone"]),
        "undersaturated_count": sum(1 for z in zones if z["is_undersaturated"]),
        "cells_with_data": len(zones),
        "zones": zones,
        "threshold_note": (
            "A cell counts as an acidification zone when its worst stored sample "
            "measures below pH 8.00 (policy MODERATE+), and as aragonite "
            "undersaturated when any sample in it has a DERIVED Omega_arag below "
            f"{ARAGONITE_SATURATION}. Aragonite is derived, not measured, and only "
            "exists for levels that carried both temperature and salinity."
        ),
    }
