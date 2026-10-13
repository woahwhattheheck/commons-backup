#!/usr/bin/env python3
"""Independent checker checks for ECMP, zero budgets, repeatability, and SIGTERM."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checker", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    checker = args.checker.resolve()
    data = args.data.resolve()
    # Three equal-cost complete paths, but the first branch gets one half,
    # not one third: ECMP splits by outgoing link at each forwarding node.
    ids = [101 + 10 * i for i in range(7)]
    pairs = [(0, 1), (0, 2), (1, 3), (2, 4), (2, 5), (3, 6), (4, 6), (5, 6)]
    links = []
    for a, b in pairs:
        for u, v in [(a, b), (b, a)]:
            links.append({"id": len(links), "from": ids[u], "to": ids[v],
                          "metric": 1, "capacity": 100})
    net = {"directed": True, "multigraph": False,
           "nodes": [{"id": i, "name": f"n{i}"} for i in ids], "links": links}
    tm = {"num_time_slots": 2, "demands": [{"s": ids[0], "t": ids[6], "v": [100, 100]}]}
    scenario = {"max_segments": 4, "budget": [{"t": 1, "value": 0}],
                "interventions": [{"t": 1, "links": [links[0]["id"]]}]}
    inputs = []
    for name, value in [("net", net), ("tm", tm), ("scenario", scenario)]:
        path = output / ("ecmp-" + name + ".json")
        path.write_text(json.dumps(value, indent=2) + "\n")
        inputs.append(path)

    def run(paths, target, *, rounds=None, seconds=20):
        env = dict(os.environ, SEDGE_SECONDS=str(seconds))
        env.pop("SEDGE_STATS", None)
        env.pop("SEDGE_MAX_ROUNDS", None)
        if rounds is not None:
            env["SEDGE_MAX_ROUNDS"] = str(rounds)
        return subprocess.run([str(root / "run.sh"), *map(str, paths), str(target)],
                              env=env, capture_output=True, text=True, check=True, timeout=35)

    def evaluate(paths, target):
        result = subprocess.run([str(checker), "--net", str(paths[0]), "--tm", str(paths[1]),
                                 "--scenario", str(paths[2]), "--srpaths", str(target)],
                                text=True, capture_output=True, check=True, timeout=30)
        value = json.loads(result.stdout)
        assert value["valid"] is True
        return value

    baseline = output / "ecmp-baseline.json"
    run(inputs, baseline, rounds=0)
    actual = evaluate(inputs, baseline)
    loads = {(x["t"], x["from"], x["to"]): x["sat"] for x in actual["saturations"]}
    for (t, a, b), expected in {
        (0, 0, 1): 0.5, (0, 0, 2): 0.5, (0, 2, 4): 0.25,
        (0, 2, 5): 0.25, (1, 0, 1): 0, (1, 0, 2): 1,
        (1, 2, 4): 0.5, (1, 2, 5): 0.5,
    }.items():
        assert abs(loads[t, ids[a], ids[b]] - expected) < 1e-10
    optimized = output / "ecmp-optimized.json"
    run(inputs, optimized, rounds=10)
    assert evaluate(inputs, optimized)["total_cost"] == 0

    prefix = data / "setB" / "setB-01"
    regular_inputs = [Path(str(prefix) + suffix) for suffix in ("-net.json", "-tm.json", "-scenario.json")]
    repeat = []
    for i in range(2):
        target = output / f"repeat-{i}.json"
        run(regular_inputs, target, rounds=4, seconds=100)
        repeat.append(target.read_bytes())
    assert repeat[0] == repeat[1], "Fixed-round runs differ"
    evaluate(regular_inputs, output / "repeat-0.json")

    # Quoted paths survive the shell wrapper; exec lets SIGTERM reach the solver.
    spaced = output / "paths with spaces"
    spaced.mkdir(exist_ok=True)
    target = spaced / "saved result.json"
    env = dict(os.environ, SEDGE_SECONDS="565")
    env.pop("SEDGE_STATS", None)
    env.pop("SEDGE_MAX_ROUNDS", None)
    process = subprocess.Popen([str(root / "run.sh"), *map(str, regular_inputs), str(target)],
                               env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert process.stderr.readline().startswith("Loaded "), "Initialization failed"
    assert target.exists(), "No incumbent written before search"
    started = time.monotonic()
    process.send_signal(signal.SIGTERM)
    stdout, stderr = process.communicate(timeout=10)
    latency = time.monotonic() - started
    assert process.returncode == 0, (process.returncode, stdout, stderr)
    evaluate(regular_inputs, target)
    summary = {
        "unequal_branch_ecmp": "pass", "noncontiguous_node_ids": "pass",
        "intervention_recomputes_forwarding": "pass", "zero_change_budget": "pass",
        "fixed_round_repeatability": "pass", "quoted_output_path": "pass",
        "sigterm_valid_output": "pass", "sigterm_exit_seconds": latency,
        "repeat_solution_sha256": hashlib.sha256(repeat[0]).hexdigest(),
        "solver_sha256": hashlib.sha256((root / "solver").read_bytes()).hexdigest(),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
