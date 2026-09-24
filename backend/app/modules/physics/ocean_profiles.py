"""Ocean physics and depth-profile engine.

Provides the analytic water-column model that powers the 4D dimension of the
platform: thermocline intelligence, temperature/salinity/oxygen depth profiles,
and derived bio-physical surface variables (oxygen, chlorophyll, pH, density,
nutrients) that are not present in the raw sensor feed.

All profiles are deterministic given a location id + surface reading, so every
engine shows stable, reproducible science while staying entirely offline.
"""

import math
import random

D = 500  # max depth (m) we model


def _rng(loc_id: int, salt: int) -> random.Random:
    return random.Random((loc_id * 7919) + (salt * 104729))


# --------------------------------------------------------------------------
# Regional context
# --------------------------------------------------------------------------

def region_context(loc):
    """Stable baseline parameters for a location (MLD, thermocline, upwelling)."""
    r = _rng(loc.id, 1)

    # West-coast summer upwelling shallows the thermocline; bays/deep seas deepen it
    if loc.region_type == "coastal":
        if "Goa" in loc.name or "Kerala" in loc.name:
            upwelling = 0.8           # strong seasonal upwelling
        else:
            upwelling = 0.35
    elif loc.region_type == "gulf":
        upwelling = 0.25
    elif loc.region_type == "bay":
        upwelling = 0.30
    else:  # open sea
        upwelling = r.uniform(0.15, 0.35)

    thermocline = round(38.0 - upwelling * 22.0, 1)          # m
    mld = round(thermocline - r.uniform(6.0, 12.0), 1)       # mixed layer top
    mld = max(8.0, mld)

    salinity_surface = round(r.uniform(34.6, 35.4), 2)
    salinity_deep = round(salinity_surface + r.uniform(0.4, 0.8), 2)
    deep_temp = round(r.uniform(8.5, 11.0), 1)

    return {
        "upwelling": upwelling,
        "thermocline_depth": thermocline,
        "mixed_layer_depth": mld,
        "salinity_surface": salinity_surface,
        "salinity_deep": salinity_deep,
        "deep_temp": deep_temp,
    }


# --------------------------------------------------------------------------
# Derived surface variables (from raw sensor values)
# --------------------------------------------------------------------------

def derive_surface(loc, temp, salinity=None, wave=None, current=None) -> dict:
    """Estimate bio-physical variables at the surface from raw readings."""
    ctx = region_context(loc)
    r = _rng(loc.id, 2)
    t = temp if temp is not None else 28.0
    s = salinity if salinity is not None else ctx["salinity_surface"]
    w = wave if wave is not None else 1.0
    cu = current if current is not None else 0.5

    # Dissolved oxygen falls as temperature rises (Henry's law proxy)
    oxygen = round(max(4.2, 10.35 - 0.17 * t + 0.02 * s + r.uniform(-0.15, 0.15)), 2)

    # Nutrients rise with upwelling + current energy
    nutrients = round(max(0.2, 0.6 + 4.5 * ctx["upwelling"] + 1.2 * cu + r.uniform(-0.3, 0.3)), 2)

    # Chlorophyll responds to nutrients + light availability
    chl_base = 0.08 + 0.75 * min(nutrients, 4.0) * (0.4 + ctx["upwelling"])
    chlorophyll = round(max(0.05, chl_base + r.uniform(-0.1, 0.1)), 2)

    ph = round(8.16 - 0.004 * (t - 20) + 0.004 * (s - 35) + r.uniform(-0.02, 0.02), 2)

    density = round(1027.5 + 0.8 * (s - 35) - 0.2 * (t - 20) + 0.02 * w, 1)

    return {
        "dissolved_oxygen": oxygen,
        "chlorophyll": chlorophyll,
        "ph": ph,
        "nutrients": nutrients,
        "density": density,
        "pressure": 0.0,
    }


# --------------------------------------------------------------------------
# Depth profile (thermocline model)
# --------------------------------------------------------------------------

def depth_profile(loc, surface_temp, salinity=None, wave=None, current=None) -> dict:
    """Full water-column profile for a location with a sigmoid thermocline."""
    ctx = region_context(loc)
    ts = surface_temp if surface_temp is not None else 28.0
    ss = salinity if salinity is not None else ctx["salinity_surface"]
    r = _rng(loc.id, 3)

    tc = ctx["thermocline_depth"]
    mld = ctx["mixed_layer_depth"]
    width = round(r.uniform(18, 30), 1)

    O_ml = derive_surface(loc, ts, ss, wave, current)["dissolved_oxygen"]
    O_min = round(r.uniform(1.2, 2.2), 2)
    O_min_z = int(r.uniform(180, 230))
    chl = derive_surface(loc, ts, ss, wave, current)["chlorophyll"]
    chl_max = round(chl * r.uniform(1.6, 2.6), 2)
    chl_z = int(r.uniform(18, 36))
    nut_surf = derive_surface(loc, ts, ss, wave, current)["nutrients"]

    depths = [0, 5, 10, 15, 20, 25, 30, 40, 50, 60, 75, 90, 110, 130, 160, 200, 250, 300, 400, 500]

    temp = []
    sal = []
    oxy = []
    press = []
    dens = []
    chl_l = []
    nut = []
    phl = []

    for z in depths:
        # Mixed layer holds surface values; below it, relax to deep values
        if z <= mld:
            t = ts
            s = ss
        else:
            rel = z - mld
            t = ctx["deep_temp"] + (ts - ctx["deep_temp"]) * math.exp(-rel / width)
            s = ctx["salinity_deep"] - (ctx["salinity_deep"] - ss) * math.exp(-rel / width)
        pressure = float(z)
        rho = 1028.0 + 0.8 * (s - 35) - 0.2 * (t - 20)
        o = O_ml - (O_ml - O_min) * math.exp(-((z - O_min_z) / 45) ** 2) + \
            (O_ml - O_min) * math.tanh(z / 420) * 0.6
        c = chl + (chl_max - chl) * math.exp(-((z - chl_z) / 14) ** 2) * \
            (1 if z < 120 else math.exp(-(z - 120) / 60))
        n = nut_surf + (18.0 - nut_surf) * (1 - math.exp(-z / 130))
        p = 8.16 - 0.0035 * (t - ts) - 0.0004 * z

        temp.append(round(t, 2))
        sal.append(round(s, 2))
        oxy.append(round(max(0.2, o), 2))
        press.append(pressure)
        dens.append(round(rho, 2))
        chl_l.append(round(max(0.01, c), 2))
        nut.append(round(n, 2))
        phl.append(round(p, 2))

    metrics = compute_thermocline(depths, temp, sal)
    return {
        "location": loc.name,
        "location_id": loc.id,
        "depths": depths,
        "temperature": temp,
        "salinity": sal,
        "dissolved_oxygen": oxy,
        "pressure": press,
        "density": dens,
        "chlorophyll": chl_l,
        "nutrients": nut,
        "ph": phl,
        "thermocline": metrics,
    }


def compute_thermocline(depths, temps, sals=None) -> dict:
    """Thermocline depth at the max gradient + strength + MLD (0.2C drop)."""
    mld = depths[-1]
    for i in range(1, len(depths)):
        if temps[i] <= temps[0] - 0.2:
            mld = depths[i - 1]
            break

    best_d, best_g = 0.0, 0.0
    for i in range(1, len(depths)):
        dz = depths[i] - depths[i - 1]
        g = abs(temps[i] - temps[i - 1]) / dz if dz else 0.0
        if g > best_g:
            best_g, best_d = g, depths[i]

    # Thermocline centre where the temperature has fallen ~63% of the way to deep
    if best_d <= 0:
        thermo_d = mld
    else:
        thermo_d = best_d

    if sals:
        sg = 0.0
        for i in range(1, len(depths)):
            dz = depths[i] - depths[i - 1]
            g = abs(sals[i] - sals[i - 1]) / dz if dz else 0.0
            sg = max(sg, g)
    else:
        sg = 0.0

    return {
        "mixed_layer_depth": round(mld, 1),
        "thermocline_depth": round(thermo_d, 1),
        "strength_c_per_m": round(best_g, 3),
        "temperature_gradient_c_per_m": round(best_g, 3),
        "salinity_gradient_psu_per_m": round(sg, 4),
    }


def thermocline(db, loc) -> dict:
    """Quick thermocline intelligence summary for a location (latest reading)."""
    import sqlalchemy
    from app.models.observation import OceanObservation

    o = (db.query(OceanObservation)
         .filter(OceanObservation.location_id == loc.id)
         .order_by(OceanObservation.timestamp.desc()).first())
    if o is None:
        return {"location": loc.name, "location_id": loc.id, "thermocline": None, "profile": None}

    prof = depth_profile(loc, o.sea_surface_temperature, o.salinity,
                         o.wave_height, o.current_speed)
    return {
        "location": loc.name,
        "location_id": loc.id,
        "latest_depths": prof["depths"],
        "thermocline": prof["thermocline"],
        "surface_temp": o.sea_surface_temperature,
    }