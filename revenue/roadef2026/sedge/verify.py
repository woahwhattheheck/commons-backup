#!/usr/bin/env python3
"""Validate the solver against the independently built official checker."""
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
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=15)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--instances", nargs="*", default=[f"setB-{i:02}" for i in range(1, 13)])
    args = parser.parse_args()
    args.data = args.data.resolve()
    args.checker = args.checker.resolve()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parent
    empty = args.output / "empty-solution.json"
    empty.write_text('{"srpaths":[]}\n')

    def verify(name):
        folder = args.output / name
        folder.mkdir(exist_ok=True)
        prefix = args.data / name[:4] / name
        inputs = [Path(str(prefix) + suffix) for suffix in ("-net.json", "-tm.json", "-scenario.json")]
        solution = folder / "solution.json"
        stats_path = folder / "stats.json"
        env = dict(os.environ, SEDGE_SECONDS=str(args.seconds), SEDGE_STATS=str(stats_path))
        env.pop("SEDGE_MAX_ROUNDS", None)
        started = time.monotonic()
        result = checked([str(root / "run.sh"), *map(str, inputs), str(solution)], env=env)
        wall = time.monotonic() - started
        (folder / "solver.log").write_text(result.stderr)
        stats = json.loads(stats_path.read_text())

        def evaluate(path, decimals, label):
            result = checked([str(args.checker), "--net", str(inputs[0]), "--tm", str(inputs[1]),
                              "--scenario", str(inputs[2]), "--srpaths", str(path),
                              "--max-decimal-places", str(decimals)])
            (folder / (label + ".json")).write_text(result.stdout)
            value = json.loads(result.stdout)
            assert value["valid"] is True, (name, label, "invalid")
            return value

        actual = evaluate(solution, 12, "checker-12")
        ranking = evaluate(solution, 6, "checker-6")
        baseline = evaluate(empty, 6, "baseline-6")
        actual_loads = {(x["t"], x["from"], x["to"]): x["sat"] for x in actual["saturations"]}
        predicted = {(x["t"], x["from"], x["to"]): x["sat"] for x in stats["loads"]}
        assert predicted.keys() == actual_loads.keys(), (name, "different load keys")
        error = max(abs(actual_loads[key] - value) for key, value in predicted.items())
        assert error < 2e-9, (name, "load mismatch", error)
        assert sum(stats["budget_used"]) == actual["total_cost"], (name, "budget cost mismatch")
        initial = sorted((x["sat"] for x in baseline["saturations"]), reverse=True)
        final = sorted((x["sat"] for x in ranking["saturations"]), reverse=True)
        assert len(initial) == len(final) and final < initial, (name, "no official-ranked improvement")
        row = {
            "instance": name, "valid": True, "official_lexicographic_improvement": True,
            "baseline_mlu_6": initial[0], "final_mlu_6": final[0],
            "relative_mlu_reduction": 1 - final[0] / initial[0],
            "max_load_error": error, "loads_compared": len(predicted),
            "total_cost": actual["total_cost"], "budget_used": stats["budget_used"],
            "accepted_moves": stats["accepted"], "attempted_moves": stats["attempted"],
            "wall_seconds": wall, "solution_sha256": digest(solution),
            "inputs_sha256": {path.name: digest(path) for path in inputs},
        }
        (folder / "result.json").write_text(json.dumps(row, indent=2) + "\n")
        print(json.dumps(row), flush=True)
        return row

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(verify, args.instances))
    summary = {
        "solver_sha256": digest(root / "solver"), "source_sha256": digest(root / "main.cpp"),
        "checker_sha256": digest(args.checker), "seconds_per_trial": args.seconds,
        "workers": args.workers, "instances": rows,
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"PASS: {len(rows)} official instances; {sum(row['loads_compared'] for row in rows)} link/slot values")


if __name__ == "__main__":
    main()
