#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compare two immutable TITAN archives with the pinned offline interpreter.

The runner extracts both archives into fresh temporary directories, verifies
archive identities and member safety, runs both candidates against one exact
packaged frozen controller on the same seeds and seats, and requires exact
score and full trace equality. It performs no network access or Kaggle write.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
from typing import Any

CURRENT_SHA = "501695d66c2642d452180b2f129d181ba0ede02647b70ddd74ebd82e3762011c"
PRIOR_SHA = "26e19f9abe986ab93873ff993cea38042921d685f099d65a96fd5edc795a43b2"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_seeds(raw: str) -> list[int]:
    try:
        seeds = [int(item.strip()) for item in raw.split(",") if item.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("seeds must be comma-separated integers") from exc
    if not seeds or len(seeds) != len(set(seeds)):
        raise argparse.ArgumentTypeError("seeds must be nonempty and distinct")
    return seeds


def safe_extract(archive: Path, destination: Path) -> dict[str, tuple[int, str]]:
    inventory: dict[str, tuple[int, str]] = {}
    with tarfile.open(archive, "r:gz") as package:
        members = package.getmembers()
        for member in members:
            relative = Path(member.name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"unsafe archive member path: {member.name}")
            if not member.isfile():
                raise ValueError(f"archive member is not a regular file: {member.name}")
        try:
            package.extractall(destination, filter="data")
        except TypeError:  # Python before tarfile extraction filters.
            package.extractall(destination)
    for path in sorted(destination.rglob("*")):
        if path.is_file():
            inventory[str(path.relative_to(destination))] = (path.stat().st_size, sha256(path))
    return inventory


def run_arm(
    *,
    label: str,
    candidate_root: Path,
    common_root: Path,
    seeds: list[int],
    rng_seed: int,
    output_dir: Path,
    action_timeout: float,
    startup_timeout: float,
    game_timeout: float,
) -> tuple[dict[str, Any], dict[str, str]]:
    evaluator = common_root / "checks/reference/evaluator/evaluate.py"
    engine = common_root / "checks/reference/engine"
    loader = common_root / "checks/reference/evaluator/loader.py"
    opponent = common_root / "frozen_selected.py"
    for path in (evaluator, engine, loader, opponent, candidate_root / "main.py"):
        if not path.exists():
            raise FileNotFoundError(path)
    report_path = output_dir / f"{label}.json"
    log_path = output_dir / f"{label}.log"
    command = [
        sys.executable,
        "-B",
        str(evaluator),
        "--engine-dir",
        str(engine),
        "--loader",
        str(loader),
        "--candidate",
        str(candidate_root / "main.py") + "::agent",
        "--opponent",
        "frozen=" + str(opponent) + "::agent",
        "--seeds",
        ",".join(str(seed) for seed in seeds),
        "--rng-seed",
        str(rng_seed),
        "--action-timeout",
        str(action_timeout),
        "--startup-timeout",
        str(startup_timeout),
        "--game-timeout",
        str(game_timeout),
        "--output",
        str(report_path),
    ]
    environment = {
        "PATH": os.defpath,
        "HOME": str(output_dir),
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    completed = subprocess.run(
        command,
        cwd=output_dir,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=max(60.0, game_timeout * len(seeds) * 2 + 60.0),
        check=False,
    )
    log_path.write_text(completed.stdout, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(f"{label} evaluator exited {completed.returncode}; see {log_path}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return report, {
        "report_sha256": sha256(report_path),
        "log_sha256": sha256(log_path),
        "evaluator_sha256": sha256(evaluator),
        "loader_sha256": sha256(loader),
        "opponent_sha256": sha256(opponent),
    }


def game_key(game: dict[str, Any]) -> tuple[str, int, int]:
    return str(game["opponent"]), int(game["seed"]), int(game["candidate_seat"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-archive", type=Path, required=True)
    parser.add_argument("--prior-archive", type=Path, required=True)
    parser.add_argument("--expected-current-sha", default=CURRENT_SHA)
    parser.add_argument("--expected-prior-sha", default=PRIOR_SHA)
    parser.add_argument("--seeds", type=parse_seeds, default=parse_seeds("9925001,9925019"))
    parser.add_argument("--rng-seed", type=int, default=20260908)
    parser.add_argument("--action-timeout", type=float, default=1.0)
    parser.add_argument("--startup-timeout", type=float, default=15.0)
    parser.add_argument("--game-timeout", type=float, default=180.0)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    for timeout in (args.action_timeout, args.startup_timeout, args.game_timeout):
        if timeout <= 0:
            parser.error("timeouts must be positive")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    current_archive = args.current_archive.resolve(strict=True)
    prior_archive = args.prior_archive.resolve(strict=True)
    current_digest, prior_digest = sha256(current_archive), sha256(prior_archive)
    if current_digest != args.expected_current_sha:
        raise ValueError(f"current archive mismatch: {current_digest}")
    if prior_digest != args.expected_prior_sha:
        raise ValueError(f"prior archive mismatch: {prior_digest}")

    with tempfile.TemporaryDirectory(prefix="titan-current-continuity-") as temporary:
        root = Path(temporary)
        current_root, prior_root = root / "current", root / "prior"
        current_root.mkdir()
        prior_root.mkdir()
        current_inventory = safe_extract(current_archive, current_root)
        prior_inventory = safe_extract(prior_archive, prior_root)
        added = sorted(set(current_inventory) - set(prior_inventory))
        removed = sorted(set(prior_inventory) - set(current_inventory))
        changed = sorted(
            path
            for path in set(current_inventory) & set(prior_inventory)
            if current_inventory[path] != prior_inventory[path]
        )
        if added or removed:
            raise ValueError(f"archive inventories differ: added={added}, removed={removed}")
        current_config = json.loads((current_root / "TITAN-CONFIG.json").read_text())
        prior_config = json.loads((prior_root / "TITAN-CONFIG.json").read_text())
        if current_config != prior_config:
            raise ValueError("current and prior public configurations differ")
        if current_inventory["frozen_selected.py"] != prior_inventory["frozen_selected.py"]:
            raise ValueError("frozen comparison opponent differs between archives")

        current_report, current_hashes = run_arm(
            label="current",
            candidate_root=current_root,
            common_root=current_root,
            seeds=args.seeds,
            rng_seed=args.rng_seed,
            output_dir=args.output_dir,
            action_timeout=args.action_timeout,
            startup_timeout=args.startup_timeout,
            game_timeout=args.game_timeout,
        )
        prior_report, prior_hashes = run_arm(
            label="prior",
            candidate_root=prior_root,
            common_root=current_root,
            seeds=args.seeds,
            rng_seed=args.rng_seed,
            output_dir=args.output_dir,
            action_timeout=args.action_timeout,
            startup_timeout=args.startup_timeout,
            game_timeout=args.game_timeout,
        )

    current_games = {game_key(game): game for game in current_report["games"]}
    prior_games = {game_key(game): game for game in prior_report["games"]}
    if set(current_games) != set(prior_games):
        raise ValueError("scheduled game keys differ between arms")
    rows: list[dict[str, Any]] = []
    for key in sorted(current_games):
        current_game, prior_game = current_games[key], prior_games[key]
        seat = key[2]
        rows.append(
            {
                "opponent": key[0],
                "seed": key[1],
                "candidate_seat": seat,
                "current_status": current_game["status"],
                "prior_status": prior_game["status"],
                "current_scores": current_game["scores"],
                "prior_scores": prior_game["scores"],
                "same_scores": current_game["scores"] == prior_game["scores"],
                "current_trace_sha256": current_game["trace_sha256"],
                "prior_trace_sha256": prior_game["trace_sha256"],
                "same_trace": current_game["trace_sha256"] == prior_game["trace_sha256"],
                "current_candidate_calls": current_game["actors"][seat]["calls"],
                "prior_candidate_calls": prior_game["actors"][seat]["calls"],
                "current_candidate_max_call_seconds": current_game["actors"][seat]["max_call_seconds"],
                "prior_candidate_max_call_seconds": prior_game["actors"][seat]["max_call_seconds"],
                "current_candidate_max_rpc_seconds": current_game["actors"][seat]["max_rpc_seconds"],
                "prior_candidate_max_rpc_seconds": prior_game["actors"][seat]["max_rpc_seconds"],
            }
        )
    result = {
        "schema": "titan.current501.continuity.v1",
        "scope": "development continuity; official interpreter; no hosted or held claim",
        "current_archive": {
            "sha256": current_digest,
            "bytes": current_archive.stat().st_size,
            "source_manifest_sha256": current_inventory["SOURCE.json"][1],
        },
        "prior_archive": {
            "sha256": prior_digest,
            "bytes": prior_archive.stat().st_size,
            "source_manifest_sha256": prior_inventory["SOURCE.json"][1],
        },
        "archive_delta": {
            "paths_added": added,
            "paths_removed": removed,
            "paths_changed": changed,
            "configuration": current_config,
        },
        "seeds": args.seeds,
        "rng_seed": args.rng_seed,
        "opponent": {
            "entry": "current archive frozen_selected.py::agent",
            "sha256": current_hashes["opponent_sha256"],
            "same_bytes_both_archives": True,
        },
        "scheduled_per_arm": len(rows),
        "completed_per_arm": sum(
            row["current_status"] == row["prior_status"] == "complete" for row in rows
        ),
        "all_complete": all(
            row["current_status"] == row["prior_status"] == "complete" for row in rows
        ),
        "all_scores_equal": all(row["same_scores"] for row in rows),
        "all_traces_equal": all(row["same_trace"] for row in rows),
        "current_summary": current_report["summary"],
        "prior_summary": prior_report["summary"],
        "current_candidate_max_call_seconds": max(
            row["current_candidate_max_call_seconds"] for row in rows
        ),
        "prior_candidate_max_call_seconds": max(
            row["prior_candidate_max_call_seconds"] for row in rows
        ),
        "current_candidate_max_rpc_seconds": max(
            row["current_candidate_max_rpc_seconds"] for row in rows
        ),
        "prior_candidate_max_rpc_seconds": max(
            row["prior_candidate_max_rpc_seconds"] for row in rows
        ),
        "inputs": {
            "current": current_hashes,
            "prior": prior_hashes,
            "engine_sha256": current_report["engine_sha256"],
            "python": current_report["python"],
        },
        "rows": rows,
    }
    output = args.output_dir / "continuity.json"
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "rows"}, indent=2))
    if not (result["all_complete"] and result["all_scores_equal"] and result["all_traces_equal"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
