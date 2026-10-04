# FloodBeacon

FloodBeacon explores how disaster imagery can help responders identify damaged
infrastructure and disrupted access. The current hackathon focus is **visible
bridge destruction in before/after imagery**.

Start with the [bridge demo and findings](docs/bridge-demo-research.md). We
retrieved and manually reviewed seven crossings in Germany, Libya and Nepal.
The comparison viewer shows original image crops, manual annotations,
coordinates, observation dates and source attribution.

## Run the API against the shared database

For frontend development, install [uv](https://docs.astral.sh/uv/getting-started/installation/),
clone this repository, and run:

```sh
uv sync --locked
cp .env.example .env
```

Edit `DATABASE_URL` in `.env` to use the shared PostgreSQL connection supplied
by the project owner. Then start the API:

```sh
uv run --locked --env-file .env uvicorn floodbeacon.api:app --reload --port 8000
```

Open [the API documentation](http://localhost:8000/docs) and
[database health](http://localhost:8000/health). The API reads completed runs
already published to the shared database. The project owner initializes that
database and prepares data on the processing machine; your teammate only needs
the connection URL. This setup requires no local PostgreSQL, Docker, imagery downloads,
model weights, or training.

`.env` is ignored by Git. `uv run --env-file .env` loads its variables explicitly;
the application does not automatically read the file. `CORS_ORIGINS=*` permits
requests from any frontend origin for the current demo, with credentialed CORS
requests disabled.

The [Rech satellite comparison](docs/rech-satellite.md) is now checked in and
served as static files. Open `/static/imagery/rech-satellite/comparison.png`
or fetch `/static/imagery/rech-satellite/manifest.json` for the aligned image
URLs, dates, map coordinates and attribution. These files need no database
query. The dated imagery catalog is published to the shared PostgreSQL database. The
dashboard Routes tab consumes `/cases/ahr-2021/imagery`; the same API supports
`derna-2023` and `nepal-2026`. Image pixels remain in Git-tracked static files,
while PostgreSQL stores dates, provenance, annotations and publication metadata.
Germany opens on the full Ahr Valley study area with dated XYZ satellite tiles,
a separate Copernicus inundation/flood-trace overlay and detailed Rech bridge
pixels on zoom. Historical RGB coverage is approximately 53% before and 55% after;
gaps remain unknown. All curated imagery and metadata total about 34 MiB.
See [frontend integration and publication](docs/imagery-integration.md).

## Dependency groups and code responsibilities

| Install | Purpose |
| --- | --- |
| `uv sync --locked` | FastAPI, Uvicorn, Pydantic and Psycopg, plus the default `dev` group for tests. |
| `uv sync --locked --group processing` | Imagery preparation, historical ingestion, CPU water modeling, spatial analysis and map previews. |
| `uv sync --locked --group damage-research` | Processing dependencies plus the GPU/model research dependencies. |

The `dev` group contains pytest and httpx. API serving lives in
`src/floodbeacon/api.py` and `db.py`; other package modules support processing
and analysis. `scripts/` holds research runners and viewers, while `tests/`
holds automated checks. Processing runs publish data; API GET requests read it.

Include the required group on each processing or research `uv run` command:
uv synchronizes the environment for that command, so a prior installation of
an optional group alone does not select it for later runs.

API and database contract checks:

```sh
uv run --locked pytest tests/test_api.py tests/test_db.py
```

API contract checks run without a database. Database integration checks opt in
through `FLOODBEACON_TEST_DATABASE_URL`. For the current shared development
instance, load `.env` and set that variable to `DATABASE_URL` in the test process.
These tests create uniquely named synthetic cases and delete only those cases.

Full checks, including processing and research:

```sh
uv run --locked --group processing --group damage-research pytest
```

## How the bridge findings were made

1. Use news and agency damage reports to select likely damaged crossings.
2. Locate the crossing and retrieve high-resolution before/after images.
3. Visually compare the bridge span and approaches, then record the finding.
4. Show the image evidence and marked location for human review.

**The delivered bridge findings are manual image assessments.** An AI assistant
visually reviewed the images; the scripts cropped, annotated and displayed
them. No trained bridge-collapse detector generated these findings. Agency damage grades are
separate evidence and retain their source attribution. The curated bridge
catalog is served by the REST API and integrated into the dashboard Routes tab.

For the initial Germany satellite view, use the now-inspected
[Rech February/July 2021 satellite pair](docs/rech-satellite.md). Its image files
and a square review annotation are included in this repository.
Another satellite demo is **Derna, Libya, September 2023**: road bridge
decks are visible before the flood and absent afterward. For the existing
Germany case, **Nepomukbrücke in Rech, July 2021** has a clearly missing section;
both satellite and earlier aerial comparisons are available. Nepal provides
additional satellite examples with more uncertainty about when each crossing was lost.

## Inspect the bridge demo

If the research inputs have already been retrieved locally:

```sh
uv run --locked python scripts/render_bridge_demo.py
uv run --locked python -m http.server 8080 --bind 127.0.0.1 --directory artifacts
```

Open [the bridge comparison viewer](http://127.0.0.1:8080/bridge-demo/).
Downloaded imagery and generated viewers are ignored by Git, so a fresh clone
must first follow the [retrieval instructions](docs/bridge-demo-research.md#inspect-and-reproduce)
and the linked source reports. Viewing the comparisons does not require
PostgreSQL or running a model. Preserve each source's attribution and license;
the selected Maxar/Vantor collections use CC BY-NC 4.0.

## What the model research established

We did not obtain and validate a pretrained model that detects bridge collapse
in these images. Bridge-location detectors are research leads; locating a
bridge does not establish its damage status.

| Experiment | Result relevant to this demo |
| --- | --- |
| Sentinel-1 Random Forest | Classifies surface water and estimates asset exposure; it does not detect missing bridge spans. |
| SpaceNet 8 | Ran on six Germany tiles. Obstructed-road recall was 31.88%; its labels describe obstruction, not bridge collapse. |
| BRIGHT building models | Both tested baselines failed to detect positive building damage in the selected Libya evaluation. They do not supply bridge-collapse findings. |
| ChangeOS building model | Inference ran, but local damage accuracy was not validated. Its task is building damage. |

The research supplied reproducible experiments and helped select suitable
imagery, but **the current bridge demo relies on manual before/after review**.
See the [measured model results](docs/damage-identification-research.md) and
[SpaceNet 8 experiment](docs/spacenet8-experiment.md) for details.

## Earlier historical flood-analysis POC

The separate responder **Response** tab now demonstrates historical access
planning with November 11–19, 2021 Coldwater gauge observations, hypothetical
closure thresholds and a schematic network. Later historical observations
provide a two-day hindsight outlook; this is not a trained forecast or a record
of actual closures. See [data, decision rules and future forecast inputs](docs/access-replay.md).
Prepare with `uv run --locked floodbeacon prepare-access-replay` and publish with
`uv run --locked --env-file .env floodbeacon publish-access-replay`.
The read-only API is `/cases/bc-2021-access-demo/access-replay`; its dedicated
case preserves existing BC analysis. The frontend also packages the same small
JSON export so this demo works independently of the API.

The existing batch pipeline publishes complete PostgreSQL runs; FastAPI and an
HTML map read those same artifacts. Its configured cases are the July 2021 Ahr
Valley flood in Germany (CEMS EMSR517 AOI15) and the November 2021
Merritt/Nicola Valley floods in British Columbia.

- A supervised Random Forest classifies surface water from pre/post Sentinel-1
  imagery and maps candidate newly water-like areas and asset exposure.
- Ahr transport destruction/damage grades come from **Copernicus agency
  assessments**, separately from model results. BC currently has bridge/culvert
  inventory context and historical gauge/rainfall observations; its historical
  impact PDF has not been converted into damage labels.
- Hypothetical 50/100 m footprint expansions illustrate sensitivity. They have
  **no forecast time or likelihood**. No model predicts that a bridge will
  collapse in two days, and no layer certifies road passability or boat access.

## Project owner: run the historical flood pipeline

Run this workflow on the processing machine against the hosted development
database configured in `.env`. The local Compose database is stopped; all current
processing and API work uses the hosted instance.
[Python's release list](https://www.python.org/downloads/)
was checked on 2026-10-03: Python 3.14.8 is the current stable release and is
pinned in `.python-version`. Dependencies are locked in `uv.lock`.
[PostgreSQL 18.6](https://www.postgresql.org/docs/release/) is pinned in Compose.

```sh
uv python install 3.14.8
uv sync --locked --group processing
uv run --locked --group processing --env-file .env floodbeacon init-db
uv run --locked --group processing --env-file .env floodbeacon train --chips-per-event 3
```

If the installed uv does not yet list Python 3.14.8, use Astral's current official
interpreter metadata. This was the successful fallback for uv 0.11.16 here:

```sh
uv python install --python-downloads-json-url https://raw.githubusercontent.com/astral-sh/uv/main/crates/uv-python/download-metadata.json 3.14.8
```

Training prints the locally generated `model` path. Pass that exact path to
batch processing; the following path is from the initial verified training run:

```sh
uv run --locked --group processing --env-file .env floodbeacon batch --case all --model data/models/water-rf-10958a17b65a7d7f/model.pkl
uv run --locked --group processing --env-file .env floodbeacon preview --output-dir artifacts
uv run --locked --env-file .env uvicorn floodbeacon.api:app --host 127.0.0.1 --port 8000
```

Open `artifacts/index.html` for a case selector, evidence layers, observations,
source details and limitations. Its basemap and JavaScript/CSS dependencies
require internet. The API documentation is at
[localhost:8000/docs](http://localhost:8000/docs).
`--case ahr-2021` or `--case bc-2021` runs one case. Inputs, locally trained
models and previews live in ignored `data/` and `artifacts/` directories.

Compose remains available as a historical local configuration, with its data
preserved while stopped. Current processing and serving require the hosted
development `DATABASE_URL`; there is no implicit local database fallback.
The API-specific `.env.example` contains a placeholder shared connection.
Use `--env-file .env` on processing and serving commands to load the connection.

## REST API

GET requests read completed runs; they do not download imagery or train models.
Use a returned `run_id` to keep frontend requests on the same immutable run.

| Resource | Endpoint |
| --- | --- |
| Database health | `/health` |
| Cases | `/cases` |
| Completed runs | `/cases/{case_id}/runs` |
| Run provenance and parameters | `/cases/{case_id}/runs/{run_id}` |
| GeoJSON | `/cases/{case_id}/layers/{layer}?run_id=...` |
| Historical observations | `/cases/{case_id}/observations?run_id=...` |
| Dated satellite images and bridge comparisons | `/cases/{case_id}/imagery?run_id=...` |
| Bridge annotations for one image date | `/cases/{case_id}/imagery/{observation_id}/bridges?run_id=...` |
| Detail image pixels | `/static/imagery/.../*.png` |
| Germany regional XYZ tiles | `/static/imagery/ahr-region/{date}/{z}/{x}/{y}.webp` |

Layer names include `assets`, `reported_damage`, `agency_flood_reference`,
`modeled_new_water`, `modeled_event_water`, `exposure`, `valid_coverage`,
`unknown_coverage`, `scenario_50m`, and `scenario_100m`; available names are in
each run's metadata. Empty layers indicate no records in that layer, not proof
of no damage. GeoJSON uses WGS84 longitude/latitude. Layer responses support
`limit`, `offset`, and `bbox=west,south,east,north`; bbox filtering uses geometry
**envelope overlap**, without clipping or exact intersection.

```sh
curl http://127.0.0.1:8000/cases
curl 'http://127.0.0.1:8000/cases/ahr-2021/layers/reported_damage?limit=20'
curl http://127.0.0.1:8000/cases/bc-2021/observations
uv run --locked pytest tests/test_api.py tests/test_db.py
```

## Evidence and verification

The initial real Sen1Floods11 training sampled nine training chips and three
Bolivia event-holdout chips. Pooled water IoU was 0.8418, but one holdout chip
had F1 0.1034; see [the full model report](docs/model.md). Those metrics do not
validate Ahr/BC transfer. The six ML contract/grid tests passed. Public source
queries and actual satellite TIFF-header reads succeeded without accounts.
Source ingestion also identified 4,323 Ahr transportation features, including
762 positive damage grades and 53 destroyed grades, plus 77 agency flood
reference features; BC's current inventory query returned ten structures.

Both real case batches published PostgreSQL runs and the live API returned
their data; both HTML case maps, the selector, and BC observation plots were
checked in the browser. Final verification passed **41 tests**, including real
PostgreSQL transactions, followed by compilation and live API checks. A current
Starlette/httpx TestClient deprecation warning remains; it did not fail tests.

To serve the preview locally:

```sh
uv run --locked python -m http.server 8080 --bind 127.0.0.1 --directory artifacts
```

Open [the inspection map](http://127.0.0.1:8080/). Its candidate-exposure overlay
shows flagged intersections; the API exposure layer retains every asset and its
unknown/not-detected status.

To inspect research imagery with synchronized zoom, human labels and separate
model predictions, run `uv run --locked --group damage-research python scripts/render_dataset_viewer.py`
after retrieving the Ahr/BRIGHT research inputs. Open the
[raw-data viewer](http://127.0.0.1:8080/dataset-viewer/).
The [SpaceNet 8 experiment](docs/spacenet8-experiment.md) has its own raw-photo,
annotation and prediction gallery; these are research outputs.

The Ahr model output had **poor agreement** with the retrospective agency
reference: modeled new-water area 0.8028 km², reference union 4.806 km²,
intersection 0.3601 km², overlap IoU 0.0686. The reference combines flood trace
and flooded-area evidence from July 18, while SAR was acquired July 15; this is
a dated spatial comparison, **not detector accuracy**. Terrain shadow/layover
has not been fully screened. Treat local output as experimental. Ahr yielded
125 candidate exposed transportation features; BC yielded zero candidates among
ten current inventory structures. Zero candidates does not establish intact
bridges or passable routes. BC has no ingested compatible flood reference for
local evaluation. See each run's metadata and preview limitations.

Sen1Floods11's official label catalog declares `proprietary` and the authors'
repository has an unresolved missing-license issue. Training-data/model rights
are recorded as unresolved; keep downloaded inputs and trained artifacts local
for this research POC. Source access currently needs no account for the tested
baseline, but access terms and quotas are separate from redistribution rights.

- [Engineering agreement](AGENTS.md)
- [Research, sources and implementation status](docs/research.md)
- [Current model and reproducibility](docs/model.md)
- [Pretrained structural-damage model research](docs/pretrained-models.md)
- [Bridge inventories and structural-data gaps](docs/structural-data.md)
