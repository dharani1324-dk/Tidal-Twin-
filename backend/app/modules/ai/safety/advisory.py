"""
OceanVerse AI - Safety & Advisory
===================================
Higher-level intelligence for coastal safety:

- ``safety_advisory``  -> per-coast sailing status + recommended safe window
- ``storm_track``      -> deterministic synthetic cyclone track (demo/showcase)
- ``model_trust``      -> rolling forecast-vs-observed error (sparkline + drift)
- ``merged_timeseries``-> observations + projected forecast merged onto one
                          timeline (powers the 3D-globe time scrubber)

Everything reuses the existing stock tables (observations, alerts) and the
risk-index scoring already implemented in ``reports.risk``.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.modules.ai.reports.risk import compute_risk_index

# Wave thresholds used for the advisory bands (metres)
SAFE_WAVE_M = 1.0
WARN_WAVE_M = 1.6
DANGER_WAVE_M = 2.4

STATUS_ORDER = {"safe": 0, "caution": 1, "danger": 2}


def _trend_slope(values: list[float | None]) -> float:
    """Linear slope (°C/h or m/h) over a series, clamped to sane bounds."""
    vals = [v for v in values if v is not None]
    if len(vals) < 6:
        return 0.0
    slope = float(np.polyfit(np.arange(len(vals)), vals, 1)[0])
    return max(-0.25, min(0.25, slope))


def _safe_windows(rows: list, ahead: int = 12) -> list[tuple[int, int]]:
    """Contiguous future hour-ranges where wave height stays under the safe
    limit, projected from the recent wave trend."""
    waves = [r.wave_height for r in rows if r.wave_height is not None]
    if not waves:
        return []
    base = waves[-1]
    slope = _trend_slope(waves)
    start: int | None = None
    out: list[tuple[int, int]] = []
    for h in range(ahead):
        ok = max(0.0, base + slope * h) < SAFE_WAVE_M
        if ok and start is None:
            start = h
        if not ok and start is not None:
            out.append((start, h - 1))
            start = None
    if start is not None:
        out.append((start, ahead - 1))
    return out


def safety_advisory(db: Session, ahead: int = 12) -> list[dict]:
    """Build a sail/no-sail style advisory for every monitored coast."""
    index = compute_risk_index(db)
    regions = index["regions"]

    out: list[dict] = []
    for region in regions:
        loc = db.query(OceanLocation).get(region["location_id"])
        if loc is None:
            continue
        rows = (
            db.query(OceanObservation)
            .filter(OceanObservation.location_id == loc.id)
            .order_by(OceanObservation.timestamp.desc())
            .limit(48)
            .all()
        )[::-1]

        temps = [r.sea_surface_temperature for r in rows if r.sea_surface_temperature is not None]
        waves = region["wave_height"]
        latest_temp = region["latest_temperature"]

        anomaly = 0.0
        if len(temps) >= 6:
            anomaly = float((temps[-1] - np.mean(temps[:-1])) if temps[:-1] else 0.0)

        # Sailing status from the risk band + physical thresholds
        band = region["band"]
        if band == "CRITICAL" or (waves or 0) >= DANGER_WAVE_M or anomaly >= 1.6:
            status = "danger"
        elif band == "ELEVATED" or (waves or 0) >= WARN_WAVE_M or anomaly >= 1.0:
            status = "caution"
        else:
            status = "safe"

        windows = _safe_windows(rows, ahead=ahead)
        now = datetime.now(timezone.utc)
        if windows:
            t0 = (now + timedelta(hours=windows[0][0])).strftime("%H:%M")
            t1 = (now + timedelta(hours=windows[0][1] + 1)).strftime("%H:%M")
            safe_window = f"{t0} – {t1} IST"
        else:
            safe_window = "Not advised"

        if status == "danger":
            headline = "Rough conditions — small vessels advised against sailing."
        elif status == "caution":
            headline = "Increased risk — exercise caution offshore today."
        else:
            headline = "Favourable conditions for coastal fishing and transit."

        msg_parts = [
            f"⚓ COASTAL ADVISORY — {loc.name}",
            f"SST {latest_temp:.1f}°C (Δ{anomaly:+.1f}°C)" if latest_temp is not None else f"SST — ",
            f"wave {waves:.1f} m" if waves is not None else "wave —",
            f"safe window {safe_window}",
            headline,
        ]
        message = " · ".join(msg_parts)

        out.append(
            {
                "location_id": loc.id,
                "location": loc.name,
                "status": status,
                "status_order": STATUS_ORDER[status],
                "risk_index": region["index"],
                "band": band,
                "safe_window": safe_window,
                "latest_temperature": latest_temp,
                "temperature_anomaly": round(anomaly, 2),
                "wave_height": waves,
                "active_alerts": region["active_alerts"],
                "headline": headline,
                "message": message,
            }
        )

    out.sort(key=lambda r: -r["status_order"])
    return out


def storm_track(now: datetime | None = None) -> dict:
    """A deterministic, synthetic cyclone for the showcase.

    The track is seeded from the calendar date so it is stable within a demo
    day but evolves across days. Starts in the Bay of Bengal and curves
    north-west toward Odisha, growing then decaying in intensity.
    """
    now = now or datetime.now(timezone.utc)
    seed = now.strftime("%Y%m%d")
    start_lat, start_lon = 12.8 + (int(seed[-2]) % 3) * 0.7, 89.5 + (int(seed[-1]) % 2)
    points = []
    for h in range(25):
        lat = start_lat + 0.16 * h + 0.9 * np.sin(h / 8.0)
        lon = start_lon - 0.42 * h + 0.7 * np.cos(h / 9.0)
        wind = min(185.0, 75.0 + 4.6 * h) if h < 18 else max(100.0, 185 - (h - 18) * 9)
        radius = min(130.0, 45 + 3.5 * h)
        points.append(
            {
                "hour": h,
                "time": (now + timedelta(hours=h)).isoformat(),
                "lat": round(float(lat), 3),
                "lon": round(float(lon), 3),
                "wind_kmh": round(float(wind)),
                "radius_km": round(float(radius)),
            }
        )
    return {
        "id": f"TC-OV-{seed}",
        "name": "Cyclone MARINER",
        "active": True,
        "updated_at": now.isoformat(),
        "headline": "Very severe cyclonic storm — Bay of Bengal, moving NW toward the Odisha coast.",
        "points": points,
    }


def model_trust(db: Session, window: int = 96) -> dict:
    """Rolling forecast-vs-observed error (MAE) per coast + a 0-100 trust score.

    For every hour past the first 24, we "had" a 24 h-ahead forecast made by
    extrapolating the trend known at that time, and measure how wrong it was.
    """
    locations = db.query(OceanLocation).all()
    now = datetime.now(timezone.utc)
    regions = []
    for loc in locations:
        rows = (
            db.query(OceanObservation)
            .filter(OceanObservation.location_id == loc.id)
            .order_by(OceanObservation.timestamp.desc())
            .limit(window)
            .all()
        )[::-1]
        temps = [r.sea_surface_temperature for r in rows if r.sea_surface_temperature is not None]
        series = []
        n = len(temps)
        for k in range(24, n):
            past = temps[k - 24 : k]
            if len(past) < 6:
                continue
            slope = _trend_slope(past)
            fcst = past[-1] + slope * 24
            mae = abs(fcst - temps[k])
            series.append({"time": (now - timedelta(hours=n - 1 - k)).isoformat(), "mae": round(float(mae), 3)})
        mean_mae = float(np.mean([s["mae"] for s in series])) if series else 0.0
        trust = int(max(0, min(100, 100 - mean_mae / 0.15 * 40)))
        drift = False
        if len(series) >= 12:
            older = np.mean([s["mae"] for s in series[: len(series) // 2]])
            newer = np.mean([s["mae"] for s in series[len(series) // 2 :]])
            drift = bool(newer > 2.0 * max(older, 0.02))
        regions.append(
            {
                "location_id": loc.id,
                "location": loc.name,
                "trust_score": trust,
                "mean_mae": round(mean_mae, 3),
                "drift": drift,
                "series": series[-48:],
            }
        )
    regions.sort(key=lambda r: r["trust_score"])
    return {"generated_at": now.isoformat(), "regions": regions}


def merged_timeseries(db: Session, obs: int = 48, ahead: int = 24) -> list[dict]:
    """Chronological per-coast timeline: observed hours, then a projected
    forecast window — used by the 3D-globe time scrubber."""
    locations = db.query(OceanLocation).all()
    out = []
    for loc in locations:
        rows = (
            db.query(OceanObservation)
            .filter(OceanObservation.location_id == loc.id)
            .order_by(OceanObservation.timestamp.desc())
            .limit(obs)
            .all()
        )[::-1]
        points = []
        for r in rows:
            points.append(
                {
                    "time": r.timestamp.isoformat(),
                    "temperature": r.sea_surface_temperature,
                    "wave": r.wave_height,
                }
            )
        if points:
            last_t = datetime.fromisoformat(points[-1]["time"])
            temps = [r.sea_surface_temperature for r in rows if r.sea_surface_temperature is not None]
            waves = [r.wave_height for r in rows if r.wave_height is not None]
            t_slope = _trend_slope(temps)
            w_slope = _trend_slope(waves)
            base_t = temps[-1] if temps else 28.0
            base_w = waves[-1] if waves else 1.2
            for h in range(1, ahead + 1):
                ft = (last_t + timedelta(hours=h)).isoformat()
                temp = max(18.0, min(34.0, base_t + t_slope * (44 + h)))
                wave = max(0.0, base_w + w_slope * h)
                points.append(
                    {
                        "time": ft,
                        "temperature": round(float(temp), 2),
                        "wave": round(float(wave), 2),
                        "forecast": True,
                    }
                )
        out.append(
            {
                "location_id": loc.id,
                "location": loc.name,
                "latitude": None,
                "longitude": None,
                "points": points,
            }
        )
    return out