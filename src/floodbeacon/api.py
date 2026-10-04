"""Read-only map API over completed PostgreSQL analysis runs."""

from datetime import date, datetime
import math
import os
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
import psycopg

from floodbeacon import db


app = FastAPI(title="FloodBeacon", description="Historical evidence, exposure and scenarios.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.environ.get("CORS_ORIGINS", "*").split(",")
        if origin.strip()
    ],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=Path(__file__).with_name("static")), name="static")


class Case(BaseModel):
    id: str
    name: str
    bbox: tuple[float, float, float, float]
    description: str


class Run(BaseModel):
    id: str
    case_id: str
    generated_at: datetime
    metadata: dict[str, Any]


class ObservationSeries(BaseModel):
    case_id: str
    run_id: str
    generated_at: datetime
    observations: list[dict[str, Any]]


class AccessReplay(BaseModel):
    """Precomputed historical hindsight with explicitly hypothetical access rules."""

    schema_version: Literal[1]
    case_id: str
    title: str
    mode: Literal["historical_replay"]
    lookahead_days: int
    station: dict[str, Any]
    network: dict[str, Any]
    sources: list[dict[str, Any]]
    assumptions: list[str]
    frames: list[dict[str, Any]]
    run_id: str
    generated_at: datetime


Position = tuple[float, float]
Bounds = tuple[float, float, float, float]


class SatelliteImage(BaseModel):
    """A static, georeferenced PNG; corners are NW, NE, SE, SW in WGS84."""

    id: str
    url: str
    bounds: Bounds
    image_coordinates: tuple[Position, Position, Position, Position]
    width: int
    height: int
    sha256: str
    bytes: int
    attribution: str
    license: str
    license_url: str
    provenance: dict[str, Any]


class BridgeFinding(BaseModel):
    model_config = ConfigDict(extra="allow")

    bridge_id: str
    name: str
    observation_id: str
    observed_date: date
    finding: str
    status: Literal["visible_crossing", "missing_span", "uncertain"]
    assessment_method: Literal["manual image review"]
    failure_time: None
    annotation: str


class ReviewSquare(BaseModel):
    type: Literal["Polygon"]
    coordinates: list[list[Position]]


class BridgeFeature(BaseModel):
    type: Literal["Feature"]
    id: str | int | None = None
    geometry: ReviewSquare
    properties: BridgeFinding


class BridgeFeatures(BaseModel):
    type: Literal["FeatureCollection"]
    features: list[BridgeFeature]


class RegionalTiles(BaseModel):
    """Precomputed XYZ satellite tiles served as static package files."""

    url: str
    bounds: Bounds
    minzoom: int
    maxzoom: int
    tile_size: int
    attribution: str
    license: str
    license_url: str
    provenance: dict[str, Any]


class FloodExtent(BaseModel):
    """Agency polygons retain their source properties and geometry types."""

    type: Literal["FeatureCollection"]
    features: list[dict[str, Any]]


class ImageryObservation(BaseModel):
    id: str
    acquired_date: date
    acquired_at: datetime | None
    label: str
    images: list[SatelliteImage]
    bridges: BridgeFeatures
    regional_tiles: RegionalTiles | None = None


class BridgeComparison(BaseModel):
    id: str
    name: str
    coordinate: Position
    failure_time: None
    comparison_url: str | None
    before_url: str | None
    after_url: str | None
    agency_evidence: dict[str, Any] | None
    limitations: list[str]


class ImageryCatalog(BaseModel):
    case_id: str
    name: str
    country: str
    bounds: Bounds
    bridges: list[BridgeComparison]
    limitations: list[str]
    run_id: str
    generated_at: datetime
    observations: list[ImageryObservation]
    study_bounds: Bounds | None = None
    flood_extent: FloodExtent | None = None
    flood_extent_source: dict[str, Any] | None = None


class ObservedBridges(BridgeFeatures):
    case_id: str
    run_id: str
    generated_at: datetime
    observation_id: str
    acquired_date: date
    acquired_at: datetime | None


RunQuery = Annotated[str | None, Query(max_length=128)]


@app.exception_handler(psycopg.Error)
def database_unavailable(request: Request, exc: psycopg.Error):
    # Driver messages can contain host names or credentials. Return no connection details.
    return JSONResponse(status_code=503, content={
        "detail": "Map storage is unavailable. Check DATABASE_URL and access to the shared database."
    })


@app.get("/health")
def health():
    with db.connect() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok"}


@app.get("/cases", response_model=list[Case])
def cases():
    return db.list_cases()


@app.get("/cases/{case_id}/runs", response_model=list[Run])
def runs(case_id: str):
    result = db.list_runs(case_id)
    if not result and not any(case["id"] == case_id for case in db.list_cases()):
        raise HTTPException(404, "Case not found")
    return result


@app.get("/cases/{case_id}/runs/{run_id}", response_model=Run)
def run(case_id: str, run_id: str):
    result = db.get_run(case_id, run_id)
    if result is None:
        raise HTTPException(404, "Case or run not found")
    return result


def _bbox(value: str | None) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    try:
        west, south, east, north = map(float, value.split(","))
    except ValueError:
        raise HTTPException(422, "bbox must be west,south,east,north") from None
    if not all(math.isfinite(v) for v in (west, south, east, north)) or not (
        -180 <= west <= east <= 180 and -90 <= south <= north <= 90
    ):
        raise HTTPException(422, "bbox must be finite WGS84 bounds without crossing the antimeridian")
    return west, south, east, north


def _positions(coordinates):
    if not isinstance(coordinates, (list, tuple)):
        return
    if len(coordinates) >= 2 and all(isinstance(v, (float, int)) for v in coordinates[:2]):
        yield coordinates[0], coordinates[1]
    else:
        for child in coordinates:
            yield from _positions(child)


def _geometry_positions(geometry):
    if not isinstance(geometry, dict):
        return
    if geometry.get("type") == "GeometryCollection":
        for child in geometry.get("geometries", []):
            yield from _geometry_positions(child)
    else:
        yield from _positions(geometry.get("coordinates", []))


def _intersects(feature: dict, bounds) -> bool:
    positions = list(_geometry_positions(feature.get("geometry")))
    if not positions:
        return False
    xs, ys = zip(*positions)
    west, south, east, north = bounds
    return min(xs) <= east and max(xs) >= west and min(ys) <= north and max(ys) >= south


@app.get("/cases/{case_id}/layers/{layer}")
def layer(
    case_id: str, layer: str, run_id: RunQuery = None,
    bbox: Annotated[str | None, Query(max_length=128)] = None,
    limit: Annotated[int, Query(ge=1, le=10000)] = 1000,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    bounds = _bbox(bbox)
    result = db.get_layer(case_id, layer, run_id)
    if result is None:
        raise HTTPException(404, "Case, run or layer not found")
    features = result["features"]
    if bounds is not None:
        # Bounding-envelope overlap, not clipping or exact geometry intersection.
        features = [feature for feature in features if _intersects(feature, bounds)]
    total = len(features)
    return {**result, "features": features[offset:offset + limit], "pagination": {
        "offset": offset, "limit": limit, "total": total,
        "next_offset": offset + limit if offset + limit < total else None,
        "bbox_filter": "geometry envelope overlap" if bounds is not None else None,
    }}


@app.get("/cases/{case_id}/observations", response_model=ObservationSeries)
def observations(case_id: str, run_id: RunQuery = None):
    selected = db.get_run(case_id, run_id)
    if selected is None:
        raise HTTPException(404, "Case or run not found")
    # Resolve latest once, so a concurrently published run cannot mix metadata/data.
    data = db.get_observations(case_id, selected["id"])
    if data is None:
        raise HTTPException(404, "Case or run not found")
    return {"case_id": case_id, "run_id": selected["id"],
            "generated_at": selected["generated_at"], "observations": data}


@app.get("/cases/{case_id}/imagery", response_model=ImageryCatalog)
def imagery(case_id: str, run_id: RunQuery = None):
    """Dated satellite files and manual bridge findings from one published run."""
    result = db.get_imagery(case_id, run_id)
    if result is None:
        raise HTTPException(404, "Case or imagery run not found")
    return result


@app.get("/cases/{case_id}/access-replay", response_model=AccessReplay)
def access_replay(case_id: str, run_id: RunQuery = None):
    """Return one immutable completed replay; no decision processing in GET."""
    result = db.get_access_replay(case_id, run_id)
    if result is None:
        raise HTTPException(404, "Case or access replay run not found")
    return result


@app.get(
    "/cases/{case_id}/imagery/{observation_id}/bridges",
    response_model=ObservedBridges,
)
def imagery_bridges(case_id: str, observation_id: str, run_id: RunQuery = None):
    """Review squares describe image observations, not a surveyed damage boundary."""
    catalog = db.get_imagery(case_id, run_id)
    if catalog is None:
        raise HTTPException(404, "Case or imagery run not found")
    selected = next(
        (item for item in catalog["observations"] if item["id"] == observation_id), None
    )
    if selected is None:
        raise HTTPException(404, "Imagery observation not found")
    return {
        **selected["bridges"],
        "case_id": case_id,
        "run_id": catalog["run_id"],
        "generated_at": catalog["generated_at"],
        "observation_id": selected["id"],
        "acquired_date": selected["acquired_date"],
        "acquired_at": selected["acquired_at"],
    }
