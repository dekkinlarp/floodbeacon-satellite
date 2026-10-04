# Responder access replay

This prototype demonstrates the second FloodBeacon feature: identify places
whose access may deteriorate so responders can consider visiting or
pre-positioning assistance earlier. It uses **real historical river observations**
and **illustrative access rules and connectivity**. It does not train a prediction
model or reconstruct actual historical road closures.

The dashboard's separate **Response** tab replays November 11–19, 2021 at
Merritt, British Columbia. Its two-day outlook deliberately looks forward into
the historical record. These later observations stand in for the forecasts a
future adapter would supply. The screen calls this historical hindsight; it
must not be described as a forecast issued during the 2021 event.

## Data actually used

| Input | Source and meaning | Treatment |
| --- | --- | --- |
| Daily mean river stage | ECCC HYDAT, Coldwater River at Merritt, station `08LG010`, November 11–19, 2021; metres relative to the station datum | Source `LEVEL` is retained without rounding or interpolation. This is not local road depth or elevation above sea level. |
| Daily mean discharge | Same station and dates; cubic metres per second | Source `DISCHARGE` is retained. November 15 and 16 carry the source's `Estimated` flag. Flow rate is not velocity at a bridge. |
| Observation dates and quality | ECCC source `DATE`, `LEVEL_SYMBOL_EN`, `DISCHARGE_SYMBOL_EN` | Daily date labels and unknown flags remain intact. Original availability times are unknown (`null`). No invented UTC observation instant. |
| Planning network | Author-created schematic at geographic anchors around Merritt | Six nodes, eight bidirectional corridors, three illustrative destinations and one demo staging point. These are not surveyed roads, real responder facilities or a complete historical network. |
| Access thresholds | Explicit demo assumptions attached to corridors | Gauge-stage thresholds of 1.6, 1.65, 2.2 and 2.8 m, and discharge thresholds of 100 and 200 m³/s. These are not measured closure thresholds or structural-failure limits. |

Exact source URL, item IDs, units, coordinate system, retrieval time, source
checksum, processing and attribution are packaged in
[`input.json`](../src/floodbeacon/static/access-replay/input.json).
The API dataset has no immutable release version, so the retrieval and checksum
identify the snapshot. The raw response remains ignored under `data/raw/`.
See [retrieval notes](access-replay-data-notes.md) for the actual source check.

Primary sources:

- [ECCC daily-mean collection](https://api.weather.gc.ca/collections/hydrometric-daily-mean?f=html)
- [Station historical availability](https://wateroffice.ec.gc.ca/report/data_availability_e.html?parameter_type=Flow+and+Level&station=08LG010&type=historical)
- [ECCC API documentation](https://eccc-msc.github.io/open-data/msc-geomet/ogc_api_en/)
- [ECCC Data Services End-use Licence](https://eccc-msc.github.io/open-data/licence/readme_en/)

Attribution: **Data Source: Environment and Climate Change Canada**. The service
licence checked during retrieval permits copying, modifying and publishing with
attribution; its page header identifies version 2.1.1, August 2026. Derived demo
recommendations are FloodBeacon scenario outputs, not ECCC recommendations.

## Decision engine

For each sampled day, compare each corridor's configured metric against its
threshold. An exceeded threshold marks it unavailable **in the scenario**.
Missing required values produce unknown status. Corridors without a threshold
have no modeled trigger; this does not certify their actual passability.

Check graph reachability from the staging point to each planning area. Alternative
corridors matter: one closed edge alone does not establish isolation. Unknown
edges are tested both available and unavailable; a result depending on an
unknown edge remains unknown.

Repeat these checks for sampled dates in the following two **calendar days**.
If a currently reachable area loses all modeled paths, suggest an earlier visit.
Show the first sampled loss date and triggering assumptions. Daily means cannot
establish the time within that day. Missing days and the end of the record leave
the outlook incomplete rather than demonstrating that access will persist.

In this scenario, Area A first loses modeled access on November 14; Area B first
loses it on November 15. Area C retains an independent corridor. Thresholds are
reversible as water recedes. That is a scenario reset, not evidence that damaged
roads or bridges reopened. No populations, medical urgency or rescue-priority
weights are invented.

## Reproduce and publish

The current locked API environment is sufficient; no processing dependency or
new package is needed:

```sh
uv sync --locked
# Fetch the small public source response and rebuild the curated input.
uv run --locked python scripts/prepare_access_replay.py
# Prepare all decisions before serving.
uv run --locked floodbeacon prepare-access-replay
# Shared DATABASE_URL must already be configured in .env.
uv run --locked --env-file .env floodbeacon publish-access-replay
```

The publication uses its own case, `bc-2021-access-demo`, and the existing
immutable-run schema. Metadata, decisions, observations and network GeoJSON
publish in one database transaction. Its content-derived run ID makes repeated
publication of the same artifact idempotent. Existing `bc-2021` analysis and
Germany imagery remain separate cases/publication kinds.

`GET /cases/bc-2021-access-demo/access-replay` returns the latest completed
replay; optional `run_id` pins a publication. It performs no inference or graph
processing. A packaged `/static/access-replay/replay.json` export also works
without a database. The dashboard commits the identical export as
`public/data/access-replay.json`, so the Response view needs no API, external
basemap or forecast service for the demo. Its diagram is a schematic access
network, not a flood-inundation map.

The prepared 53,978-byte export's SHA-256 for this snapshot is
`b23aceeac37a7166909b14a949d5f0049b06a457f403307b262b337d7a0b94ab`.
It matches the frontend export byte for byte. Both source dates and access
assumptions are retained in it.

```sh
uv run --locked floodbeacon prepare-access-replay \
  --output ../floodbeacon-dashboard-access-replay/public/data/access-replay.json
uv run --locked python -m pytest tests/test_access.py tests/test_access_api.py
```

## Data we would use for the live version

| Planned input | Candidate source | Required connection to the engine |
| --- | --- | --- |
| River-stage or discharge forecast | Local hydrological forecast service; [RLP forecast gauges](https://www.hochwasser.rlp.de/faq) for a German case; [GloFAS](https://ewds.climate.copernicus.eu/datasets/cems-glofas-forecast?tab=overview) for broader discharge context | Normalize each forecast's issue time, availability time, valid time, station/reach, units, datum and quality. GloFAS discharge is not a local road-depth estimate. |
| Live river observations | [ECCC hydrometric observations](https://eccc-msc.github.io/open-data/msc-data/obs_hydrometric/readme_hydrometric_en/) or the local gauge operator | Anchor the forecast to current measured conditions; retain provisional flags and gaps. |
| Terrain and local water-surface relationship | Authoritative terrain, river geometry and gauge/reach calibration; [RLP open terrain](https://lvermgeo.rlp.de/geodaten-geoshop/open-data/) for Germany | Convert projected water level into road/approach inundation. Terrain and gauge stage alone do not provide bridge-deck elevation. |
| Road network and settlements | Historical/current authoritative transport data or [OpenStreetMap](https://www.openstreetmap.org/copyright) | Replace the schematic network; preserve topology, direction, vehicle restrictions and alternatives beyond the study boundary. |
| Bridge condition and geometry | Bridge owner inventories, inspections, deck/approach elevations and, for scour assessment, foundation/hydraulic information | Replace demonstration thresholds with supported access-concern rules. Structural failure would require additional modeling and evidence. |
| Confirmed closures and field reports | Road authority and responder updates | Override threshold-based availability and avoid reopening damaged infrastructure just because water recedes. |

These future inputs are **not integrated**. The implemented network evaluator
is separate from the historical replay wrapper. A future forecast adapter can
normalize forecast values into its metric inputs, while preserving the
observation/forecast/scenario distinctions in the publication and UI. A local
stage forecast is the simplest first integration; weather-to-river ML is optional.

For a historical predictive evaluation, forecasts must actually have been issued
and available before each cutoff. Reanalysis, final agency assessments and later
historical observations may be references, but cannot be earlier forecast inputs.
Historical forecast retrieval for July 2021 Germany has not been verified.

## Verification performed

- Real nine-day ECCC input was freshly retrieved, checksummed and reproduced
  from the retained raw response. Source dates, exact values and estimated
  discharge flags were checked separately from synthetic tests.
- Backend suite: 113 passed, five database-dependent checks skipped in the
  ordinary processing-environment run. The seven PostgreSQL integration tests
  were also run explicitly against the hosted development database and passed,
  using unique synthetic case IDs and cleaning only those IDs.
- The actual demo publication succeeded; a repeated publish returned the same
  content-derived run. Live API and static delivery returned all nine frames.
- Frontend production build and lint completed; lint retains three existing
  warnings and the build retains its existing bundle-size warning.
- Browser checks covered desktop, 390px phone and the phone breakpoint,
  English/Thai, light/dark, selection, numeric trigger explanations, playback,
  end-of-record uncertainty, estimated flags, missing/malformed data and
  rendering with external network services blocked. No page errors occurred.

These checks validate the implementation and replay provenance. They do not
measure forecasting performance or the accuracy of the assumed access rules.
