#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the source-pinned historical check and exact-current LAND holdout."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from ci_evaluate import compare_current, run_panel, write_summary
from ci_prepare import (
    build_current,
    historical_check,
    install_engine,
    route_probe,
    write_manifest,
)
from ci_support import run
from historical_provenance import verify_historical_pair

LANE_PATH = (
    "revenue/kaggriculture/cloud-execution-lab/candidates/"
    "v3-l01-land-admission-current"
)
LAB_PATH = "revenue/kaggriculture/cloud-execution-lab"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--expected-head", required=True)
    args = parser.parse_args()

    repo, work = args.repo_root.resolve(), args.work_root.resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    lane, lab = repo / LANE_PATH, repo / LAB_PATH
    pin = json.loads((lane / "PIN.json").read_text(encoding="utf-8"))
    actual = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    if actual != args.expected_head:
        raise ValueError(f"checkout mismatch: {actual} != {args.expected_head}")
    (work / "CHECKOUT.sha").write_text(actual + "\n", encoding="utf-8")

    exit_code = 1
    try:
        tests = run(
            [
                sys.executable, "-B", "-m", "unittest", "discover",
                "-s", str(lane), "-p", "test_*.py", "-v",
            ], cwd=repo, stdout=work / "UNIT-TESTS.stdout.txt",
            stderr=work / "UNIT-TESTS.stderr.txt", check=False,
        )
        if tests.returncode:
            raise RuntimeError(f"unit tests failed: {tests.returncode}")
        historical_delta = historical_check(repo, lane, work, pin)
        verify_historical_pair(work / "historical-l01", pin["historical_source"])
        build = build_current(repo, lane, lab, work)
        python, engine = install_engine(repo, lab, work, pin)
        route_probe(repo, lane, work, python)
        write_manifest(repo, lab, work, pin, build, engine, historical_delta)
        baseline = run_panel(repo, lane, lab, work, python, engine, pin, "baseline")
        candidate = run_panel(repo, lane, lab, work, python, engine, pin, "land")
        if baseline["returncode"] or candidate["returncode"]:
            raise RuntimeError(
                f"paired run failed: baseline={baseline['returncode']} "
                f"land={candidate['returncode']}"
            )
        compare_current(repo, lane, work, python, pin)
        exit_code = 0
    except Exception as error:
        (work / "FAILURE.json").write_text(
            json.dumps(
                {
                    "schema": "titan-v3-land-admission-ci-failure-v1",
                    "type": type(error).__name__, "message": str(error),
                }, indent=2, sort_keys=True,
            ) + "\n", encoding="utf-8",
        )
        raise
    finally:
        write_summary(work)
        (work / "EXIT_CODE.txt").write_text(
            str(exit_code) + "\n", encoding="utf-8"
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
