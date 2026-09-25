"""
TidalTwin - AI / Ocean Intelligence Explanation Engine
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

    if status in ("unknown", "no data") or diff is None:
        observed = res.get("observed")
        if observed is not None:
            what = (
                f"A {meta['label'].lower()} reading of {observed:g}{meta['unit']} is available at {loc.name}, "
                "but there is not enough eligible history to calculate a comparison baseline."
            )
            explanation = (
                f"The measurement comes from {res.get('observation_source', 'an unrecorded source')}. "
                f"{res.get('model_note') or 'More eligible historical measurements are needed before a difference can be calculated.'}"
            )
        else:
            what = (
                f"There is not enough eligible {meta['label'].lower()} reading data at {loc.name} "
                "to compare a measurement with a historical baseline yet."
            )
            explanation = (
                "The comparison is unavailable because no eligible reading is available. "
                f"{res.get('note', 'A difference or cause cannot be determined.')}"
            )
        cause = "There is not enough evidence to identify a cause."
        evidence = [
            f"Variable: {meta['label']}",
            f"Data status: {res.get('provenance_status', 'UNKNOWN')}",
            *( [f"Measurement: {res.get('observed')}{meta['unit']}"] if res.get("observed") is not None else [] ),
            *( [f"Source: {res.get('observation_source')}"] if res.get("observation_source") else [] ),
        ]
        magnitude_note = None
    elif status == "low":
        what = (
            f"At {loc.name}, the latest eligible {meta['label'].lower()} reading is close to "
            "the historical baseline, within the comparison's low-disagreement range."
        )
        explanation = (
            f"The eligible reading and historical baseline differ by {abs(diff or 0.0):.1f}{meta['unit']}. "
            "This comparison does not indicate a significant mismatch."
        )
        cause = "No cause is indicated because the observation and estimate agree closely."
        evidence = [
            f"Difference: {diff:+.1f}{meta['unit']} "
            f"({res.get('percent_difference') or 0:+.1f}%)",
            f"Agreement band: {status}",
        ]
        magnitude_note = f"Difference is within the normal band (< {meta['moderate']}{meta['unit']})."
    else:
        direction = "higher than" if (diff or 0) > 0 else "lower than"
        comparison_direction = "above the historical baseline" if (diff or 0) > 0 else "below the historical baseline"
        nearby_txt = _nearby_agreement_txt(db, loc.id, variable, depth_m, meta.get("column"), comparison_direction)

        explanation = (
            f"At {loc.name}, the latest eligible {meta['label'].lower()} reading is {abs(diff or 0.0):.1f}{meta['unit']} "
            f"{direction} the historical baseline. {nearby_txt}"
        )
        what = explanation
        cause = CAUSE_HINTS.get((variable, "above" if (diff or 0) > 0 else "below"))
        if not cause:
            cause = "Available data does not identify a cause for this difference."
        else:
            cause = "Possible drivers include " + cause[0].lower() + cause[1:] + " These are hypotheses, not confirmed causes."
        evidence = [
            f"Variable: {meta['label']}",
            f"Historical baseline: {res.get('baseline', res.get('model'))}{meta['unit']}",
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
        "confidence_basis": res.get("confidence_basis", "Heuristic disagreement score; it is not a probability that the cause is correct."),
        "explanation": explanation,
        "cause": cause,
        "data_status": res.get("data_status"),
        "status": status,
        "provenance_status": res.get("provenance_status", "UNKNOWN"),
        "limitations": [res.get("note")] if status in ("unknown", "no data") and res.get("note") else [],
    }


def _nearby_agreement_txt(
    db: Session, location_id: int, variable: str, depth_m: float, column: str | None, direction: str
) -> str:
    """Summarize whether other monitored regions deviate in the same direction."""
    if not column:
        return "There is no spatial comparison available for this variable."
    locs = db.query(OceanLocation).all()
    same = 0
    total = 0
    for loc in locs:
        if loc.id == location_id:
            continue
        r = compare(db, loc, variable=variable, depth_m=depth_m)
        d = r.get("difference")
        if d is None:
            continue
        total += 1
        if direction == "above the historical baseline" and d > 0:
            same += 1
        elif direction == "below the historical baseline" and d < 0:
            same += 1
    if total == 0:
        return "Other regions do not have enough observations to assess spatial extent."
    frac = same / total
    if frac >= 0.5:
        return (
            f"{same} of {total} other monitored regions show a similar deviation. "
            "This supports a regional pattern but does not establish its cause."
        )
    return (
        f"Most other monitored regions do not share this deviation ({same}/{total} in the same direction), "
        "so spatial extent is currently limited."
    )
