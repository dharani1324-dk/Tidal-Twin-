# OceanVerse workflow

The application supports a practical ocean monitoring workflow:

| Step | User task | Application area |
|---|---|---|
| Monitor | Review current system and ocean conditions | Dashboard |
| Detect | Explore detected anomalies and events | Anomalies |
| Investigate | Review event context and evidence | Forensics |
| Inspect data | Check sources, coverage, and quality | Data Layers |
| Explore | Compare model fields or run a coastal scenario | Digital Twin / Scenarios |
| Ask | Query available conditions and project data | Ocean Copilot |

## Data provenance

Values retain their source and data-type labels. Model-derived forecasts,
historical records, direct measurements, satellite-derived values, and simulated
demo observations are distinct categories. The interface reports gaps and
unavailable sources explicitly. It does not treat a model forecast as a direct
measurement or a demonstration record as an observation.

See [`SCIENTIFIC_LIMITATIONS.md`](SCIENTIFIC_LIMITATIONS.md) for method and
coverage limits and [`API.md`](API.md) for route groups.
