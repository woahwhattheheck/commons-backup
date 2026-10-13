"""Compose ROOT-SIM-A configs for the existing full-trajectory league runner."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


CONTROLLERS = {
    "current499989ab": (
        "current", "499989ab907331d4c0c990af2ab3703e6731dc83078964aca8563ea5a069e48e"
    ),
    "historical7b58": (
        "historical-v1", "7b58fa06da778b1519b81d509d28dff3481b3bbcc7a2d656e8bdfe4a22540524"
    ),
}
OPPONENTS = {
    "arlene": "cloud-execution-lab/reference/next-panel/vendor/arlene.py::agent",
    "euler": "20260907-offline-agent/main.py::agent",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def cells(seeds: range, opponents: tuple[str, ...], identity: str = "") -> list[dict]:
    return [
        {"id": f"{opponent}-{seed}-s{seat}{identity}", "seed": seed, "seat": seat,
         "opponent": opponent}
        for seed in seeds for opponent in opponents for seat in (0, 1)
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--job-root", type=Path, required=True)
    parser.add_argument("--phase", choices=("calibration", "setup-fixed-apex", "calibration-rest", "remaining", "low-concurrency-fixed"), required=True)
    parser.add_argument("--jobs", type=int, required=True)
    args = parser.parse_args()
    repo, root = args.repo.resolve(), args.job_root.resolve()
    if args.phase in {"calibration", "setup-fixed-apex"}:
        seed_range, opponents = range(1909081401, 1909081403), tuple(("apex", *OPPONENTS)) if args.phase == "calibration" else ("apex",)
    elif args.phase == "calibration-rest":
        seed_range, opponents = range(1909081402, 1909081403), tuple(OPPONENTS)
    elif args.phase == "remaining":
        seed_range, opponents = range(1909081403, 1909081433), tuple(("apex", *OPPONENTS))
    else:
        seed_range, opponents = range(1909081426, 1909081427), ("arlene", "euler")
    archive_dir = repo / "revenue/kaggriculture/cloud-execution-lab/exports"
    archive_paths = {
        "current499989ab": archive_dir / "titan-current.tar.gz",
        "historical7b58": archive_dir / "historical/titan-7b58fa06da778b1519b81d509d28dff3481b3bbcc7a2d656e8bdfe4a22540524.tar.gz",
    }
    for label, (_, expected) in CONTROLLERS.items():
        actual = sha256(archive_paths[label])
        if actual != expected:
            raise SystemExit(f"{label} archive moved: {actual}")
    common = {
        "opponents": {
            "apex": str(root / "opponents/apex/main.py") + "::agent",
            **{label: str(repo / "revenue/kaggriculture" / rel)
               for label, rel in OPPONENTS.items()},
        },
        "engine": str(root / "engine"),
        "loader": str(repo / "revenue/kaggriculture/20260907-offline-agent/evaluate.py"),
        "evaluator": str(repo / "revenue/kaggriculture/cloud-eval/evaluate.py"),
        "rng_seed": 20260907,
        "action_timeout": 1.0,
        "startup_timeout": 10.0,
        "game_timeout": 120.0,
        "jobs": args.jobs,
    }
    for label, (directory, _) in CONTROLLERS.items():
        config = {
            **common,
            "candidate": str(root / "agents" / directory / "main.py") + "::agent",
            "cells": cells(seed_range, opponents,
                           "-setup-fixed" if args.phase == "setup-fixed-apex"
                           else "-low-concurrency-fixed" if args.phase == "low-concurrency-fixed" else ""),
            "output": str(root / "results" / args.phase / label),
        }
        path = root / "configs" / f"{args.phase}-{label}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, indent=2) + "\n")


if __name__ == "__main__":
    main()
