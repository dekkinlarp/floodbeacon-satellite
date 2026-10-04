"""API contracts use synthetic publications; no processing or database writes."""

from fastapi.testclient import TestClient
import json
from pathlib import Path
import psycopg

from floodbeacon import api


def replay():
    return {"schema_version": 1, "case_id": "synthetic-access", "title": "Synthetic replay",
            "mode": "historical_replay", "lookahead_days": 2,
            "station": {"id": "fixture", "stage_datum_note": "Synthetic gauge"},
            "network": {"note": "Synthetic network"}, "sources": [],
            "assumptions": ["Synthetic fixture"], "frames": [{"date": "2021-11-15",
                "observation": {"available_at": None, "discharge_quality": "Estimated"}}],
            "run_id": "synthetic-v1", "generated_at": "2026-10-04T00:00:00Z"}


def test_replay_pins_publication_and_preserves_hindsight_and_quality(monkeypatch):
    calls = []
    def read(case_id, run_id):
        calls.append((case_id, run_id))
        return replay()
    monkeypatch.setattr(api.db, "get_access_replay", read)
    with TestClient(api.app) as client:
        response = client.get("/cases/synthetic-access/access-replay?run_id=synthetic-v1",
                              headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 200
    assert calls == [("synthetic-access", "synthetic-v1")]
    assert response.headers["access-control-allow-origin"] == "*"
    result = response.json()
    assert result["mode"] == "historical_replay"
    assert result["frames"][0]["observation"]["available_at"] is None
    assert result["frames"][0]["observation"]["discharge_quality"] == "Estimated"


def test_missing_replay_and_database_failure_are_explicit(monkeypatch):
    monkeypatch.setattr(api.db, "get_access_replay", lambda *args: None)
    with TestClient(api.app) as client:
        assert client.get("/cases/missing/access-replay").status_code == 404
        def unavailable(*args):
            raise psycopg.OperationalError("private host password=secret")
        monkeypatch.setattr(api.db, "get_access_replay", unavailable)
        response = client.get("/cases/synthetic-access/access-replay")
        assert response.status_code == 503
        assert "private" not in response.text and "secret" not in response.text


def test_access_endpoint_has_documented_contract():
    with TestClient(api.app) as client:
        schema = client.get("/openapi.json").json()
    assert "AccessReplay" in schema["components"]["schemas"]
    assert "/cases/{case_id}/access-replay" in schema["paths"]


def test_packaged_export_matches_engine_and_serves_without_database(monkeypatch):
    from floodbeacon.access import load_bundled_replay
    root = Path(api.__file__).with_name("static") / "access-replay"
    payload = (root / "replay.json").read_bytes()
    assert json.loads(payload) == load_bundled_replay()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(api.app) as client:
        response = client.get("/static/access-replay/replay.json")
    assert response.status_code == 200 and response.content == payload
    assert response.json()["frames"][4]["observation"]["discharge_quality"] == "Estimated"
