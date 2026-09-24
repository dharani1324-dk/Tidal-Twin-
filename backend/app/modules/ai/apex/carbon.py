"""Marine Carbon Monitoring — air-sea CO2 flux & blue-carbon potential.

Pure model estimates (no API keys, fully offline and explainable):

  • pCO2 of surface seawater:  temperature-driven baseline tempered by a
    chlorophyll biological drawdown term  (Takahashi-style).
  • Gas transfer velocity:       Wanninkhof (1992) quadratic in wind speed
    with the Schmidt-number correction.
  • Solubility constant:         Weiss (1974).
  • Net air-sea CO2 flux (mol/m²/day and g-C/m²/year) with sign convention
    negative = ocean absorbs CO2 (sink), positive = ocean releases (source).
"""

import math

from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.models.observation import OceanObservation
from app.modules.ai.validation.engine import _latest_rows

PCO2_AIR = 420.0  # current atmospheric CO2 partial pressure (µatm)


def _pco2_sw(sst: float, chl: float | None) -> float:
    """Takahashi-style temperature dependence + biological drawdown."""
    bio_drawdown = 0.12 * min(1.0, (chl or 0.8) / 2.0)      # more biomass → uptake
    return 390.0 * 2 ** ((sst - 20.0) / 10.0) * (1.0 - bio_drawdown)


def _schmidt_number(sst: float) -> float:
    T = max(0.0, min(35.0, sst))
    return 2073.1 - 125.62 * T + 3.6276 * T ** 2 - 0.043219 * T ** 3


def _solubility_weiss(sst: float) -> float:
    """CO2 solubility (mol L⁻¹ atm⁻¹) after Weiss (1974)."""
    Tk = sst + 273.15
    ln_k0 = -60.2409 + 93.4517 * (100.0 / Tk) + 23.3585 * math.log(Tk / 100.0)
    return math.exp(ln_k0)


def _co2_flux(sst: float, wind_ms: float, chl: float | None) -> dict:
    p_sw = _pco2_sw(sst, chl)
    delta_p = p_sw - PCO2_AIR
    sch = _schmidt_number(sst)
    k_cm_h = 0.31 * (wind_ms ** 2) * (sch / 660.0) ** (-0.5)   # cm/h
    k_m_s = k_cm_h / 100.0 / 3600.0
    # Weiss gives mol/(L·atm); gas flux needs mol/(m³·atm) → ×1000.
    k0_m3 = _solubility_weiss(sst) * 1000.0
    flux_mol_m2_s = k_m_s * k0_m3 * delta_p * 1e-6             # µatm→atm
    flux_mol_m2_day = flux_mol_m2_s * 86400.0
    flux_gc_m2_yr = flux_mol_m2_s * 12.011 * 86400.0 * 365.0   # g-C m⁻² yr⁻¹

    if flux_gc_m2_yr < -100:
        category = "strong sink"
    elif flux_gc_m2_yr < 0:
        category = "moderate sink"
    elif flux_gc_m2_yr > 90:
        category = "source"
    else:
        category = "near-neutral"

    return {
        "pco2_seawater": round(p_sw, 1),
        "pco2_atmosphere": PCO2_AIR,
        "pco2_gradient": round(delta_p, 1),
        "schmidt_number": round(sch, 1),
        "gas_transfer_velocity_cm_per_h": round(k_cm_h, 2),
        "solubility_mol_per_m3_atm": round(k0_m3, 2),
        "flux_mol_per_m2_day": round(flux_mol_m2_day, 4),
        "flux_gc_per_m2_yr": round(flux_gc_m2_yr, 1),
        "category": category,
    }


def carbon_monitoring(db: Session) -> dict:
    """Per-region CO2 flux, uptake totals and blue-carbon potential."""
    regions = []
    total_gc_yr = 0.0

    for loc in db.query(OceanLocation).all():
        obs = _latest_rows(db, loc, window=24)
        if not obs:
            continue
        latest = obs[-1]
        sst = latest.sea_surface_temperature
        if sst is None:
            continue
        wind_ms = max(0.5, (latest.wave_height if latest.wave_height is not None else 1.0) * 2.4)
        flux = _co2_flux(sst, wind_ms, latest.chlorophyll)

        # 100×100 km envelope approximation for the national aggregate.
        area_km2 = 10000.0
        uptake_gc_yr = flux["flux_gc_per_m2_yr"] * area_km2 * 1e6
        total_gc_yr += uptake_gc_yr

        regions.append({
            "location_id": loc.id,
            "location": loc.name,
            "sst": round(sst, 2),
            "surface_chlorophyll": round(latest.chlorophyll, 3) if latest.chlorophyll is not None else None,
            "wind_estimate_ms": round(wind_ms, 2),
            "flux": flux,
            "regional_uptake_ktC_per_yr": round(uptake_gc_yr / 1e9, 2),
        })

    regions.sort(key=lambda r: r["flux"]["flux_gc_per_m2_yr"])
    strongest_sink = regions[0]["location"] if regions else None

    return {
        "engine": "Marine Carbon Monitoring (Takahashi + Wanninkhof + Weiss)",
        "national_total_uptake_MtC_per_yr": round(-total_gc_yr / 1e12, 3),
        "strongest_co2_sink": strongest_sink,
        "atmosphere_reference_pco2": PCO2_AIR,
        "regions": regions,
    }