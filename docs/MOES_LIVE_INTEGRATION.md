# MoES Live Data Integration

Updated: 2026-09-28

The MoES workspace adds live source discovery and adapters to the existing
TidalTwin system. It does not label every feed as live measurements. Catalog
health, measurement timestamp, and data type are reported separately.

## Connected sources

| Provider | Machine-readable endpoint | Connected product | Status and limits |
| --- | --- | --- | --- |
| INCOIS | [ERDDAP](https://erddap.incois.gov.in/erddap/) tabledap / griddap / WMS and [THREDDS Ocean State Forecast](https://incois.gov.in/oceanservices/LSF/index.html) WMS / NCSS | Public dataset catalog and metadata; Argo grids; HYCOM temperature, salinity, currents, sea-level forecasts; WaveWatch III waves and wind forecasts | Catalog and THREDDS requests are checked live. Product run age and valid times are separate. Argo analysis currently ends on 2026-07-30 and is **STALE**; the latest wave run is marked stale when its run age exceeds the freshness window. Forecast output is not observation data. |
| NIOT | [Ocean Observation Systems buoy network](https://services.niot.res.in/BuoyNetwork/) JSON station API | Buoy station positions, type, deployment and source-reported date ranges | Station catalog responds live. This endpoint does not return sensor time series; date ranges are not current readings. |
| CMLRE / IndOBIS | [OBIS API v3](https://api.obis.org/) with the [IndOBIS node](https://indobis.in/) | Dated marine species occurrence records | API is available. Records may be historical and are not live tracks or abundance estimates. |
| NCCR | [National Assessment of Shoreline Changes](https://www.nccr.gov.in/sites/default/files/schangenew.pdf) | Shoreline change classes and assessment maps, 1990-2016 | Official PDF report is linked; no machine-readable service was verified. |
| IMD | [Official IMD APIs](https://mausam.imd.gov.in/responsive/apis.php) | Port weather API availability probe | Current server is rejected until its IP/domain is whitelisted (**ACCESS_RESTRICTED**); no values are ingested. |
| NCPOR | [National Polar Data Center](https://data.ncpor.res.in/) | Public polar data portal and current weather dashboard link | Dashboard conditions are HTML only; no stable machine-readable weather API was verified. Individual archive downloads may require a request. |
| NCMRWF | [Public data portal](https://www.ncmrwf.gov.in/data/) | Forecast data access portal | No stable machine-readable service was verified from this environment. |
| IITM | [THREDDS archive](https://ardc.tropmet.res.in/thredds/) | Public climate/ocean-atmosphere archives | Catalog exists, but the current validated TLS request fails; source status is **TEMPORARILY_UNAVAILABLE**. |
| NCESS | [National Geoscience Data Centre](https://ngdc.ncess.gov.in/) | Official data portal | Portal reports testing/trial; no stable API is connected. |

NCCR has no verified public machine-readable endpoint. NCMRWF's official
forecast data portal is linked, but no stable service was verified. IITM's
official [THREDDS archive](https://ardc.tropmet.res.in/thredds/) is registered;
its catalog probe currently fails validated TLS access, so it is marked
temporarily unavailable. NCESS's
official geoscience portal identifies itself as in testing/trial, so its status
is **PORTAL_IN_TRIAL**. No data are fabricated or substituted for these
sources.

## API routes

- `GET /api/v1/moes/registry` — source status, official portal, endpoint, check
  time, and errors.
- `GET /api/v1/moes/datasets?q=...` — current public INCOIS ERDDAP catalog.
- `GET /api/v1/moes/datasets/{dataset_id}` — official variables, units,
coverage, time extent, attribution, and license metadata when published. Each
catalog row also shows the age in days of ERDDAP's latest observation timestamp;
that timestamp is not treated as a catalog refresh time or a live-data claim.
- `GET /api/v1/moes/buoys` — regional NIOT buoy station metadata and source-
  reported periods when data are available; no sensor time series.
- `GET /api/v1/moes/argo-grid?variable=TEMP|SAL&depth_m=5` — bounded regional
  grid subset. Depth is snapped to the nearest source level. Values outside
  basic physical ranges and ERDDAP missing-value sentinels are omitted.
- `GET /api/v1/moes/biodiversity` — bounded IndOBIS occurrence records,
  retaining event dates and record links.

Remote catalog/status checks are cached for five minutes. Grid values have the
same short cache. TLS validation remains enabled and uses the operating
system's trusted certificate store.

## User interface

The Dashboard has separate cards for the 20 requested ocean-intelligence
features. `/moes/:feature` opens a dedicated feature view, links to the
existing analysis workspace, and searches the matching source catalog.
Temperature and salinity display the gridded INCOIS analysis; biodiversity
displays IndOBIS occurrence records. Catalog dataset rows expand to show
official variable units and license metadata.

Wave, wind, current, temperature, salinity, sea-level, and forecast views sample
the public INCOIS operational forecasts. Wave and current views also show the
NIOT buoy directory. Its positions and date ranges are metadata, not readings.
Coastal, event, disagreement, confidence, fusion, health, and provenance cards
link to existing project workspaces and show the relevant source availability.
Existing Open-Meteo products remain model forecasts and are not relabelled as
MoES measurements.

## Normalized records and feature availability

`GET /api/v1/moes/registry` now returns the same metadata shape for all nine
institutions, including category, protocol, variable, units, temporal
resolution, coverage, spatial resolution, attribution, license, check time,
status, cache state, and any error. Sources without a verified machine-readable
service report `PUBLIC_ENDPOINT_NOT_AVAILABLE`.

`GET /api/v1/moes/features/{feature_id}` maps each feature card to curated
catalog products and states whether the connected source exposes a live
measurement feed. A successful catalog request is distinct from current
measurements.

`GET /api/v1/moes/normalized/argo-grid` and
`GET /api/v1/moes/normalized/biodiversity` return `UnifiedOceanRecord/v1`
records with provider, dataset, variable, value, units, observed time,
retrieval time, coordinates, depth, quality flags, source URL, attribution, and
license fields. Argo analysis cells retain `MODEL_DERIVED` status; IndOBIS
items remain dated occurrence records.

`GET /api/v1/moes/forecast/hydrodynamics?product=currents|temperature|salinity|sea-level`
samples the latest public INCOIS RSMC HYCOM operational run at a requested
point and returns available 6-hourly forecast valid times.

`GET /api/v1/moes/forecast/waves?variable=HS&latitude=10&longitude=80` samples
an INCOIS RSMC WaveWatch III field at its latest advertised valid time. Pass
`valid_at` to select another advertised forecast step.
