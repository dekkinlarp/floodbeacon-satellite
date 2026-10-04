"""Synthetic scenarios verify decision semantics, not real-world accuracy."""

from copy import deepcopy
import json

import pytest

from floodbeacon.access import build_replay, evaluate_network


def observation(day, stage, discharge=10, **extra):
    return {
        "date": day,
        "stage_m": stage,
        "discharge_m3_s": discharge,
        "stage_quality": None,
        "discharge_quality": None,
        "available_at": None,
        **extra,
    }


def edge(edge_id, start, end, threshold=None, metric="stage_m"):
    return {
        "id": edge_id, "name": edge_id, "from": start, "to": end,
        "coordinates": [[-121, 50], [-120.9, 50.1]],
        "trigger": None if threshold is None else {
            "metric": metric, "threshold": threshold,
            "reason": "Synthetic test threshold, not an observed closure.",
        },
    }


def replay_input(observations=None, edges=None):
    return {
        "schema_version": 1,
        "case_id": "synthetic-access-test",
        "title": "Synthetic test network",
        "mode": "historical_replay",
        "station": {
            "id": "synthetic-station", "name": "Test gauge",
            "coordinate": [-121, 50], "stage_datum_note": "Local synthetic datum.",
        },
        "observations": observations or [
            observation("2021-11-13", 1),
            observation("2021-11-14", 2),
            observation("2021-11-15", 3),
        ],
        "network": {
            "nodes": [
                {"id": "base", "name": "Selected base", "coordinate": [-121, 50], "kind": "base"},
                {"id": "junction", "name": "Junction", "coordinate": [-120.95, 50.05], "kind": "junction"},
                {"id": "village", "name": "Village", "coordinate": [-120.9, 50.1], "kind": "community"},
            ],
            "edges": edges if edges is not None else [
                edge("approach", "base", "junction"),
                edge("crossing", "junction", "village", 3),
            ],
            "base_node_id": "base",
            "community_node_ids": ["village"],
            "note": "Selected bidirectional corridors; not a complete road network.",
        },
        "sources": [{"title": "Synthetic fixture"}],
        "assumptions": ["All observations and thresholds in this fixture are synthetic."],
    }


def community(frame):
    return frame["communities"][0]


def test_known_daily_loss_generates_traceable_earlier_visit():
    frames = build_replay(replay_input())["frames"]
    first = community(frames[0])
    assert first["status"] == "reachable"
    assert first["action"] == "consider_earlier_visit"
    assert first["first_loss_date"] == "2021-11-15"
    assert first["days_until_loss"] == 2
    assert first["affected_edge_ids"] == ["crossing"]
    assert "historical observations, not a forecast" in first["reason"]
    last = community(frames[-1])
    assert last["status"] == "isolated"
    assert last["action"] == "access_lost_in_scenario"
    assert last["days_until_loss"] == 0
    assert frames[-1]["edge_states"][1]["status"] == "scenario_unavailable"


def test_alternative_route_prevents_false_isolation_and_warning():
    data = replay_input()
    data["network"]["edges"].append(edge("alternative", "base", "village"))
    frames = build_replay(data)["frames"]
    assert community(frames[0])["action"] == "monitor"
    assert community(frames[0])["first_loss_date"] is None
    assert community(frames[-1])["status"] == "reachable"
    assert community(frames[-1])["affected_edge_ids"] == []


def test_unknown_alternative_does_not_certify_passability_or_isolation():
    data = replay_input([observation("2021-11-13", 4, discharge=None)])
    data["network"]["edges"].append(edge("alternative", "base", "village", 30, "discharge_m3_s"))
    frame = build_replay(data)["frames"][0]
    result = community(frame)
    assert result["status"] == "unknown"
    assert result["action"] == "verify_access"
    assert result["first_loss_date"] is None
    assert result["affected_edge_ids"] == ["alternative"]
    assert frame["edge_states"][-1]["status"] == "unknown"


def test_known_alternative_can_resolve_missing_metric_on_other_route():
    data = replay_input([observation("2021-11-13", None)])
    data["network"]["edges"].append(edge("alternative", "base", "village"))
    assert community(build_replay(data)["frames"][0])["status"] == "reachable"


def test_calendar_window_excludes_far_away_next_row():
    data = replay_input([
        observation("2021-11-13", 1),
        observation("2021-11-20", 4),
    ])
    frame = build_replay(data)["frames"][0]
    assert frame["outlook"] == []
    result = community(frame)
    assert result["action"] == "verify_access"
    assert result["first_loss_date"] is None
    assert "missing dates" in result["reason"]


def test_missing_day_does_not_erase_known_later_sample_but_onset_uncertain():
    data = replay_input([
        observation("2021-11-13", 1),
        observation("2021-11-15", 4),
    ])
    first = community(build_replay(data)["frames"][0])
    assert first["action"] == "consider_earlier_visit"
    assert first["days_until_loss"] == 2
    assert "not a precise onset date" in first["reason"]


def test_missing_future_metric_does_not_establish_loss_free_outlook():
    data = replay_input([
        observation("2021-11-13", 1),
        observation("2021-11-14", None),
        observation("2021-11-15", 2),
    ])
    first = community(build_replay(data)["frames"][0])
    assert first["status"] == "reachable"
    assert first["action"] == "verify_access"
    assert first["affected_edge_ids"] == ["crossing"]


def test_quality_availability_and_source_metadata_are_retained():
    data = replay_input()
    data["observations"][0]["stage_quality"] = "E: estimated"
    data["observations"][0]["available_at"] = "2022-01-01T00:00:00Z"
    original = deepcopy(data)
    catalog = build_replay(data)
    assert catalog["frames"][0]["observation"]["stage_quality"] == "E: estimated"
    assert catalog["frames"][0]["observation"]["available_at"] == "2022-01-01T00:00:00Z"
    assert catalog["sources"] == data["sources"]
    assert catalog["assumptions"] == data["assumptions"]
    json.dumps(catalog, allow_nan=False)
    catalog["network"]["nodes"][0]["name"] = "Changed"
    assert data == original


def test_recession_changes_scenario_without_claiming_actual_reopening():
    data = replay_input([
        observation("2021-11-13", 4),
        observation("2021-11-14", 1),
        observation("2021-11-15", 1),
        observation("2021-11-16", 1),
    ])
    frames = build_replay(data)["frames"]
    assert community(frames[0])["status"] == "isolated"
    assert community(frames[1])["status"] == "reachable"
    assert community(frames[1])["action"] == "monitor"
    assert "reopening are unverified" in frames[1]["edge_states"][1]["reason"]


def test_edges_are_bidirectional_and_observations_are_sorted():
    data = replay_input()
    data["observations"].reverse()
    for item in data["network"]["edges"]:
        item["from"], item["to"] = item["to"], item["from"]
    first = build_replay(data)["frames"][0]
    assert first["date"] == "2021-11-13"
    assert community(first)["status"] == "reachable"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "1"])
def test_invalid_metrics_rejected(value):
    data = replay_input()
    data["observations"][0]["stage_m"] = value
    with pytest.raises(ValueError, match="stage_m"):
        build_replay(data)


def test_negative_datum_stage_valid_but_negative_discharge_invalid():
    data = replay_input([observation("2021-11-13", -0.5)])
    data["network"]["edges"][1]["trigger"]["threshold"] = -0.2
    assert community(build_replay(data)["frames"][0])["status"] == "reachable"
    data["observations"][0]["discharge_m3_s"] = -1
    with pytest.raises(ValueError, match="discharge_m3_s"):
        build_replay(data)


def test_reusable_network_rules_are_independent_of_replay_mode():
    data = replay_input()
    before = deepcopy(data)
    score = evaluate_network(data["network"], observation("2030-01-01", 4))
    assert score["communities"][0]["status"] == "isolated"
    assert score["communities"][0]["affected_edge_ids"] == ["crossing"]
    assert score["edge_states"][1]["status"] == "scenario_unavailable"
    assert "mode" not in score
    assert "first_loss_date" not in score["communities"][0]
    assert data == before


@pytest.mark.parametrize("mutation, message", [
    (lambda data: data["observations"].append(data["observations"][0]), "dates must be unique"),
    (lambda data: data["observations"][0].update(date="20211113"), "YYYY-MM-DD"),
    (lambda data: data["network"]["edges"][0].update(to="missing"), "endpoints"),
    (lambda data: data["network"]["nodes"][0].update(coordinate=[50, 181]), "WGS84"),
    (lambda data: data["network"]["edges"][1]["trigger"].update(threshold=True), "threshold"),
    (lambda data: data["network"]["edges"].append(data["network"]["edges"][0]), "edge IDs"),
    (lambda data: data["network"].update(base_node_id="village"), "base node"),
    (lambda data: data["network"].update(community_node_ids=["base"]), "community nodes"),
    (lambda data: data["observations"][0].update(available_at="2021-11-13"), "timezone"),
])
def test_invalid_graph_or_times_rejected(mutation, message):
    data = replay_input()
    mutation(data)
    with pytest.raises(ValueError, match=message):
        build_replay(data)
