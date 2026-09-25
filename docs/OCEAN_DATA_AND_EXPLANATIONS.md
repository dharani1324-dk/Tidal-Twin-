# Ocean data, evidence, and explanations

## What the application currently stores

The refresh action calls Open-Meteo Marine at each configured location and stores hourly sea-surface-temperature and wave forecast values. These are marked data_type=model_forecast, with source Open-Meteo Marine forecast. They are forecast model output, not in-situ measurements. The application no longer fills those records with pseudo-random oxygen, chlorophyll, pH, density, or nutrient values.

The database also supports separately ingested Argo, glider, CTD, satellite-grid, and ocean-model products. Their presence in the code does not mean those datasets are loaded in a given deployment. Check the source registry and each record provenance at runtime.

## Evidence classes

| Class | Meaning in TidalTwin | How explanations use it |
|---|---|---|
| REAL | Source identified as an in-situ or direct measurement stream (for example Argo, glider, buoy, CTD) | May be considered for measurement comparisons |
| HISTORICAL | Historical gridded or climatology record (for example ERSST) | May be compared as historical evidence, with its grid/time limits |
| SATELLITE_DERIVED | Remote-sensing retrieval or ocean-colour product | May be considered as a derived measurement, not an in-situ sample |
| MODEL_DERIVED | Numerical model, forecast, or model grid | Kept available for forecasts and context; excluded from measured-observation baselines |
| SIMULATED / SYNTHETIC | Demonstration or generated values | Must remain visibly labelled and excluded from claims about real observations |
| UNKNOWN | Provenance could not be inferred from stored source/type | Not silently promoted to a measurement |

These labels identify the source category. They are not source-specific quality-control results. The observation response provides available fields, broad plausibility flags, freshness, coordinates when available, and explicit NOT_PROVIDED_BY_SOURCE QC status where QC flags are not stored. Broad physical-range checks are screening aids, not sensor validation.

## Source register and scientific limits

| Product or pathway | Intended variables and scale | Evidence type | Current code boundary |
|---|---|---|---|
| [Open-Meteo Marine API](https://open-meteo.com/en/docs/marine-weather-api) | Hourly marine forecast at requested coordinates; wave products are gridded model output | MODEL_DERIVED | Connected by the refresh API. Stored rows are forecasts; they do not establish local measured conditions. |
| [NOAA ERSST v5](https://www.ncei.noaa.gov/products/extended-reconstructed-sst) | Monthly 2° reconstructed SST analysis | HISTORICAL | NetCDF ingestion and grid-query code exist. A gridded reconstruction is not a station reading or satellite SST. |
| [NOAA CoastWatch VIIRS ocean colour](https://coastwatch.noaa.gov/cwn/products/noaa-msl12-ocean-color-science-quality-viirs-snpp.html) | Chlorophyll-a retrievals; product resolution/compositing depend on level and product | SATELLITE_DERIVED | Grid ingestion/query path exists; no assumption is made that the live database contains a product. |
| [Argo GDAC](https://argo.ucsd.edu/data/data-from-gdacs/) profiles and [QC guidance](https://argo.ucsd.edu/data/how-to-use-argo-files/) | Profiled temperature, salinity, pressure with per-parameter QC | REAL when a profile is ingested | NetCDF ingestion exists. The legacy importer must not treat unqualified raw values as QC-verified; source QC/adjusted-value handling requires explicit verification for each file. |
| HYCOM GLBu0.08 model output | Regular 0.08° grid, vertical levels and model variables | MODEL_DERIVED | Fetch/ingest and query code exist; output is a model field, not an observation. |
| Glider and CTD pathways | Deployment or cast samples at recorded locations/depths | REAL when source measurements are ingested | Parsers/import paths exist; availability and QC depend on the source file and deployment. |

## How explanation mode now works

1. It selects only records classified as REAL, HISTORICAL, or SATELLITE_DERIVED for measured comparisons. Forecast, model, simulated, and synthetic rows are excluded.
2. It compares the latest eligible field with the mean of earlier eligible field values. That mean is called a historical baseline; it is not an independent numerical-model forecast.
3. With no eligible measurement, the API returns an unavailable explanation and identifies when Open-Meteo forecast rows exist. With a measurement but insufficient history, it names the measurement and says the baseline cannot yet be computed.
4. Explanations state the location, variable, value, baseline, difference, source, and evidence category when available. Potential physical drivers are explicitly hypotheses; the comparison alone does not establish a cause.
5. Confidence values are heuristic support scores. They are not calibrated probabilities and do not express confidence in a causal explanation.
6. A depth profile only uses a qualifying measured surface value as its measured point. Deeper values are labeled as model-derived. If no measured input exists, the service returns no profile instead of substituting default ocean conditions.

## What this does not establish

The code audit does not establish that a live database is populated with any optional source, that source-specific QC flags have been applied, or that the heuristics predict ocean events accurately. Those claims require inspecting the running database and comparing forecasts and derived products with independently quality-controlled reference measurements.
