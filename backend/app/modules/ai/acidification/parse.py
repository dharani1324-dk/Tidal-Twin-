"""
TidalTwin - Acidification: Argo NetCDF pH parser
=================================================
Reads in-situ pH out of a real per-cycle Argo BGC profile NetCDF using xarray +
netCDF4.  The parser extracts MEASURED levels and nothing else: NaN, absent
variables and implausible values all stay out.

WHAT IS READ
------------
* Position and time from the file's profile arrays (``LATITUDE``,
  ``LONGITUDE``, ``JULD`` as days since 1950-01-01).
* pH: ``PH_IN_SITU_TOTAL_ADJUSTED`` (+ QC) when present, else
  ``PH_IN_SITU_TOTAL`` (+ QC), else the free-scale pair.  Total scale is
  preferred because every threshold in this module is defined on it.
* Free-scale pH recorded alongside when published, never substituted for the
  total-scale value.
* Co-located ``TEMP``/``PSAL``/``PRES``.  These are NOT optional decoration:
  carbonate equilibria are strongly temperature dependent, so a level without
  temperature cannot yield an aragonite saturation at all.

THE IMPLAUSIBLE-VALUE PROBLEM, AND WHY IT IS HANDLED HERE
----------------------------------------------------------
BGC-Argo pH arrives as real-time data that has not been through delayed-mode
QC.  Inspected directly in the Indian Ocean box, some profiles report pH of
-1.6 to 6.2 - values that cannot occur in seawater - while others report a
perfectly ordinary 7.4-8.5 and carry the *same* or a worse QC flag.  The
parser therefore records the measurement AND the plausibility verdict, and
leaves the accept/reject decision to ``normalize``, which owns the policy.
Counting the rejects is essential: a silent drop would look identical to a
float that simply carried no pH.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("tidaltwin.acidification.parse")

ARGO_EPOCH = datetime(1950, 1, 1, tzinfo=timezone.utc)
MAX_LEVELS_PER_FILE = 8000

_WMO = re.compile(r"(\d{7})")

# pH variable preference, most authoritative first.  ``_ADJUSTED`` is the
# delayed-mode QC'd series; the bare variable is real-time.  Total scale comes
# before free scale because the module's thresholds are total-scale.
PH_VARIABLE_PREFERENCE = (
    "PH_IN_SITU_TOTAL_ADJUSTED",
    "PH_IN_SITU_TOTAL",
    "PH_IN_SITU_FREE_ADJUSTED",
    "PH_IN_SITU_FREE",
)

# Which scale each candidate reports on, so the row can say which it holds.
PH_VARIABLE_SCALE = {
    "PH_IN_SITU_TOTAL_ADJUSTED": "total",
    "PH_IN_SITU_TOTAL": "total",
    "PH_IN_SITU_FREE_ADJUSTED": "free",
    "PH_IN_SITU_FREE": "free",
}


def _decode_qc(value) -> str:
    """Numpy bytes / str / int -> '1'..'4' style flag, or '?'."""
    if value is None:
        return "?"
    if isinstance(value, bytes):
        return value.decode("ascii", "replace").strip() or "?"
    if isinstance(value, float) and value != value:
        # NaN padding in a QC variable carries no flag.
        return "?"
    text = str(value).strip()
    return text or "?"


def _as_float(value) -> float | None:
    """Finite float or None.  NaN and +/-inf are treated as absent.

    A BGC profile file stacks several sensor groups along the profile axis and
    pads every level to the same length, so the overwhelming majority of cells
    in any one variable are NaN.  Only finite cells are real measurements, so
    this is the single gate that keeps padding out of the database.
    """
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out:  # NaN
        return None
    if out in (float("inf"), float("-inf")):
        return None
    return out


def _pick_var(ds, names: tuple[str, ...]):
    """Return the first variable in ``names`` that exists and has real values."""
    for name in names:
        if name in ds.variables and _has_values(ds[name].values):
            return name
    return None


def _level_value(arrays: list, i: int, j: int) -> float | None:
    """First usable value for level (i, j) across a preference-ordered stack.

    The *_ADJUSTED variables are the delayed-mode, scientifically corrected
    fields and are preferred wherever they exist. But they are processed per
    cast, not per array: a real-time file can ship a mostly-empty
    ``PSAL_ADJUSTED`` next to a fully populated raw ``PSAL``. Choosing once per
    ARRAY (as ``_pick_var`` does) then silently discards every raw value
    outside the handful of already-adjusted levels. This resolves per LEVEL, so
    a partially processed adjusted field costs nothing.
    """
    for arr in arrays:
        if arr is None:
            continue
        value = _as_float(_index_2d(arr, i, j))
        if value is not None:
            return value
    return None


def _stacked_vars(ds, names: tuple[str, ...]) -> list:
    """All existing variables in ``names``, in preference order."""
    return [ds[n].values for n in names if n in ds.variables]


def parse_netcdf_ph(
    path: str, source_url: str | None = None, core_physics=None
) -> dict:
    """Parse one per-cycle Argo profile NetCDF into measured pH levels.

    ``core_physics`` is the optional co-located CORE profile list from
    ``parse_core_physics``/``core_profile_url``.  It supplies measured
    temperature and salinity where the BGC file itself carries no salinity,
    which is the normal case.  It is matched by PRESSURE, not array index -
    see ``build_core_lookup`` for why the index assumption fails on real files.

    A level already carrying its own values keeps them: the BGC sensor's own
    co-located reading is preferred over the core CTD because it belongs to the
    same instrument package.
    """
    try:
        import xarray as xr  # noqa: F401 - lazy import keeps tests light
    except ImportError as exc:  # pragma: no cover - environment guard
        return {
            "status": "ERROR",
            "reason": f"xarray is not available in this environment: {exc}",
            "profiles": [],
            "levels": 0,
            "levels_with_ph": 0,
            "levels_implausible": 0,
        }

    try:
        ds = xr.open_dataset(path, decode_times=False, engine="netcdf4")
    except Exception as exc:  # defensive: a corrupt file must not kill the run
        logger.warning("Cannot open %s: %s", path, exc.__class__.__name__)
        return {
            "status": "ERROR",
            "reason": f"cannot open NetCDF ({exc.__class__.__name__})",
            "profiles": [],
            "levels": 0,
            "levels_with_ph": 0,
            "levels_implausible": 0,
        }

    try:
        return _extract(ds, path, source_url, core_physics)
    except Exception as exc:  # defensive
        logger.warning("Parse %s failed: %s", path, exc.__class__.__name__)
        return {
            "status": "ERROR",
            "reason": f"parse failed ({exc.__class__.__name__}: {exc})",
            "profiles": [],
            "levels": 0,
            "levels_with_ph": 0,
            "levels_implausible": 0,
        }
    finally:
        try:
            ds.close()
        except Exception:  # pragma: no cover
            pass


def _extract(ds, path: str, source_url: str | None, core_physics=None) -> dict:
    from app.modules.ai.acidification.units import is_ph_plausible

    names = set(ds.variables)

    ph_var = _pick_var(ds, PH_VARIABLE_PREFERENCE)
    if ph_var is None:
        return {
            "status": "NO_PH",
            "reason": (
                "file carries no measured pH (not a BGC file, or the pH sensor "
                "data is absent)"
            ),
            "profiles": int(ds.sizes.get("N_PROF", 0)),
            "levels": 0,
            "levels_with_ph": 0,
            "levels_implausible": 0,
            "variables_present": sorted(names),
        }
    qc_var = f"{ph_var}_QC" if f"{ph_var}_QC" in names else None
    ph_scale = PH_VARIABLE_SCALE.get(ph_var, "total")

    lat_values = ds["LATITUDE"].values if "LATITUDE" in names else None
    lon_values = ds["LONGITUDE"].values if "LONGITUDE" in names else None
    juld = ds["JULD"].values if "JULD" in names else None

    # BGC per-profile files publish pressure, not geometric depth.  Prefer a
    # real DEPTH when the file carries one, else use PRES and say so.
    depth_var = _pick_var(ds, ("DEPTH", "PRES"))
    depth_from = (
        "DEPTH" if depth_var == "DEPTH" else ("PRES" if depth_var == "PRES" else None)
    )
    depth_values = ds[depth_var].values if depth_var else None
    pres_values = ds["PRES"].values if "PRES" in names else None

    # Stacked rather than picked so a partly-processed *_ADJUSTED field falls
    # back to its raw counterpart per level (see _level_value). TEMP_DOXY is
    # the optode's co-located sensor, so it comes after the core CTD fields.
    temp_stack = _stacked_vars(
        ds, ("TEMP_ADJUSTED", "TEMP", "TEMP_DOXY_ADJUSTED", "TEMP_DOXY")
    )
    psal_stack = _stacked_vars(ds, ("PSAL_ADJUSTED", "PSAL"))

    # Free-scale pH, recorded separately when the float publishes both.
    free_var = _pick_var(ds, ("PH_IN_SITU_FREE_ADJUSTED", "PH_IN_SITU_FREE"))
    free_values = ds[free_var].values if free_var else None

    ph_values = ds[ph_var].values
    qc_values = ds[qc_var].values if qc_var else None

    # Float and cycle identity, fall back to the filename.
    float_id = _first_scalar(ds.get("PLATFORM_NUMBER"))
    cycle = _first_scalar(ds.get("CYCLE_NUMBER")) or _first_scalar(
        ds.get("NC_CYCLE_NUMBER")
    )
    filename = path.replace("\\", "/").split("/")[-1]
    if not float_id:
        match = _WMO.search(filename)
        float_id = match.group(1) if match else None
    float_id = _clean_text(float_id)
    if cycle is None:
        match = re.search(r"_(\d{3,5})\.nc$", filename) or re.search(
            r"_(\d{3})_prof\.nc$", filename
        )
        cycle = int(match.group(1)) if match else None
    else:
        try:
            cycle = int(float(cycle))
        except (TypeError, ValueError):
            cycle = None

    n_prof, n_levels = ph_values.shape[:2]
    levels: list[dict] = []
    considered = 0
    implausible = 0

    # Build the pressure-based core join BEFORE the level loop, because it needs
    # each BGC profile's full pressure span in order to pick the matching core
    # profile. Doing it per level would force a scan of every core profile for
    # every single level.
    core_lookup: dict[tuple[int, int], dict] = {}
    if core_physics:
        bgc_pressures: dict[int, list[float | None]] = {}
        for i in range(n_prof):
            row = [_as_float(_index_2d(pres_values, i, j)) for j in range(n_levels)]
            if any(p is not None for p in row):
                bgc_pressures[i] = row
        core_lookup = build_core_lookup(bgc_pressures, core_physics)

    for i in range(n_prof):
        latitude = _as_float(_index_value(lat_values, i, n_levels))
        longitude = _as_float(_index_value(lon_values, i, n_levels))
        timestamp = _juld_to_dt(_index_value(juld, i, n_levels))
        if latitude is None or longitude is None:
            continue
        for j in range(n_levels):
            if len(levels) >= MAX_LEVELS_PER_FILE:
                break
            considered += 1
            value = _as_float(_index_2d(ph_values, i, j))
            if value is None:
                # NaN padding - not a measurement.
                continue
            depth = _as_float(_index_2d(depth_values, i, j))
            if depth is None:
                continue
            plausible = is_ph_plausible(value)
            if not plausible:
                # Counted, then still handed to normalize so the rejection is
                # visible in the ingest report rather than silently dropped.
                implausible += 1
            qc = "?"
            if qc_values is not None:
                qc = _decode_qc(_index_2d(qc_values, i, j))
            # Co-located physics: prefer what this BGC file itself measured,
            # fall back to the co-located CORE profile (which is the only place
            # practical salinity appears at all).
            physics = apply_core_physics(
                {
                    "temperature_c": _level_value(temp_stack, i, j),
                    "salinity_psu": _level_value(psal_stack, i, j),
                },
                (core_lookup or {}).get((i, j)),
            )
            levels.append(
                {
                    "latitude": latitude,
                    "longitude": longitude,
                    "timestamp": timestamp,
                    "depth_m": depth,
                    "depth_source": depth_from,
                    "ph_total": value if ph_scale == "total" else None,
                    "ph_free": (
                        value
                        if ph_scale == "free" and ph_total_is_absent(ds)
                        else _as_float(_index_2d(free_values, i, j))
                    ),
                    "ph_variable": ph_var,
                    "ph_scale": ph_scale,
                    "plausible": plausible,
                    "qc_flag": qc,
                    "source_file": filename,
                    "source_url": source_url,
                    "profile_index": i,
                    "level_index": j,
                    "float_id": float_id,
                    "cycle": cycle,
                    "temperature_c": physics["temperature_c"],
                    "salinity_psu": physics["salinity_psu"],
                    "pressure_dbar": _as_float(_index_2d(pres_values, i, j)),
                }
            )

    return {
        "status": "OK",
        "reason": None,
        "float_id": float_id,
        "cycle": cycle,
        "ph_var_used": ph_var,
        "ph_scale_used": ph_scale,
        "qc_var_used": qc_var,
        "depth_var_used": depth_from,
        "profiles": n_prof,
        "levels": len(levels),
        "levels_considered": considered,
        "levels_with_ph": len(levels),
        "levels_implausible": implausible,
        "variables_present": sorted(names),
        "levels_list": levels,
        "source_url": source_url,
    }


def ph_total_is_absent(ds) -> bool:
    """True when the file publishes no total-scale pH at all.

    Only used in the narrow case where the chosen primary variable is
    free-scale: then that reading IS the free-scale value rather than
    something to be paired with a separately-stored free value.
    """
    names = set(ds.variables)
    return not any(
        name in names
        for name in ("PH_IN_SITU_TOTAL", "PH_IN_SITU_TOTAL_ADJUSTED")
    )


# --------------------------------------------------------------------------
# Co-located CORE profile join
# --------------------------------------------------------------------------
# WHY THIS EXISTS
#
# BGC-Argo files carry the pH and oxygen sensors but NO practical salinity:
# inspecting real pH profiles, ``PSAL`` is absent from every one of them,
# while ``TEMP_DOXY`` is present but is the optode's co-located sensor
# temperature, not the core CTD temperature.
#
# That matters enormously.  Carbonate equilibria are strongly temperature
# dependent, and the salinity relation is the entire basis of the alkalinity
# estimate, so with no PSAL the module can derive NO aragonite saturation at
# all - which is precisely what happens on a BGC file alone.  Rather than
# substitute a climatological salinity (which would be a fabricated input to a
# scientific claim), the module fetches the co-located CORE profile, which
# publishes real measured ``PSAL`` and ``TEMP``, and joins it level by level.
#
# The two files describe the same cast, but they must NOT be joined by array
# index: see build_core_lookup below for a real file where the pH and the
# salinity sit in different profile indices, and where an index join silently
# returns nothing at all.
def core_profile_url(bgc_url: str) -> str:
    """Co-located CORE profile URL for a BGC profile URL.

    Argo file names encode the file type in the first character.  A BGC
    real-time profile is ``B<type><wmo>_<cycle>.nc`` and its core counterpart
    is the same name without the leading ``B``::

        BR2903464_116.nc  ->  R2903464_116.nc
        BD6990514_151.nc  ->  D6990514_151.nc

    Returns an empty string when the name does not follow the convention, so
    the caller skips the join rather than guess a path that might not exist.
    """
    if not bgc_url:
        return ""
    head, sep, tail = bgc_url.rpartition("/")
    if not sep or not tail.startswith("B") or "_" not in tail:
        # Require the real name shape B<type><wmo>_<cycle>.nc. The cycle
        # separator is the structural marker; without it there is nothing
        # identifying to derive a core name from, and stripping the leading
        # character anyway would invent a path such as "B.nc" -> ".nc".
        return ""
    return f"{head}/{tail[1:]}"


def apply_core_physics(level: dict, core_entry: dict | None) -> dict:
    """Fill a level's missing temperature/salinity from the co-located core.

    A level that already carries its own value keeps it: the BGC sensor's
    co-located reading belongs to the same instrument package as the pH, so
    it is preferred over the core CTD even where both exist. Only the gap is
    filled. Returns the same dict for convenient in-place use.
    """
    if not core_entry:
        return level
    if level.get("temperature_c") is None:
        value = core_entry.get("temperature_c")
        if value is not None:
            level["temperature_c"] = value
    if level.get("salinity_psu") is None:
        value = core_entry.get("salinity_psu")
        if value is not None:
            level["salinity_psu"] = value
    return level


# --------------------------------------------------------------------------
# Joining the core profile by PRESSURE, not by array index
# --------------------------------------------------------------------------
# WHY NOT BY (N_PROF, N_LEVELS) INDEX
#
# It looks safe - the BGC and core files share the cast's shape - and it is
# wrong. A real file makes the point: for BR6990700_072.nc the pH lives in
# profile 5 (304 levels, 0.3-1999.5 dbar) while the core file's PSAL lives in
# profile 6 (84 levels, 0.3-1999.5 dbar). The arrays are the same size, the
# cast time is identical, and an index join returns NOTHING for every level -
# silently, because a miss and an absent value look identical downstream.
#
# Worse, the failure is not even consistent: on some files the indices happen
# to coincide, so a partially working index join is easy to mistake for a
# working one.
#
# So the join is on physics, not layout: match the core profile whose pressure
# grid spans the same range as the BGC pH profile, then interpolate onto each
# BGC level's own pressure. Same cast, different sensor resolution - which is
# exactly what these two files are.

#: Minimum pressure tolerance (dbar) for accepting a nearest-neighbour core
#: lookup. BGC pH is reported at roughly 1-2 dbar resolution, so 5 dbar is a
#: loose bound that still refuses to pair a surface sample with a mid-water one.
CORE_PRESSURE_TOLERANCE_DBAR = 5.0


def _interpolate_by_pressure(
    profile: list[dict], pressure: float
) -> dict | None:
    """Core T/S at ``pressure`` by interpolation between bracketing levels.

    Pure linear interpolation between the two core measurements that straddle
    the requested pressure. Properties that matter here:

    * It NEVER extrapolates. A pressure outside the core profile's measured span
      returns None, so the level derives nothing instead of being extended
      beyond the instrument's reach.
    * It never reaches past a real measurement to the next real one, which is
      what the earlier nearest-within-half-a-gap rule tried and failed to do:
      a cast with 84 levels over 2000 dbar has ~24 dbar gaps, so a tolerance
      derived from spacing left 34% of pH levels with nothing.

    Interpolating temperature and salinity is routine oceanographic practice -
    both are smooth in the water column, and the alternative is discarding real
    measured pH because the co-located CTD happened to sample on a different
    grid. Where both bracketing levels carry a value, that value is used;
    where the interpolation pair is incomplete, the available side is taken
    only if it is within ``CORE_PRESSURE_TOLERANCE_DBAR`` of the request.
    """
    if not profile or pressure is None:
        return None
    pressures = profile_pressures(profile)
    if not pressures:
        return None
    lo_p, hi_p = pressures[0], pressures[-1]
    if pressure < lo_p or pressure > hi_p:
        return None  # outside the measured span: no extrapolation

    # First level at or beyond the request, and its predecessor.
    idx = 0
    while idx < len(pressures) - 1 and profile[idx]["pressure_dbar"] < pressure:
        idx += 1
    upper = profile[idx]
    lower = profile[max(idx - 1, 0)]
    if lower is upper:
        return _values_at(upper)
    span = upper["pressure_dbar"] - lower["pressure_dbar"]
    if span <= 0:
        return _values_at(upper)
    f = (pressure - lower["pressure_dbar"]) / span

    out: dict = {}
    for key in ("temperature_c", "salinity_psu"):
        a, b = lower.get(key), upper.get(key)
        if a is not None and b is not None:
            out[key] = a + (b - a) * f
        else:
            # Only one side measured: adopt it when it is genuinely adjacent,
            # never from further away than the strict tolerance.
            side = a if a is not None else b
            ref = lower if a is not None else upper
            if side is not None and abs(ref["pressure_dbar"] - pressure) <= CORE_PRESSURE_TOLERANCE_DBAR:
                out[key] = side
    return out or None


def profile_pressures(profile: list[dict]) -> list[float]:
    """Ascending pressures of the levels that have at least one usable value."""
    return [
        e["pressure_dbar"]
        for e in profile
        if e.get("pressure_dbar") is not None
        and (e.get("temperature_c") is not None or e.get("salinity_psu") is not None)
    ]


def _values_at(entry: dict) -> dict:
    return {
        "temperature_c": entry.get("temperature_c"),
        "salinity_psu": entry.get("salinity_psu"),
    }


def parse_core_physics(path: str) -> list[list[dict]]:
    """Read the co-located CORE profile as a list of depth-indexed profiles.

    Each profile is a list of ``{"pressure_dbar", "temperature_c",
    "salinity_psu"}`` sorted by ascending pressure. An unreadable file yields
    an empty list, which makes the caller fall back to whatever the BGC file
    itself carried - never to a guess.
    """
    try:
        import xarray as xr
    except ImportError:  # pragma: no cover - environment guard
        return []

    try:
        ds = xr.open_dataset(path, decode_times=False, engine="netcdf4")
    except Exception as exc:
        logger.debug("Cannot open core profile %s: %s", path, exc.__class__.__name__)
        return []

    try:
        temp_stack = _stacked_vars(ds, ("TEMP_ADJUSTED", "TEMP"))
        psal_stack = _stacked_vars(ds, ("PSAL_ADJUSTED", "PSAL"))
        pres_stack = _stacked_vars(ds, ("PRES", "PRES_ADJUSTED"))
        if not temp_stack and not psal_stack:
            return []
        shape = (temp_stack or psal_stack)[0].shape
        if len(shape) < 2:
            return []

        profiles: list[list[dict]] = []
        for i in range(shape[0]):
            levels: list[dict] = []
            for j in range(shape[1]):
                temperature = _level_value(temp_stack, i, j)
                salinity = _level_value(psal_stack, i, j)
                if temperature is None and salinity is None:
                    continue
                levels.append(
                    {
                        "pressure_dbar": _level_value(pres_stack, i, j),
                        "temperature_c": temperature,
                        "salinity_psu": salinity,
                    }
                )
            levels.sort(
                key=lambda e: (
                    e["pressure_dbar"] is None,
                    e["pressure_dbar"] if e["pressure_dbar"] is not None else 0.0,
                )
            )
            profiles.append(levels)
        return profiles
    except Exception as exc:  # defensive
        logger.debug("Core profile %s parse failed: %s", path, exc.__class__.__name__)
        return []
    finally:
        try:
            ds.close()
        except Exception:  # pragma: no cover
            pass


def _profile_span(profile: list[dict]) -> tuple[float, float] | None:
    """(min, max) pressure actually covered by a core profile."""
    values = [
        e["pressure_dbar"] for e in profile if e["pressure_dbar"] is not None
    ]
    if not values:
        return None
    return (min(values), max(values))


def _nearest_by_pressure(
    profile: list[dict], pressure: float, tolerance: float | None = None
) -> dict | None:
    """Deprecated shim kept for the nearest-neighbour behaviour.

    The live path is ``_interpolate_by_pressure``; see that function for why
    nearest-within-a-tolerance was not sufficient.
    """
    if tolerance is None:
        tolerance = CORE_PRESSURE_TOLERANCE_DBAR
    if not profile or pressure is None:
        return None
    best = None
    best_delta = None
    for entry in profile:
        p = entry.get("pressure_dbar")
        if p is None:
            continue
        delta = abs(p - pressure)
        if best_delta is None or delta < best_delta:
            best, best_delta = entry, delta
    if best is None or best_delta is None or best_delta > tolerance:
        return None
    return _values_at(best)


def build_core_lookup(
    bgc_pressures: dict[int, list[float | None]],
    core_profiles: list[list[dict]],
) -> dict[tuple[int, int], dict]:
    """Map ``(profile_index, level_index)`` to core T/S for one BGC file.

    For each BGC profile that carries pH, the core profile whose pressure span
    best covers it is selected, then each level is matched by pressure within
    ``CORE_PRESSURE_TOLERANCE_DBAR``.
    """
    if not core_profiles:
        return {}

    spans = [(idx, _profile_span(p)) for idx, p in enumerate(core_profiles)]
    # A usable core profile has levels and a real vertical extent. The test is
    # the span WIDTH, not a positive start: the topmost pressure bin is
    # routinely slightly negative (R4902626_145's core profile spans
    # -0.1 to 1968.2 dbar), and rejecting that would silently drop a perfectly
    # good cast.
    usable = [
        (idx, span)
        for idx, span in spans
        if span is not None and (span[1] - span[0]) > 0.5 and len(core_profiles[idx]) > 1
    ]
    if not usable:
        return {}

    lookup: dict[tuple[int, int], dict] = {}
    claimed: set[int] = set()
    for bgc_index, pressures in bgc_pressures.items():
        present = [p for p in pressures if p is not None]
        if not present:
            continue
        lo, hi = min(present), max(present)
        # Prefer the core profile covering this span; break ties toward the
        # one with more levels (a denser cast is the better interpolant) and
        # toward the earliest profile for a stable, reproducible choice.
        best_idx = None
        best_key = None
        for idx, (c_lo, c_hi) in usable:
            coverage = min(hi, c_hi) - max(lo, c_lo)
            if coverage <= 0:
                continue
            key = (coverage, len(core_profiles[idx]), -idx)
            if best_key is None or key > best_key:
                best_key, best_idx = key, idx
        if best_idx is None:
            continue
        # Two BGC profiles matching the same core profile is legitimate (a
        # file can carry several casts), so a profile is not consumed once used.
        claimed.add(best_idx)
        chosen = core_profiles[best_idx]
        for level_index, pressure in enumerate(pressures):
            entry = (
                _interpolate_by_pressure(chosen, pressure)
                if pressure is not None
                else None
            )
            if entry is not None:
                lookup[(bgc_index, level_index)] = entry
    return lookup


def _clean_text(value) -> str | None:
    """Bytes/str/numpy scalar -> stripped string, or None."""
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("ascii", "replace")
    text = str(value).strip()
    return text or None


def _has_values(values) -> bool:
    """True when the array holds at least one finite (real, non-NaN) number."""
    if values is None or not hasattr(values, "shape") or values.size == 0:
        return False
    try:
        import numpy as np

        arr = np.asarray(values)
        if arr.dtype.kind in "SU":
            return arr.size > 0
        if arr.dtype.kind not in "fiu":
            return arr.size > 0
        return bool(np.any(np.isfinite(arr.astype("float64", copy=False))))
    except Exception:  # pragma: no cover - defensive
        return False


def _index_value(values, idx: int, n_levels: int):
    """Position array indexed by profile; flatten 1xN arrays as Argo stores."""
    if values is None:
        return None
    if getattr(values, "ndim", None) == 2 and values.shape[1] == n_levels:
        return values[idx, 0] if idx < values.shape[0] else None
    if values.ndim >= 1 and idx < values.shape[0]:
        return values[idx]
    return None


def _index_2d(values, i: int, j: int):
    if values is None:
        return None
    if len(values.shape) >= 2 and i < values.shape[0] and j < values.shape[1]:
        return values[i, j]
    return None


def _first_scalar(var):
    if var is None:
        return None
    try:
        return var.values.item()
    except Exception:  # pragma: no cover - defensive
        vals = var.values
        if getattr(vals, "size", 0):
            try:
                return vals.ravel()[0]
            except Exception:  # pragma: no cover
                return None
    return None


def _juld_to_dt(days: float | None) -> datetime | None:
    if days is None:
        return None
    try:
        return ARGO_EPOCH + timedelta(days=float(days))
    except (OverflowError, TypeError, ValueError):  # pragma: no cover
        return None
