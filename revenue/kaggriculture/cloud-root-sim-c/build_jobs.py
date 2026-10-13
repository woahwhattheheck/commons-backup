"""Freeze the predeclared ROOT-SIM-C full-game league jobs.

This is a thin configuration builder for the existing cloud-ultra-league driver.
It does not implement or modify game semantics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SEEDS = list(range(1909081601, 1909081633))
CONTROLLERS = ("current", "historical_v1")
OPPONENTS = ("apex", "arlene", "euler")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def files_under(root: Path):
    return sorted(path for path in root.rglob("*") if path.is_file())


def cells(seeds, controller, run_tag):
    # Interleave opponents so a bounded worker wave does not start several
    # Apex compilation/loading cells simultaneously.
    return [
        {
            "id": f"{run_tag}-{controller}-{opponent}-{seed}-s{seat}",
            "seed": seed,
            "seat": seat,
            "opponent": opponent,
        }
        for seed in seeds
        for seat in (0, 1)
        for opponent in OPPONENTS
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--run-identity", default="titan-root-sim-c-20260908-1345")
    parser.add_argument("--run-tag", default="root-sim-c")
    args = parser.parse_args()

    input_root = args.input_root.resolve()
    output_root = args.output_root.resolve()
    repo = args.repo.resolve()
    engine = args.engine.resolve()
    candidates = {
        "current": input_root / "current" / "main.py",
        "historical_v1": input_root / "historical_v1" / "main.py",
    }
    opponents = {
        "apex": str(input_root / "opponents" / "apex" / "main.py") + "::agent",
        "arlene": str(input_root / "opponents" / "next-panel" / "vendor" / "arlene.py") + "::agent",
        "euler": str(input_root / "opponents" / "euler" / "main.py") + "::agent",
    }
    loader = repo / "revenue/kaggriculture/20260907-offline-agent/evaluate.py"
    evaluator = repo / "revenue/kaggriculture/cloud-eval/evaluate.py"

    required = [*candidates.values(), *(Path(x.partition("::")[0]) for x in opponents.values()),
                loader, evaluator, *(engine / name for name in
                    ("kaggriculture.py", "kaggriculture.json", "utils.py"))]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("Missing frozen inputs: " + ", ".join(missing))
    if args.jobs < 1:
        raise SystemExit("jobs must be positive")

    output_root.mkdir(parents=True, exist_ok=True)
    config_root = output_root / "configs"
    config_root.mkdir(exist_ok=False)
    common = {
        "opponents": opponents,
        "engine": str(engine),
        "loader": str(loader),
        "evaluator": str(evaluator),
        "rng_seed": 20260908,
        "action_timeout": 1.0,
        "startup_timeout": 10.0,
        "game_timeout": 120.0,
        "episode_steps": 720,
        "jobs": args.jobs,
    }
    written = []
    for controller in CONTROLLERS:
        for phase, seeds in (("calibration", SEEDS[:2]), ("remaining", SEEDS[2:])):
            config = {
                **common,
                "candidate": str(candidates[controller]) + "::agent",
                "cells": cells(seeds, controller, args.run_tag),
                "output": str(output_root / "raw" / phase / controller),
            }
            path = config_root / f"{phase}-{controller}.json"
            path.write_text(json.dumps(config, indent=2) + "\n")
            written.append(path)

    frozen_files = files_under(input_root) + files_under(engine) + [loader, evaluator]
    manifest = {
        "operation": args.run_identity,
        "repository_commit": "9ab11ca5a5d130e20ba1a87d339a1044c27fa507",
        "seeds": SEEDS,
        "controllers": list(CONTROLLERS),
        "opponents": list(OPPONENTS),
        "seats": [0, 1],
        "episode_steps": 720,
        "scheduled_games": len(SEEDS) * len(CONTROLLERS) * len(OPPONENTS) * 2,
        "files": {str(path): {"bytes": path.stat().st_size, "sha256": sha256(path)}
                  for path in frozen_files},
        "configs": {str(path): sha256(path) for path in written},
    }
    manifest_path = output_root / "FREEZE.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"freeze": str(manifest_path), "freeze_sha256": sha256(manifest_path),
                      "scheduled_games": manifest["scheduled_games"],
                      "configs": [str(path) for path in written]}, indent=2))


if __name__ == "__main__":
    main()
