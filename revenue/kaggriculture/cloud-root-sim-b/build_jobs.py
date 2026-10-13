#!/usr/bin/env python3
"""Build immutable job files for ROOT-SIM-B using the existing league driver."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


CONTROLLERS = {
    "current": "/tmp/titan-root-sim-b/current/main.py::agent",
    "historical": "/tmp/titan-root-sim-b/historical/main.py::agent",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--first-seed", type=int, default=1909081503)
    parser.add_argument("--last-seed", type=int, default=1909081532)
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()

    repo = args.repo.resolve()
    output = args.output.resolve()
    jobs_dir = output / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    opponents = {
        "apex": str(repo / "revenue/kaggriculture/cloud-execution-lab/reference/apex/main.py") + "::agent",
        "arlene": str(repo / "revenue/kaggriculture/cloud-execution-lab/reference/next-panel/vendor/arlene.py") + "::agent",
        "euler": str(repo / "revenue/kaggriculture/20260907-offline-agent/main.py") + "::agent",
    }
    common = {
        "opponents": opponents,
        "engine": "/tmp/kag-engine",
        "loader": str(repo / "revenue/kaggriculture/20260907-offline-agent/evaluate.py"),
        "evaluator": str(repo / "revenue/kaggriculture/cloud-eval/evaluate.py"),
        "rng_seed": 20260907,
        "action_timeout": 1.0,
        "startup_timeout": 10.0,
        "game_timeout": 120.0,
        "jobs": args.jobs,
    }
    manifests = {}
    for label, candidate in CONTROLLERS.items():
        cells = [
            {
                "id": f"{label}-{opponent}-{seed}-s{seat}",
                "seed": seed,
                "seat": seat,
                "opponent": opponent,
            }
            for seed in range(args.first_seed, args.last_seed + 1)
            for opponent in opponents
            for seat in (0, 1)
        ]
        job = {
            "candidate": candidate,
            **common,
            "cells": cells,
            "output": str(output / f"full-{label}"),
        }
        path = jobs_dir / f"{label}.json"
        path.write_text(json.dumps(job, indent=2) + "\n")
        manifests[label] = {
            "job": str(path),
            "sha256": sha256(path),
            "cells": len(cells),
            "candidate": candidate,
        }
    (output / "JOB-MANIFEST.json").write_text(json.dumps({
        "operation": "titan-root-sim-b-20260908-1345",
        "first_seed": args.first_seed,
        "last_seed": args.last_seed,
        "jobs_per_controller": args.jobs,
        "controllers_launched_concurrently": 2,
        "episode_steps": 720,
        "jobs": manifests,
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
