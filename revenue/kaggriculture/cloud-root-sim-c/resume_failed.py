"""Create an explicit continuation job without hiding prior failed attempts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--replay-suffix", default="replay1")
    args = parser.parse_args()

    config_bytes = args.config.read_bytes()
    state_bytes = args.state.read_bytes()
    config = json.loads(config_bytes)
    state = json.loads(state_bytes)
    by_id = {row["id"]: row for row in state["finished_cells"]}
    completed = [cell["id"] for cell in config["cells"]
                 if by_id.get(cell["id"], {}).get("status") == "complete"]
    failed = [cell["id"] for cell in config["cells"]
              if cell["id"] in by_id and by_id[cell["id"]].get("status") != "complete"]
    unattempted = [cell["id"] for cell in config["cells"] if cell["id"] not in by_id]
    replay_map = {}
    continuation = []
    for cell in config["cells"]:
        if cell["id"] in completed:
            continue
        item = dict(cell)
        if cell["id"] in failed:
            item["id"] = cell["id"] + "-" + args.replay_suffix
            replay_map[cell["id"]] = item["id"]
        continuation.append(item)
    config.update(cells=continuation, output=str(args.output.resolve()), jobs=args.jobs)
    payload = (json.dumps(config, indent=2) + "\n").encode()
    args.output_config.parent.mkdir(parents=True, exist_ok=True)
    args.output_config.write_bytes(payload)
    receipt = {
        "source_config": str(args.config.resolve()),
        "source_config_sha256": digest(config_bytes),
        "source_state": str(args.state.resolve()),
        "source_state_sha256": digest(state_bytes),
        "completed_not_repeated": completed,
        "failed_preserved_and_replayed": replay_map,
        "unattempted_scheduled": unattempted,
        "continuation_config": str(args.output_config.resolve()),
        "continuation_config_sha256": digest(payload),
        "jobs": args.jobs,
    }
    receipt_path = args.output_config.with_suffix(".continuity.json")
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"cells": len(continuation), "completed": len(completed),
                      "failed_replays": len(failed), "unattempted": len(unattempted),
                      "config_sha256": digest(payload), "receipt": str(receipt_path)}, indent=2))


if __name__ == "__main__":
    main()
