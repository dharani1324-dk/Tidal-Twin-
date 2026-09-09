"""
OceanVerse AI - Story Mode Module
=================================
Interactive guided narratives that explain ocean science using
REAL data from our monitored regions. Think of it as a mini
interactive documentary built into the platform.

Each story has narrative chapters PLUS a data hook that computes
live statistics from our database for rich visualization.
"""

from sqlalchemy.orm import Session

from app.models.location import OceanLocation
from app.models.observation import OceanObservation

STORY_META = [
    {
        "id": "heatwave",
        "title": "Marine Heatwaves",
        "tagline": "When the sea runs a fever",
        "category": "Climate",
        "accent": "#fb7185",
        "icon": "thermometer",
        "narrative": [
            {
                "heading": "The Ocean Has a Fever",
                "text": (
                    "Marine heatwaves are periods when sea surface temperature stays "
                    "unusually high for days to weeks. They're the ocean's equivalent of "
                    "a heatwave on land — and they're becoming more common worldwide.\n\n"
                    "Our AI monitors every region for these spikes. When a reading climbs "
                    "well above the recent normal, an alert fires with a confidence score."
                ),
            },
            {
                "heading": "Why It Matters for India",
                "text": (
                    "India's coastal waters nurture fisheries that support millions of "
                    "families. A marine heatwave can stress coral reefs (like the Gulf of "
                    "Mannar), force fish to move, and increase storm intensity.\n\n"
                    "In this chapter, watch how our anomaly detector reacts to a simulated "
                    "heatwave event — the same signal chain a launch-monitoring team would use."
                ),
            },
            {
                "heading": "Read the Data",
                "text": (
                    "Compare each region's current temperature against its recent average. "
                    "The bigger the gap, the hotter the water relative to normal — and the "
                    "higher the alert confidence."
                ),
            },
        ],
    },
    {
        "id": "monsoon",
        "title": "Southwest Monsoon Pulse",
        "tagline": "The rhythm that shapes India's coast",
        "category": "Weather",
        "accent": "#38bdf8",
        "icon": "cloud",
        "narrative": [
            {
                "heading": "The Monsoon Engine",
                "text": (
                    "Every summer, the Southwest Monsoon drives warm, moist air across the "
                    "Arabian Sea toward India's west coast, then sweeps northeast. The result: "
                    "rains that feed billions and powerful ocean swells that reach our shores.\n\n"
                    "Wave height is one of the clearest fingerprints of monsoon activity — "
                    "watch the wave charts climb as the monsoon strengthens."
                ),
            },
            {
                "heading": "Waves as Weather Signals",
                "text": (
                    "Monsoon winds build taller, longer-period swell. When our stations report "
                    "wave heights climbing rapidly, it may signal an approaching weather system.\n\n"
                    "This is exactly the kind of lead time coastal regulators use to warn fishing "
                    "communities before conditions turn dangerous."
                ),
            },
        ],
    },
    {
        "id": "fishing",
        "title": "Safe Fishing Grounds",
        "tagline": "Where should fleets go today?",
        "category": "Livelihoods",
        "accent": "#34d399",
        "icon": "ship",
        "narrative": [
            {
                "heading": "Data for Livelihoods",
                "text": (
                    "Fishing is the livelihood of millions in India. Planners and vessel "
                    "skippers need to know: which grounds are calm, which are risky, and "
                    "what's changing hour by hour."
                ),
            },
            {
                "heading": "Our Safety Layer",
                "text": (
                    "The AI Safety Check (try it in the Ocean Assistant) converts wave "
                    "height into practical advice — calm swells mean green light, rough "
                    "seas mean caution. This is decision intelligence that reaches real boats."
                ),
            },
        ],
    },
    {
        "id": "climate",
        "title": "Reading the Climate",
        "tagline": "Trends hidden in hourly data",
        "category": "Science",
        "accent": "#a5b4fc",
        "icon": "activity",
        "narrative": [
            {
                "heading": "From Hourly to Long-Term",
                "text": (
                    "A single reading is weather. A long series of readings reveals climate. "
                    "Our trend analysis looks at the direction of change — is this region "
                    "warming, cooling, or steady?"
                ),
            },
            {
                "heading": "Signals vs Noise",
                "text": (
                    "Day-to-day wobbles are noise. Our forecast engine fits the underlying "
                    "trend and flags when short-term spikes exceed the baseline — separating "
                    "real signals (like a heatwave) from ordinary variation."
                ),
            },
        ],
    },
]


def compute_story_hook(db: Session, story_id: str) -> dict:
    """Compute live data summaries for a story using real observations."""
    locations = db.query(OceanLocation).all()
    obs = (
        db.query(OceanObservation)
        .order_by(OceanObservation.timestamp.desc())
        .limit(200)
        .all()
    )
    if not obs:
        return {"available": False}

    temps = [(o.sea_surface_temperature or 0.0) for o in obs]
    waves = [(o.wave_height or 0.0) for o in obs]

    # Recent normal = the observations we're comparing against
    base = {
        "regions": len(locations),
        "samples": len(obs),
        "avg_temperature": round(sum(temps) / len(temps), 2),
        "avg_wave_height": round(sum(waves) / len(waves), 2),
        "max_temperature": round(max(temps), 2),
        "max_wave_height": round(max(waves), 2),
    }

    if story_id == "heatwave":
        # Find the warmest region and its delta vs the global avg
        warmest = None
        for loc in locations:
            lo = (
                db.query(OceanObservation)
                .filter(OceanObservation.location_id == loc.id)
                .order_by(OceanObservation.timestamp.desc())
                .first()
            )
            if lo and lo.sea_surface_temperature:
                if warmest is None or lo.sea_surface_temperature > warmest[1]:
                    warmest = (loc.name, lo.sea_surface_temperature)
        base["warmest_region"] = warmest[0] if warmest else None
        base["warmest_temp"] = warmest[1] if warmest else None
        base["hot_today"] = bool(warmest and warmest[1] > base["avg_temperature"] + 0.8)

    elif story_id == "monsoon":
        calmer = None
        rough = None
        for loc in locations:
            lo = (
                db.query(OceanObservation)
                .filter(OceanObservation.location_id == loc.id)
                .order_by(OceanObservation.timestamp.desc())
                .first()
            )
            if lo and lo.wave_height is not None:
                if rough is None or lo.wave_height > rough[1]:
                    rough = (loc.name, lo.wave_height)
                if calmer is None or lo.wave_height < calmer[1]:
                    calmer = (loc.name, lo.wave_height)
        base["roughest"] = rough[0] if rough else None
        base["rough_wave"] = round(rough[1], 2) if rough else None
        base["calmest"] = calmer[0] if calmer else None
        base["calm_wave"] = round(calmer[1], 2) if calmer else None

    elif story_id == "fishing":
        safe = []
        for loc in locations:
            lo = (
                db.query(OceanObservation)
                .filter(OceanObservation.location_id == loc.id)
                .order_by(OceanObservation.timestamp.desc())
                .first()
            )
            if lo and lo.wave_height is not None and lo.wave_height < 1.0:
                safe.append(loc.name)
        base["safe_grounds"] = safe
        base["safe_count"] = len(safe)

    elif story_id == "climate":
        # Simple warming indicator: compare first vs last half of readings
        if len(temps) >= 12:
            half = len(temps) // 2
            first = sum(temps[:half]) / half
            second = sum(temps[half:]) / (len(temps) - half)
            base["trend_delta"] = round(second - first, 2)
            base["warming"] = second > first

    base["available"] = True
    return base


def all_stories(db: Session) -> list[dict]:
    """Return all stories with their live data hooks attached."""
    out = []
    for s in STORY_META:
        hook = compute_story_hook(db, s["id"])
        out.append({**s, "hook": hook})
    return out