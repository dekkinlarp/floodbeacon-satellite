"""Prepare portable replay artifacts and publish completed runs, outside GET."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from floodbeacon import db
from floodbeacon.cases import CASES

REPLAY_FILE = Path(__file__).with_name("static") / "access-replay/replay.json"


def export_replay(output: Path = REPLAY_FILE) -> Path:
    from floodbeacon.access import load_bundled_replay

    replay = load_bundled_replay()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(replay, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    return output


def publish_replay() -> dict:
    """Publish checked-in results and graph in one transaction; retry is idempotent."""
    from floodbeacon.access import load_bundled_replay

    payload = REPLAY_FILE.read_bytes()
    replay = json.loads(payload)
    if replay != load_bundled_replay():
        raise ValueError("Replay export is stale; run floodbeacon prepare-access-replay before publishing")
    case_id = replay["case_id"]
    checksum = hashlib.sha256(payload).hexdigest()
    run_id = f"{case_id}-access-{checksum[:16]}"
    previous = db.get_access_replay(case_id, run_id)
    if previous is not None:
        return {"run_id": run_id, "status": "already_published", "sha256": checksum}
    network = replay["network"]
    features = [{"type": "Feature", "id": edge["id"],
                 "geometry": {"type": "LineString", "coordinates": edge["coordinates"]},
                 "properties": {key: value for key, value in edge.items() if key != "coordinates"}}
                for edge in network["edges"]]
    run = {"id": run_id, "case_id": case_id,
           "generated_at": datetime.now(timezone.utc).isoformat(),
           "metadata": {"kind": "access_replay", "mode": "historical_replay",
                        "access_replay": replay, "sha256": checksum,
                        "provenance": replay["sources"]}}
    case = {**CASES["bc-2021"], "id": case_id,
            "name": "Merritt historical access replay — illustrative planning scenario",
            "description": "Real Coldwater gauge observations drive hypothetical thresholds and a schematic access network; not reported historical closures."}
    db.publish_run(case, run,
                   {"access_network": {"type": "FeatureCollection", "features": features}},
                   [frame["observation"] for frame in replay["frames"]])
    return {"run_id": run_id, "status": "published", "sha256": checksum}
