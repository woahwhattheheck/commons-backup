#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reproduce the M1 complete-day contract and non-vacuity mutation probes.

Read-only with respect to the supplied source/tests: all execution uses a fresh
local temporary directory. No legacy V4 materializer or network call is used.
Exact pins describe this receipt, not an authorization to activate M1.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

PINS = {
    "source": "87eb8ccbee13b33ef656ba0a5ba0114ac30f4658",
    "boundary_tests": "71e1c92337bb36463bb65f43f70f8e7ffc6158ee",
    "money_tests": "5695a41e8baca3da1b0b730ebcb3c27e6fa0bc8d",
}
MUTATIONS = {
    "remove_complete_day_guard": (
        "    if len(tape) <= expected_day_end:\n        return None, 0\n    day_end = expected_day_end",
        "    day_end = min(len(tape) - 1, expected_day_end)"),
    "allow_missing_last_day_step": (
        "if len(tape) <= expected_day_end:", "if len(tape) < expected_day_end:"),
    "ignore_final_same_day_purchase": (
        "range(candidate_due + 1, day_end + 1)", "range(candidate_due + 1, day_end)"),
    "scan_dead_eleventh_market_row": (
        "prefix = rows[:MAX_ORDERS]", "prefix = rows[:MAX_ORDERS + 1]"),
    "charge_next_day_cash_owner": (
        "    day_end = expected_day_end", "    day_end = len(tape) - 1"),
    "disable_eligible_m1_buys": (
        "    if due is None:\n        return action", "    if True:\n        return action"),
    "remove_price_surcharge": (
        "SAME_TURN_WHEAT_SURCHARGE = 25", "SAME_TURN_WHEAT_SURCHARGE = 0"),
}


def blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def verified(path: Path, key: str) -> bytes:
    data = path.read_bytes()
    actual = blob_sha(data)
    if actual != PINS[key]:
        raise ValueError(f"{key}: expected {PINS[key]}, got {actual} at {path}")
    return data


def execute(source: bytes, tests: dict[str, bytes], optimized: bool) -> dict:
    # No pycache or state is shared across modes or mutations.
    with tempfile.TemporaryDirectory(prefix="titan-m1-complete-day-") as directory:
        root = Path(directory)
        (root / "r04_m1_wheat_trade.py").write_bytes(source)
        for name, data in tests.items():
            (root / name).write_bytes(data)
        command = [sys.executable, "-I"] + (["-O"] if optimized else []) + [
            "-m", "unittest", "discover", "-s", str(root), "-p", "test_v4_m1_*.py"]
        run = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=20)
    output = run.stdout + run.stderr
    count = re.search(r"^Ran (\d+) tests? in ", output, re.MULTILINE)
    failure = re.search(r"^FAILED \(([^)]+)\)$", output, re.MULTILINE)
    invalid = any(word in output for word in ("SyntaxError", "ImportError", "ModuleNotFoundError"))
    executed = int(count.group(1)) if count else 0
    passed = run.returncode == 0 and executed == 26 and bool(re.search(r"^OK$", output, re.MULTILINE))
    rejected = run.returncode != 0 and executed == 26 and failure is not None and not invalid
    return {
        "optimized": optimized,
        "returncode": run.returncode,
        "test_count": executed,
        "passed": passed,
        "behaviorally_rejected": rejected,
        "rejection_kind": ("runtime_exception" if failure and "errors=" in failure.group(1)
                           else "assertion" if failure else None),
        "summary": failure.group(1) if failure else "OK" if passed else output[-1500:],
        "log_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
    }


def validate(source: bytes, boundary_tests: bytes, money_tests: bytes) -> dict:
    tests = {"test_v4_m1_complete_day_boundaries.py": boundary_tests,
             "test_v4_m1_money_overflow.py": money_tests}
    baseline = [execute(source, tests, mode) for mode in (False, True)]
    if not all(row["passed"] for row in baseline):
        raise RuntimeError("Repaired baseline failed: " + json.dumps(baseline))
    text = source.decode("utf-8")
    results = []
    for name, (old, new) in MUTATIONS.items():
        if text.count(old) != 1:
            raise ValueError(f"{name}: expected exactly one mutation anchor")
        mutant = text.replace(old, new, 1).encode("utf-8")
        for mode in (False, True):
            row = {"mutation": name, **execute(mutant, tests, mode)}
            results.append(row)
    return {
        "schema": 1,
        "mechanism": "M1 complete-day funding coverage",
        "input_git_blobs": PINS,
        "baseline": baseline,
        "timing_subcases_per_baseline_run": 2660,
        "mutation_results": results,
        "all_mutations_rejected": all(row["behaviorally_rejected"] for row in results),
        "production_activation": False,
        "economic_gate_run": False,
    }


def main() -> int:
    package = Path(__file__).resolve().parent
    overlay = package.parents[2] / "donor" / "overlay"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=overlay / "r04_m1_wheat_trade.py")
    parser.add_argument("--boundary-tests", type=Path,
                        default=overlay / "checks" / "test_v4_m1_complete_day_boundaries.py")
    parser.add_argument("--money-tests", type=Path,
                        default=package / "test_v4_m1_money_overflow.py")
    args = parser.parse_args()
    try:
        result = validate(verified(args.source, "source"),
                          verified(args.boundary_tests, "boundary_tests"),
                          verified(args.money_tests, "money_tests"))
    except (OSError, UnicodeError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"error": str(error), "valid": False}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["all_mutations_rejected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
