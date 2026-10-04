# FloodBeacon engineering agreement

## Product intent and current status

This is the FloodBeacon data and analysis repository. The intended users are
first responders and disaster recovery services. The eventual web frontend will
render maps using a REST API from this repository.

The product has two goals:

1. Identify damaged infrastructure and disrupted access, especially roads and
   bridges, to support response planning.
2. Identify areas whose access may deteriorate so responders can consider
   visiting them earlier.

The user approved a historical POC for Germany's July 2021 Ahr Valley flood
(EMSR517 AOI15) and British Columbia's November 2021 floods, focused on
Merritt/Coldwater and the Nicola Valley/Highway 8 corridor. The approved initial
approach is supervised satellite flood/asset-exposure ML, agency damage
evidence, hypothetical access-risk scenarios, and batch publication to
PostgreSQL 18. Case bounds and source configurations live in
`src/floodbeacon/cases.py`; they are study areas, not whole-event coverage.

The implemented ML is a small CPU Random Forest trained on Sen1Floods11 hand
labels. It classifies present surface water in Sentinel-1 imagery; spatial
overlay estimates candidate infrastructure exposure. It does not detect
structural destruction or predict future collapse. Ahr destruction grades are
imported agency assessments. BC uses a current bridge/culvert inventory as map
context; the historical impact PDF is researched but not ingested as damage
labels. Hypothetical 50/100 m flood-footprint expansions have no predicted time
or likelihood. Rainfall and gauges provide historical context, not a trained
failure model.

FastAPI reads completed PostgreSQL runs; a generated HTML preview reads the
same layers. Runtime/dependency locking and real small-sample model training
are implemented. Full pipeline and delivery verification must be reported from
actual runs. Automated building damage is a possible additional scope,
pending the user's choice; research alone does not authorize adding it.
The user subsequently authorized deep damage-model research and local CUDA
experiments. Standalone runners, pinned research dependencies and ignored
experimental outputs live separately from the production batch/API. The local
RTX 3080 Laptop GPU is working. See
[actual CUDA experiments and recommendations](docs/damage-identification-research.md)
before choosing a damage model; successful inference is not validated damage
detection. Research authorization does not itself approve a product scope change.
The user also approved the SpaceNet 8 experiment. Its standalone native CUDA
runner and six-tile same-event results are documented in
[the SpaceNet experiment](docs/spacenet8-experiment.md); they do not validate
unseen-event road damage or authorize production integration.
See [research and implementation status](docs/research.md),
[the current model](docs/model.md), [pretrained damage models](docs/pretrained-models.md)
and [structural-data limits](docs/structural-data.md).

The current bridge demo serves curated satellite observations for Rech, Germany
(`ahr-2021`), Derna, Libya (`derna-2023`) and Syabrubesi, Nepal (`nepal-2026`).
The dashboard Routes tab opens on Germany's Ahr study area with dated regional
XYZ tiles, separate Copernicus inundation/flood-trace polygons and detailed bridge
images on zoom. It consumes dated imagery with square review annotations. Findings are manual image reviews; agency evidence remains
separate, and failure times remain unknown. Curated lawful PNGs, WebP tiles and provenance
are packaged under `src/floodbeacon/static/imagery/` (about 34 MiB total); raw
TIFFs remain ignored. PostgreSQL stores metadata, observations and GeoJSON only.
Preparation is separate from serving, and `floodbeacon publish-imagery` publishes
immutable complete cases. See [integration](docs/imagery-integration.md) and
[preprocessing](docs/bridge-imagery-preprocessing.md).

The user authorized the second feature as historical access replay, with a
future forecast adapter rather than new predictive training for the demo.
The separate dashboard Response tab uses real ECCC Coldwater daily stage and
discharge (November 11–19, 2021) with explicitly illustrative planning areas,
network links and concern thresholds. Its two-day outlook uses later historical
observations as hindsight; it is not a forecast available during the event.
Preparation exports a small package JSON and publication creates an immutable
`bc-2021-access-demo` run in the hosted database. GET only reads prepared data.
The frontend commits the same export for an API-independent SVG diagram.
See [access replay and planned data](docs/access-replay.md). Do not present this
schematic graph as actual road geometry or its access losses as historical
closures. No bridge collapse, local road depth or calibrated risk is modeled.
Frontend changes require a PR based on freshly fetched `main`.

All current work uses the hosted development database configured through the
ignored `.env`. `DATABASE_URL` is required; there is no local database fallback.
The local Compose PostgreSQL container is stopped. Real database tests create
unique synthetic cases and clean up only their own case IDs.

## User requirements

- Curated published imagery is stored as small Git-tracked package files under
  `src/floodbeacon/static/`, served at `/static`; do not store image bytes in
  PostgreSQL. The inspected Rech satellite pair and manual review square are
  documented in `docs/rech-satellite.md`. Raw TIFFs remain ignored. Static
  delivery must work without processing dependencies or a database connection.
- Default application dependencies support API serving only: FastAPI, Uvicorn,
  Pydantic and Psycopg. The default `dev` group contains pytest and httpx;
  geospatial/CPU modeling and preview dependencies belong in `processing`.
  `damage-research` includes `processing` alongside its research dependencies.
- Frontend developers run `uv sync --locked`, set the shared `DATABASE_URL` in
  `.env`, then run `uv run --locked --env-file .env uvicorn floodbeacon.api:app
  --reload --port 8000`. The processing owner initializes and publishes to the
  shared PostgreSQL instance; API-only users need no local database or imagery.
  CORS permits `*` for the current demo with credentials disabled. Pass optional
  groups on every processing/research `uv run` command.
- Use Python for analysis and uv for environments and package management.
- Use the latest stable compatible Python release. Commit `.python-version`,
  `pyproject.toml`, and `uv.lock` when implementation begins.
- Use FastAPI for the eventual REST API serving the map frontend.
- Batch processing with PostgreSQL persistence is approved. Keep processing
  out of GET requests and publish each complete run in one database transaction.
- Use PostgreSQL 18, with its latest stable patch release at implementation
  time. The current Compose uses PostgreSQL 18.6, localhost port 55432, and
  the PostgreSQL 18 volume layout. Spatial layers use JSONB; PostGIS is not
  currently required.
- Provide a way to inspect results before the actual frontend exists: a
  notebook, HTML map, or image is acceptable.
- Use a subagent for the initial data and modeling research, use multiple 
  subagents and other models as needed; parallelize
  independent research, implementation and review work where useful.
- Stop and ask the user when a business decision is needed or materially
  different implementation approaches are available. Explain the tradeoffs and
  recommend a concrete option. Routine details within an approved approach do
  not need repeated approval.

## Global engineering default

Before manually writing or changing a dependency, runtime, tool, GitHub Action,
provider, infrastructure module, API, or engine version, search the web and
prefer the official release notes, documentation, or registry to identify the
current latest stable compatible version. Use that version by default unless
the user requests a different version or the repository's compatibility and
stability constraints require one; state the reason whenever the latest stable
version is not used.

## Evidence and modeling rules

- Keep observed inundation, reported damage, inferred exposure, and projected
  risk distinct in the data and map legend. Preserve the source's damage grade.
- A flooded footprint is not proof of structural destruction. A mapped bridge
  crossing a river is not automatically flooded, closed, or destroyed. Check
  approaches, deck elevation where available, and explicit damage evidence.
- Missing observations, clouds, SAR shadow, and unexamined areas mean unknown;
  they do not establish that an asset is intact or a route is passable.
- Do not claim an exact bridge failure time or calibrated failure probability
  from rainfall, wind, or a flood mask alone. Structural failure modeling needs
  appropriate asset attributes, hydraulics, failure labels, and validation.
- A road access concern does not establish that a boat route is navigable.
  Transport recommendations require a separately agreed scope and evidence.
- Imported agency assessments must be attributed as agency assessments. Do not
  present them as output from a FloodBeacon detector.
- Historical playback must track acquisition/observation time, publication or
  availability time, and forecast issue/valid times. Use only inputs available
  at the replay cutoff for predictive evaluation. Final reanalysis and post-event
  assessments can be retrospective references, not earlier forecast inputs.
- Explicitly mark hypothetical scenarios and synthetic fixtures. Do not use
  them as historical measurements or model performance evidence.
- For prioritization, explain the access concern and evidence. Do not invent
  population, service urgency, or rescue priority weights without agreement.
- RF vote fractions are uncalibrated water scores, not flood/bridge-failure
  probabilities. Document Sen1Floods11 sigma-naught versus Planetary Computer
  RTC gamma-naught domain shift. Training holdout metrics do not establish
  Ahr/BC transfer accuracy. Preserve per-chip failures alongside pooled scores.
- The present valid-coverage layer identifies usable raster observations; it
  is not a complete SAR shadow/layover or reliability mask. Do not equate full
  raster coverage with reliable damage detection.

## Reproducibility and delivery

- Record source URLs, dataset/item IDs and versions, license/attribution,
  acquisition times, retrieval times, units, CRS, processing parameters, and
  checksums for downloaded inputs and generated outputs.
- Keep large raw imagery and credentials out of Git. Check in small lawful
  fixtures only when needed; provide reproducible retrieval instructions.
- Sen1Floods11's official label catalog declares `proprietary` and the authors'
  repository has an unresolved missing-license issue. Record these exact facts;
  do not infer rights from third-party mirrors. Current downloads and locally
  trained models are ignored research artifacts. Local research is authorized;
  publication/redistribution is outside the current task scope.
- Use a suitable projected CRS for distances and areas. Serve GeoJSON in
  WGS84 longitude/latitude order. Preserve no-data masks and quality flags.
- Keep analysis in reusable Python modules; notebooks or previews should use
  those modules and the same artifacts consumed by the API.
- Do not fetch imagery, train models, or run heavy geospatial processing inside
  map-data GET requests. If batch processing is approved, publish complete,
  versioned runs atomically and include their timestamps and provenance.
- Validate geometry and time alignment, uncertainty behavior, historical
  leakage, and API contracts. Report real-data checks separately from tests
  using synthetic fixtures.
- A delivered POC needs documented commands, an inspectable visualization,
  reproducible inputs or an explicit access limitation, and tested API output.
  Do not claim these exist before they have been implemented and verified.
