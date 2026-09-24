"""TIDE Voice Agent - tool registry (server-side definition).

The Voice Agent is an INTERACTION LAYER over the existing TidalTwin platform.
Every tool here is a thin, validated contract over an EXISTING endpoint or an
existing frontend/UI control.  No duplicate data endpoints are created and no
new tables/observation stores are introduced.

Execution split:
  * ``tidetwin_*`` tools run in the browser through the existing API client
    (``frontend/src/api/client.ts``) or the in-page context registry.
  * ``ui_*`` tools run in the browser through the voice command bus.
  * ``web_search`` runs server-side in ``app/api/voice.py`` (no API key).

Tool names use only letters, digits and underscores (no dots): the OpenAI
Realtime GA API rejects names outside ``^[a-zA-Z0-9_-]+$``.

The registry is the single source of truth for: the OpenAI Realtime session
tools, the parameter schemas the model must satisfy, and the validation used
by tests.  The browser receives these schemas with the session payload and
re-validates arguments before executing a tool.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Shared enumerations (kept aligned with the existing platform vocabulary).
# ---------------------------------------------------------------------------

OCEAN_VARIABLES = (
    "temperature",
    "salinity",
    "oxygen",
    "chlorophyll",
    "wave_height",
    "current_speed",
    "pressure",
    "density",
    "ph",
    "nutrients",
)

# Mirrors LayerKey in frontend/src/components/3d/globe/CesiumGlobe.tsx.
UI_LAYERS = (
    "labels",
    "temperature",
    "waves",
    "currents",
    "storm",
    "uncertainty",
    "priority",
    "argo",
    "realArgo",
    "realSST",
    "realChl",
    "disagreement",
    "anomalies",
    "tide",
    "isos",
    "vectors",
    "modelgrid",
    "glider",
)

# Mirrors the application routes in frontend/src/App.tsx.
UI_PAGES = (
    "home",
    "globe",
    "monitoring",
    "classic",
    "assistant",
    "validate",
    "anomalies",
    "forensics",
    "intelligence",
    "tide",
    "replay",
    "validation",
    "oceanvision",
    "coastal",
    "scenarios",
    "safety",
    "risk",
    "stories",
    "reports",
)

# Scroll-to targets inside the Digital Twin page.
UI_PANELS = (
    "depth-profile",
    "transect",
    "anomaly",
    "tide-candidates",
    "provenance",
    "ersst",
    "chlor",
    "model-comparison",
    "event-replay",
    "argo-profile",
)

TIME_LABELS = ("now", "start", "mid", "end", "forecast")

SEVERITIES = ("low", "medium", "high")


def _str(description: str) -> dict:
    return {"type": "string", "description": description}


def _num(description: str, *, minimum: float | None = None, maximum: float | None = None) -> dict:
    schema: dict[str, Any] = {"type": "number", "description": description}
    if minimum is not None:
        schema["minimum"] = minimum
    if maximum is not None:
        schema["maximum"] = maximum
    return schema


def _int(description: str, *, minimum: int | None = None, maximum: int | None = None) -> dict:
    schema: dict[str, Any] = {"type": "integer", "description": description}
    if minimum is not None:
        schema["minimum"] = minimum
    if maximum is not None:
        schema["maximum"] = maximum
    return schema


def _bool(description: str) -> dict:
    return {"type": "boolean", "description": description}


def _enum(description: str, values: tuple[str, ...]) -> dict:
    return {"type": "string", "enum": list(values), "description": description}


def _region_props() -> dict:
    """Common 'where' arguments accepted by every data tool.

    The model rarely knows numeric ids, so tools accept a human region name
    which the browser resolves against the loaded TidalTwin locations and a
    built-in gazetteer (Bay of Bengal, Arabian Sea, ...).
    """
    return {
        "location_id": _int("Numeric TidalTwin location id when known."),
        "region": _str("Human region or place name, e.g. 'Bay of Bengal', 'Goa'."),
    }


def _where_required() -> list[str]:
    return []


def _variable_props() -> dict:
    return {"variable": _enum("Ocean variable to analyse.", OCEAN_VARIABLES)}


def _depth_props() -> dict:
    return {"depth_m": _num("Depth in metres (0 = surface).", minimum=0, maximum=11000)}


def _tool(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required or [],
            "additionalProperties": False,
        },
    }


# ---------------------------------------------------------------------------
# The registry.
# ---------------------------------------------------------------------------

TOOL_SPECS: list[dict] = [
    # --- Project information -------------------------------------------
    _tool(
        "tidetwin_get_project_status",
        "Health and identity of the running TidalTwin platform: version, "
        "release, per-subsystem status and monitored-region count. Use when "
        "the user asks what TidalTwin is, what is running, or system status.",
        {},
    ),
    _tool(
        "tidetwin_get_ui_context",
        "Current UI context of the page the user is on: focused region, "
        "latitude/longitude, depth, time cursor, selected variable, active "
        "layers, selected event/anomaly, current TIDE recommendation and page "
        "route. ALWAYS call this before answering questions that contain "
        "'here', 'this', 'it', 'this region' or that depend on what is "
        "currently visible.",
        {},
    ),
    _tool(
        "tidetwin_get_data_sources",
        "Registered TidalTwin data sources and provenance entries (which "
        "instruments/models/feeds support the numbers on screen). Use for "
        "'where did this come from', 'what data supports this', "
        "'are these observations real or simulated'.",
        {},
    ),
    # --- Ocean twin fields ---------------------------------------------
    _tool(
        "tidetwin_get_region_overview",
        "Latest observation snapshot plus model-vs-observation comparison for "
        "one region. Returns recent readings with their data status "
        "(REAL/HISTORICAL/SIMULATED/SYNTHETIC/MODEL_DERIVED), the model "
        "value, observed value, difference, severity and confidence.",
        {**_region_props(), **_variable_props()},
        _where_required(),
    ),
    _tool(
        "tidetwin_get_ocean_field",
        "Read one ocean variable for a region or coordinate: surface grids "
        "use the real NOAA ERSST/VIIRS fields, depth queries use the real "
        "model grid slices, and point queries use stored observations. Never "
        "invent a value - the result carries data_status and limitations.",
        {
            **_variable_props(),
            **_region_props(),
            "latitude": _num("Latitude in degrees when a coordinate is known."),
            "longitude": _num("Longitude in degrees when a coordinate is known."),
            **_depth_props(),
        },
        ["variable"],
    ),
    _tool(
        "tidetwin_get_depth_profile",
        "Vertical profile of one variable with depth for a region "
        "(thermocline / mixed-layer structure from the existing Twin profile "
        "service).",
        {**_region_props(), **_variable_props()},
        _where_required(),
    ),
    _tool(
        "tidetwin_get_observations",
        "Recent stored observations for a region with an honest per-row data "
        "status (REAL, HISTORICAL, SIMULATED, SYNTHETIC, MODEL_DERIVED) and "
        "summary counts. Use for 'how many observations', 'is this real "
        "data', 'are these simulated'.",
        {**_region_props(), "limit": _int("Rows to return (1-20).", minimum=1, maximum=20)},
        _where_required(),
    ),
    _tool(
        "tidetwin_get_satellite_observations",
        "Satellite/analysis inputs currently loaded: NOAA ERSST sea-surface "
        "temperature and VIIRS satellite chlorophyll, with availability and "
        "coverage metadata.",
        {
            "latitude": _num("Optional latitude to resolve a nearest grid cell."),
            "longitude": _num("Optional longitude to resolve a nearest grid cell."),
        },
    ),
    _tool(
        "tidetwin_get_argo_observations",
        "Real Argo profiling floats currently registered in TidalTwin "
        "(count, ids, positions). Use for questions about Argo floats.",
        {},
    ),
    # --- Anomaly Radar ---------------------------------------------------
    _tool(
        "tidetwin_get_anomalies",
        "Detected anomalies from the existing Ocean Anomaly Radar, sorted by "
        "severity. Each row carries location, variable, model vs observed "
        "values, severity, confidence and data_status.",
        {
            **_variable_props(),
            "severity": _enum("Minimum severity filter.", SEVERITIES),
            "region": _str("Optional region name filter."),
            "limit": _int("Rows to return (1-10).", minimum=1, maximum=10),
        },
    ),
    _tool(
        "tidetwin_get_anomaly_statistics",
        "Aggregate the current anomaly set: total, counts by severity and "
        "variable, and the single strongest anomaly. Use for 'what is "
        "abnormal here', 'is this getting worse', 'strongest anomaly'.",
        _variable_props(),
    ),
    # --- Forensics / events --------------------------------------------
    _tool(
        "tidetwin_get_events",
        "Detected ocean events from the existing intelligence/forensics "
        "engine (type, region, variable, severity, when it began, data "
        "status).",
        {},
    ),
    _tool(
        "tidetwin_investigate_event",
        "Run the existing Ocean Forensics investigation for a region: "
        "contributing factors, evidence, confidence, uncertainty, event DNA "
        "fingerprint and a stage timeline. Use for 'why did this happen', "
        "'what caused this', 'when did it start', 'what is happening here'.",
        {**_region_props(), "event_index": _int("Event index when the user referred to a numbered event.", minimum=0)},
        _where_required(),
    ),
    _tool(
        "tidetwin_get_event_timeline",
        "Stage timeline for a region's ocean event "
        "(Normal -> Observed -> Intensifying -> Severe -> Turning point -> "
        "Recovery) with onset timing.",
        _region_props(),
        _where_required(),
    ),
    # --- TIDE decision intelligence -------------------------------------
    _tool(
        "tidetwin_get_tide_candidates",
        "Ranked TIDE next-observation candidates with decision impact, "
        "uncertainty, data gap, anomaly persistence, observation cost, "
        "observation value, affected decision, reason and limitations. "
        "Recommendations are MODEL_DERIVED and never persisted.",
        {**_region_props(), **_variable_props(), **_depth_props()},
        _where_required(),
    ),
    _tool(
        "tidetwin_get_tide_explanation",
        "TIDE explanation for the top candidate: why it was chosen, the "
        "evidence chain, confidence context, factors and limitations.",
        {**_region_props(), **_variable_props(), **_depth_props()},
        _where_required(),
    ),
    _tool(
        "tidetwin_get_tide_evidence",
        "Raw TIDE evidence records behind the recommendation: evidence type, "
        "strength, description, source system and data status.",
        {**_region_props(), **_variable_props(), **_depth_props()},
        _where_required(),
    ),
    _tool(
        "tidetwin_get_tide_verdict",
        "Evidence-based TIDE verdict for one location: "
        "LIKELY_SENSOR_ISSUE / LIKELY_MODEL_ISSUE / LIKELY_MISSING_PHENOMENON "
        "/ INSUFFICIENT_EVIDENCE with confidence, evidence, alternative "
        "explanation and recommended observation.",
        {**_region_props(), **_variable_props(), **_depth_props()},
        _where_required(),
    ),
    _tool(
        "tidetwin_get_tide_uncertainty",
        "Current TIDE uncertainty, data gaps and model-observation "
        "disagreements for a region. Use for 'how confident are you', "
        "'what is missing here', 'what would reduce uncertainty'.",
        _region_props(),
        _where_required(),
    ),
    _tool(
        "tidetwin_recommend_next_observation",
        "One-shot TIDE recommendation: top-ranked next observation plus its "
        "explanation, evidence, confidence and limitations. Use for 'where "
        "should we observe next', 'what does TIDE recommend', 'why there'.",
        {**_region_props(), **_variable_props(), **_depth_props()},
        _where_required(),
    ),
    _tool(
        "tidetwin_get_event_context",
        "Existing event composed with its Event DNA and TIDE context "
        "(event-id form, e.g. 'event-2').",
        {"event_id": _str("Event id, e.g. 'event-2'.")},
        ["event_id"],
    ),
    _tool(
        "tidetwin_get_replay",
        "Read-only Decision Replay for an existing event: model-only vs "
        "TIDE-assisted step walkthrough, comparison metrics, decision change "
        "and regret. Nothing is written to the observation store.",
        {"event_id": _str("Event id, e.g. 'event-1'."), **_region_props(), **_variable_props(), **_depth_props()},
        ["event_id"],
    ),
    _tool(
        "tidetwin_get_validation_status",
        "Honest TIDE validation status: maturity buckets (IMPLEMENTED / "
        "DEMONSTRATED / TESTED / EMPIRICALLY_VALIDATED), dataset, ground "
        "truth and the scientific boundary. Use for 'is TIDE validated', "
        "'validation status', 'benchmark results'.",
        {},
    ),
    # --- Simulation / comparison ----------------------------------------
    _tool(
        "tidetwin_run_whatif",
        "Run the existing deterministic What-If scenario engine for a region "
        "(wind %, temperature, salinity or mixing deltas). The result is "
        "SIMULATED, never persisted, and carries limitations.",
        {
            **_region_props(),
            "wind_percent": _num("Relative wind change in percent, e.g. 30.", minimum=-200, maximum=200),
            "temp_delta": _num("Temperature delta in degC.", minimum=-10, maximum=10),
            "salinity_delta": _num("Salinity delta in PSU.", minimum=-10, maximum=10),
            "mixing_factor": _num("Mixing multiplier.", minimum=0, maximum=5),
        },
        _where_required(),
    ),
    _tool(
        "tidetwin_compare_scenarios",
        "Compare a baseline (unchanged conditions) against a What-If "
        "scenario for the same region and report which indicators changed.",
        {
            **_region_props(),
            "wind_percent": _num("Relative wind change in percent.", minimum=-200, maximum=200),
            "temp_delta": _num("Temperature delta in degC.", minimum=-10, maximum=10),
            "salinity_delta": _num("Salinity delta in PSU.", minimum=-10, maximum=10),
            "mixing_factor": _num("Mixing multiplier.", minimum=0, maximum=5),
        },
        _where_required(),
    ),
    _tool(
        "tidetwin_get_model_comparison",
        "Model vs observation comparison for a region: model value, observed "
        "value, difference, percent difference, severity band, confidence "
        "factors and the existing textual explanation.",
        {**_region_props(), **_variable_props()},
        _where_required(),
    ),
    # --- Current information --------------------------------------------
    _tool(
        "web_search",
        "Search the public web for CURRENT external information (news, "
        "today's events, live prices, recent releases). Use ONLY for "
        "Category D questions about the outside world; never use it for "
        "TidalTwin or ocean-data questions, and always label the answer as "
        "a web result.",
        {
            "query": {"type": "string", "minLength": 1, "maxLength": 250, "description": "Search query."},
            "max_results": _int("Maximum results (1-5).", minimum=1, maximum=5),
        },
        ["query"],
    ),
    # --- Globe / UI control ---------------------------------------------
    _tool(
        "ui_focus_region",
        "Move and zoom the Cesium globe to a region or coordinate. Accepts a "
        "location id, a human region name ('Bay of Bengal', 'Arabian Sea', "
        "'Goa') or raw lat/lon. Use for 'take me to', 'go to', 'show ... "
        "region', 'where is the event/recommended observation'.",
        {
            **_region_props(),
            "latitude": _num("Latitude when no named region matches."),
            "longitude": _num("Longitude when no named region matches."),
        },
    ),
    _tool(
        "ui_set_depth",
        "Set the globe depth-slice level in metres (snaps to the nearest "
        "available model depth level).",
        {"depth_m": _num("Depth in metres.", minimum=0, maximum=6000)},
        ["depth_m"],
    ),
    _tool(
        "ui_set_time",
        "Move the globe event-replay time cursor. 'now' is the latest "
        "observed hour; 'forecast' the far end of the projected window.",
        {"label": _enum("Time anchor.", TIME_LABELS), "hours_ago": _int("Hours before 'now' when label is omitted.", minimum=0, maximum=2000)},
    ),
    _tool(
        "ui_set_variable",
        "Select the compared/displayed ocean variable on the globe "
        "(temperature, wave_height, salinity, current_speed).",
        {"variable": _enum("Variable to show.", OCEAN_VARIABLES)},
        ["variable"],
    ),
    _tool(
        "ui_toggle_layer",
        "Activate or deactivate a globe data layer by its LayerKey "
        "(e.g. 'anomalies', 'tide', 'realArgo', 'realSST', 'realChl', "
        "'disagreement', 'storm', 'glider').",
        {"layer": _enum("Layer key.", UI_LAYERS), "on": _bool("true to activate, false to deactivate (omit to toggle).")},
        ["layer"],
    ),
    _tool(
        "ui_navigate",
        "Open an existing TidalTwin page: globe (Digital Twin), forensics, "
        "tide (TIDE Command Center), replay (Decision Replay), validation "
        "(TIDE Validation), anomalies (Anomaly Radar), scenarios (What-If "
        "Scenario Lab), validate, monitoring, intelligence, assistant, "
        "safety, risk, reports, stories, oceanvision, coastal, classic, "
        "home. Optional location_id/variable deep-link into TIDE pages.",
        {
            "page": _enum("Target page.", UI_PAGES),
            "location_id": _int("Optional location id to deep-link."),
            "variable": _enum("Optional variable to deep-link.", OCEAN_VARIABLES),
        },
        ["page"],
    ),
    _tool(
        "ui_reveal_panel",
        "Scroll the Digital Twin page to an on-screen panel so the user can "
        "see it: depth-profile, transect, anomaly, tide-candidates, "
        "provenance, ersst, chlor, model-comparison, event-replay, "
        "argo-profile. Navigate to the globe first when the user is "
        "elsewhere.",
        {"panel": _enum("Panel target.", UI_PANELS)},
        ["panel"],
    ),
]


def tool_names() -> list[str]:
    return [spec["name"] for spec in TOOL_SPECS]


def tool_payloads() -> list[dict]:
    """Tools exactly as registered with the Realtime session (and returned to
    the browser so it can re-validate arguments before executing)."""
    return [dict(spec) for spec in TOOL_SPECS]


def _gemini_schema(value):
    """Recursively prune anything the Gemini ``Schema`` proto does not accept.

    The registry follows the OpenAI/JSON-Schema dialect, which stamps
    ``additionalProperties`` on every object; the Live ``BidiGenerateContent``
    wire parser rejects unknown fields with a 1007 close, so those are removed
    here (they only exist to make the browser-side validator strict anyway).
    """
    if isinstance(value, list):
        return [_gemini_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: _gemini_schema(item)
        for key, item in value.items()
        if key not in {"additionalProperties"}
    }


def tool_payloads_gemini() -> list[dict]:
    """The registry as Gemini Live ``functionDeclarations``.

    Gemini accepts ``name`` / ``description`` / ``parameters`` on each
    declaration (the same 'type' discriminator is not part of the schema, so
    it is stripped).  Tool names already follow Gemini's ``[a-z0-9_]`` rule.
    """
    return [
        {
            "name": spec["name"],
            "description": spec["description"],
            "parameters": _gemini_schema(spec["parameters"]),
        }
        for spec in TOOL_SPECS
    ]


def get_tool(name: str) -> dict | None:
    for spec in TOOL_SPECS:
        if spec["name"] == name:
            return spec
    return None


# ---------------------------------------------------------------------------
# Server-side parameter validation (defensive; the browser re-validates too).
# ---------------------------------------------------------------------------

_TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
}


def _check_value(value: Any, schema: dict, path: str, errors: list[str]) -> None:
    expected = schema.get("type")
    enum = schema.get("enum")
    if expected and not _TYPE_CHECKS[expected](value):
        errors.append(f"{path}: expected {expected}")
        return
    if enum is not None and value not in enum:
        errors.append(f"{path}: must be one of {list(enum)}")
        return
    if expected in ("number", "integer") and isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: must be >= {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: must be <= {schema['maximum']}")
    if expected == "string" and isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: shorter than minLength")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: longer than maxLength")


def validate_tool_args(name: str, args: Any) -> tuple[bool, str]:
    """Validate tool arguments against the registered JSON schema.

    Returns ``(ok, error_message)``.  Unknown tools, non-object payloads,
    missing required keys, wrong types, bad enums and out-of-range numbers
    are all rejected with a precise message.
    """
    spec = get_tool(name)
    if spec is None:
        return False, f"unknown tool '{name}'"
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return False, "arguments must be a JSON object"
    schema = spec["parameters"]
    errors: list[str] = []
    for key in schema.get("required", []):
        if key not in args:
            errors.append(f"missing required argument '{key}'")
    properties = schema.get("properties", {})
    for key, value in args.items():
        if key not in properties:
            if schema.get("additionalProperties") is False:
                errors.append(f"unexpected argument '{key}'")
            continue
        _check_value(value, properties[key], key, errors)
    if errors:
        return False, "; ".join(errors)
    return True, ""
