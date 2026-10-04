#!/usr/bin/env python3
"""Curate real daily gauge observations and a clearly schematic planning graph.

No processing dependencies are required. Run with ``uv run --locked python``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = (
    "https://api.weather.gc.ca/collections/hydrometric-daily-mean/items"
    "?f=json&STATION_NUMBER=08LG010&datetime=2021-11-11%2F2021-11-19&limit=1000"
)
LICENSE_URL = "https://eccc-msc.github.io/open-data/licence/readme_en/"


def planning_network() -> dict:
    """Author-authored geographic anchors; lines do not trace surveyed roads."""
    nodes = [
        {"id": "base", "name": "Demo staging point", "coordinate": [-120.7815, 50.117], "kind": "base"},
        {"id": "north", "name": "Northern planning junction", "coordinate": [-120.795, 50.112], "kind": "junction"},
        {"id": "south", "name": "Southern planning junction", "coordinate": [-120.795, 50.099], "kind": "junction"},
        {"id": "area-a", "name": "Planning area A", "coordinate": [-120.814, 50.104], "kind": "community"},
        {"id": "area-b", "name": "Planning area B", "coordinate": [-120.798, 50.089], "kind": "community"},
        {"id": "area-c", "name": "Planning area C", "coordinate": [-120.768, 50.109], "kind": "community"},
    ]
    coordinates = {node["id"]: node["coordinate"] for node in nodes}
    definitions = [
        ("base-north", "Northern staging corridor", "base", "north", None),
        ("base-south", "Southern staging corridor", "base", "south", ("stage_m", 2.2, "Assumed concern threshold for a low approach")),
        ("north-a", "Area A northern corridor", "north", "area-a", ("stage_m", 1.6, "Assumed low-road concern threshold")),
        ("south-a", "Area A alternative corridor", "south", "area-a", ("stage_m", 1.65, "Assumed alternative low-road concern threshold")),
        ("north-b", "Area B northern crossing", "north", "area-b", ("stage_m", 2.8, "Assumed crossing-approach concern threshold")),
        ("south-b", "Area B alternative crossing", "south", "area-b", ("discharge_m3_s", 200.0, "Assumed high-flow concern threshold; not a structural failure model")),
        ("base-c", "Area C independent corridor", "base", "area-c", None),
        ("north-c", "Area C alternative corridor", "north", "area-c", ("discharge_m3_s", 100.0, "Assumed flow-sensitive corridor threshold")),
    ]
    edges = []
    for edge_id, name, start, end, condition in definitions:
        trigger = None
        if condition:
            metric, threshold, reason = condition
            trigger = {"metric": metric, "threshold": threshold, "reason": reason}
        edges.append({"id": edge_id, "name": name, "from": start, "to": end,
                      "coordinates": [coordinates[start], coordinates[end]], "trigger": trigger})
    return {
        "nodes": nodes, "edges": edges, "base_node_id": "base",
        "community_node_ids": ["area-a", "area-b", "area-c"],
        "note": "Schematic planning graph: all nodes, straight-line corridor geometry, connectivity and concern thresholds are illustrative author assumptions at Merritt geographic anchors. This is not a surveyed, complete or historical road network. No actual community isolation, road closure or bridge collapse is established. Untriggered corridors mean no modeled trigger, not verified passability.",
    }


def curate(raw: bytes, retrieved_at: str, raw_path: Path) -> dict:
    payload = json.loads(raw)
    observations = []
    coordinates = None
    for feature in payload["features"]:
        properties = feature["properties"]
        if properties["STATION_NUMBER"] != "08LG010":
            raise ValueError("Unexpected station in source response")
        date = properties["DATE"]
        if not "2021-11-11" <= date <= "2021-11-19":
            continue
        coordinates = feature["geometry"]["coordinates"]
        observations.append({
            "date": date,
            "stage_m": properties.get("LEVEL"),
            "discharge_m3_s": properties.get("DISCHARGE"),
            "stage_quality": properties.get("LEVEL_SYMBOL_EN"),
            "discharge_quality": properties.get("DISCHARGE_SYMBOL_EN"),
            "available_at": None,
        })
    observations.sort(key=lambda row: row["date"])
    expected_dates = [f"2021-11-{day:02d}" for day in range(11, 20)]
    if [row["date"] for row in observations] != expected_dates:
        raise ValueError("Expected one source record for each day, November 11–19")
    try:
        raw_file = str(raw_path.relative_to(ROOT))
    except ValueError:
        raw_file = raw_path.name
    return {
        "schema_version": 1, "case_id": "bc-2021-access-demo",
        "title": "Merritt access planning — November 2021 historical replay",
        "mode": "historical_replay",
        "station": {
            "id": "08LG010", "name": "COLDWATER RIVER AT MERRITT", "coordinate": coordinates,
            "stage_datum_note": "Gauge stage in metres above the station reference datum, not elevation above sea level or water depth over a road. The station datum was not independently resolved for this demo.",
        },
        "observations": observations,
        "network": planning_network(),
        "sources": [{
            "source_id": "eccc-hydrometric-daily-mean", "title": "ECCC HYDAT daily mean water level and flow",
            "source_url": SOURCE_URL,
            "documentation_url": "https://eccc-msc.github.io/open-data/msc-geomet/ogc_api_en/",
            "dataset_id": "hydrometric-daily-mean", "station_id": "08LG010",
            "item_ids": [f"08LG010.{date}" for date in expected_dates],
            "version": "Historical archive as retrieved; API provides no immutable dataset release version",
            "retrieved_at": retrieved_at, "response_timestamp": payload.get("timeStamp"),
            "observation_period": {"start": expected_dates[0], "end": expected_dates[-1]},
            "time_resolution": "daily_mean", "date_semantics": "Source daily dates preserved verbatim; no UTC acquisition instant is inferred",
            "available_at": None, "forecast_issued_at": None, "forecast_valid_at": None,
            "units": {"stage_m": "m above station datum", "discharge_m3_s": "m³/s"},
            "crs": "OGC:CRS84 (WGS84 longitude, latitude)",
            "license": "Environment and Climate Change Canada Data Services End-use Licence, page header version 2.1.1 (August 2026)",
            "license_url": LICENSE_URL,
            "attribution": "Data Source: Environment and Climate Change Canada",
            "raw_file": raw_file, "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "processing": "Select November 11–19, sort by source DATE, rename LEVEL/DISCHARGE, preserve exact numeric values, nulls and English quality symbols; no interpolation or rounding",
        }],
        "assumptions": [
            "Real historical daily observations drive an illustrative access scenario; future historical values are retrospective look-ahead, not forecasts available in 2021.",
            "Original publication/availability times are unknown, represented as null; no predictive skill or historical no-leakage evaluation is claimed.",
            "Daily means cannot resolve intraday peaks or exact access-loss times. Calendar-day windows are used without invented hourly precision.",
            "Nov 15 and Nov 16 discharge values carry ECCC's Estimated flag; missing source flags remain null rather than becoming a verified quality claim.",
            "Gauge thresholds are hypothetical scenario parameters, not local road depths, calibrated closure thresholds, bridge failure probabilities or evidence of actual destruction.",
            "Graph geometry, connectivity, destinations and staging point are synthetic. Destination names do not assert settlements, population, responder bases or rescue urgency.",
            "A triggered edge represents modeled access concern. An untriggered edge does not establish actual passability.",
            "Thresholds recover as daily values fall in this reversible scenario; actual damaged infrastructure may remain unavailable long after water recedes.",
            "A live forecast adapter must provide valid times, issue/availability times, gauge units/datum and quality before using the same engine operationally.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="Normalize an already downloaded response without network access")
    parser.add_argument("--retrieved-at", help="Actual UTC retrieval timestamp; required with --source")
    parser.add_argument("--output", type=Path, default=ROOT / "src/floodbeacon/static/access-replay/input.json")
    args = parser.parse_args()
    if args.source:
        if not args.retrieved_at:
            parser.error("--source requires its truthful --retrieved-at receipt")
        raw_path = args.source.resolve()
        raw, retrieved_at = raw_path.read_bytes(), args.retrieved_at
    else:
        request = Request(SOURCE_URL, headers={"User-Agent": "FloodBeacon historical-replay prototype"})
        with urlopen(request, timeout=45) as response:
            raw = response.read()
        stamp = datetime.now(timezone.utc)
        retrieved_at = stamp.isoformat().replace("+00:00", "Z")
        digest = hashlib.sha256(raw).hexdigest()
        raw_path = ROOT / "data/raw/bc-2021" / f"access-replay-hydrometric-{stamp:%Y%m%dT%H%M%SZ}-{digest[:12]}.json"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(raw)
    result = curate(raw, retrieved_at, raw_path)
    encoded = (json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encoded)
    print(json.dumps({"output": str(args.output), "output_sha256": hashlib.sha256(encoded).hexdigest(),
                      "raw_file": str(raw_path), "retrieved_at": retrieved_at, "days": len(result["observations"])}))


if __name__ == "__main__":
    main()
