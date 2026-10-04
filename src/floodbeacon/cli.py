"""Reproducible batch commands. GET endpoints never launch processing."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from floodbeacon import db


def main():
    parser = argparse.ArgumentParser(prog="floodbeacon")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db")
    sub.add_parser("publish-imagery", help="Publish the bundled bridge imagery catalog to PostgreSQL")
    access = sub.add_parser("prepare-access-replay", help="Export the bundled historical decision replay")
    access.add_argument("--output", type=Path, default=Path(__file__).with_name("static") / "access-replay/replay.json")
    sub.add_parser("publish-access-replay", help="Publish the prepared replay atomically to PostgreSQL")
    train = sub.add_parser("train")
    train.add_argument("--data-dir", type=Path, default=Path("data"))
    train.add_argument("--chips-per-event", type=int, default=3)
    batch = sub.add_parser("batch")
    batch.add_argument("--case", choices=["ahr-2021", "bc-2021", "all"], default="all")
    batch.add_argument("--data-dir", type=Path, default=Path("data"))
    batch.add_argument("--model", type=Path, required=True)
    preview = sub.add_parser("preview")
    preview.add_argument("--output-dir", type=Path, default=Path("artifacts"))
    args = parser.parse_args()
    if args.command == "init-db":
        db.init_db()
        print("Database schema initialized")
    elif args.command == "publish-imagery":
        from floodbeacon.imagery import publish_catalog
        print(json.dumps(publish_catalog(), indent=2))
    elif args.command == "prepare-access-replay":
        from floodbeacon.access_publication import export_replay
        print(export_replay(args.output).resolve())
    elif args.command == "publish-access-replay":
        from floodbeacon.access_publication import publish_replay
        print(json.dumps(publish_replay(), indent=2))
    elif args.command == "train":
        from floodbeacon.ml import train_model
        path, details = train_model(args.data_dir, args.chips_per_event)
        print(json.dumps({"model": str(path), "evaluation": details}, indent=2))
    elif args.command == "preview":
        from floodbeacon.preview import export_preview
        print(export_preview(args.output_dir).resolve())
    else:
        from floodbeacon.cases import CASES
        from floodbeacon.exposure import exposure_layers
        from floodbeacon.evaluation import compare_water_reference
        from floodbeacon.satellite import SCENES, infer_case
        from floodbeacon.sources import ingest_case
        selected = CASES.keys() if args.case == "all" else [args.case]
        for case_id in selected:
            case = CASES[case_id]
            print(f"Ingesting {case_id}", flush=True)
            layers, observations, provenance = ingest_case(case_id, args.data_dir)
            print(f"Running satellite inference for {case_id}", flush=True)
            satellite_layers, scene_provenance, metrics = infer_case(case, args.model, args.data_dir / "satellite")
            layers.update(satellite_layers)
            comparison = compare_water_reference(
                layers["modeled_new_water"], layers.get("agency_flood_reference"),
                layers["valid_coverage"], SCENES[case_id][2],
                modeled_observed_at=scene_provenance[1]["observed_at"],
                reference_observed_at=(layers.get("agency_flood_reference", {}).get("features") or [{}])[0].get("properties", {}).get("observed_at"),
            )
            if case_id == "ahr-2021":
                comparison["reference_semantics"] = "Agency observedEventA union includes flood traces and flooded area; it is not a same-time water truth mask."
            layers.update(exposure_layers(
                layers.get("assets", {"type": "FeatureCollection", "features": []}),
                layers["modeled_new_water"], layers["valid_coverage"], SCENES[case_id][2],
                exposure_observed_at=scene_provenance[1]["observed_at"],
            ))
            run = {
                "id": f"{case_id}-{uuid4().hex[:12]}", "case_id": case_id,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "metadata": {
                    "mode": "retrospective", "operational_status": "experimental research POC",
                    "provenance": provenance + scene_provenance,
                    "agency_comparison": comparison,
                    "model": str(args.model), "satellite": metrics,
                    "model_evaluation": json.loads(args.model.with_name("metadata.json").read_text()) if args.model.with_name("metadata.json").exists() else None,
                    "layer_names": list(layers), "scenarios": {
                        "type": "hypothetical horizontal footprint expansion",
                        "distances_m": [50,100], "forecast_horizon_hours": None,
                        "likelihood": None,
                    },
                    "limitations": metrics["limitations"] + [
                        "Current BC inventory is map context, not an event-time road network.",
                        "Reported agency damage and classifier flood exposure are independent fields.",
                        "Ahr SAR July15 and CEMS July18 cannot establish same-time detector accuracy.",
                        "Sen1Floods11 input/model redistribution rights remain unresolved; local research only.",
                    ],
                },
            }
            db.publish_run(case, run, layers, observations)
            print(f"Published completed run {run['id']}", flush=True)


if __name__ == "__main__":
    main()
