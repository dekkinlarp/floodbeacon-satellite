"""Prepare an illustrative access replay from historical daily gauge observations.

Future observations are intentionally hindsight inputs, never archived forecasts.
Thresholds describe an assumed scenario, not observed road closures or structural
failure. Preparation is separate from serving the completed replay catalog.
"""

from collections import deque
from copy import deepcopy
from datetime import date, datetime, timedelta
from importlib.resources import files
import json
import math
from typing import Any


LOOKAHEAD_DAYS = 2
METRICS = {"stage_m", "discharge_m3_s"}


def _text(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")


def _number(value: Any, label: str, *, nonnegative: bool = True) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    if not math.isfinite(value) or (nonnegative and value < 0):
        raise ValueError(f"{label} must be finite and nonnegative")


def _coordinate(value: Any, label: str) -> None:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{label} must be [longitude, latitude]")
    for number in value:
        _number(number, label, nonnegative=False)
    if not -180 <= value[0] <= 180 or not -90 <= value[1] <= 90:
        raise ValueError(f"{label} is outside WGS84 coordinate bounds")


def _day(value: Any) -> date:
    if not isinstance(value, str):
        raise ValueError("observation date must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("observation date must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise ValueError("observation date must be YYYY-MM-DD")
    return parsed


def _validate_observation(observation: dict) -> date:
    if not isinstance(observation, dict):
        raise ValueError("each observation must be an object")
    day = _day(observation.get("date"))
    for metric in METRICS:
        if observation.get(metric) is not None:
            # A gauge datum can produce negative stages; discharge cannot be negative.
            _number(observation[metric], metric, nonnegative=metric == "discharge_m3_s")
    for key in ("stage_quality", "discharge_quality"):
        if observation.get(key) is not None:
            _text(observation[key], key)
    availability = observation.get("available_at")
    if availability is not None:
        if not isinstance(availability, str):
            raise ValueError("available_at must be an ISO timestamp or null")
        try:
            parsed = datetime.fromisoformat(availability)
        except ValueError as exc:
            raise ValueError("available_at must be an ISO timestamp or null") from exc
        if parsed.tzinfo is None:
            raise ValueError("available_at must include a timezone")
    return day


def _validate_network(network: dict) -> None:
    if not isinstance(network, dict):
        raise ValueError("network must be an object")
    _text(network.get("note"), "network.note")
    nodes, edges = network.get("nodes"), network.get("edges")
    if not isinstance(nodes, list) or not nodes or not isinstance(edges, list):
        raise ValueError("network requires nodes and edges lists")
    node_ids = set()
    kinds = {}
    for node in nodes:
        if not isinstance(node, dict):
            raise ValueError("each node must be an object")
        for key in ("id", "name"):
            _text(node.get(key), f"node.{key}")
        if node["id"] in node_ids:
            raise ValueError("node IDs must be unique")
        node_ids.add(node["id"])
        kinds[node["id"]] = node.get("kind")
        if node.get("kind") not in {"base", "junction", "community"}:
            raise ValueError("node kind must be base, junction or community")
        _coordinate(node.get("coordinate"), "node.coordinate")
    base = network.get("base_node_id")
    if not isinstance(base, str) or kinds.get(base) != "base":
        raise ValueError("base_node_id must reference a base node")
    communities = network.get("community_node_ids")
    if not isinstance(communities, list) or not communities:
        raise ValueError("community_node_ids must be a nonempty list")
    if any(not isinstance(item, str) for item in communities):
        raise ValueError("community_node_ids must contain strings")
    if len(set(communities)) != len(communities):
        raise ValueError("community_node_ids must be unique")
    if any(kinds.get(item) != "community" for item in communities):
        raise ValueError("community_node_ids must reference community nodes")
    edge_ids = set()
    for edge in edges:
        if not isinstance(edge, dict):
            raise ValueError("each edge must be an object")
        for key in ("id", "name", "from", "to"):
            _text(edge.get(key), f"edge.{key}")
        if edge["id"] in edge_ids:
            raise ValueError("edge IDs must be unique")
        edge_ids.add(edge["id"])
        if edge["from"] not in node_ids or edge["to"] not in node_ids:
            raise ValueError("edge endpoints must reference network nodes")
        if edge["from"] == edge["to"]:
            raise ValueError("edge endpoints must be different nodes")
        coordinates = edge.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            raise ValueError("edge coordinates require at least two points")
        for coordinate in coordinates:
            _coordinate(coordinate, "edge.coordinates")
        trigger = edge.get("trigger")
        if trigger is not None:
            if not isinstance(trigger, dict) or trigger.get("metric") not in METRICS:
                raise ValueError("trigger metric must be stage_m or discharge_m3_s")
            _number(trigger.get("threshold"), "trigger.threshold", nonnegative=trigger["metric"] == "discharge_m3_s")
            _text(trigger.get("reason"), "trigger.reason")


def _validate(data: dict) -> None:
    if not isinstance(data, dict):
        raise ValueError("replay input must be an object")
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("replay schema_version must be 1")
    if data.get("mode") != "historical_replay":
        raise ValueError("replay mode must be historical_replay")
    for key in ("case_id", "title"):
        _text(data.get(key), key)
    station = data.get("station")
    if not isinstance(station, dict):
        raise ValueError("station must be an object")
    for key in ("id", "name", "stage_datum_note"):
        _text(station.get(key), f"station.{key}")
    _coordinate(station.get("coordinate"), "station.coordinate")

    observations = data.get("observations")
    if not isinstance(observations, list) or not observations:
        raise ValueError("observations must be a nonempty list")
    dates = set()
    for observation in observations:
        day = _validate_observation(observation)
        if day in dates:
            raise ValueError("observation dates must be unique")
        dates.add(day)
    _validate_network(data.get("network"))
    sources, assumptions = data.get("sources"), data.get("assumptions")
    if not isinstance(sources, list) or not all(isinstance(s, dict) for s in sources):
        raise ValueError("sources must be a list of provenance objects")
    if not isinstance(assumptions, list):
        raise ValueError("assumptions must be a list")
    for assumption in assumptions:
        _text(assumption, "assumption")


def _edge_states(network: dict, observation: dict) -> list[dict]:
    states = []
    for edge in network["edges"]:
        trigger = edge.get("trigger")
        state = {"edge_id": edge["id"], "metric": None, "value": None, "threshold": None}
        if trigger is None:
            state.update(
                status="modeled_available",
                reason="Baseline corridor assumed available in this illustrative network; actual passability is unverified.",
            )
        else:
            metric = trigger["metric"]
            value, threshold = observation.get(metric), trigger["threshold"]
            state.update(metric=metric, value=value, threshold=threshold)
            if value is None:
                state.update(status="unknown", reason=f"Missing {metric}; cannot evaluate the assumed threshold. {trigger['reason']}")
            elif value >= threshold:
                state.update(status="scenario_unavailable", reason=f"Daily {metric} {value:g} meets the assumed threshold {threshold:g}. {trigger['reason']}")
            else:
                state.update(
                    status="modeled_available",
                    reason=f"Daily {metric} {value:g} is below the assumed threshold {threshold:g}; actual passability and reopening are unverified. {trigger['reason']}",
                )
        states.append(state)
    return states


def _reachable(network: dict, states: dict[str, str], start: str, *, allow_unknown: bool) -> set[str]:
    adjacency = {node["id"]: [] for node in network["nodes"]}
    for edge in network["edges"]:
        status = states[edge["id"]]
        if status == "modeled_available" or (allow_unknown and status == "unknown"):
            adjacency[edge["from"]].append(edge["to"])
            adjacency[edge["to"]].append(edge["from"])
    reached = {start}
    queue = deque([start])
    while queue:
        for neighbor in adjacency[queue.popleft()]:
            if neighbor not in reached:
                reached.add(neighbor)
                queue.append(neighbor)
    return reached


def _access_states(network: dict, edge_states: list[dict]) -> dict[str, dict]:
    states = {state["edge_id"]: state["status"] for state in edge_states}
    base = network["base_node_id"]
    pessimistic = _reachable(network, states, base, allow_unknown=False)
    optimistic = _reachable(network, states, base, allow_unknown=True)
    result = {}
    for community in network["community_node_ids"]:
        if community in pessimistic:
            result[community] = {"status": "reachable", "affected_edge_ids": []}
            continue
        isolated = community not in optimistic
        component = _reachable(network, states, community, allow_unknown=isolated)
        # Report the unavailable/unknown boundary of this community's component,
        # rather than closures elsewhere that do not affect its access.
        affected = [
            edge["id"] for edge in network["edges"]
            if ((edge["from"] in component) != (edge["to"] in component))
            and states[edge["id"]] == ("scenario_unavailable" if isolated else "unknown")
        ]
        result[community] = {
            "status": "isolated" if isolated else "unknown",
            "affected_edge_ids": affected,
        }
    return result


def evaluate_network(network: dict, observation: dict) -> dict:
    """Score one dated water-condition sample independently of replay/hindsight.

    A future adapter can supply forecast samples to these same rules after
    recording issue/valid times and gauge/threshold compatibility. This function
    itself does not forecast, model hydraulics, or assign a rescue priority.
    """
    _validate_network(network)
    _validate_observation(observation)
    states = _edge_states(network, observation)
    access = _access_states(network, states)
    names = {node["id"]: node["name"] for node in network["nodes"]}
    return {
        "edge_states": states,
        "communities": [
            {"node_id": node_id, "name": names[node_id], **access[node_id]}
            for node_id in network["community_node_ids"]
        ],
    }


def build_replay(input_dict: dict) -> dict:
    """Return a validated, independent catalog; never modify the input object.

    Outlooks use the next two *calendar* days. Missing dates and missing metrics
    preserve uncertainty. ``first_loss_date`` is the first sampled scenario loss
    in the current outlook, not an exact closure/failure timestamp.
    """
    _validate(input_dict)
    data = deepcopy(input_dict)
    network = data["network"]
    observations = sorted(data["observations"], key=lambda item: item["date"])
    by_date = {_day(observation["date"]): observation for observation in observations}
    edge_states = {day: _edge_states(network, observation) for day, observation in by_date.items()}
    access = {day: _access_states(network, states) for day, states in edge_states.items()}
    names = {node["id"]: node["name"] for node in network["nodes"]}
    frames = []
    for day, observation in by_date.items():
        future_days = [day + timedelta(days=offset) for offset in range(1, LOOKAHEAD_DAYS + 1)]
        outlook = [by_date[future] for future in future_days if future in by_date]
        communities = []
        for node_id in network["community_node_ids"]:
            current = access[day][node_id]
            window = [day, *future_days]
            loss_day = next((sample for sample in window if sample in access and access[sample][node_id]["status"] == "isolated"), None)
            uncertain_outlook = any(sample not in access or access[sample][node_id]["status"] == "unknown" for sample in future_days)
            affected = current["affected_edge_ids"]
            if current["status"] == "isolated":
                action = "access_lost_in_scenario"
                reason = "No route to the selected base remains in the illustrative scenario, even allowing unknown edges. This is not a verified closure or complete-network isolation."
            elif current["status"] == "unknown":
                action = "verify_access"
                reason = "Connection to the selected base depends on edges with missing observations. Verify access before planning travel."
            elif loss_day is not None:
                action = "consider_earlier_visit"
                affected = access[loss_day][node_id]["affected_edge_ids"]
                reason = f"A modeled route exists today, but none remains on the {loss_day.isoformat()} daily sample under the assumed thresholds. Consider an earlier visit or pre-positioning; this outlook uses later historical observations, not a forecast."
                if uncertain_outlook:
                    reason += " Missing outlook information means the first sampled loss is not a precise onset date."
            elif uncertain_outlook:
                action = "verify_access"
                reason = "A modeled route exists today, but missing dates or metrics leave part of the next two calendar days unknown. Verify access; no loss-free outlook is established."
                affected = sorted({edge_id for sample in future_days if sample in access for edge_id in access[sample][node_id]["affected_edge_ids"]})
            else:
                action = "monitor"
                reason = "A route to the selected base remains in all available daily scenario samples over the next two calendar days. Actual passability, conditions between samples and reopening are unverified."
            communities.append({
                "node_id": node_id,
                "name": names[node_id],
                "status": current["status"],
                "first_loss_date": loss_day.isoformat() if loss_day else None,
                "days_until_loss": (loss_day - day).days if loss_day else None,
                "action": action,
                "reason": reason,
                "affected_edge_ids": affected,
            })
        frames.append({
            "date": day.isoformat(),
            "observation": observation,
            "outlook": outlook,
            "edge_states": edge_states[day],
            "communities": communities,
        })
    return {
        "schema_version": 1,
        "case_id": data["case_id"],
        "title": data["title"],
        "mode": data["mode"],
        "station": data["station"],
        "lookahead_days": LOOKAHEAD_DAYS,
        "network": network,
        "sources": data["sources"],
        "assumptions": data["assumptions"],
        "frames": frames,
    }


def load_bundled_replay() -> dict:
    """Build the package's replay for preparation/publication, not GET handlers."""
    source = files("floodbeacon").joinpath("static/access-replay/input.json")
    return build_replay(json.loads(source.read_text(encoding="utf-8")))
