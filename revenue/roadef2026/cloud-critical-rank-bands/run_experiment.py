#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run equal-source top-32 and expanded-rank continuations from one incumbent."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked(command: list[str], *, env: dict[str, str] | None = None,
            stdout: Path | None = None, stderr: Path | None = None,
            timeout: int = 900) -> float:
    begin = time.perf_counter()
    with ExitStack() as stack:
        out = stack.enter_context(stdout.open("w")) if stdout else subprocess.DEVNULL
        err = stack.enter_context(stderr.open("w")) if stderr else subprocess.DEVNULL
        result = subprocess.run(command, env=env, stdout=out, stderr=err, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}")
    return time.perf_counter() - begin


def load_checker(path: Path) -> dict:
    return json.loads(path.read_text(), parse_float=Decimal)


def vector(checker: dict) -> list[Decimal]:
    return [row["sat"] for row in checker["saturations"]]


def first_difference(left: list[Decimal], right: list[Decimal]) -> dict | None:
    for index, (a, b) in enumerate(zip(left, right), 1):
        if a != b:
            return {"rank": index, "control": str(a), "expanded": str(b),
                    "winner": "expanded" if b < a else "control"}
    if len(left) != len(right):
        return {"rank": min(len(left), len(right)) + 1,
                "control": None if len(left) < len(right) else str(left[-1]),
                "expanded": None if len(right) < len(left) else str(right[-1]),
                "winner": "expanded" if len(right) < len(left) else "control"}
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--vendor", required=True, type=Path)
    parser.add_argument("--checker", required=True, type=Path)
    parser.add_argument("--net", required=True, type=Path)
    parser.add_argument("--tm", required=True, type=Path)
    parser.add_argument("--scenario", required=True, type=Path)
    parser.add_argument("--incumbent", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--compiler", default="g++")
    parser.add_argument("--seconds", type=float, default=34.0)
    parser.add_argument("--rounds", type=int)
    parser.add_argument("--stall-limit", type=int, default=128)
    parser.add_argument("--expanded-rank-limit", type=int, default=128)
    parser.add_argument("--order", default="expanded-first")
    args = parser.parse_args()
    if args.order not in ("expanded-first", "control-first"):
        parser.error("order must be expanded-first or control-first")
    if args.seconds <= 0 or args.stall_limit <= 0 or args.expanded_rank_limit <= 32:
        parser.error("seconds/stall limit must be positive and expanded rank limit must exceed 32")
    if args.rounds is not None and args.rounds < 0:
        parser.error("rounds must be nonnegative")
    if not shutil.which(args.compiler):
        parser.error(f"compiler unavailable: {args.compiler}")
    args.output.mkdir(parents=True, exist_ok=False)
    here = Path(__file__).resolve().parent
    candidate = args.output / "candidate.cpp"
    subprocess.run([str(here / "build_candidate.py"), "--source", str(args.source),
                    "--output", str(candidate)], check=True)
    binary = args.output / "candidate"
    subprocess.run([args.compiler, "-std=c++20", "-O3", "-DNDEBUG", "-I", str(args.vendor),
                    str(candidate), "-o", str(binary)], check=True)
    order = ["expanded", "control"] if args.order == "expanded-first" else ["control", "expanded"]
    rows: dict[str, dict] = {}
    for arm in order:
        rank_limit = args.expanded_rank_limit if arm == "expanded" else 32
        solution = args.output / f"{arm}-solution.json"
        stats = args.output / f"{arm}-stats.json"
        env = os.environ.copy()
        for key in ("SEDGE_MAX_ROUNDS", "CLOUD_INITIAL_SOLUTION", "SEDGE_STATS",
                    "FLEET_CRITICAL_RANK_LIMIT", "FLEET_CRITICAL_STALL_LIMIT"):
            env.pop(key, None)
        env.update(CLOUD_INITIAL_SOLUTION=str(args.incumbent), SEDGE_STATS=str(stats),
                   SEDGE_SECONDS=str(args.seconds), FLEET_CRITICAL_RANK_LIMIT=str(rank_limit),
                   FLEET_CRITICAL_STALL_LIMIT=str(args.stall_limit))
        if args.rounds is not None:
            env["SEDGE_MAX_ROUNDS"] = str(args.rounds)
        wall = checked([str(binary), str(args.net), str(args.tm), str(args.scenario), str(solution)],
                       env=env, stdout=args.output/f"{arm}.stdout", stderr=args.output/f"{arm}.stderr")
        checker_files = {}
        for decimals in (6, 12):
            result = args.output / f"{arm}-checker-{decimals}.json"
            checked([str(args.checker), "--net", str(args.net), "--tm", str(args.tm),
                     "--scenario", str(args.scenario), "--srpaths", str(solution),
                     "--max-decimal-places", str(decimals)], stdout=result,
                    stderr=args.output/f"{arm}-checker-{decimals}.stderr")
            checker_files[str(decimals)] = load_checker(result)
        rows[arm] = {"wall_seconds": wall, "solution_sha256": digest(solution),
                     "stats": json.loads(stats.read_text()), "checker": checker_files}
    left, right = rows["control"]["checker"]["6"], rows["expanded"]["checker"]["6"]
    report = {"schema": "roadef-critical-rank-experiment-v1", "status": "COMPLETE",
              "source_sha256": digest(args.source), "candidate_sha256": digest(candidate),
              "binary_sha256": digest(binary), "checker_sha256": digest(args.checker),
              "inputs": {path.name: digest(path) for path in (args.net, args.tm, args.scenario)},
              "incumbent_sha256": digest(args.incumbent), "seconds": args.seconds,
              "rounds": args.rounds, "stall_limit": args.stall_limit,
              "expanded_rank_limit": args.expanded_rank_limit, "order": order,
              "arms": {name: {"wall_seconds": row["wall_seconds"],
                               "solution_sha256": row["solution_sha256"],
                               "stats": row["stats"],
                               "valid_6": row["checker"]["6"]["valid"],
                               "valid_12": row["checker"]["12"]["valid"],
                               "total_cost_diagnostic": row["checker"]["6"]["total_cost"]}
                       for name, row in rows.items()},
              "comparison": {"first_six_decimal_difference": first_difference(vector(left), vector(right)),
                             "load_count": len(vector(left)),
                             "cost_used_in_ranking": False},
              "limits": ["One source-fixed incumbent and instance; not a qualification score forecast.",
                         "Wall-time trials are environment-sensitive; fixed-round evidence is separate.",
                         "The official checker vector, not accepted-move count or diagnostic cost, decides ranking."]}
    (args.output / "experiment.json").write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n")
    print(json.dumps(report["comparison"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
