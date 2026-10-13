#!/usr/bin/env python3
"""Validate monotonic continuation against the official ROADEF checker."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked(command, *, env=None):
    result = subprocess.run(command, env=env, text=True, capture_output=True, timeout=180)
    if result.returncode:
        raise RuntimeError(f"Command failed: {command}\n{result.stdout}\n{result.stderr}")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--checker", type=Path, required=True)
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=2)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--instances", nargs="*", default=[f"setB-{i:02}" for i in range(1, 13)])
    args = parser.parse_args()
    args.data = args.data.resolve()
    args.checker = args.checker.resolve()
    args.baseline_dir = args.baseline_dir.resolve()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parent

    def evaluate(inputs, solution, decimals):
        result = checked([
            str(args.checker), "--net", str(inputs[0]), "--tm", str(inputs[1]),
            "--scenario", str(inputs[2]), "--srpaths", str(solution),
            "--max-decimal-places", str(decimals),
        ])
        value = json.loads(result.stdout)
        if value["valid"] is not True:
            raise AssertionError((solution, "invalid"))
        return value

    def verify(name):
        folder = args.output / name
        folder.mkdir(exist_ok=True)
        prefix = args.data / name[:4] / name
        inputs = [Path(str(prefix) + suffix) for suffix in ("-net.json", "-tm.json", "-scenario.json")]
        incumbent = args.baseline_dir / name / "solution.json"
        solution = folder / "solution.json"
        stats_path = folder / "stats.json"
        env = dict(os.environ, SEDGE_SECONDS=str(args.seconds), SEDGE_STATS=str(stats_path))
        env.pop("SEDGE_MAX_ROUNDS", None)
        started = time.monotonic()
        result = checked([str(root / "run.sh"), *map(str, inputs), str(incumbent), str(solution)], env=env)
        wall = time.monotonic() - started
        (folder / "solver.log").write_text(result.stderr)
        stats = json.loads(stats_path.read_text())
        if stats.get("resumed") is not True:
            raise AssertionError((name, "optimizer did not report resumed state"))

        before = evaluate(inputs, incumbent, 6)
        after = evaluate(inputs, solution, 6)
        exact = evaluate(inputs, solution, 12)
        before_loads = sorted((x["sat"] for x in before["saturations"]), reverse=True)
        after_loads = sorted((x["sat"] for x in after["saturations"]), reverse=True)
        if after_loads > before_loads:
            raise AssertionError((name, "official ranking regressed"))
        first = next((i for i, pair in enumerate(zip(before_loads, after_loads)) if pair[0] != pair[1]), None)
        predicted = {(x["t"], x["from"], x["to"]): x["sat"] for x in stats["loads"]}
        actual = {(x["t"], x["from"], x["to"]): x["sat"] for x in exact["saturations"]}
        if predicted.keys() != actual.keys():
            raise AssertionError((name, "different load keys"))
        error = max(abs(actual[key] - value) for key, value in predicted.items())
        if error >= 2e-9:
            raise AssertionError((name, "load mismatch", error))
        if sum(stats["budget_used"]) != exact["total_cost"]:
            raise AssertionError((name, "budget cost mismatch"))
        row = {
            "instance": name,
            "valid": True,
            "official_non_regression": True,
            "strict_improvement": after_loads < before_loads,
            "first_changed_rank": first,
            "before_at_first_change": None if first is None else before_loads[first],
            "after_at_first_change": None if first is None else after_loads[first],
            "before_mlu_6": before_loads[0],
            "after_mlu_6": after_loads[0],
            "accepted_moves": stats["accepted"],
            "attempted_moves": stats["attempted"],
            "total_cost": exact["total_cost"],
            "max_load_error": error,
            "wall_seconds": wall,
            "incumbent_sha256": digest(incumbent),
            "solution_sha256": digest(solution),
        }
        (folder / "result.json").write_text(json.dumps(row, indent=2) + "\n")
        print(json.dumps(row), flush=True)
        return row

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(verify, args.instances))
    summary = {
        "solver_sha256": digest(root / "solver"),
        "source_sha256": digest(root / "main.cpp"),
        "checker_sha256": digest(args.checker),
        "seconds_per_continuation": args.seconds,
        "workers": args.workers,
        "strict_improvements": sum(row["strict_improvement"] for row in rows),
        "instances": rows,
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"PASS: {len(rows)} valid non-regressions; {summary['strict_improvements']} strict improvements")


if __name__ == "__main__":
    main()
