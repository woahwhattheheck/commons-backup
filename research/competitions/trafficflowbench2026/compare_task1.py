#!/usr/bin/env python3
"""Run an exact organizer-scorer A/B for Task 1."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


def run(name: str, command: list[str], cwd: Path) -> dict:
    print(f"\n[{name}] {' '.join(command)}", flush=True)
    started = time.perf_counter()
    proc = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    elapsed = time.perf_counter() - started
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if proc.returncode:
        raise SystemExit(f"{name} failed with exit {proc.returncode}")
    return {
        "name": name,
        "elapsed_seconds": elapsed,
        "command": command,
        "stdout_tail": proc.stdout[-4000:],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--official-repo", type=Path, required=True)
    ap.add_argument("--release-root", type=Path, required=True)
    ap.add_argument("--candidate", type=Path, required=True)
    ap.add_argument("--panel", default="D12_I5_N")
    ap.add_argument("--max-gap-steps", type=int, default=6)
    ap.add_argument("--work-dir", type=Path, required=True)
    args = ap.parse_args()

    repo = args.official_repo.resolve()
    release = args.release_root.resolve()
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)

    baseline = work / "baseline.csv"
    candidate = work / "shortgap.csv"
    baseline_score = work / "baseline_score.csv"
    candidate_score = work / "shortgap_score.csv"
    py = sys.executable

    receipts = [
        run(
            "build_baseline",
            [
                py,
                "src/task1/build_task1_baseline_submission.py",
                "--release-root", str(release),
                "--split", "train",
                "--panel", args.panel,
                "--output", str(baseline),
            ],
            repo,
        ),
        run(
            "score_baseline",
            [
                py,
                "src/task1/score_task1.py",
                "--submission", str(baseline),
                "--release-root", str(release),
                "--split", "train",
                "--panel", args.panel,
                "--output", str(baseline_score),
            ],
            repo,
        ),
        run(
            "build_shortgap",
            [
                py,
                str(args.candidate.resolve()),
                "--official-repo", str(repo),
                "--release-root", str(release),
                "--split", "train",
                "--panel", args.panel,
                "--max-gap-steps", str(args.max_gap_steps),
                "--output", str(candidate),
            ],
            repo,
        ),
        run(
            "score_shortgap",
            [
                py,
                "src/task1/score_task1.py",
                "--submission", str(candidate),
                "--release-root", str(release),
                "--split", "train",
                "--panel", args.panel,
                "--output", str(candidate_score),
            ],
            repo,
        ),
    ]

    receipt = {
        "official_repo": str(repo),
        "release_root": str(release),
        "panel": args.panel,
        "max_gap_steps": args.max_gap_steps,
        "runs": receipts,
        "score_csvs": {
            "baseline": str(baseline_score),
            "shortgap": str(candidate_score),
        },
        "claim_boundary": (
            "Exact organizer scripts on public train only. This does not claim "
            "validation/private leaderboard performance or Task 3 improvement."
        ),
    }
    path = work / "receipt.json"
    path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"\nReceipt: {path}")


if __name__ == "__main__":
    main()
