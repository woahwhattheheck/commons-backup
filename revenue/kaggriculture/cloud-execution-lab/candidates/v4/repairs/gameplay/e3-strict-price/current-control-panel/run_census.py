# SPDX-License-Identifier: Apache-2.0
"""Execute the pinned offline evaluator without modifying its game driver."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time


def blob(path):
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    plan = json.loads(args.plan.read_text())
    if plan["episode_steps"] != 720 or plan["seats"] != [0, 1]:
        raise ValueError("This census requires full 720-step episodes and both physical seats")
    if len(plan["seeds"]) != len(set(plan["seeds"])):
        raise ValueError("Duplicate planned seeds")
    for rel, expected in plan["required_blobs"].items():
        if blob(root / rel) != expected:
            raise ValueError("Source pin mismatch: " + rel)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    evaluator_path = root / "checks/reference/evaluator/evaluate.py"
    loader = root / "checks/reference/evaluator/loader.py"
    cache = root / "checks/reference/engine"
    evaluator = load(evaluator_path, "_e3_original_evaluator")
    engine, engine_hashes = evaluator.get_engine(cache, loader)
    source = {str(p.relative_to(root)): {"git_blob": blob(p), "bytes": p.stat().st_size}
              for p in sorted(root.rglob("*"))
              if p.is_file() and p.suffix in (".py", ".json") and "__pycache__" not in p.parts}
    (output / "SOURCE.json").write_text(json.dumps(source, sort_keys=True, indent=2) + "\n")
    (output / "PLAN.json").write_bytes(args.plan.read_bytes())
    baseline = str(root / "main.py")
    wrapper = str(Path(__file__).with_name("trace_current.py"))
    games = []
    started = time.time()
    for seed in plan["seeds"]:
        for seat in plan["seats"]:
            trace_path = output / (str(seed) + "-" + str(seat) + ".jsonl")
            pair = [baseline, baseline]
            if not args.baseline:
                # The official evaluator deliberately sanitizes worker env.
                # Use an explicit data-only adapter; do not weaken isolation.
                adapter = output / (str(seed) + "-" + str(seat) + "-observer.py")
                adapter.write_text(
                    "import importlib.util\n"
                    + "s=importlib.util.spec_from_file_location('_e3_observer', " + repr(wrapper) + ")\n"
                    + "m=importlib.util.module_from_spec(s)\ns.loader.exec_module(m)\n"
                    + "m.setup(" + repr(str(root)) + ", " + repr(str(trace_path)) + ")\n"
                    + "agent=m.agent\n")
                pair[seat] = str(adapter)
            game = evaluator.play(
                engine, pair, cache, loader, seed, seat,
                rng_seed=plan["agent_rng_seed"],
                action_timeout=plan["action_rpc_seconds"],
                startup_timeout=plan["startup_seconds"],
                game_timeout=plan["game_seconds"], episode_steps=720)
            game["opponent"] = "same-current-canonical"
            game["mode"] = "uninstrumented" if args.baseline else "observed"
            games.append(game)
            report = {"schema": "titan.e3.current-residual-execution.v1",
                      "plan_sha256": hashlib.sha256(args.plan.read_bytes()).hexdigest(),
                      "source_sha256": hashlib.sha256((output / "SOURCE.json").read_bytes()).hexdigest(),
                      "engine_sha256": engine_hashes,
                      "evaluator_blob": blob(evaluator_path), "loader_blob": blob(loader),
                      "observer_blob": blob(Path(wrapper)), "runner_blob": blob(Path(__file__)),
                      "python": sys.version, "started_unix": started, "games": games}
            (output / "GAMES.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
            print(json.dumps({key: game[key] for key in
                              ("seed", "candidate_seat", "status", "scores", "steps", "failure", "wall_seconds")}), flush=True)
    return int(any(game["status"] != "complete" for game in games))


if __name__ == "__main__":
    raise SystemExit(main())
