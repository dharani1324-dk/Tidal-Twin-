"""
OceanVerse AI - Reports & Risk Intelligence Module
===================================================
Computes a National Ocean Risk Index for every monitored region and
auto-generates an executive summary in plain stakeholder language.

Risk model (higher = more dangerous):
  - Temperature anomaly (deviation from recent normal)         weight 0.35
  - Active alert severity contribution                          weight 0.30
  - Wave height vs safety threshold (1.0 m small-boat limit)    weight 0.20
  - Recent temperature volatility (std of last 24h)             weight 0.15

Composite score is normalized to 0-100.
"""

import numpy as np
from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.models.alert import OceanAlert

SAFE_WAVE_H = 1.0    # metres - typical small-boat comfort limit
SEV_WEIGHT = {"low": 1, "medium": 2, "high": 3, "critical": 4}

W_TEMP = 0.35
W_ALERT = 0.30
W_WAVE = 0.20
W_VOLAT = 0.15


def compute_risk_index(db: Session) -> dict:
    """Compute the composite risk index for all regions."""
    locations = db.query(OceanLocation).all()
    alerts = (
        db.query(OceanAlert)
        .filter(OceanAlert.status == "active")
        .all()
    )
    active_by_loc: dict = {}
    for a in alerts:
        active_by_loc.setdefault(a.location_id, []).append(a)

    rows = []
    for loc in locations:
        obs = (
            db.query(OceanObservation)
            .filter(OceanObservation.location_id == loc.id)
            .order_by(OceanObservation.timestamp.desc())
            .limit(48)
            .all()
        )
        obs = list(reversed(obs))

        temps = [o.sea_surface_temperature for o in obs if o.sea_surface_temperature is not None]
        waves = [o.wave_height for o in obs if o.wave_height is not None]

        temp_anom = 0.0
        if len(temps) >= 5:
            normal = float(np.mean(temps[:-1]))
            temp_anom = max(0.0, temps[-1] - normal)

        volatility = float(np.std(temps)) if len(temps) >= 5 else 0.0

        wave_current = waves[-1] if waves else 0.0
        wave_risk = max(0.0, (wave_current - SAFE_WAVE_H) / 1.5)

        alert_contrib: int = 0
        max_sev = 0
        for a in active_by_loc.get(loc.id, []):
            alert_contrib += SEV_WEIGHT.get(a.severity, 0)
            max_sev = max(max_sev, SEV_WEIGHT.get(a.severity, 0))

        temp_norm = min(1.0, temp_anom / 3.0)
        alert_norm = min(1.0, (alert_contrib or (max_sev / 4.0)) / 4.0)
        wave_norm = min(1.0, wave_risk)
        vol_norm = min(1.0, volatility / 1.0)

        composite = int(round(
            temp_norm * W_TEMP * 100
            + alert_norm * W_ALERT * 100
            + wave_norm * W_WAVE * 100
            + vol_norm * W_VOLAT * 100
        ))
        composite = min(100, composite)

        band = risk_band(composite)

        rows.append({
            "location_id": loc.id,
            "location": loc.name,
            "index": composite,
            "band": band,
            "signal": round(temp_anom, 2),
            "volatility": round(volatility, 3),
            "wave_height": round(wave_current, 2),
            "active_alerts": len(active_by_loc.get(loc.id, [])),
            "latest_temperature": round(temps[-1], 2) if temps else None,
        })

    rows.sort(key=lambda r: r["index"], reverse=True)
    return {
        "generated_at": np.datetime64("now", "s").astype(str),
        "regions": rows,
        "model": {
            "temp_weight": W_TEMP,
            "alert_weight": W_ALERT,
            "wave_weight": W_WAVE,
            "volatility_weight": W_VOLAT,
            "safe_wave_m": SAFE_WAVE_H,
        },
    }


def risk_band(score: int) -> str:
    if score >= 60:
        return "CRITICAL"
    if score >= 35:
        return "ELEVATED"
    if score >= 15:
        return "MODERATE"
    return "STABLE"


def build_executive_summary(db: Session) -> str:
    """Plain-language summary for stakeholders."""
    index = compute_risk_index(db)
    rows = index["regions"]
    if not rows:
        return "No observational data available yet. Run a data refresh first."

    top = rows[0]
    troubled = [r for r in rows if r["band"] in ("CRITICAL", "ELEVATED")]
    calm = [r for r in rows if r["band"] == "STABLE"]

    lines = [
        f"This nation-wide ocean assessment covers {len(rows)} monitored regions "
        f"across India's coastline, from the Arabian Sea to the Bay of Bengal.",
        "",
        f"Overall, the ocean conditions are {tone_line(len(troubled), len(rows))}. "
        f"{len(troubled)} region(s) currently show elevated or critical conditions, "
        f"while {len(calm)} region(s) remain stable.",
    ]

    if top:
        reason = risk_reason(top)
        lines.append(
            f"The highest-priority region is {top['location']}, with a composite "
            f"risk score of {top['index']} out of 100. {reason}"
        )

    if troubled:
        names = ", ".join(r["location"] for r in troubled[:3])
        lines.append(
            f"Regions deserving attention: {names}. Recommended action is to "
            f"brief coastal authorities, reinforce small-craft advisories, and "
            f"re-run the AI monitoring scan within the next 6 hours."
        )

    if calm:
        names = ", ".join(r["location"] for r in calm[:3])
        lines.append(
            f"{names} are operating under stable conditions, suitable for "
            f"normal maritime activity including small-boat fishing."
        )

    lines.append(
        "This report was generated automatically by the OceanVerse AI decision "
        "intelligence platform using live sensor observations and the anomaly "
        "detection engine."
    )
    return "\n".join(lines)


def tone_line(troubled: int, total: int) -> str:
    if troubled == 0:
        return "mostly calm and stable"
    ratio = troubled / total
    if ratio > 0.5:
        return "elevated across several regions"
    if ratio > 0.25:
        return "mixed, with pockets of elevated risk"
    return "generally calm with isolated areas of concern"


def risk_reason(row: dict) -> str:
    reasons = []
    if row["signal"] >= 1.5:
        reasons.append(f"sea surface temperature is {row['signal']:.1f}°C above its recent normal")
    if row["wave_height"] > SAFE_WAVE_H + 0.3:
        reasons.append(f"wave heights are {row['wave_height']:.2f}m, above the small-craft comfort level")
    if row["active_alerts"] > 0:
        reasons.append(f"{row['active_alerts']} active AI alert(s) are currently firing")
    if row["volatility"] > 0.5:
        reasons.append(f"unusually high short-term variability (±{row['volatility']:.2f}°C)")
    if not reasons:
        reasons.append("the risk model's weighted components place it slightly above average")
    return "The main contributors are " + "; ".join(reasons) + "."