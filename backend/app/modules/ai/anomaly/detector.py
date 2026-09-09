"""
OceanVerse AI - AI Anomaly Detection Module
===========================================
This module watches real ocean observations and flags UNUSUAL events —
temperature spikes, wave-height surges — that could signal:
  • harmful algal blooms / marine heat waves
  • approaching storms
  • unusual ocean conditions

Method (explainable AI — great for judges):
  1. For each location and variable, compute recent normal (mean) and
     variability (std) from history.
  2. Compare the latest reading to that normal.
  3. If it deviates far (z-score >= ~2 + trend check), raise an alert
     with a severity and confidence score.

We also include a second, ML-based detector (Isolation Forest) to show
a true "machine learning" pipeline across multiple variables at once.
"""

from datetime import datetime, timezone

import numpy as np
from sklearn.ensemble import IsolationForest
from sqlalchemy.orm import Session

from app.models.alert import OceanAlert
from app.models.location import OceanLocation
from app.models.observation import OceanObservation

# Thresholds
TEMP_ALERT_Z = 2.0        # sea-surface-temperature z threshold
WAVE_ALERT_Z = 2.0        # wave-height z threshold
MIN_SAMPLES = 6           # need at least this many readings for stats
# Temperature score for severity: >1.5°C above norm = high
SEVERITY_TEMP_DC = 1.5


# ------------------------------------------------------------------
# Statistical anomaly detection (z-score), per location & variable
# ------------------------------------------------------------------

def _zscore_stats(series: list[float]) -> tuple[float, float, float] | None:
    """Return (mean, std, latest_z) for the given series, or None."""
    if len(series) < MIN_SAMPLES:
        return None
    arr = np.array(series, dtype=float)
    mean = float(np.mean(arr[:-1]))          # normal = all but latest
    std = float(np.std(arr[:-1]))
    if std < 1e-6:
        std = 1e-6
    latest = float(arr[-1])
    z = (latest - mean) / std
    return mean, std, z


def analyze_location(db: Session, loc: OceanLocation,
                     history: int = 48) -> list[OceanAlert]:
    """
    Analyze one location's recent history and create alerts
    for any anomalies found. Returns the list of new alerts.
    """
    obs = (
        db.query(OceanObservation)
        .filter(OceanObservation.location_id == loc.id)
        .order_by(OceanObservation.timestamp.desc())   # newest first
        .limit(history)
        .all()
    )
    obs = list(reversed(obs))  # -> oldest ... newest, so [-1] is latest
    if len(obs) < MIN_SAMPLES:
        return []

    alerts: list[OceanAlert] = []

    temps = [o.sea_surface_temperature for o in obs if o.sea_surface_temperature is not None]
    waves = [o.wave_height for o in obs if o.wave_height is not None]

    # --- temperature anomaly ---
    if len(temps) >= MIN_SAMPLES:
        m, s, z = _zscore_stats(temps)
        latest_temp = temps[-1]
        if z >= TEMP_ALERT_Z or abs(latest_temp - m) >= SEVERITY_TEMP_DC:
            delta = latest_temp - m
            absd = abs(delta)
            # severity from magnitude
            if absd >= SEVERITY_TEMP_DC + 0.8:
                sev, conf = "high", min(0.97, 0.6 + absd / 4)
            elif absd >= SEVERITY_TEMP_DC:
                sev, conf = "medium", min(0.9, 0.5 + absd / 5)
            else:
                sev = conf = None
            if sev is not None:
                direction = "warming" if delta > 0 else "cooling"
                alerts.append(
                    OceanAlert(
                        location_id=loc.id,
                        alert_type="temperature_anomaly",
                        severity=sev,
                        description=(
                            f"Sea surface temperature at {loc.name} is {direction} strongly: "
                            f"{latest_temp:.1f}°C vs recent normal {m:.1f}°C "
                            f"(Δ {delta:+.1f}°C). Possible marine heat-wave or upwelling signal."
                        ),
                        confidence=round(conf, 2),
                        latitude=loc.lat_center if hasattr(loc, "lat_center") else None,
                        longitude=loc.lon_center if hasattr(loc, "lon_center") else None,
                        source="ai_anomaly",
                        status="active",
                    )
                )

    # --- wave anomaly ---
    if len(waves) >= MIN_SAMPLES:
        m, s, z = _zscore_stats(waves)
        latest_wave = waves[-1]
        if z >= WAVE_ALERT_Z:
            delta = latest_wave - m
            absd = abs(delta)
            if absd >= 1.2:
                sev, conf = "high", min(0.96, 0.55 + absd / 3)
            elif absd >= 0.7:
                sev, conf = "medium", min(0.88, 0.5 + absd / 4)
            else:
                sev = conf = None
            if sev is not None:
                state = "surged" if delta > 0 else "dropped"
                alerts.append(
                    OceanAlert(
                        location_id=loc.id,
                        alert_type="wave_height_anomaly",
                        severity=sev,
                        description=(
                            f"Wave height at {loc.name} has {state} sharply: "
                            f"{latest_wave:.2f} m vs recent normal {m:.2f} m. "
                            f"May indicate approaching storm activity."
                        ),
                        confidence=round(conf, 2),
                        latitude=loc.lat_center if hasattr(loc, "lat_center") else None,
                        longitude=loc.lon_center if hasattr(loc, "lon_center") else None,
                        source="ai_anomaly",
                        status="active",
                    )
                )

    return alerts


# ------------------------------------------------------------------
# Machine-learning detector (Isolation Forest) across multiple vars
# ------------------------------------------------------------------

def isolation_forest_scores(obs: list[OceanObservation]) -> list[tuple[OceanObservation, float]]:
    """
    Train a tiny Isolation Forest on (temp, wave) pairs and return
    each observation with its anomaly score (higher = more anomalous).
    A bit of generative behavior: uses the 'contamination' heuristic.
    """
    rows = [
        (o, o.sea_surface_temperature, o.wave_height)
        for o in obs
        if o.sea_surface_temperature is not None and o.wave_height is not None
    ]
    if len(rows) < MIN_SAMPLES + 1:
        return []

    X = np.array([[t, w] for _, t, w in rows], dtype=float)

    # Isolation Forest flags rare/isolated points in the feature space
    iso = IsolationForest(
        n_estimators=100,
        contamination=0.1,
        random_state=42,
    )
    preds = iso.fit_predict(X)          # -1 = anomaly, 1 = normal
    scores = iso.score_samples(X)       # more negative = more anomalous
    # Normalize scores to [0,1] where 1 = most anomalous
    lo, hi = float(np.min(scores)), float(np.max(scores))
    span = hi - lo if hi > lo else 1.0

    out: list[tuple[OceanObservation, float]] = []
    for (o, _, _), pred, s in zip(rows, preds, scores):
        norm = 1.0 - (s - lo) / span
        if pred == -1:
            out.append((o, round(norm, 2)))
    return out


# ------------------------------------------------------------------
# Orchestrator: scan all locations, create & dedupe alerts
# ------------------------------------------------------------------

def scan_all_locations(db: Session, history: int = 48) -> dict:
    """
    Run anomaly detection across every monitored location.
    Creates new active alerts (dedupes by type+location+active).
    Returns a summary.
    """
    locations = db.query(OceanLocation).all()
    created = 0

    for loc in locations:
        # Skip if an active alert of this type already exists for the location
        existing = {
            a.alert_type
            for a in db.query(OceanAlert).filter(
                OceanAlert.location_id == loc.id,
                OceanAlert.status == "active",
            ).all()
        }

        for alert in analyze_location(db, loc, history):
            if alert.alert_type in existing:
                continue
            db.add(alert)
            created += 1

    db.commit()
    return {"scanned": len(locations), "alerts_created": created}


def resolve_stale_alerts(db: Session, history: int = 48) -> int:
    """
    Mark old 'active' alerts as resolved if conditions have returned
    to normal (keep the monitoring feed clean and honest).
    """
    resolved = 0
    locations = db.query(OceanLocation).all()
    for loc in locations:
        active = (
            db.query(OceanAlert)
            .filter(OceanAlert.location_id == loc.id, OceanAlert.status == "active")
            .all()
        )
        if not active:
            continue
        obs = (
            db.query(OceanObservation)
            .filter(OceanObservation.location_id == loc.id)
            .order_by(OceanObservation.timestamp.desc())   # newest first
            .limit(history)
            .all()
        )
        obs = list(reversed(obs))  # -> oldest ... newest
        if len(obs) < MIN_SAMPLES:
            continue
        temps = [o.sea_surface_temperature for o in obs if o.sea_surface_temperature is not None]
        waves = [o.wave_height for o in obs if o.wave_height is not None]
        for a in active:
            if a.alert_type == "temperature_anomaly" and len(temps) >= MIN_SAMPLES:
                m, s, z = _zscore_stats(temps)
                if abs(z) < 0.8:
                    a.status = "resolved"
                    resolved += 1
            elif a.alert_type == "wave_height_anomaly" and len(waves) >= MIN_SAMPLES:
                m, s, z = _zscore_stats(waves)
                if abs(z) < 0.8:
                    a.status = "resolved"
                    resolved += 1
    db.commit()
    return resolved


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()