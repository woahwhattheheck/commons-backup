# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import statistics
import time

from joint_action_beam import BeamConfig, propose_worker_action
from mechanics_adapter import MechanicsContext, bounded_worker_candidates, mechanics_scorer, mechanics_transition
from test_mechanics_adapter import fixture

HERE = Path(__file__).resolve().parent
MECHANICS_PATH = Path(os.environ.get("S01_MECHANICS", HERE.parent / "cloud-execution-lab" / "mechanics.py"))
EXPECTED_MECHANICS_BLOB = "044a4f9c0a4a44dde10ada57563238bcaf82075d"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def load_mechanics():
    spec = importlib.util.spec_from_file_location("s01_contract_mechanics", MECHANICS_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--runs", type=int, default=64)
    args = parser.parse_args()

    data = MECHANICS_PATH.read_bytes()
    blob = git_blob(data)
    if blob != EXPECTED_MECHANICS_BLOB:
        raise SystemExit(f"mechanics blob drift: {blob}")

    mechanics = load_mechanics()
    transition = mechanics_transition(mechanics, MechanicsContext(board_size=10, day=0, turns_per_day=24))
    scorer = mechanics_scorer(mechanics)
    canonical = {
        "farmer": ["PASS"],
        "hands": [["PASS"], ["PASS"], ["PASS"]],
        "market": [["SELL", "WHEAT", 1]],
        "hire": 0,
        "buyLand": 0,
    }

    elapsed_ms = []
    fallbacks = 0
    reasons = {}
    complete_outputs = set()
    max_frontier = 0
    max_expanded = 0
    for _ in range(args.runs):
        state = fixture(4)
        start = time.perf_counter_ns()
        proposed, result = propose_worker_action(
            canonical,
            state,
            lambda s, i, c: bounded_worker_candidates(mechanics, s, i, c),
            transition,
            scorer,
            config=BeamConfig(width=24, depth=4, budget_ns=35_000_000, max_candidates=32),
        )
        elapsed_ms.append((time.perf_counter_ns() - start) / 1_000_000)
        reasons[result.reason] = reasons.get(result.reason, 0) + 1
        max_frontier = max(max_frontier, result.frontier_peak)
        max_expanded = max(max_expanded, result.expanded)
        if result.used_fallback:
            fallbacks += 1
            if proposed != canonical:
                raise SystemExit("deadline fallback changed canonical full action")
            if not result.reason.startswith("deadline-"):
                raise SystemExit(f"unexpected fallback: {result.reason}")
        else:
            if proposed["market"] != canonical["market"] or proposed["hire"] != canonical["hire"] or proposed["buyLand"] != canonical["buyLand"]:
                raise SystemExit("worker proposer changed controller fields")
            complete_outputs.add(json.dumps(proposed, sort_keys=True, separators=(",", ":")))

    deadline_fallbacks = sum(n for reason, n in reasons.items() if reason.startswith("deadline-"))
    if deadline_fallbacks:
        raise SystemExit(f"deadline fallbacks fail closed: {deadline_fallbacks} {reasons}")
    if fallbacks:
        raise SystemExit(f"non-complete searches fail closed: {fallbacks} {reasons}")
    max_elapsed = max(elapsed_ms) if elapsed_ms else 0.0
    if max_elapsed > 35:
        raise SystemExit(f"max elapsed {max_elapsed} ms exceeds 35 ms contract")

    if len(complete_outputs) > 1:
        raise SystemExit("complete searches were not deterministic")
    rss_kib = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if rss_kib >= 192 * 1024:
        raise SystemExit(f"RSS exceeds 192 MiB contract: {rss_kib} KiB")

    ordered = sorted(elapsed_ms)
    p95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95) - 1))
    report = {
        "schema": "titan.s01.contract.v1",
        "mechanics_git_blob": blob,
        "mechanics_sha256": hashlib.sha256(data).hexdigest(),
        "beam": {"width": 24, "depth": 4, "budget_ms": 35, "max_candidates": 32},
        "runs": args.runs,
        "complete": args.runs - fallbacks,
        "fallbacks": fallbacks,
        "reasons": reasons,
        "deterministic_complete_outputs": len(complete_outputs),
        "max_frontier": max_frontier,
        "max_expanded": max_expanded,
        "timing_ms": {
            "min": min(elapsed_ms),
            "median": statistics.median(elapsed_ms),
            "p95": ordered[p95_index],
            "max": max(elapsed_ms),
        },
        "max_rss_kib": rss_kib,
        "controller_fields_preserved": True,
        "fallback_is_exact_canonical": True,
        "gameplay_claim": False,
    }
    Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
