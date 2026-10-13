#!/usr/bin/env python3
"""Evidence-bound lifecycle for disposable Muhlnickel puzzle candidates.

This module creates, measures, promotes, and fires candidate specifications. It
does not mine a live network, move money, or call an external service. A
"fastest" result is scoped to comparable receipts for one named puzzle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "commons-muhlnickel-candidate-lab-v1"
STATES = {"CREATED", "MEASURED", "PROMOTED", "FIRED"}


def _text(value: Any, field: str) -> str:
    value = " ".join(str(value or "").split())
    if not value:
        raise ValueError(f"{field} must be nonempty")
    return value


def new_lab(puzzle_id: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "puzzle_id": _text(puzzle_id, "puzzle_id"),
        "claim_state": "BENCHMARK_REQUIRED",
        "commercial_disposition": "PUBLIC_SALE_ALLOWED",
        "active_candidate": None,
        "candidates": [],
        "boundaries": {
            "live_network_bound": False,
            "money_moved": False,
            "private_distro_included": False,
            "source_candidates_deleted_when_fired": False,
        },
    }


def _validate_lab(lab: dict[str, Any]) -> None:
    if lab.get("schema") != SCHEMA or not isinstance(lab.get("candidates"), list):
        raise ValueError("unsupported candidate lab schema")
    for row in lab["candidates"]:
        if row.get("state") not in STATES:
            raise ValueError("invalid candidate state")


def _candidate(lab: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    for row in lab["candidates"]:
        if row["candidate_id"] == candidate_id:
            return row
    raise KeyError(f"unknown candidate: {candidate_id}")


def create_candidate(
    lab: dict[str, Any], candidate_id: str, backend: str, source: str,
    root: Path = ROOT,
) -> dict[str, Any]:
    _validate_lab(lab)
    candidate_id = _text(candidate_id, "candidate_id")
    backend = _text(backend, "backend")
    source = _text(source, "source")
    if any(row["candidate_id"] == candidate_id for row in lab["candidates"]):
        raise ValueError(f"duplicate candidate: {candidate_id}")
    source_path = root / source
    if not source_path.is_file():
        raise FileNotFoundError(f"missing candidate source: {source}")
    row = {
        "candidate_id": candidate_id,
        "backend": backend,
        "source": source,
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "state": "CREATED",
        "trials": [],
        "fire_reason": None,
    }
    lab["candidates"].append(row)
    lab["claim_state"] = "BENCHMARK_REQUIRED"
    return row


def record_trial(
    lab: dict[str, Any], candidate_id: str, attempts: int, elapsed_ns: int,
    solution_digest: str, *, solved: bool = True,
) -> dict[str, Any]:
    _validate_lab(lab)
    row = _candidate(lab, candidate_id)
    if row["state"] == "FIRED":
        raise ValueError("cannot measure a fired candidate")
    if not isinstance(attempts, int) or attempts <= 0:
        raise ValueError("attempts must be a positive integer")
    if not isinstance(elapsed_ns, int) or elapsed_ns <= 0:
        raise ValueError("elapsed_ns must be a positive integer")
    digest = _text(solution_digest, "solution_digest").lower()
    if any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("solution_digest must be hexadecimal")
    trial = {
        "puzzle_id": lab["puzzle_id"],
        "attempts": attempts,
        "elapsed_ns": elapsed_ns,
        "attempts_per_second": attempts * 1_000_000_000 / elapsed_ns,
        "solution_digest": digest,
        "solved": bool(solved),
    }
    row["trials"].append(trial)
    row["state"] = "MEASURED"
    return trial


def fastest_candidate(lab: dict[str, Any]) -> dict[str, Any] | None:
    _validate_lab(lab)
    measured = []
    for row in lab["candidates"]:
        solved = [trial for trial in row["trials"] if trial["solved"]]
        if row["state"] != "FIRED" and solved:
            measured.append((max(t["attempts_per_second"] for t in solved), row["candidate_id"], row))
    return max(measured, default=(None, None, None), key=lambda item: (item[0], item[1]))[2]


def promote_fastest(lab: dict[str, Any]) -> dict[str, Any]:
    winner = fastest_candidate(lab)
    if winner is None:
        raise ValueError("no solved measured candidate is eligible for promotion")
    for row in lab["candidates"]:
        if row is winner:
            row["state"] = "PROMOTED"
        elif row["state"] == "MEASURED":
            row["state"] = "FIRED"
            row["fire_reason"] = "slower-on-this-measured-puzzle"
    lab["active_candidate"] = winner["candidate_id"]
    lab["claim_state"] = "FASTEST_ON_NAMED_PUZZLE_RECEIPTS"
    return winner


def fire_candidate(lab: dict[str, Any], candidate_id: str, reason: str) -> dict[str, Any]:
    _validate_lab(lab)
    row = _candidate(lab, candidate_id)
    if row["state"] == "FIRED":
        return row
    row["state"] = "FIRED"
    row["fire_reason"] = _text(reason, "reason")
    if lab["active_candidate"] == candidate_id:
        lab["active_candidate"] = None
        lab["claim_state"] = "BENCHMARK_REQUIRED"
    return row


def _load(path: Path) -> dict[str, Any]:
    lab = json.loads(path.read_text(encoding="utf-8"))
    _validate_lab(lab)
    return lab


def _save(path: Path, lab: dict[str, Any]) -> None:
    _validate_lab(lab)
    path.write_text(json.dumps(lab, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("puzzle_id")
    create = commands.add_parser("create")
    create.add_argument("candidate_id")
    create.add_argument("backend")
    create.add_argument("source")
    trial = commands.add_parser("trial")
    trial.add_argument("candidate_id")
    trial.add_argument("attempts", type=int)
    trial.add_argument("elapsed_ns", type=int)
    trial.add_argument("solution_digest")
    fire = commands.add_parser("fire")
    fire.add_argument("candidate_id")
    fire.add_argument("reason")
    commands.add_parser("promote")
    args = parser.parse_args(argv)
    if args.command == "init":
        lab = new_lab(args.puzzle_id)
    else:
        lab = _load(args.registry)
        if args.command == "create":
            create_candidate(lab, args.candidate_id, args.backend, args.source)
        elif args.command == "trial":
            record_trial(lab, args.candidate_id, args.attempts, args.elapsed_ns, args.solution_digest)
        elif args.command == "fire":
            fire_candidate(lab, args.candidate_id, args.reason)
        elif args.command == "promote":
            promote_fastest(lab)
    _save(args.registry, lab)
    print(json.dumps(lab, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
