"""
TidalTwin - Acidification: carbonate chemistry and the acidification ladder
==========================================================================
This is the load-bearing science file of the acidification module.  Two
separate things live here and they must not be confused:

1. MEASURED pH.  BGC-Argo pH sensors report in-situ pH on the TOTAL scale.
   Every threshold below is defined on that scale.

2. DERIVED aragonite saturation.  No BGC-Argo float measures Omega_arag, so it
   is computed here from the measured pH together with the measured
   temperature and salinity, via CO2SYS (PyCO2SYS).  That is a derivation, not
   an observation, and it is labelled as such everywhere it surfaces.

THE ALKALINITY ASSUMPTION, STATED PLAINLY
------------------------------------------
A carbonate system needs two independent inputs.  We have pH from the float.
We do NOT have total alkalinity, because BGC-Argo does not carry a TA sensor.
So TA is estimated from salinity with the published global surface relation of
Lee et al. (2006)::

    TA = 2305 + 58.66*dS + 2.32*dS^2 - 1.41*dS^3      dS = S - 35
    in umol/kg, dS in practical salinity units.

How wrong can that be?  Measured against a known TA of 2300, sweeping the
assumption by +-50 umol/kg moves Omega_arag by only about +-0.08 (roughly
+-2.4 percent) across the pH range this module cares about.  That is small
next to the biological thresholds, so the derivation is usable - but it is an
estimate, the uncertainty is real, and ``DERIVED_OMEGA_NOTE`` says so wherever
it is displayed.  Temperature matters FAR more than the alkalinity guess: the
same pH of 7.70 gives Omega_arag 0.99 at 10 C and 2.11 at 30 C.  That is why a
missing co-located temperature yields NO aragonite value at all rather than a
climatological substitute - a wrong number here would be worse than no number.

THE SEVERITY LADDER
-------------------
Ocean acidification is conventionally discussed against aragonite saturation,
but the only quantity we ever *measure* is pH.  The ladder is therefore
anchored on pH, with aragonite reported alongside as the biological
interpretation:

    pH (total)   label      biological reading
    >= 8.05      NORMAL     comfortably above pre-industrial open-ocean pH
    8.00 - 8.05  LOW        measurably reduced, aragonite still healthy
    7.90 - 8.00  MODERATE   approaching aragonite undersaturation
    7.75 - 7.90  HIGH       Omega_arag ~1-2, shell formation at risk
    < 7.75       CRITICAL   Omega_arag near or below 1, actively corrosive

``is_acidic`` is true below 8.00.  ``is_undersaturated`` is the separate,
harder biological test: Omega_arag below 1.0, where minerals actively
dissolve.
"""

from __future__ import annotations

import math

# Canonical unit strings.
UNIT_PH = "pH (total scale)"
UNIT_OMEGA = "ratio (dimensionless)"

# --------------------------------------------------------------------------
# Physical plausibility window for seawater pH on the total scale.
# --------------------------------------------------------------------------
# WHY THIS EXISTS, AND WHY IT IS THE PRIMARY FILTER RATHER THAN THE QC FLAG
#
# BGC-Argo pH arrives as REAL-TIME data (PARAMETER_DATA_MODE 'R') that has not
# been through delayed-mode QC.  Inspected directly in the Indian Ocean box,
# the QC flags are actively misleading as an acceptance test:
#
#   * profiles whose every value is QC '3' or QC '0' carry pH of 7.44-8.47,
#     which is entirely normal seawater;
#   * profiles whose every value is QC '4' ("bad") carry pH from -1.6 to 6.2,
#     which is not physically possible for seawater at all.
#
# So rejecting on QC alone would throw away the good data, and accepting on QC
# alone would admit sensor nonsense.  Physical plausibility separates the two
# populations perfectly and is the primary gate; the QC flag is retained and
# used only to MODULATE CONFIDENCE.  Rejecting a value for being
# outside the range of seawater is not a judgement call - pH 6.2 cannot occur.
#
# The window is wide on purpose.  It spans every value the ocean plausibly
# occupies, including the acidified extremes we specifically want to catch, and
# it excludes only the impossible.
PH_PLAUSIBLE_MIN = 7.4
PH_PLAUSIBLE_MAX = 8.6

# Severity ordinals are 1-based, matching dissolved_oxygen_samples so the two
# modules rank on one comparable scale.  1-based means "no classification" is
# None rather than colliding with NORMAL.
SEVERITY_ORDINALS = {
    "NORMAL": 1,
    "LOW": 2,
    "MODERATE": 3,
    "HIGH": 4,
    "CRITICAL": 5,
}

SEVERITY_LABEL_DISPLAY = {
    "NORMAL": "Normal",
    "LOW": "Low",
    "MODERATE": "Moderate",
    "HIGH": "High",
    "CRITICAL": "Critical",
}

SEVERITY_ORDINAL_TO_LABEL: dict[int, str] = {
    ordinal: label for label, ordinal in SEVERITY_ORDINALS.items()
}

# (low_inclusive_ph, high_exclusive_or_None_ph, label)
# The ladder is read on the measured pH and must stay identical to
# hotspots.SEVERITY_LADDER and the ingest classifier.
SEVERITY_LADDER: tuple[tuple[float, float | None, str], ...] = (
    (0.0, 7.75, "CRITICAL"),
    (7.75, 7.90, "HIGH"),
    (7.90, 8.00, "MODERATE"),
    (8.00, 8.05, "LOW"),
    (8.05, None, "NORMAL"),
)

# Conventional pH anchor for "reduced relative to open-ocean pre-industrial".
ACIDIFICATION_THRESHOLD_PH = 8.00

# Aragonite saturation: 1.0 is the point at which aragonite begins to
# dissolve, so it is the single hardest biological threshold in oceanography.
ARAGONITE_SATURATION = 1.0
# 2.0 is widely used as the practical operational threshold for shellfish
# aquaculture and larval recruitment.
ARAGONITE_STRESS = 2.0

# Depth bands, matching the deoxygenation module so the two dashboards read the
# same way side by side.
DEPTH_BANDS = (
    ("surface", 0.0, 30.0, "Surface (0-30 m)"),
    ("pycnocline", 30.0, 200.0, "Pycnocline (30-200 m)"),
    ("deep", 200.0, 20000.0, "Deep (>200 m)"),
)

DERIVED_OMEGA_NOTE = (
    "Aragonite and calcite saturation are DERIVED, not measured. BGC-Argo floats "
    "carry no alkalinity sensor, so total alkalinity is estimated from salinity "
    "with the Lee et al. (2006) global surface relation and the carbonate system "
    "is solved with CO2SYS. A +-50 umol/kg error in that alkalinity assumption "
    "moves Omega_arag by roughly +-0.08. No aragonite value is produced when the "
    "co-located temperature or salinity is missing, because carbonate equilibria "
    "are strongly temperature dependent and a substitute would be misleading."
)


# --------------------------------------------------------------------------
# Carbonate chemistry
# --------------------------------------------------------------------------
def total_alkalinity_from_salinity(salinity_psu: float) -> float:
    """Lee et al. (2006) global surface total-alkalinity vs salinity, umol/kg.

    Pure salinity regression: no external data, fully deterministic, and the
    resulting Omega_arag error is small enough (see module docstring) to be
    reported alongside the value rather than hidden.
    """
    d = float(salinity_psu) - 35.0
    return 2305.0 + 58.66 * d + 2.32 * d**2 - 1.41 * d**3


def _co2sys_available() -> bool:
    try:
        import PyCO2SYS  # noqa: F401
        return True
    except Exception:  # pragma: no cover - environment guard
        return False


def derive_carbonate_chemistry(
    ph_total: float | None,
    temperature_c: float | None,
    salinity_psu: float | None,
    total_alkalinity_umol_kg: float | None = None,
) -> dict:
    """Derive DIC, pCO2 and calcite/aragonite saturation from measured pH.

    Returns a dict with ``status``:

    * ``OK``            - every field is a number; ``derived`` is True.
    * ``NO_PH``         - no measured pH, so nothing can be derived.
    * ``MISSING_T_S``   - pH present but temperature or salinity absent.
    * ``NON_PHYSICAL``  - pH outside the seawater plausibility window; the
                          system is not solvable from an impossible input.
    * ``SOLVE_FAILED``  - CO2SYS refused the inputs.
    * ``NO_LIBRARY``    - PyCO2SYS is not installed in this environment.

    ``derived`` is True only for ``OK``.  Callers must not treat any other
    status as a zero.
    """
    base = {
        "status": "OK",
        "derived": False,
        "dic_umol_kg": None,
        "pco2_uatm": None,
        "omega_arag": None,
        "omega_calc": None,
        "alk_umol_kg": None,
        "reason": None,
    }

    if ph_total is None:
        return {**base, "status": "NO_PH", "reason": "no measured pH on this level"}
    if not (is_ph_plausible(ph_total)):
        return {
            **base,
            "status": "NON_PHYSICAL",
            "reason": (
                f"pH {ph_total:.3f} is outside the seawater plausibility window "
                f"[{PH_PLAUSIBLE_MIN}, {PH_PLAUSIBLE_MAX}]; the carbonate system "
                "cannot be solved from an impossible input"
            ),
        }
    if temperature_c is None or salinity_psu is None:
        missing = []
        if temperature_c is None:
            missing.append("temperature")
        if salinity_psu is None:
            missing.append("salinity")
        return {
            **base,
            "status": "MISSING_T_S",
            "reason": (
                "carbonate equilibria are strongly temperature dependent; missing "
                + " and ".join(missing)
                + " on this level, so no aragonite saturation was derived"
            ),
        }
    if not _co2sys_available():
        return {
            **base,
            "status": "NO_LIBRARY",
            "reason": "PyCO2SYS is not installed, so no carbonate chemistry was derived",
        }

    alk = (
        float(total_alkalinity_umol_kg)
        if total_alkalinity_umol_kg is not None
        else total_alkalinity_from_salinity(salinity_psu)
    )

    try:
        import PyCO2SYS

        out = PyCO2SYS.CO2SYS(
            PAR1=ph_total,
            PAR2=alk,
            PAR1TYPE=3,   # pH
            PAR2TYPE=1,   # total alkalinity, umol/kg
            SAL=float(salinity_psu),
            TEMPIN=float(temperature_c),   # degrees Celsius
            TEMPOUT=float(temperature_c),
            PRESIN=0,
            PRESOUT=0,
            SI=0,
            PO4=0,
            pHSCALEIN=1,      # total scale
            K1K2CONSTANTS=10,  # Lueker et al. 2000, total scale, real seawater
            KSO4CONSTANTS=1,   # Dickson 1990a + Uppstrom 1974
        )
    except Exception as exc:  # defensive: a bad level must not kill an ingest
        return {
            **base,
            "status": "SOLVE_FAILED",
            "reason": f"CO2SYS could not solve this level ({exc.__class__.__name__})",
        }

    def _val(key: str) -> float | None:
        raw = out.get(key)
        if raw is None:
            return None
        try:
            value = float(raw[0])
        except (TypeError, ValueError, IndexError):
            return None
        return value if math.isfinite(value) else None

    dic = _val("TCO2")
    omega_arag = _val("OmegaARout")
    omega_calc = _val("OmegaCAout")
    pco2 = _val("pCO2out")

    if dic is None or omega_arag is None:
        return {
            **base,
            "status": "SOLVE_FAILED",
            "reason": "CO2SYS returned a non-finite carbonate state for this level",
        }

    return {
        "status": "OK",
        "derived": True,
        "dic_umol_kg": round(dic, 2),
        "pco2_uatm": round(pco2, 1) if pco2 is not None else None,
        "omega_arag": round(omega_arag, 4),
        "omega_calc": round(omega_calc, 4) if omega_calc is not None else None,
        "alk_umol_kg": round(alk, 1),
        "reason": None,
    }


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------
def is_ph_plausible(ph: float | None) -> bool:
    """True when a pH value could physically be seawater.

    See the long note at the top of the module: this is the primary acceptance
    gate for real-time BGC-Argo pH, precisely because the QC flag is not.
    """
    if ph is None:
        return False
    try:
        value = float(ph)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(value):
        return False
    return PH_PLAUSIBLE_MIN <= value <= PH_PLAUSIBLE_MAX


def severity_label_for_ordinal(ordinal: int | None) -> str:
    """Display label for a severity ordinal, never a misleading default."""
    if ordinal is None:
        return "Unknown"
    label = SEVERITY_ORDINAL_TO_LABEL.get(ordinal)
    if label is None:
        return "Unknown"
    return SEVERITY_LABEL_DISPLAY.get(label, label)


def severity_for_ph(ph_total: float | None) -> tuple[str | None, int | None, bool]:
    """Resolve a measured pH into (label, ordinal, is_acidic).

    ``ph_total`` of ``None`` yields all-``None``/``False`` rather than guessing.
    An implausible pH is also never classified: it is not a measurement of the
    ocean, it is a broken sensor, and labelling it would launder a fault into a
    scientific claim.
    """
    if ph_total is None or not is_ph_plausible(ph_total):
        return None, None, False
    for low, high, label in SEVERITY_LADDER:
        if ph_total >= low and (high is None or ph_total < high):
            return label, SEVERITY_ORDINALS[label], ph_total < ACIDIFICATION_THRESHOLD_PH
    return None, None, False


def is_undersaturated(omega_arag: float | None) -> bool:
    """True when aragonite is at or below saturation.

    ``None`` (never derived) is False - absence of a derivation is not evidence
    of undersaturation, and reporting it as such would manufacture an alert.
    """
    if omega_arag is None:
        return False
    try:
        return float(omega_arag) < ARAGONITE_SATURATION
    except (TypeError, ValueError):
        return False


# --------------------------------------------------------------------------
# Alert tiers - the policy layer, mirroring the deoxygenation module's shape.
# --------------------------------------------------------------------------
ALERT_TIER_RULES = (
    (5, "critical", "SHELLFISH_CORAL_ADVISORY",
     "pH below 7.75 - aragonite at or near saturation, actively corrosive to "
     "shell and skeleton. Suspend shellfish seeding and advise fisheries."),
    (4, "high", "FISHERIES_ALERT",
     "pH between 7.75 and 7.90 - Omega_arag roughly 1-2, shell formation at "
     "risk. Flag for fisheries advisory and increase monitoring."),
    (3, "medium", "REPEAT_MONITORING",
     "pH between 7.90 and 8.00 - measurably acidified and approaching "
     "undersaturation. Repeat sampling and flag for policy review."),
    (2, "low", "MONITOR",
     "pH between 8.00 and 8.05 - reduced relative to pre-industrial "
     "open-ocean values but not yet limiting. Keep watching."),
    (1, "info", "NONE",
     "pH at or above 8.05 - normal open-ocean conditions."),
)


def alert_for_ordinal(ordinal: int | None) -> tuple[str, str, str]:
    """Map a severity ordinal to (severity, action, rationale)."""
    if ordinal is None:
        return "unknown", "INSUFFICIENT_BASIS", "No measured pH value."
    for threshold, severity, action, rationale in ALERT_TIER_RULES:
        if ordinal >= threshold:
            return severity, action, rationale
    return "unknown", "INSUFFICIENT_BASIS", "Ordinal outside the known ladder."


def depth_band_for_depth(depth_m: float | None) -> str:
    """Which depth band a sample belongs to."""
    if depth_m is None:
        return "deep"
    for key, low, high, _label in DEPTH_BANDS:
        if low <= depth_m < high:
            return key
    return "deep"
