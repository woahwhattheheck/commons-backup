#!/usr/bin/env python3
"""Run the shipped stale-queue canceller across a bounded repository set.

Dry-run is the default.  ``--execute`` is explicit, every repository receives a
create-exclusive receipt, and the existing ``host.actions_queue_cancel`` module
retains all classification and final provider re-read authority.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

DEFAULT_REPOS = (
    "woahwhattheheck/commons",
    "woahwhattheheck/smb-showcase-inventory",
    "woahwhattheheck/motel-ops-suite",
    "woahwhattheheck/pack-market",
)
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
CANCEL_SCHEMA = "commons-actions-queue-cancel/v1"
SUMMARY_SCHEMA = "actions-queue-emergency/v1"
FIELDS = (
    "queued_total_reported",
    "queued_runs_observed",
    "initial_cancel_candidates",
    "cancel_posts_attempted",
    "cancel_accepted",
    "holds",
)


def _repos(values: Iterable[str]) -> tuple[str, ...]:
    out: list[str] = []
    for repo in values:
        if not REPO_RE.fullmatch(repo):
            raise ValueError(f"invalid repository: {repo!r}")
        if repo not in out:
            out.append(repo)
    if not out:
        raise ValueError("at least one repository is required")
    return tuple(out)


def build_command(
    *, python: str, repo: str, receipt: Path, cap: int,
    max_cancels: int, min_age_seconds: int, execute: bool,
) -> tuple[str, ...]:
    _repos((repo,))
    if cap <= 0 or max_cancels <= 0 or min_age_seconds < 0:
        raise ValueError("invalid queue bounds")
    command = [
        python, "-m", "host.actions_queue_cancel", "--repo", repo,
        "--cap", str(cap), "--max-cancels", str(max_cancels),
        "--min-age-seconds", str(min_age_seconds), "--out", str(receipt),
    ]
    if execute:
        command.append("--execute")
    return tuple(command)


def _read_receipt(path: Path, repo: str, execute: bool) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"unreadable receipt: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("receipt root must be an object")
    if data.get("schema") != CANCEL_SCHEMA or data.get("repo") != repo:
        raise ValueError("receipt identity mismatch")
    if data.get("mode") != ("execute" if execute else "dry_run"):
        raise ValueError("receipt mode mismatch")
    for field in FIELDS:
        value = data.get(field)
        if type(value) is not int or value < 0:
            raise ValueError(f"invalid receipt field: {field}")
    if data["cancel_accepted"] > data["cancel_posts_attempted"]:
        raise ValueError("accepted count exceeds attempted count")
    return data


def run_one(
    *, repo: str, round_number: int, receipt: Path, checkout: Path,
    python: str, cap: int, max_cancels: int, min_age_seconds: int,
    execute: bool,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    command = build_command(
        python=python, repo=repo, receipt=receipt, cap=cap,
        max_cancels=max_cancels, min_age_seconds=min_age_seconds,
        execute=execute,
    )
    try:
        done = runner(list(command), cwd=checkout, text=True,
                      capture_output=True, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"repo": repo, "round": round_number, "command": list(command),
                "error": f"start failed: {exc}"}
    try:
        data = _read_receipt(receipt, repo, execute)
    except ValueError as exc:
        return {"repo": repo, "round": round_number, "command": list(command),
                "returncode": done.returncode, "error": str(exc)}
    error = None if done.returncode in (0, 2) else f"unexpected returncode {done.returncode}"
    return {
        "repo": repo, "round": round_number, "command": list(command),
        "returncode": done.returncode, "receipt": str(receipt),
        "error": error, **{field: data[field] for field in FIELDS},
        "queued_inventory_complete": data.get("queued_inventory_complete"),
        "stop_reason": data.get("stop_reason"),
        "rate_limit": data.get("rate_limit"),
        "candidates_unprocessed": data.get("candidates_unprocessed"),
    }


def _write_exclusive(path: Path, payload: dict[str, Any]) -> None:
    body = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        view = memoryview(body)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def orchestrate(
    *, repos: Sequence[str], rounds: int, receipt_root: Path, run_id: str,
    checkout: Path, python: str, cap: int, max_cancels: int,
    min_age_seconds: int, execute: bool, sleep_seconds: float,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> tuple[dict[str, Any], Path]:
    selected = _repos(repos)
    if rounds <= 0 or sleep_seconds < 0:
        raise ValueError("invalid orchestration bounds")
    run_dir = receipt_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    rows: list[dict[str, Any]] = []
    stop = "ROUND_LIMIT_REACHED"
    completed_rounds = 0
    for round_number in range(1, rounds + 1):
        current: list[dict[str, Any]] = []
        for repo in selected:
            result = run_one(
                repo=repo, round_number=round_number,
                receipt=run_dir / f"round-{round_number:03d}--{repo.replace('/', '--')}.json",
                checkout=checkout, python=python, cap=cap,
                max_cancels=max_cancels, min_age_seconds=min_age_seconds,
                execute=execute, runner=runner,
            )
            rows.append(result)
            current.append(result)
            # Repositories share the provider quota. A worker backoff signal
            # must stop this pass before starting another repository or round.
            if result.get("stop_reason") == "RATE_LIMITED":
                break
        if len(current) == len(selected):
            completed_rounds += 1
        if any(row.get("stop_reason") == "RATE_LIMITED" for row in current):
            stop = "RATE_LIMITED"
            break
        if any(row.get("error") for row in current):
            stop = "ORCHESTRATION_ERROR"
            break
        if not execute:
            stop = "DRY_RUN_COMPLETE"
            break
        if sum(row["initial_cancel_candidates"] for row in current) == 0:
            stop = "NO_STALE_CANDIDATES"
            break
        if sum(row["cancel_accepted"] for row in current) == 0:
            stop = "NO_CANCELLATIONS_ACCEPTED"
            break
        if round_number < rounds and sleep_seconds:
            time.sleep(sleep_seconds)
    summary = {
        "schema": SUMMARY_SCHEMA,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "execute" if execute else "dry_run",
        "run_id": run_id, "repos": list(selected), "stop_reason": stop,
        "requested_rounds": rounds,
        "completed_rounds": completed_rounds,
        "bounds": {"cap_per_repo": cap, "max_cancels_per_repo_round": max_cancels,
                   "min_age_seconds": min_age_seconds},
        "totals": {
            "invocations": len(rows),
            "orchestration_errors": sum(bool(row.get("error")) for row in rows),
            **{field: sum(int(row.get(field, 0)) for row in rows)
               for field in FIELDS[2:]},
        },
        "safety": {"delegates_to_shipped_canceller": True,
                   "dry_run_default": True, "bounded": True,
                   "receipt_per_repo_per_round": True},
        "invocations": rows,
    }
    summary_path = run_dir / "summary.json"
    _write_exclusive(summary_path, summary)
    return summary, summary_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", action="append", dest="repos")
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--cap", type=int, default=5000)
    parser.add_argument("--max-cancels", type=int, default=25)
    parser.add_argument("--min-age-seconds", type=int, default=900)
    parser.add_argument("--sleep-seconds", type=float, default=2.0)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--receipt-root", type=Path, default=Path("actions-queue-emergency-receipts"))
    parser.add_argument("--run-id")
    parser.add_argument("--checkout", type=Path, default=Path.cwd())
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args(argv)
    run_id = args.run_id or ("execute-" if args.execute else "dry-run-") + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    try:
        summary, path = orchestrate(
            repos=tuple(args.repos) if args.repos else DEFAULT_REPOS,
            rounds=args.rounds, receipt_root=args.receipt_root, run_id=run_id,
            checkout=args.checkout, python=args.python, cap=args.cap,
            max_cancels=args.max_cancels, min_age_seconds=args.min_age_seconds,
            execute=args.execute, sleep_seconds=args.sleep_seconds,
        )
    except (OSError, ValueError) as exc:
        parser.exit(2, f"actions_queue_emergency: {exc}\n")
    print(json.dumps({"summary": str(path), "totals": summary["totals"],
                      "stop_reason": summary["stop_reason"]}, sort_keys=True))
    return 2 if (summary["totals"]["orchestration_errors"]
                 or summary["stop_reason"] == "RATE_LIMITED") else 0


if __name__ == "__main__":
    raise SystemExit(main())
