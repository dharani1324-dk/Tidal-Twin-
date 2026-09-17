"""
TidalTwin - AI Forecast Module
==================================
Predicts short-term ocean conditions (temperature/waves) for each region
using a simple, explainable model: linear regression on recent readings
with a small polynomial fit for trend.

We deliberately keep it interpretable (for judges we can explain every
number) and fast (no huge model files).
"""

import numpy as np
from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.models.observation import OceanObservation


# Number of hours ahead we forecast
FORECAST_HORIZON = 12


def _fit_trend(values: list[float]) -> tuple[list[float], float, float]:
    """
    Fit a degree-1 polynomial (straight line) to the values.
    Return: (fitted points, slope, intercept).
    """
    n = len(values)
    if n < 3:
        return [], 0.0, 0.0
    x = np.arange(n, dtype=float)
    y = np.array(values, dtype=float)
    # Polyfit degree 1: y = slope*x + intercept
    coef = np.polyfit(x, y, 1)
    fitted = list(coef[0] * x + coef[1])
    return fitted, float(coef[0]), float(coef[1])


def forecast_location(db: Session, loc: OceanLocation, history: int = 24) -> dict:
    """
    Produce a 12-hour forecast for one location from its recent history.
    Returns a dict the API can serialize.
    """
    obs = (
        db.query(OceanObservation)
        .filter(OceanObservation.location_id == loc.id)
        .order_by(OceanObservation.timestamp.asc())
        .limit(history)
        .all()
    )
    if len(obs) < 4:
        return {
            "location_id": loc.id,
            "location": loc.name,
            "forecast": None,
            "note": "Need more history to forecast.",
        }

    times = [o.timestamp for o in obs]
    temps = [o.sea_surface_temperature for o in obs if o.sea_surface_temperature is not None]
    waves = [o.wave_height for o in obs if o.wave_height is not None]

    result: dict = {
        "location_id": loc.id,
        "location": loc.name,
        "generated_at": times[-1].isoformat(),
        "forecast": [],
    }

    # Forecast temperature
    if len(temps) >= 4:
        fitted, slope_t, _ = _fit_trend(temps)
        last_val = temps[-1]
        step = slope_t  # per-reading change
        # Clamp the step so we never forecast something absurd
        step = max(min(step, 0.15), -0.15)
        step = round(step, 4)

        for h in range(1, FORECAST_HORIZON + 1):
            pred_temp = last_val + step * h
            result["forecast"].append({
                "hours_ahead": h,
                "temperature": round(max(18.0, min(34.0, pred_temp)), 2),
            })

    # Forecast waves (same technique)
    if len(waves) >= 4:
        _, slope_w, _ = _fit_trend(waves)
        last_wave = waves[-1]
        step_w = max(min(slope_w, 0.08), -0.08)
        step_w = round(step_w, 4)
        for h in range(1, FORECAST_HORIZON + 1):
            pred_wave = last_wave + step_w * h
            result["forecast"][h - 1]["wave_height"] = round(max(0.0, pred_wave), 2)

    result["note"] = (
        "Linear-trend forecast from recent readings; "
        "refreshes as new observations arrive."
    )
    return result


def forecast_all(db: Session, history: int = 24) -> list[dict]:
    """Forecast for every monitored region."""
    locations = db.query(OceanLocation).all()
    return [forecast_location(db, loc, history) for loc in locations]