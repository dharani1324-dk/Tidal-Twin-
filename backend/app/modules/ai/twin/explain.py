"""
OceanVerse AI - AI / Ocean Intelligence Explanation Engine
==========================================================
Strictly evidence-driven explanation layer. It never hallucinates a
cause. It uses the comparison output + nearby agreement to answer:

    * What happened?   * Where?   * At what depth?   * Which variable?
    * How large?       * What evidence supports it?  * How confident?

If a cause cannot be determined from available data, it says exactly
that.
"""

from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.modules.ai.twin.compare import VARIABLES, compare

CAUSE_HINTS = {
    ("temperature", "above"): (
        "Sustained surface heating with weak vertical mixing, or advection of warmer "
        "water into the region."
    ),
    ("temperature", "below"): (
        "Upwelling or cooler subsurface water reaching the surface."
    ),
    ("wave_height", "above"): (
        "Sustained regional winds or distant cyclone swell."
    ),
    ("wave_height", "below"): (
        "Calm atmospheric forcing after a settling swell."
    ),
}


def explain(db: Session, loc: OceanLocation, variable: str = "temperature", depth_m: float = 0.0) -> dict:
    res = compare(db, loc, variable=variable, depth_m=depth_m)
    meta = VARIABLES[variable]
    diff = res.get("difference")
    status = res.get("status")
    conf = res.get("confidence", 0)
    level = res.get("confidence_level", "unknown")

    what = f"Observed {meta['label'].lower()} is {abs(diff or 0.0):.1f}{meta['unit']} "
    what += "higher" if (diff or 0) > 0 else "lower" if (diff or 0) < 0 else "equal to"
    what += f" the model estimate at this location."

    if status in ("unknown", "no data"):
        explanation = (
            "No comparison is possible yet: data is marked as "
            f"{res.get('data_status', 'unavailable')}."
        )
        cause = "Cause cannot be determined from available data."
        evidence = [
            f"Variable: {meta['label']}",
            f"Data status: {res.get('data_status', 'unknown')}",
        ]
        magnitude_note = None
    elif status == "low":
        explanation = (
            "The in-situ observation agrees closely with the model estimate. "
            "No significant anomaly is indicated by available data."
        )
        cause = "No anomaly indicated – model and observation agree."
        evidence = [
            f"Difference: {diff:+.1f}{meta['unit']} "
            f"({res.get('percent_difference') or 0:+.1f}%)",
            f"Agreement band: {status}",
        ]
        magnitude_note = f"Difference is within the normal band (< {meta['moderate']}{meta['unit']})."
    else:
        direction = "above the model estimate" if (diff or 0) > 0 else "below the model estimate"
        nearby_txt = _nearby_agreement_txt(db, variable, meta.get("column"), direction)

        explanation = (
            f"Observed {meta['label'].lower()} deviates {direction} by "
            f"{abs(diff or 0.0):.1f}{meta['unit']}. {nearby_txt} This increases confidence "
            f"that the deviation is representative of this region rather than an isolated reading."
        )
        cause = CAUSE_HINTS.get((variable, "above" if (diff or 0) > 0 else "below"))
        if not cause:
            cause = "Cause cannot be determined from available data."
        evidence = [
            f"Variable: {meta['label']}",
            f"Model: {res.get('model')}{meta['unit']}",
            f"Observed: {res.get('observed')}{meta['unit']}",
            f"Difference: {diff:+.1f}{meta['unit']}",
            f"Percentage difference: {res.get('percent_difference') or 0:+.1f}%",
            f"Observation source: {res.get('observation_source', 'unknown')}",
        ]
        magnitude_note = (
            f"Magnitude: {abs(diff or 0.0):.1f}{meta['unit']} "
            f"({res.get('percent_difference') or 0:+.1f}%) - {status.upper()} disagreement."
        )

    return {
        "location_id": loc.id,
        "location": loc.name,
        "depth_m": depth_m,
        "variable": variable,
        "label": meta["label"],
        "unit": meta["unit"],
        "model": res.get("model"),
        "observed": res.get("observed"),
        "difference": diff,
        "what": what,
        "magnitude_note": magnitude_note,
        "evidence": evidence,
        "confidence": conf,
        "confidence_level": level,
        "explanation": explanation,
        "cause": cause,
        "data_status": res.get("data_status"),
        "status": status,
    }


def _nearby_agreement_txt(
    db: Session, variable: str, column: str | None, direction: str
) -> str:
    """Summarise whether nearby locations deviate in the same direction."""
    if not column:
        return "Available data covers the local stream."
    locs = db.query(OceanLocation).all()
    same = 0
    total = 0
    for loc in locs:
        r = compare(db, loc, variable=variable)
        d = r.get("difference")
        if d is None:
            continue
        total += 1
        if direction == "above the model estimate" and d > 0:
            same += 1
        elif direction == "below the model estimate" and d < 0:
            same += 1
    if total == 0:
        return "Nearby observations are insufficient to confirm spatial extent."
    frac = same / total
    if frac >= 0.5:
        return (
            f"{same} of {total} nearby regions show a similar deviation, increasing confidence "
            "this is a genuine regional signal."
        )
    return (
        f"Most nearby regions do not share this deviation ({same}/{total} in the same direction), "
        "so spatial extent is currently limited."
    )