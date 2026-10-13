# SPDX-License-Identifier: Apache-2.0
"""Offline EXEC-PACE-2 sensor oracle; no policy, router, or activation writes.

Replays unmodified official-interpreter observations through the exact recovered
sensor and an optional source-pinned candidate. Valid sequential paths must match
an independent 25-step reference. Injected invalid prices are CHARACTERIZATION,
not real-game observations or an economic gate. Only supplied local code executes.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import importlib.util
import json
import math
import random
import sys
import types
from pathlib import Path
from typing import Any, Callable

ENGINE_BLOBS = {
    "kaggriculture.py": "3c202c7ee921da239356789e266b694635103fc4",
    "kaggriculture.json": "b354d06b742fe48402513792253f1a5c29366b20",
    "utils.py": "91c8822ee6201ba4a5a8416c7dbe34f95dd61c87",
}
DONOR_BLOB = "0ef551145dbcac9884e7d1710bcf11238dafc504"
GOODS = ("WOOL", "MILK", "STRAWBERRY", "MELON", "EGG", "CARROT", "TOMATO")
MODES = ("pass-pass", "starter-starter", "market-cycle")
WINDOW = 25
THRESHOLD = 0.03


class CheckFailure(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise CheckFailure(message)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def identity(path):
    data = Path(path).read_bytes()
    return {"bytes": len(data), "git_blob": hashlib.sha1(
        b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest(),
        "sha256": hashlib.sha256(data).hexdigest()}


def checked(path, expected):
    receipt = identity(path)
    require(receipt["git_blob"] == expected, f"source mismatch: {path}")
    return receipt


def import_file(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Struct(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None

    def __setattr__(self, key, value):
        self[key] = value


def load_engine(root):
    root = Path(root)
    pins = {name: checked(root / name, blob) for name, blob in ENGINE_BLOBS.items()}
    parsed = ast.parse((root / "utils.py").read_text())
    helpers = [node for node in parsed.body if isinstance(node, ast.FunctionDef)
               and node.name == "resolve_episode_seed"]
    require(len(helpers) == 1, "upstream seed helper is not unique")
    namespace = {"Any": Any, "Callable": Callable, "random": random}
    exec(compile(ast.Module(body=helpers, type_ignores=[]), "pinned_seed_helper", "exec"), namespace)
    package = types.ModuleType("kaggle_environments")
    utils = types.ModuleType("kaggle_environments.utils")
    utils.resolve_episode_seed = namespace["resolve_episode_seed"]
    previous = {key: sys.modules.get(key) for key in
                ("kaggle_environments", "kaggle_environments.utils")}
    try:
        sys.modules["kaggle_environments"] = package
        sys.modules["kaggle_environments.utils"] = utils
        engine = import_file(root / "kaggriculture.py", "exec_pace_official_engine")
    finally:
        for key, value in previous.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value
    return engine, pins


def action_for(engine, observation, mode, step, seat):
    if mode == "starter-starter" or (mode == "market-cycle" and seat == 1):
        return engine.starter_agent(observation)
    action = {"farmer": ["PASS"], "hands": [], "market": []}
    if mode == "market-cycle":
        good = GOODS[(step // 2) % len(GOODS)]
        shed = observation["private"]["shed"]
        if shed.get(good, 0):
            action["market"] = [["SELL", good, shed[good]]]
        elif observation["farms"][seat]["money"] >= observation["market"]["prices"][good]:
            action["market"] = [["BUY_PRODUCT", good, 1]]
    return action


def check_observation(module, observation, histories, context):
    before = encoded(observation)
    module.note_prices(observation)
    require(encoded(observation) == before, context + ": sensor mutated observation")
    rising_count = 0
    for good in GOODS:
        price = observation["market"]["prices"][good]
        require(type(price) in (int, float) and math.isfinite(price) and price >= 1,
                context + ": unexpected official price domain")
        window = histories[good]
        window.append(float(price))
        del window[:-WINDOW]
        expected = None if len(window) < WINDOW else (window[-1] - window[0]) / (WINDOW - 1)
        actual = module.slope(good)
        require(actual == expected, f"{context}:{good}: slope {actual!r} != {expected!r}")
        expected_rising = expected is not None and expected > THRESHOLD
        require(module.rising(good) is expected_rising, context + ": rising mismatch " + good)
        rising_count += expected_rising
    return rising_count


def run_game(engine, modules, seed, mode):
    cfg = Struct({key: value.get("default") if isinstance(value, dict) else value
                  for key, value in engine.specification["configuration"].items()})
    cfg.seed = seed
    env = Struct(configuration=cfg, done=False, info={})
    state = [Struct(observation=Struct(), action={}, status="ACTIVE", reward=0)
             for _ in range(2)]
    engine.interpreter(state, env)
    histories = {}
    activations = {}
    for label, pair in modules.items():
        histories[label] = [{good: [] for good in GOODS} for _ in range(2)]
        activations[label] = [0, 0]
        for module in pair:
            module.reset()
    observation_digest = hashlib.sha256()
    action_digest = hashlib.sha256()
    for step in range(cfg.episodeSteps):
        for seat, item in enumerate(state):
            item.observation.step = step
            observation = copy.deepcopy(item.observation)
            observation_digest.update(encoded({"seat": seat, "observation": observation}) + b"\n")
            for label, pair in modules.items():
                activations[label][seat] += check_observation(pair[seat], copy.deepcopy(observation),
                    histories[label][seat], f"{mode}/{seed}/{seat}/{step}/{label}")
            item.action = action_for(engine, observation, mode, step, seat)
            action_digest.update(encoded({"step": step, "seat": seat, "action": item.action}) + b"\n")
        engine.interpreter(state, env)
        if any(item.status == "DONE" for item in state):
            break
    require([item.status for item in state] == ["DONE", "DONE"], "incomplete episode")
    require(step + 1 == cfg.episodeSteps - 1, "unexpected framework callback count")
    return {"seed": seed, "mode": mode, "steps": step + 1, "seats": [0, 1],
            "observation_sha256": observation_digest.hexdigest(),
            "action_sha256": action_digest.hexdigest(), "rising_good_callbacks": activations,
            "terminal_rewards_harness_only": [item.reward for item in state]}


def safe_value(value):
    if type(value) is float and not math.isfinite(value):
        return repr(value)
    return value


def characterize_invalid_prices(module):
    """Synthetic single-good corruption, deliberately separate from game parity."""
    values = [("positive_inf", float("inf")), ("negative_inf", float("-inf")),
              ("nan", float("nan")), ("null", None), ("bool", True),
              ("numeric_string", "3.4"), ("missing", None), ("negative", -1)]
    rows = []
    for good in GOODS:
        for position in (0, 24):
            for label, value in values:
                module.reset()
                for step in range(WINDOW):
                    prices = {item: 1 + 0.1 * step for item in GOODS}
                    if step == position:
                        if label == "missing":
                            prices.pop(good)
                        else:
                            prices[good] = value
                    module.note_prices({"step": step, "market": {"prices": prices}})
                value = module.slope(good)
                rising = module.rising(good)
                rows.append({"good": good, "bad_position": position, "fault": label,
                             "slope": safe_value(value), "rising": rising,
                             "window_invalidated": value is None and rising is False})
    return {"scope": "synthetic malformed-input characterization, not natural gameplay",
            "cells": len(rows), "invalidated": sum(row["window_invalidated"] for row in rows),
            "rows": rows}


def run(engine_dir, donor, candidate=None, candidate_blob=None, seeds=(1, 17, 101)):
    require(bool(candidate) == bool(candidate_blob), "candidate path and exact blob must be supplied together")
    require(len(set(seeds)) == len(seeds) and len(seeds) > 0, "seeds must be nonempty and unique")
    engine, engine_pins = load_engine(engine_dir)
    pins = {"donor": checked(donor, DONOR_BLOB)}
    paths = {"donor": Path(donor)}
    if candidate:
        pins["candidate"] = checked(candidate, candidate_blob)
        paths["candidate"] = Path(candidate)
    modules = {label: [import_file(path, f"exec_pace_{label}_{seat}") for seat in range(2)]
               for label, path in paths.items()}
    games = [run_game(engine, modules, seed, mode) for seed in seeds for mode in MODES]
    callbacks = sum(game["steps"] * 2 for game in games)
    faults = {label: characterize_invalid_prices(pair[0]) for label, pair in modules.items()}
    return {"schema": "exec-pace-official-observation-oracle/v1", "status": "PASS",
            "scope": "sensor only; no TITAN router, hosted runner, policy alteration, or economic inference",
            "oracle": identity(__file__), "engine": engine_pins, "modules": pins,
            "planned": {"seeds": list(seeds), "modes": list(MODES), "seats": [0, 1]},
            "games": games, "observation_callbacks_per_module": callbacks,
            "good_checks_per_module": callbacks * len(GOODS),
            "synthetic_fault_characterization": faults}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-dir", required=True, type=Path)
    parser.add_argument("--donor", type=Path, default=Path(__file__).parent / "raw" / "r04_exec_adaptive.py")
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--candidate-blob")
    parser.add_argument("--seeds", default="1,17,101")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        protected = [args.donor, Path(__file__), *(args.engine_dir / name for name in ENGINE_BLOBS)]
        if args.candidate:
            protected.append(args.candidate)
        require(args.output.resolve() not in {path.resolve() for path in protected}, "output overwrites source")
        report = run(args.engine_dir, args.donor, args.candidate, args.candidate_blob,
                     tuple(int(value) for value in args.seeds.split(",")))
        temporary = args.output.with_name(args.output.name + ".tmp")
        require(not temporary.exists(), "temporary output already exists")
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n")
        temporary.replace(args.output)
        print(json.dumps({"status": "PASS", "games": len(report["games"]),
              "observations_per_module": report["observation_callbacks_per_module"],
              "good_checks_per_module": report["good_checks_per_module"],
              "output_sha256": identity(args.output)["sha256"]}, sort_keys=True))
        return 0
    except (CheckFailure, OSError, ValueError, TypeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
