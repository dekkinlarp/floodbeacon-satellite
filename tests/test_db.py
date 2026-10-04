"""Real PostgreSQL checks. Set FLOODBEACON_TEST_DATABASE_URL to opt in."""

import os
from uuid import uuid4

import psycopg
import pytest

from floodbeacon import db


def test_missing_database_url_never_connects_to_a_local_default(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    def unexpected(*args, **kwargs):
        pytest.fail("Missing configuration must not attempt a database connection")
    monkeypatch.setattr(psycopg, "connect", unexpected)
    with pytest.raises(psycopg.OperationalError, match="DATABASE_URL"):
        db.connect()


@pytest.fixture
def case(monkeypatch):
    url = os.environ.get("FLOODBEACON_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set FLOODBEACON_TEST_DATABASE_URL for PostgreSQL integration checks")
    monkeypatch.setenv("DATABASE_URL", url)
    db.init_db()
    item = {"id": "test-" + uuid4().hex, "name": "Test case", "bbox": [6, 49, 8, 51],
            "description": "Synthetic test fixture"}
    yield item
    with db.connect() as conn:
        conn.execute("DELETE FROM cases WHERE id=%s", (item["id"],))


def make_run(case, identifier, timestamp):
    return {"id": identifier, "case_id": case["id"], "generated_at": timestamp,
            "metadata": {"fixture": "synthetic", "provenance": []}}


def test_atomic_publication_and_immutable_runs(case):
    run = make_run(case, "v1", "2026-10-03T00:00:00+00:00")
    layers = {"exposure": {"type": "FeatureCollection", "features": []}}
    db.publish_run(case, run, layers, [{"quality": "Estimated", "available_at": None}])
    with pytest.raises(psycopg.errors.UniqueViolation):
        db.publish_run({**case, "name": "Must roll back"}, run, layers, [])
    assert next(item for item in db.list_cases() if item["id"] == case["id"])["name"] == "Test case"
    assert len(db.list_runs(case["id"])) == 1
    assert db.get_observations(case["id"]) == [{"quality": "Estimated", "available_at": None}]
    assert db.get_layer(case["id"], "exposure")["run_id"] == "v1"


def test_failed_layer_insert_rolls_back_entire_run(case):
    # A DB failure after inserting the case/run must not expose a partial run.
    class NonJson:
        pass
    run = make_run(case, "failed", "2026-10-03T00:00:00+00:00")
    with pytest.raises(TypeError):
        db.publish_run(case, run, {
            "good": {"type": "FeatureCollection", "features": []},
            "bad": {"type": "FeatureCollection", "features": [], "invalid": NonJson()},
        }, [])
    assert db.get_run(case["id"]) is None
    assert not any(item["id"] == case["id"] for item in db.list_cases())


def test_latest_is_generation_time_and_explicit_runs_remain_accessible(case):
    layers = {"damage": {"type": "FeatureCollection", "features": []}}
    db.publish_run(case, make_run(case, "z-old", "2026-10-01T00:00:00Z"), layers, [])
    db.publish_run(case, make_run(case, "a-new", "2026-10-03T00:00:00Z"), layers, [])
    assert db.get_run(case["id"])["id"] == "a-new"
    assert db.get_layer(case["id"], "damage", "z-old")["run_id"] == "z-old"
    assert db.get_observations(case["id"], "a-new") == []
    assert db.get_layer(case["id"], "missing") is None
    assert db.get_run(case["id"], "missing") is None


def test_rejects_naive_run_timestamp_before_database_access(monkeypatch):
    def unexpected():
        pytest.fail("Invalid timestamps should not access PostgreSQL")
    monkeypatch.setattr(db, "connect", unexpected)
    case = {"id": "test"}
    with pytest.raises(ValueError, match="timezone"):
        db.publish_run(case, make_run(case, "v1", "2026-10-03T00:00:00"),
                       {"damage": {"type": "FeatureCollection", "features": []}}, [])


def test_latest_imagery_ignores_newer_analysis_and_pins_observations(case):
    layers = {"bridges": {"type": "FeatureCollection", "features": []}}
    first = make_run(case, "imagery-old", "2026-10-01T00:00:00Z")
    first["metadata"] = {"kind": "bridge_imagery", "imagery": {"name": "Older imagery"}}
    second = make_run(case, "imagery-new", "2026-10-02T00:00:00Z")
    second["metadata"] = {"kind": "bridge_imagery", "imagery": {"name": "Newer imagery"}}
    db.publish_run(case, first, layers, [{"id": "old-observation"}])
    db.publish_run(case, second, layers, [{"id": "new-observation"}])
    db.publish_run(case, make_run(case, "analysis-latest", "2026-10-03T00:00:00Z"), layers, [])
    selected = db.get_imagery(case["id"])
    assert selected["run_id"] == "imagery-new"
    assert selected["observations"] == [{"id": "new-observation"}]
    assert db.get_imagery(case["id"], "imagery-old")["observations"] == [{"id": "old-observation"}]
    assert db.get_imagery(case["id"], "analysis-latest") is None
    assert db.get_imagery(case["id"], "missing") is None


def test_access_replay_ignores_other_publications_and_is_immutable(case):
    layers = {"access_network": {"type": "FeatureCollection", "features": []}}
    record = make_run(case, "access-v1", "2026-10-01T00:00:00Z")
    record["metadata"] = {"kind": "access_replay", "access_replay": {
        "mode": "historical_replay", "frames": [{"date": "2021-11-15"}]}}
    db.publish_run(case, record, layers, [])
    db.publish_run(case, make_run(case, "analysis-newer", "2026-10-02T00:00:00Z"), layers, [])
    selected = db.get_access_replay(case["id"])
    assert selected["run_id"] == "access-v1"
    assert selected["frames"] == [{"date": "2021-11-15"}]
    assert db.get_access_replay(case["id"], "analysis-newer") is None
    assert db.get_access_replay(case["id"], "missing") is None
