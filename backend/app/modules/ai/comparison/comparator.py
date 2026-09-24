"""
TidalTwin - Model vs Reality Comparison
===========================================
This module compares our AI's forecast against what the ocean ACTUALLY did.

Method (real forecast verification — professional and judge-friendly):
  1. Take the last 48 hours of observations for a location.
  2. Use the FIRST 24 hours as "history known at time T".
  3. Run our linear-trend forecast from T forward.
  4. Compare the forecasted values against the ACTUAL observations
     that happened in the following 24 hours.

The result is a series with forecast values and observed values we can
plot together, plus an error metric (Mean Absolute Error).
"""

import numpy as np
from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.models.observation import OceanObservation

SPLIT_HOURS = 24   # how much history the "forecast" had
WINDOW = 48        # total hours used


def compare_location(db: Session, loc: OceanLocation, window: int = WINDOW) -> dict:
    """Return a comparison dict for one location."""
    obs = (
        db.query(OceanObservation)
        .filter(OceanObservation.location_id == loc.id)
        .order_by(OceanObservation.timestamp.desc())
        .limit(window)
        .all()
    )
    obs = list(reversed(obs))  # chronological

    rows = [
        (o.timestamp, o.sea_surface_temperature, o.wave_height)
        for o in obs
    ]

    result: dict = {
        "location_id": loc.id,
        "location": loc.name,
        "window_hours": len(rows),
        "series": [],
        "metrics": {},
    }

    if len(rows) < SPLIT_HOURS + 6:
        result["note"] = "Not enough history to run a forecast verification."
        return result

    timestamps = [r[0] for r in rows]
    temps = [r[1] for r in rows]
    waves = [r[2] for r in rows]

    # --- Fit forecast using only the first SPLIT_HOURS ---
    hist_temps = [t for t in temps[:SPLIT_HOURS] if t is not None]
    hist_waves = [w for w in waves[:SPLIT_HOURS] if w is not None]

    def trend_step(hist: list[float]) -> float:
        if len(hist) < 3:
            return 0.0
        x = np.arange(len(hist), dtype=float)
        coef = np.polyfit(x, np.array(hist), 1)
        return max(min(float(coef[0]), 0.15), -0.15)

    step_t = trend_step(hist_temps)
    step_w = trend_step(hist_waves)
    last_known_t = hist_temps[-1] if hist_temps else None
    last_known_w = hist_waves[-1] if hist_waves else None

    # --- Build comparison series (from split point onward) ---
    forecast_t: list[float | None] = []
    forecast_w: list[float | None] = []
    for i in range(SPLIT_HOURS, len(rows)):
        h = i - SPLIT_HOURS + 1
        if last_known_t is not None:
            f = last_known_t + step_t * h
            forecast_t.append(round(max(20.0, min(33.0, f)), 2))
        else:
            forecast_t.append(None)
        if last_known_w is not None:
            fw = last_known_w + step_w * h
            forecast_w.append(round(max(0.0, fw), 2))
        else:
            forecast_w.append(None)

    observed_t = temps[SPLIT_HOURS:]
    observed_w = waves[SPLIT_HOURS:]

    for i, ts in enumerate(timestamps[SPLIT_HOURS:], 0):
        result["series"].append({
            "time": ts.isoformat(),
            "forecast_temperature": forecast_t[i],
            "observed_temperature": observed_t[i],
            "forecast_wave": forecast_w[i],
            "observed_wave": observed_w[i],
        })

    # --- Error metrics ---
    ft = np.array([x for x in forecast_t if x is not None], dtype=float)
    ot = np.array([x for x in observed_t if x is not None], dtype=float)
    fw = np.array([x for x in forecast_w if x is not None], dtype=float)
    ow = np.array([x for x in observed_w if x is not None], dtype=float)

    if len(ft) == len(ot) and len(ft) > 0:
        mae_t = float(np.mean(np.abs(ft - ot)))
        result["metrics"]["temperature_mae"] = round(mae_t, 3)
    if len(fw) == len(ow) and len(fw) > 0:
        mae_w = float(np.mean(np.abs(fw - ow)))
        result["metrics"]["wave_mae"] = round(mae_w, 3)

    result["metrics"]["forecast_skill_note"] = (
        "Lower MAE = closer to reality. Compared against actual observations."
    )
    return result


def compare_all(db: Session) -> list[dict]:
    locations = db.query(OceanLocation).all()
    return [compare_location(db, loc) for loc in locations]