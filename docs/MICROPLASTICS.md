# Microplastics Intelligence

Microplastic detection, regional mapping, hotspot ranking and 24–72 h drift
projection, built entirely from open-source data. No hardware, no proprietary
feed, no invented values.

Wired into the platform as a **new anomaly category** (`Microplastic Hotspot`)
alongside the existing thermal and wave anomalies, so hotspot output flows into
the same decision-intelligence layer rather than sitting beside it.

---

## 1. The two rules this module will not break

Everything unusual about the implementation follows from these.

### Rule 1 — concentrations are never combined across unit families

The NOAA NCEI collection reports microplastics in **three incompatible units**
depending on how the sample was taken:

| Source field `Medium` | Unit in the dataset | Records in the India window |
|---|---|---|
| `Ocean water` | `pieces/m3` | 192 |
| `Ocean sediment` | `pieces kg-1 d.w.` | 117 |
| `Beach` | `pieces/m3` | 80 |
| `Beach-Nurdle Patrol` | `pieces/10 mins` | 2 |
| | **total** | **391** |

`pieces/m3` and `pieces/kg` are **not convertible into one another** — the
relationship depends on sampling depth, grain size, organic content and trawl
mesh. So the value `54` is `Medium` in a sediment grab and roughly five times
the top of the water-column ladder.

Worse, the severity ladder itself is **per-medium**. Reconstructing it from the
live records reconciles exactly to the published counts:

| Ladder | Very Low | Low | Medium | High | Very High | assigned |
|---|---|---|---|---|---|---|
| water (`pieces/m3`) | 0–0.0005 | 0.0005–0.005 | 0.005–1 | ≥ 1 | — | 192 ✓ |
| sediment (`pieces/kg dw`) | 0–2 | 2–20 | 20–150 | 150–200 | ≥ 200 | 117 ✓ |
| beach | 0–100 | 100–500 | ≥ 500 | — | — | 80 ✓ |

Each band's membership count matched its medium's record count one-for-one.
That is what proves the ladder belongs to the medium, not to the number.

**Consequence for the API and UI:** there is no single "microplastics score",
no region-level microplastic risk number, and no blended colour ramp. Every
aggregate is grouped by `(region_id, medium)`, and every value carries its own
unit label. Any such blended number would be meaningless, so none is produced.

### Rule 2 — absence is never rendered as a number

* Grid cells with no sample within the search radius produce **no value**.
  They are counted and reported as gaps. A cell is never filled with `0`,
  because `0` means "sampled and clean" while a gap means "nobody looked".
* Unreachable connectors return a **reason**, never an empty grid.
* A hotspot's recency is measured against the collection, not against today
  (see §4).
* Drift is refused, with a reason, when no real forcing exists (§6).

---

## 2. Module layout

```
backend/app/models/microplastics.py          MicroplasticSample table
backend/app/modules/ai/microplastics/
    units.py       unit families + the published severity ladder
    sources.py     NOAA NCEI connector, optional NASA connector
    normalize.py   raw source record -> unified schema
    regions.py     mapping to monitored regions + IDW interpolation
    hotspots.py    ranking, priority score, plain-language actions
    drift.py       24-72 h Lagrangian corridor + forcing quality gates
    engine.py      orchestration, persistence, cache, coverage, timeline
backend/app/api/microplastics.py             the router
backend/scripts/ingest_microplastics.py      scheduled refresh
backend/tests/test_microplastics.py          77 tests, no DB and no network
frontend/src/pages/Microplastics.tsx          the workspace (interrogate one region)
frontend/src/pages/MicroplasticsDashboard.tsx the dashboard (which region to look at)
```

### Two frontend surfaces, deliberately

| Route | Nav label | Job |
|---|---|---|
| `/microplastics/dashboard` | MP Dashboard | Scannable situation summary: KPIs, hotspot leaderboard, coverage gaps, alert status, survey-year histogram, and the raising/ingesting actions |
| `/microplastics` | Microplastics | The full workspace: surfaces, per-hotspot evidence, drift projection, sources |

The sidebar entry for the workspace uses `end: true` so the two items do not
both highlight while the nested dashboard route is open.

On the dashboard, sample **counts** are summed (an inventory is safe to add up)
but no mean, peak or severity is ever aggregated across media. That is the one
place where breaking the unit-family rule would be easiest and most tempting,
so it is stated on the screen itself rather than only here.

Pipeline:

```
fetch → normalise → map to region → persist → score → project drift
```

`ingest()` is idempotent, keyed on `(source, source_record_id)`, so NOAA
republishing a correction under the same `OBJECTID` updates rather than
duplicates.

---

## 3. Data sources

| Source | Access | Licence | Status |
|---|---|---|---|
| **NOAA NCEI** global Marine Microplastics collection | Public ArcGIS Feature Service, **no key** | U.S. Government work — public domain | **Working.** 391 records ingested |
| **Published literature** (curated) | Hand-entered rows in `literature_samples.csv` | By-study; each row keeps its own DOI and must be cited | **Working.** 9 real rows from 7 studies (Mumbai, Chennai, Goa, Nattika/Kerala, Odisha, Lakshadweep) with verified DOIs; scored after ingest |
| **NASA Earthdata** satellite plastic signal | Requires an Earthdata token | NASA Earthdata, attribution | **Not implemented.** Reports `UNAVAILABLE` without a token, and says so with a token too |

The NOAA endpoint is
`services2.arcgis.com/C8EMgrsFcRFL6LrL/arcgis/rest/services/Marine_Microplastics_WGS84/FeatureServer/0`
and is overridable via `MICROPLASTICS_NOAA_URL`.

### The literature connector (why it exists)

NOAA NCEI publishes **no** microplastic samples near six of the eight monitored
coasts (Mumbai, Chennai, Goa, Kochi, Odisha, Lakshadweep) and the 220 samples it
*does* contain near them are 600+ km from any coast in the Bay of Bengal,
Myanmar and Sri Lanka — nothing can be honestly snapped there. The only way to
cover those coasts is genuine published measurements.

Operators add rows to
`backend/app/modules/ai/microplastics/literature_samples.csv` (columns and rules
are documented in that file's header). Each row is one real measurement with a
`doi` and `reference`, normalised through the exact same pipeline as NOAA rows
and stored `origin_status = REAL`. An empty file is an honest empty state —
those coasts stay listed as gaps until a real value is entered. Nothing is ever
estimated in a gap's place.

The path is overridable via `MICROPLASTICS_LITERATURE_CSV`.

The NASA connector is deliberately credential-gated and currently returns an
honest `ERROR` explaining that retrieval is unimplemented when a token *is*
present. Fabricating a satellite layer to fill the gap would defeat the point
of the module.

### The window we ingest

`INDIA_BBOX = {lon 60–100, lat 0–25}` — slightly wider than the currents
router's EEZ window so a sample just outside still maps to its nearest coast.

---

## 4. The vintage problem

**The NOAA collection is an archive, not a live feed.** Inside our window its
records span **2013-05-27 → 2021-12-08** (8.53 years).

Ranking regions by how "recent" a sample is relative to *today* would mark every
region equally stale and produce a meaningless uniform penalty. So recency is
measured against **the newest sample in the collection itself**, and the basis
is stated in the payload. The API returns `is_live_feed: false` and the UI
renders a prominent "Archival record — not a live feed" banner.

A hotspot therefore means *"this is the most recent evidence we have"*, never
*"this was measured today"*.

---

## 5. Hotspot priority score

Fully transparent, no fitted weights:

```
priority = 100 × ( 0.55·severity + 0.10·evidence + 0.15·recency + 0.20·trust )

severity = published class ordinal / 4        (0..1)
evidence = min(1, n_samples / 10)             (0..1)
recency  = 0.5 ** (age_years / 3)             half-life 3 years
trust    = mean sample confidence / 100       (0..1)
```

The weights are set so that **one class band outranks up to ten times the
sample count**: a region with one `High` sample beats a region with ten `Medium`
samples. The class already encodes concentration, so ten samples of a weaker
class are ten repetitions of a lesser signal, not a stronger one.

Evidence deliberately carries the *smallest* weight because a sample count is
not a magnitude. What a thin sample base undermines is **confidence**, so it is
reported there instead — every hotspot carries `basis` caveats such as
*"Single published sample — this is a point observation, not a spatial
pattern."*

Severity comes from the **worst** sample in the group while `latest_*` fields
report the newest one, so a group can legitimately read `published_class: "Very
High"` / `latest_published_class: "Medium"` without contradiction. This was a
real bug found in review: the earlier code reported the latest class beside the
worst-driven severity and looked self-contradictory.

### Alert tiers (our policy layer, on top of the source's science)

| Ordinal | Severity | Action |
|---|---|---|
| 4 `Very High` | critical | `CLEANUP_PRIORITY` |
| 3 `High` | high | `CLEANUP_PRIORITY` |
| 2 `Medium` | medium | `FURTHER_SAMPLING` |
| 1 `Low` | low | `MONITOR` |
| 0 `Very Low` | info | `NONE` |

`POST /alerts/refresh` writes these into the platform's existing `ocean_alerts`
table with `source="microplastics"`, idempotently per region+medium, so they
appear in Monitoring & Alerts and the notification bell without accumulating
noise.

---

## 6. Drift projection, and when it refuses

`project_drift` advects a plume with a single-layer surface Lagrangian method
plus a wind-leeway term and a √t diffusive spread.

Forcing is resolved in trust order:
1. `ocean_observations.current_speed` / `current_direction` where provenance is
   `REAL` or `HISTORICAL`;
2. `derived_currents` — AIS-derived surface vectors.

**No forcing → no projection.** The response is `status="NO_FORCING"` with the
list of sources checked and the reason. (`coastal/spill.py` defaults to 0.15 m/s
at 45° when it finds nothing; this module deliberately does not, because a
corridor drawn from an invented current is worse than no corridor.)

If a vector is found it is put through **credibility gates** before being
trusted, and failures are attached to the output rather than suppressed:

| Gate | Threshold | Why |
|---|---|---|
| vessels in cell | ≥ 2 | a single vessel is not a current |
| position reports | ≥ 5 | too few samples for a robust vector |
| surface speed | ≤ 1.5 m/s | faster is far more likely unremoved vessel motion |
| distance from origin | ≤ 100 km | uniformity is assumed over that gap |
| uncertainty | > 0 | a zero-width estimate cannot be cross-checked |

On the current demo dataset the only nearby derived vector is **2.05 m/s from 1
vessel, 1 report, 140 km away** — so the corridor is drawn, but confidence drops
to `VERY_LOW` and all five failures are listed in the UI. This is working as
intended, and it also surfaces a genuine data-quality finding in
`derived_currents` worth investigating separately.

---

## 7. Endpoints

All under `/api/v1/microplastics`.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/overview` | hotspots + surfaces + coverage, in one call. Cached. |
| `GET` | `/coverage` | how much real evidence exists; names regions with no data |
| `GET` | `/samples` | stored samples, filterable by `medium`, `unit_family`, `min_ordinal` |
| `GET` | `/hotspots` | ranked hotspots + recommendations |
| `GET` | `/surface` | IDW surface for one medium, with explicit gap counts |
| `GET` | `/timeline` | yearly buckets per region and medium, for scrubbing |
| `GET` | `/sources` | provenance, licences, endpoints |
| `GET` | `/method` | ladders, weights, rules and limitations, exposed openly |
| `POST` | `/ingest` | pull NOAA + literature, normalise, map and store |
| `POST` | `/drift` | 24–72 h corridor; may return `NO_FORCING` |
| `POST` | `/alerts/refresh` | raise hotspots into the platform alert store |

---

## 8. Configuration

| Setting | Default | Meaning |
|---|---|---|
| `MICROPLASTICS_ENABLED` | `true` | master switch |
| `MICROPLASTICS_NOAA_URL` | the NOAA FeatureServer | overridable for a mirror |
| `MICROPLASTICS_LITERATURE_CSV` | module's `literature_samples.csv` | overridable path to the curated literature file |
| `NASA_EARTHDATA_TOKEN` | `""` | empty → NASA connector reports `UNAVAILABLE` |
| `MICROPLASTICS_CACHE_TTL_SECONDS` | `300` | in-process overview cache |

## 9. Running it

```bash
cd backend
.venv/Scripts/python -m scripts.init_db              # creates microplastic_samples
.venv/Scripts/python -m scripts.ingest_microplastics # pulls ~391 NOAA records + literature rows
.venv/Scripts/python -m unittest tests.test_microplastics
```

To cover the six coasts NOAA skips, add real measurements to
`app/modules/ai/microplastics/literature_samples.csv` (one row per sample, with
`doi` and `reference`) and re-run the ingest.

Schedule the refresh (the collection is updated infrequently; daily is
generous, the point is that new publications need no manual step):

```
0 4 * * *  cd /srv/tidaltwin/backend && .venv/bin/python -m scripts.ingest_microplastics
```

---

## 10. Current coverage, stated honestly

As ingested on this build:

- **391** real published samples (NOAA NCEI) + **9** curated literature rows
  (7 studies), all `origin_status = REAL`
- NOAA mapping on this build covers **2 of 8** monitored regions (Laccadive Sea
  / Gulf of Mannar, and the Andaman Sea)
- the **9 literature rows** target the six coasts NOAA has no samples near
  (Mumbai, Chennai, Goa, Nattika/Kerala, Odisha and Lakshadweep), so the next
  ingest brings regional coverage to **8 of 8**; this build's ingest was not
  re-run, so those rows are present in the file but not yet mapped
- **220 samples unassigned** — further than the 600 km mapping radius from every
  monitored region, stored unassigned rather than snapped to the nearest coast
- **4** region/medium groups, of which **3** reach the hotspot threshold
- surface coverage: 543 of 1824 water-column grid cells interpolated, **1281
  reported as gaps**

Any region with no published microplastic sample is listed by name in the API
and UI as a data gap. It is not given an estimated value.

### Limitations

- IDW is a distance-weighted interpolation, **not** a kriged field with a
  fitted variogram. We have nowhere near enough samples to fit one.
- Trend buckets are **yearly** because the source publishes discrete surveys,
  not a continuous series. Monthly buckets would imply precision that is not
  there.
- Per-region sample counts are small, so per-region statistics carry wide
  uncertainty, reported alongside them.
- Microplastics are not a passive tracer: buoyant particles wind-slip and dense
  ones sink. Neither is modelled.
- The NOAA collection ends in 2021. Nothing here describes present-day
  conditions.

### Not yet built

- **The Cesium layer on the Digital Twin globe.** The data layer it needs is
  exposed by `/surface` and `/overview` with `latitude`/`longitude`/`value`/
  `confidence`/`is_estimate` per node and the owning unit per surface, but the
  globe plugin itself is not wired. The workspace page renders an equivalent 2D
  surface meanwhile.
- **The NASA satellite connector**, which is credential-gated and unimplemented.
- A **kriging** option, once there is enough data to justify fitting a variogram.
