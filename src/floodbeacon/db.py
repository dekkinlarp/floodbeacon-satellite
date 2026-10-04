"""Explicit schema initialization and atomic, immutable PostgreSQL map runs."""

from datetime import datetime, timezone
import os
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


def connect():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise psycopg.OperationalError("DATABASE_URL must point to the shared database")
    return psycopg.connect(
        database_url,
        connect_timeout=5,
        row_factory=dict_row,
    )


def init_db() -> None:
    """Called by the setup CLI, never by map-data requests."""
    with connect() as conn:
        conn.execute(Path(__file__).with_name("schema.sql").read_text())


def _run(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {**row, "generated_at": row["generated_at"].astimezone(timezone.utc).isoformat()}


def _get_run(conn, case_id: str, run_id: str | None = None) -> dict | None:
    if run_id is None:
        row = conn.execute(
            "SELECT id, case_id, generated_at, metadata FROM runs WHERE case_id=%s "
            "ORDER BY generated_at DESC, id DESC LIMIT 1", (case_id,)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id, case_id, generated_at, metadata FROM runs WHERE case_id=%s AND id=%s",
            (case_id, run_id),
        ).fetchone()
    return _run(row)


def publish_run(
    case: dict, run: dict, layers: dict[str, dict], observations: list[dict]
) -> dict:
    """Commit all layers/observations together; existing runs cannot be replaced."""
    if run["case_id"] != case["id"]:
        raise ValueError("Run case_id must match case id")
    timestamp = datetime.fromisoformat(str(run["generated_at"]).replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("generated_at must include a timezone")
    if not layers:
        raise ValueError("A completed run must include at least one layer")
    for data in layers.values():
        if data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
            raise ValueError("Layers must be GeoJSON FeatureCollections")
    with connect() as conn:
        conn.execute(
            "INSERT INTO cases (id,name,bbox,description) VALUES (%s,%s,%s,%s) "
            "ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, bbox=EXCLUDED.bbox, "
            "description=EXCLUDED.description",
            (case["id"], case["name"], Jsonb(case["bbox"]), case.get("description", "")),
        )
        conn.execute(
            "INSERT INTO runs (case_id,id,generated_at,metadata) VALUES (%s,%s,%s,%s)",
            (case["id"], run["id"], timestamp, Jsonb(run.get("metadata", {}))),
        )
        for name, data in layers.items():
            conn.execute(
                "INSERT INTO layers (case_id,run_id,name,data) VALUES (%s,%s,%s,%s)",
                (case["id"], run["id"], name, Jsonb(data)),
            )
        for ordinal, data in enumerate(observations):
            conn.execute(
                "INSERT INTO observations (case_id,run_id,ordinal,data) VALUES (%s,%s,%s,%s)",
                (case["id"], run["id"], ordinal, Jsonb(data)),
            )
        return _get_run(conn, case["id"], run["id"])


def list_cases() -> list[dict]:
    with connect() as conn:
        return conn.execute("SELECT id,name,bbox,description FROM cases ORDER BY id").fetchall()


def list_runs(case_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id,case_id,generated_at,metadata FROM runs WHERE case_id=%s "
            "ORDER BY generated_at DESC,id DESC", (case_id,)
        ).fetchall()
        return [_run(row) for row in rows]


def get_run(case_id: str, run_id: str | None = None) -> dict | None:
    with connect() as conn:
        return _get_run(conn, case_id, run_id)


def get_layer(case_id: str, layer: str, run_id: str | None = None) -> dict | None:
    with connect() as conn:
        run = _get_run(conn, case_id, run_id)
        if run is None:
            return None
        row = conn.execute(
            "SELECT data FROM layers WHERE case_id=%s AND run_id=%s AND name=%s",
            (case_id, run["id"], layer),
        ).fetchone()
        if row is None:
            return None
        return {**row["data"], "case_id": case_id, "run_id": run["id"],
                "generated_at": run["generated_at"]}


def get_observations(case_id: str, run_id: str | None = None) -> list[dict] | None:
    with connect() as conn:
        run = _get_run(conn, case_id, run_id)
        if run is None:
            return None
        rows = conn.execute(
            "SELECT data FROM observations WHERE case_id=%s AND run_id=%s ORDER BY ordinal",
            (case_id, run["id"]),
        ).fetchall()
        return [row["data"] for row in rows]


def get_imagery(case_id: str, run_id: str | None = None) -> dict | None:
    """Read a complete imagery publication, independent of newer analysis runs."""
    with connect() as conn:
        query = (
            "SELECT id,case_id,generated_at,metadata FROM runs WHERE case_id=%s "
            "AND metadata->>'kind'='bridge_imagery'"
        )
        params = (case_id,)
        if run_id is None:
            query += " ORDER BY generated_at DESC,id DESC LIMIT 1"
        else:
            query += " AND id=%s"
            params = (case_id, run_id)
        run = _run(conn.execute(query, params).fetchone())
        if run is None:
            return None
        # Select once and pin all observations to the immutable publication.
        rows = conn.execute(
            "SELECT data FROM observations WHERE case_id=%s AND run_id=%s ORDER BY ordinal",
            (case_id, run["id"]),
        ).fetchall()
        return {
            **run["metadata"]["imagery"],
            "case_id": case_id,
            "run_id": run["id"],
            "generated_at": run["generated_at"],
            "observations": [row["data"] for row in rows],
        }


def get_access_replay(case_id: str, run_id: str | None = None) -> dict | None:
    """Read a prepared decision replay, independent of other publication kinds."""
    with connect() as conn:
        query = (
            "SELECT id,case_id,generated_at,metadata FROM runs WHERE case_id=%s "
            "AND metadata->>'kind'='access_replay'"
        )
        params = (case_id,)
        if run_id is None:
            query += " ORDER BY generated_at DESC,id DESC LIMIT 1"
        else:
            query += " AND id=%s"
            params = (case_id, run_id)
        run = _run(conn.execute(query, params).fetchone())
        if run is None:
            return None
        return {**run["metadata"]["access_replay"], "run_id": run["id"],
                "generated_at": run["generated_at"]}
