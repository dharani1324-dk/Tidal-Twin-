"""
TidalTwin - Deoxygenation: low-oxygen zones
============================================
Zones are the plan-view companion to the depth layers: measured oxygen levels
aggregated onto a coarse 0.5-degree grid, so "where is the oxygen dropping"
reads off a map instead of a scatter plot.

Rules
-----
* A zone cell is only ever built from REAL stored samples; the cell carries
  ``n_samples`` so thin evidence is visible.
* ``is_zone`` means the worst sample in the cell scored MODERATE or worse
  (oxygen < 4 mg/L on the 1-based ladder); ``is_dead_zone`` means any sample
  measured below the 0.5 mg/L near-anoxic line.  Both thresholds are the
  documented policy classifier from ``units``.
* The depth band filter lets the same grid be drawn per layer, which is what
  makes the 3D/story views honest rather than a single blended average.
"""

from __future__ import annotations

from app.modules.ai.deoxygenation.units import (
    DEAD_ZONE_THRESHOLD_MG_L,
    SEVERITY_ORDINALS,
    depth_band_for_depth,
    severity_label_for_ordinal,
)

ZONE_GRID_STEP = 0.5
# MODERATE on the 1-based severity ladder (units.SEVERITY_ORDINALS), i.e. the
# worst sample in the cell is below 4 mg/L. This was previously 2, which is LOW
# on that scale and so flagged every cell - including 6.2 mg/L surface water -
# as a low-oxygen zone.
ZONE_THRESHOLD_ORDINAL = SEVERITY_ORDINALS["MODERATE"]


def _cell_key(latitude: float, longitude: float) -> tuple[int, int]:
    return (
        int((latitude + 0.0) // ZONE_GRID_STEP),
        int((longitude + 0.0) // ZONE_GRID_STEP),
    )


def _cell_center(row: int, col: int) -> tuple[float, float]:
    return round(col * ZONE_GRID_STEP + ZONE_GRID_STEP / 2, 4), round(
        row * ZONE_GRID_STEP + ZONE_GRID_STEP / 2, 4
    )


def build_zones(
    records: list[dict],
    min_depth: float | None = None,
    max_depth: float | None = None,
    band: str | None = None,
    threshold_ordinal: int = ZONE_THRESHOLD_ORDINAL,
) -> dict:
    """Aggregate measured oxygen onto the grid, per depth window.

    ``records`` are the normalised sample dicts (need ``latitude``,
    ``longitude``, ``depth_m``, ``do_mg_l``, ``severity_ordinal``).
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
        values = [r["do_mg_l"] for r in recs if r.get("do_mg_l") is not None]
        ordinals = [r["severity_ordinal"] for r in recs if r.get("severity_ordinal") is not None]
        if not values:
            continue
        worst_ordinal = max(ordinals) if ordinals else None
        zones.append({
            "latitude": center_lat,
            "longitude": center_lon,
            "n_samples": len(recs),
            "n_floats": len({r.get("float_id") for r in recs if r.get("float_id")}),
            "mean_mg_l": round(sum(values) / len(values), 4),
            "min_mg_l": round(min(values), 4),
            "max_mg_l": round(max(values), 4),
            "worst_ordinal": worst_ordinal,
            "worst_label": severity_label_for_ordinal(worst_ordinal),
            "is_zone": worst_ordinal is not None and worst_ordinal >= threshold_ordinal,
            "is_dead_zone": any(v < DEAD_ZONE_THRESHOLD_MG_L for v in values),
            "depth_min": round(min(r["depth_m"] for r in recs), 1),
            "depth_max": round(max(r["depth_m"] for r in recs), 1),
        })

    zones.sort(key=lambda z: (-z["worst_ordinal"] if z["worst_ordinal"] is not None else -1,
                              z["mean_mg_l"]))

    return {
        "grid_step_deg": ZONE_GRID_STEP,
        "band": band,
        "min_depth_m": min_depth,
        "max_depth_m": max_depth,
        "zone_count": sum(1 for z in zones if z["is_zone"]),
        "dead_zone_count": sum(1 for z in zones if z["is_dead_zone"]),
        "cells_with_data": len(zones),
        "zones": zones,
        "threshold_note": (
            "A cell counts as a low-oxygen zone when its worst stored sample "
            "measures below 4 mg/L (policy MODERATE+), and as a dead zone when "
            "any sample is below 0.5 mg/L (near anoxic)."
        ),
    }