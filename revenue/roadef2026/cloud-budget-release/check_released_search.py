#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Execute or inspect the predeclared two-case incumbent-encoding comparison.

Uses the existing fleet benchmark.execute, original solver, and official checker.
No neighborhood, tuning, source preparation, or scenario generator is added.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any

CASES = ("setB-07", "setB-11")
INPUTS = {
    "setB-07": {
        "original": "5b9b48ffb9f5ec2d3c7d9b72d910330d449508ba08e38551357bf3c8111dd7ca",
        "released": "2aa5487bdd14a01e1792b22a47d75c90949e0b75663d60e8cf79a88a77fda7c8",
    },
    "setB-11": {
        "original": "3b830deece4c58008cff0cdacf1cf4a899faf527c3a657ba74f772beb88c3b6e",
        "released": "5e6ff37c4493fc09a41e1ba4cc7f2bdbb3848b0c422234dfd9f778a5d1bafa89",
    },
}

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path: Path, *, exact: bool = False) -> Any:
    options = {"parse_float": Decimal, "parse_int": Decimal} if exact else {}
    return json.loads(path.read_text(encoding="utf-8"), **options)

def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)

def case_inputs(screen: Path, released: Path, name: str):
    files = [screen / "inputs/setB" / f"{name}-{suffix}.json"
             for suffix in ("net", "tm", "scenario")]
    starts = {"original": screen / "screen30" / name / "sedge/solution.json",
              "released": released / name / "sedge/neutral/solution.json"}
    for label, path in starts.items():
        require(digest(path) == INPUTS[name][label], f"Different {name}/{label} incumbent")
    source = read(screen / "screen30" / name / "sedge/result.json")
    for path in files:
        require(digest(path) == source["input_sha256"][path.name], "Public input identity differs")
    return files, starts

def inspect_case(folder: Path, name: str) -> dict[str, Any]:
    vectors, arms = {}, {}
    for label in ("original", "released"):
        path = folder / name / label
        stats = read(path / "stats.json")
        checks = {p: read(path / f"checker-{p}.stdout", exact=True) for p in (6, 12)}
        for check in checks.values():
            require(check.get("valid") is True, "Official checker did not validate output")
            values = [r["sat"] for r in check["saturations"]]
            require(all(v.is_finite() and v >= 0 for v in values), "Invalid saturation")
        predicted = {(r["t"], r["from"], r["to"]): r["sat"] for r in stats["loads"]}
        actual = {(int(r["t"]), int(r["from"]), int(r["to"])): float(r["sat"])
                  for r in checks[12]["saturations"]}
        require(predicted.keys() == actual.keys(), "Native/checker load coordinates differ")
        error = max(abs(predicted[k] - actual[k]) for k in predicted)
        require(error < 2e-9, "Native/checker saturation disagreement")
        require(sum(stats["budget_used"]) == checks[12]["total_cost"], "Budget cost disagrees")
        # The pinned run has at most8 rounds; its stalled exit needs64. These
        # completed calls were nowhere near their30s ceiling. No equal-attempt
        # or equal-runtime interpretation is assigned to a fixed round count.
        require(0 <= stats["seconds"] < 29, "Time ceiling may have truncated fixed rounds")
        vectors[label] = sorted([r["sat"] for r in checks[6]["saturations"]], reverse=True)
        arms[label] = {"accepted": stats["accepted"], "attempted": stats["attempted"],
                       "budget_used": stats["budget_used"], "native_seconds": stats["seconds"],
                       "solution_sha256": digest(path / "solution.json"),
                       "maximum_load_error": error, "peak_saturation": str(vectors[label][0])}
    a, b = vectors["original"], vectors["released"]
    require(len(a) == len(b), "Different vector dimensions")
    first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
    return {"instance": name, "arms": arms, "load_count": len(a),
            "released_vs_original": "win" if b < a else "loss" if b > a else "tie",
            "first_difference_rank": None if first is None else first + 1,
            "first_values": None if first is None else {"original": str(a[first]), "released": str(b[first])}}

def execute_cases(screen: Path, released: Path, output: Path, benchmark: Path,
                  solver: Path, checker: Path) -> None:
    spec = importlib.util.spec_from_file_location("existing_fleet_benchmark", benchmark)
    require(spec is not None and spec.loader is not None, "Missing existing benchmark loader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output.mkdir(parents=True, exist_ok=False)
    environment = {k: v for k, v in os.environ.items()
                   if not k.startswith(("SEDGE_", "FLEET_", "CLOUD_"))}
    environment.update(SEDGE_SECONDS="30", SEDGE_MAX_ROUNDS="8")
    manifest = {"fixed_rounds": 8, "seconds_ceiling": 30,
                "solver_sha256": digest(solver), "checker_sha256": digest(checker),
                "benchmark_sha256": digest(benchmark), "cases": []}
    for name in CASES:
        files, starts = case_inputs(screen, released, name)
        order = ("original", "released") if name == "setB-07" else ("released", "original")
        for label in order:
            folder = output / name / label
            folder.mkdir(parents=True)
            env = {**environment, "CLOUD_INITIAL_SOLUTION": str(starts[label]),
                   "SEDGE_STATS": str(folder / "stats.json")}
            command = [solver, *files, folder / "solution.json"]
            _, wall = module.execute(command, folder, "solver", env=env, timeout=40)
            recorded = {"instance": name, "arm": label, "command": list(map(str, command)),
                        "incumbent_sha256": digest(starts[label]), "wall_seconds": wall,
                        "checker_commands": []}
            for precision in (6, 12):
                command = [checker, "--net", files[0], "--tm", files[1], "--scenario", files[2],
                           "--srpaths", folder / "solution.json", "--max-decimal-places", precision]
                module.execute(command, folder, f"checker-{precision}", timeout=90)
                recorded["checker_commands"].append(list(map(str, command)))
            manifest["cases"].append(recorded)
            (output / "EXECUTION.json").write_text(json.dumps(manifest, indent=2) + "\n")
        inspect_case(output, name)

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--execute", action="store_true", help="Run only these predeclared four calls; otherwise read saved results")
    for name in ("screen", "released", "benchmark", "solver", "checker"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    try:
        if args.execute:
            missing = [n for n in ("screen", "released", "benchmark", "solver", "checker") if getattr(args, n) is None]
            require(not missing, "Execution requires: " + ", ".join(missing))
            execute_cases(*(getattr(args, n).resolve() for n in ("screen", "released", "results", "benchmark", "solver", "checker")))
        report = {"schema": "date.released-budget-fixed-round-comparison.v1",
                  "results": [inspect_case(args.results.resolve(), name) for name in CASES],
                  "limits": ["One fixed-round public pair per predeclared case; no general or statistical superiority.",
                             "Fixed rounds are not equal attempted moves or equal elapsed time.",
                             "Initial route encoding and budget headroom jointly affect later search."]}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, allow_nan=False))

if __name__ == "__main__":
    main()
