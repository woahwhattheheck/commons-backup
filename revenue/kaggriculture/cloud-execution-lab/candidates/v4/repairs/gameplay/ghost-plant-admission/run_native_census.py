# SPDX-License-Identifier: Apache-2.0
"""Census ghost-row PLANT poisoning on an authenticated native artifact.

This is a diagnostic field runner, not a production composer.  It deliberately
uses the official interpreter directly because the historical evaluator loader
rejects surplus raw hand rows even though the engine accepts and semantically
counts them during atomic PLANT validation.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

from ghost_plant_admission import repair_ghost_plant_poisoning

ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"
LOADER_BLOB = "23948e10cfc3d32f46c9abb1321b0d8fc8db21d5"


def git_blob(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def load_fixture(root):
    root = Path(root)
    engine_root = root / "checks/reference/engine"
    loader_path = root / "checks/reference/evaluator/loader.py"
    if git_blob((engine_root / "kaggriculture.py").read_bytes()) != ENGINE_BLOB:
        raise RuntimeError("official engine fixture changed")
    if git_blob(loader_path.read_bytes()) != LOADER_BLOB:
        raise RuntimeError("offline loader source changed")
    spec = importlib.util.spec_from_file_location("seedghost_census_loader", loader_path)
    loader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loader)
    engine, _ = loader.get_engine(engine_root)
    return loader, engine


def load_main(root):
    name = "seedghost_native_main_" + str(time.time_ns())
    spec = importlib.util.spec_from_file_location(name, Path(root) / "main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.agent


def plant_counts(action, live_hands=None):
    hands = action.get("hands", [])
    if live_hands is not None:
        hands = hands[:live_hands]
    rows = [action.get("farmer", ["PASS"]), *hands]
    out = {}
    for row in rows:
        if isinstance(row, list) and len(row) >= 2 and row[0] == "PLANT" and isinstance(row[1], str):
            out[row[1]] = out.get(row[1], 0) + 1
    return out


def fresh_world(loader, engine, seed, agents=2):
    cfg = loader.Struct({k: v.get("default") if isinstance(v, dict) else v
                         for k, v in engine.specification["configuration"].items()})
    cfg.seed = seed
    env = loader.Struct(configuration=cfg, done=False, info={})
    state = [loader.Struct(observation=loader.Struct(), action={}, status="ACTIVE", reward=0)
             for _ in range(agents)]
    engine.interpreter(state, env)
    return cfg, env, state


def run_game(root, loader, engine, seed, seat, enabled):
    cfg, env, state = fresh_world(loader, engine, seed)
    candidate = load_main(root)
    action_hash = hashlib.sha256()
    state_hash = hashlib.sha256()
    surplus_callbacks = ghost_plants = changes = 0
    certified_hits = []
    max_surplus = 0
    for step in range(cfg.episodeSteps):
        for player, item in enumerate(state):
            item.observation.step = step
            if player == seat:
                returned = candidate(copy.deepcopy(item.observation), cfg)
                live = len(item.observation.farms[player]["hands"])
                hands = returned.get("hands", [])
                if len(hands) > live:
                    surplus_callbacks += 1
                    max_surplus = max(max_surplus, len(hands) - live)
                    ghost_plants += sum(
                        isinstance(row, list) and len(row) >= 2 and row[0] == "PLANT"
                        for row in hands[live:])
                if enabled:
                    transformed, report = repair_ghost_plant_poisoning(
                        item.observation, returned, enabled=True)
                    if report["changed"]:
                        changes += 1
                        certified_hits.append({"step": step, "report": report})
                    returned = transformed
                action_hash.update(json.dumps(returned, sort_keys=True, separators=(",", ":")).encode())
                item.action = returned
            else:
                item.action = engine.starter_agent(copy.deepcopy(item.observation))
        engine.interpreter(state, env)
        snapshot = {"farms": state[0].observation.farms,
                    "market": state[0].observation.market,
                    "town": state[0].observation.town,
                    "private": state[seat].observation.private}
        state_hash.update(json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode())
        if any(item.status == "DONE" for item in state):
            break
    return {"seed": seed, "seat": seat, "enabled": enabled, "steps": step + 1,
            "bank": [item.reward for item in state],
            "surplus_callbacks": surplus_callbacks, "max_surplus": max_surplus,
            "ghost_plant_rows": ghost_plants, "changes": changes,
            "certified_hits": certified_hits,
            "action_hash": action_hash.hexdigest(), "state_hash": state_hash.hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--seeds", default="11,17,101")
    parser.add_argument("--parity-seeds", default="17,101")
    args = parser.parse_args()
    root = Path(args.runtime).resolve()
    sys.path.insert(0, str(root))
    loader, engine = load_fixture(root)
    seeds = [int(x) for x in args.seeds.split(",") if x]
    parity = {int(x) for x in args.parity_seeds.split(",") if x}
    rows = []
    for seed in seeds:
        for seat in (0, 1):
            off = run_game(root, loader, engine, seed, seat, False)
            rows.append(off)
            if seed in parity:
                on = run_game(root, loader, engine, seed, seat, True)
                rows.append(on)
                if not (off["bank"] == on["bank"] and
                        off["action_hash"] == on["action_hash"] and
                        off["state_hash"] == on["state_hash"]):
                    raise RuntimeError(f"ON/OFF parity failed seed={seed} seat={seat}")
    report = {"engine_blob": ENGINE_BLOB, "loader_blob": LOADER_BLOB,
              "runtime_main_blob": git_blob((root / "main.py").read_bytes()),
              "runtime_blob": git_blob((root / "titan_runtime.py").read_bytes()),
              "rows": rows}
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"rows": len(rows),
                      "changes": sum(row["changes"] for row in rows if row["enabled"]),
                      "ghost_plant_rows": sum(row["ghost_plant_rows"] for row in rows if not row["enabled"]),
                      "surplus_callbacks": sum(row["surplus_callbacks"] for row in rows if not row["enabled"])},
                     sort_keys=True))


if __name__ == "__main__":
    main()
