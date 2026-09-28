# Data and scientific limitations

OceanVerse is a monitoring and exploration application. An available API or
visualization does not by itself establish scientific validation. Results
depend on source coverage, observation quality, temporal alignment, and the
limits of each analysis method. Model forecasts, historical records, direct
measurements, and simulated demonstration rows must be interpreted according
to their source labels.

## Ground truth and simulation

- Event labels come from the application's event detection logic; there is no
  independent event-label dataset in this project for measuring false alarms
  or missed events.
- Demonstration records are labelled as simulated and are not real ocean
  observations. Demo reset only removes simulation-labelled rows.
- A comparison between a forecast and an observation is a model-observation
  comparison, not independent validation of either source.
- Missing provider data is reported as unavailable or as a gap; it is not
  replaced with fabricated readings.

## Microplastics module

Full detail is in [`MICROPLASTICS.md`](MICROPLASTICS.md). Key limits:

- The NOAA NCEI collection is an archive, not a live feed. Indian Ocean records
  span 2013-05-27 to 2021-12-08; they do not describe present-day conditions.
- Concentrations are not combined across unit families (`pieces/m3`,
  `pieces/kg dw`, and `pieces/10 min` describe different samples and effort).
- Published severity classes are preserved. Interpolation uses inverse
  distance weighting, not kriging; cells without nearby samples remain gaps.
- Drift output is a surface corridor, not a forecast. It is unavailable without
  real current forcing and does not model sinking, beaching, resuspension, or
  vertical shear.
- Only two of eight monitored regions have published microplastic samples.
- The NASA satellite-derived plastic-signal connector is unimplemented and
  returns unavailable rather than fabricating a layer.
