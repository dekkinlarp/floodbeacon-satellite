# Responder replay data and assumptions

This prototype replays **real historical daily river observations** through a
**hypothetical access decision engine**. It demonstrates the question “which
planning destinations could lose their modeled routes next?” without training
a forecast model. Future historical observations are shown retrospectively;
they are not forecasts that were available to responders in November 2021.

The selected example is Coldwater River at Merritt, British Columbia, November
11–19, 2021. The German satellite damage demo remains a separate feature. BC is
used here because the existing research already identified a suitable official
level/discharge series, and both measurements are actually available for these
dates. The replay is published under `bc-2021-access-demo` to keep its synthetic
planning layers separate from the existing `bc-2021` analysis case.

## Data actually used

| Input | Source and representation | What it establishes |
| --- | --- | --- |
| Daily river stage | ECCC HYDAT `hydrometric-daily-mean`, station `08LG010`, source `LEVEL`, metres above the station reference datum | Historical gauge-level means; not water depth over a road or bridge deck |
| Daily discharge | Same collection and station, source `DISCHARGE`, m³/s | Historical daily flow means at the gauge; not local flow velocity or a bridge failure probability |
| Quality symbols | Source `LEVEL_SYMBOL_EN` and `DISCHARGE_SYMBOL_EN` | Preserve ECCC's `Estimated` discharge symbols on November 15 and 16; null symbols remain null |
| Gauge position | Source GeoJSON point `[-120.8030014038086, 50.10979843139648]` | Gauge location in WGS84 longitude/latitude |
| Planning graph | Author-authored six geographic anchors near Merritt, eight straight-line corridors and three planning areas | Synthetic example connectivity; not OSM geometry, surveyed roads, a complete network, real responder bases or actual community isolation |
| Concern thresholds | Author-selected gauge stage 1.6, 1.65, 2.2, 2.8 m and discharge 100, 200 m³/s | Illustrative trigger rules; not physical closure/failure thresholds derived from elevations or engineering |

Official [ECCC OGC API documentation](https://eccc-msc.github.io/open-data/msc-geomet/ogc_api_en/)
describes station/date filtering. The collection metadata defines a daily mean
as the average of unit values for the day. We retain its `DATE` as a date string
without inventing midnight UTC acquisition timestamps. No intraday closure time
can be inferred from a daily mean.

Request URL:

```text
https://api.weather.gc.ca/collections/hydrometric-daily-mean/items?f=json&STATION_NUMBER=08LG010&datetime=2021-11-11%2F2021-11-19&limit=1000
```

Fresh retrieval completed `2026-10-04T10:47:20.060973Z`. The API's response
timestamp is recorded separately in the curated JSON. There is no immutable
archive-release version supplied by this endpoint. Item IDs are
`08LG010.2021-11-11` through `08LG010.2021-11-19`.

Original publication/availability timestamps for the historical values were
not supplied and are stored as `null`; forecast issue/valid times are also
`null` because these are observations. This is a retrospective demonstration,
not a no-leakage forecast evaluation. The archive may contain post-event quality
assessment or revisions.

### Selected actual measurements

| Source date | Stage (m, rounded for this table) | Discharge (m³/s, rounded) | Discharge symbol |
| --- | ---: | ---: | --- |
| 2021-11-13 | 1.460 | 12.3 | Not supplied |
| 2021-11-14 | 1.681 | 32.9 | Not supplied |
| 2021-11-15 | 3.182 | 239.0 | Estimated |
| 2021-11-16 | 2.291 | 106.0 | Estimated |
| 2021-11-17 | 1.814 | 51.9 | Not supplied |

The JSON preserves the exact source numeric values, including floating-point
representation; table rounding is only for readability. No interpolation,
resampling, gap filling, hydrological forecast or flood-footprint expansion is
used for this feature.

### Licence and attribution

The API data service's current primary licence is the
[Environment and Climate Change Canada Data Services End-use Licence](https://eccc-msc.github.io/open-data/licence/readme_en/),
whose page header states **version 2.1.1, August 2026** (the final versioning
paragraph still says 2.1). It permits copying, modification, publication and
distribution with attribution, and disclaims endorsement. We record the specific
service licence rather than assuming the separate Government of Canada Open
Government Licence applies to every endpoint.

Attribution: **Data Source: Environment and Climate Change Canada**.

Raw JSON is ignored under `data/raw/bc-2021/`; only the small normalized replay
input is Git-tracked under `src/floodbeacon/static/access-replay/input.json`.
No image bytes or raw source payloads are placed in PostgreSQL.

## Reproduce and verify

No new dependency is needed; the curator uses Python's standard library.

```bash
uv run --locked python scripts/prepare_access_replay.py
```

This downloads only the nine requested daily records, saves the raw response
under the ignored data directory, and writes the normalized static input. It
prints a retrieval receipt and SHA-256 checksum for the generated output.
Retrieval timestamps and server response timestamps can change between runs.

Exact reproduction using the retained response and its actual retrieval receipt:

```bash
uv run --locked python scripts/prepare_access_replay.py \
  --source data/raw/bc-2021/access-replay-hydrometric-20261004T104720Z-95078cc2ac72.json \
  --retrieved-at 2026-10-04T10:47:20.060973Z
```

Recorded SHA-256 checksums:

- Raw source response:
  `95078cc2ac7294e9a52637e769569f675ac2a02d5067935860c2987067575f7f`.
- Curated `input.json`:
  `33da546438324a31ace6a17af51ff58c444651b6ff03ed041cba77b85e9bbde2`.

These checksums describe this retrieval, not a promise that a live service will
always return identical bytes. The source record and preparation parameters are
included in the input JSON.

## What the assumed access rules show

The graph allows alternate routes and includes an independent corridor with no
modeled trigger. Stage thresholds of 1.6/1.65 m first affect planning area A on
November 14. Higher stage/flow thresholds first affect area B on November 15.
Area C retains an untriggered route in this graph. These are scenario results,
not documented historical isolation of actual neighborhoods.

At a November 12 replay position, a two-calendar-day look-ahead can therefore
say “consider visiting planning area A before its modeled access concern on
November 14.” The justification is the assumed corridor thresholds and graph
connectivity. No population or rescue-urgency weights are invented.

Edges become available again when measurements fall below the trigger. This
reversible assumption demonstrates water-related access concerns only; a
destroyed bridge would need a separate persistent damage/closure state.
An edge without a trigger, or a value below a threshold, means **no modeled
concern**, not verified safe travel. Gauge stage cannot establish local road
depth; discharge cannot establish structural destruction.

## Future inputs, currently not ingested

| Planned input | Candidate official source | Integration work remaining |
| --- | --- | --- |
| Live river measurements | [ECCC real-time hydrometric CSV service](https://eccc-msc.github.io/open-data/msc-data/obs_hydrometric/readme_hydrometric-datamart_en/) | Station availability, observation timestamp/timezone, quality and gauge datum must be checked; live observations alone do not supply a future trajectory |
| Future river trajectories | [BC River Forecast Centre](https://www2.gov.bc.ca/gov/content/environment/air-land-water/water/drought-flooding-dikes-dams/river-forecast-centre) hydrological forecasts | Verify Coldwater/Merritt coverage, machine-readable format, terms, forecast issue/availability/valid times and units; do not assume a gauge-specific forecast already exists |
| Local terrain | [NRCan HRDEM/CanElevation](https://open.canada.ca/data/en/dataset/957782bf-847c-4644-a757-e383c0057995) | Verify tile coverage and acquisition date, use DTM rather than a canopy/building surface, reconcile vertical datum with the gauge, and implement river hydraulics or a clearly simplified inundation model |
| Real road network | OpenStreetMap or official road-centerline data | Acquire a dated/licensed network, model bridges and road restrictions, check routes beyond the study boundary; current schematic lines do not provide this |
| Crossing and approach elevations | Official asset surveys, engineering records and local terrain | Obtain road/deck/approach heights and bridge attributes; a terrain pixel at a river crossing is insufficient |
| Historical closures and failures | Agency incident/closure records | Obtain evidence with event and publication times, keep damage separate from inundation, validate the access rules on held-out events |

For a real-time version, a forecast adapter would replace the retrospective
look-ahead with a versioned trajectory carrying station ID, issue and availability
times, valid times, units, datum, source and quality. The same decision engine can
then evaluate threshold crossings and connectivity. Local road/bridge attributes
must replace the assumed triggers before treating outputs as physically grounded
access estimates. This demo establishes neither forecast accuracy nor calibrated
bridge failure probabilities.
