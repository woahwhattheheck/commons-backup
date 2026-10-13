# SPDX-License-Identifier: Apache-2.0
"""Execute route-library cases with the pinned, unmodified official interpreter.

Synthetic fixed states, not game panels. The full two-player evaluator state is
kept here only; it is not passed to a runtime agent. No network or new game seed.
"""
from __future__ import annotations
import argparse
import ast
import base64
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys
import time
import types
from typing import Any, Callable

from route_frontier import (Alternative, BoundRoute, Incompatible, exact_key,
                            kernel_model, pareto_frontier, rollout, splice)

ENGINE_REF = "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c"
ENGINE_HASHES = {
    "kaggriculture.py": "bc8a54879ef02c7ea64b8b333d6a976f0ea65c4949149d01f463f23bccee653e",
    "kaggriculture.json": "a82c89c1a2315b93f39775d8e025471a01b738647c9772658368ee6b1b6f4867",
    "utils.py": "537b627b11784d424147ef57ebb0369b039bf83c9f891e81f10486b1f552334b",
}
KERNEL_BLOB = "d05b35057509ed706679c0c841a81ffba05a9936"


class Struct(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None

    def __setattr__(self, key, value):
        self[key] = value


def load_module(file: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_engine(root: Path):
    hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
              for name in ENGINE_HASHES}
    if hashes != ENGINE_HASHES:
        raise ValueError("engine files differ from the recorded source pin")
    tree = ast.parse((root / "utils.py").read_text())
    helper = next(node for node in tree.body
                  if isinstance(node, ast.FunctionDef) and node.name == "resolve_episode_seed")
    namespace = {"Any": Any, "Callable": Callable, "random": random}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(root / "utils.py"), "exec"), namespace)
    package = types.ModuleType("kaggle_environments")
    utils = types.ModuleType("kaggle_environments.utils")
    utils.resolve_episode_seed = namespace["resolve_episode_seed"]
    previous = {name: sys.modules.get(name) for name in (package.__name__, utils.__name__)}
    sys.modules[package.__name__] = package
    sys.modules[utils.__name__] = utils
    try:
        return load_module(root / "kaggriculture.py", "bridge_official_engine")
    finally:
        for name, value in previous.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


def fixture(engine, *, step=716, seat=0):
    config = {key: value.get("default") if isinstance(value, dict) else value
              for key, value in engine.specification["configuration"].items()}
    # No initialization/random game draw is run. Cases finish before EOD.
    return {"step": step, "seat": seat,
            "farms": [engine._new_farm(10, 0), engine._new_farm(10, 0)],
            "privates": [engine._new_private(), engine._new_private()],
            "market": engine._new_market(), "town": engine._new_town(),
            "config": config, "info": {"seed": 0},
            "done": False, "status": ["ACTIVE", "ACTIVE"], "reward": [0, 0]}


def advance_factory(engine, rival_stream=None):
    rival_stream = deepcopy(rival_stream or {})

    def advance(snapshot, own_action):
        data = deepcopy(snapshot)
        if data["done"]:
            raise Incompatible("no transition exists after interpreter DONE")
        step, seat = data["step"], data["seat"]
        env = Struct(configuration=Struct(data["config"]), done=False, info=data["info"])
        actions = [None, None]
        actions[seat] = deepcopy(own_action)
        actions[1 - seat] = deepcopy(rival_stream.get(step, action()))
        states = [Struct(observation=Struct(
            step=step, player=i, private=data["privates"][i], farms=data["farms"],
            market=data["market"], town=data["town"],
            day=step // data["config"]["turnsPerDay"],
            hour=step % data["config"]["turnsPerDay"]), action=actions[i],
            status=data["status"][i], reward=data["reward"][i]) for i in (0, 1)]
        engine.interpreter(states, env)
        data["step"] += 1
        data["status"] = [s.status for s in states]
        data["reward"] = [s.reward for s in states]
        data["done"] = any(s.status == "DONE" for s in states)
        return data
    return advance


def action(unit="PASS", market=None):
    return {"farmer": [unit] if isinstance(unit, str) else unit,
            "hands": [], "market": market or []}


def money(trace, seat, index=-1):
    return trace.state(index)["farms"][seat]["money"]


def incompatible_splice(prefix, suffix):
    try:
        splice(prefix, suffix)
    except Incompatible:
        return True
    return False


def run(engine, kernel=None):
    start = time.perf_counter()
    results, evidence, timings = [], [], []
    for seat in (0, 1):
        context = exact_key({"engine": ENGINE_REF, "seat": seat, "rival": "PASS", "scenario": "fixed-state"})
        advance = advance_factory(engine)
        initial = fixture(engine, seat=seat)
        initial["privates"][seat]["inventories"][0] = {"MILK": 2}
        initial["town"]["unlocked_shops"] = ["PIZZA_SHOP"] * 4
        early_actions = [action("DROP", [["SELL", "MILK", 2]]), action(), action()]
        late_actions = [action(), action(), action("DROP", [["SELL", "MILK", 2]])]
        early = rollout("early", initial, early_actions, advance, context=context)
        late = rollout("late", initial, late_actions, advance, context=context)
        alternatives = [Alternative(t.name, (t,), ("terminal_cash", "cash_after_716"),
                                    ((money(t, seat), money(t, seat, 1)),),
                                    ("DONE",), "terminal-no-continuation") for t in (early, late)]
        frontier = pareto_frontier(alternatives)
        assert len(frontier.kept) == 2 and not frontier.approximate
        assert money(late, seat) > money(early, seat) > money(late, seat, 1)
        unconstrained = max(frontier.kept, key=lambda a: a.values[0][0]).name
        funded = max((a for a in frontier.kept if a.values[0][1] >= 100),
                     key=lambda a: a.values[0][0]).name
        assert (unconstrained, funded) == ("late", "early")
        # Exact-match prefix/suffix composition equals a direct full execution.
        prefix = rollout("first", initial, early_actions[:1], advance, context=context)
        suffix = rollout("rest", prefix.state(), early_actions[1:], advance, context=context)
        composed = splice(prefix, suffix)
        assert composed.snapshots == early.snapshots and composed.actions == early.actions
        bound = BoundRoute(early)
        for i in range(3):
            tick = time.perf_counter()
            assert bound.act(early.state(i), action()) == early.action(i)
            assert bound.act(early.state(i), action()) == early.action(i)
            timings.append(time.perf_counter() - tick)
        assert bound.act(early.state(), action()) == action() and bound.status == "complete"
        # A different worker position makes a previously profitable suffix fail.
        moving = fixture(engine, step=714, seat=seat)
        moving["privates"][seat]["inventories"][0] = {"MILK": 2}
        west = rollout("west", moving, [action("WEST")], advance, context=context)
        expected = west.state()
        expected["farms"][seat]["farmer"] = list(engine._default_spawn(10))
        drop = rollout("drop-at-shed", expected, [action("DROP", [["SELL", "MILK", 2]])], advance, context=context)
        naive = rollout("incompatible-naive", west.state(), [drop.action()], advance, context=context)
        assert incompatible_splice(west, drop) and money(naive, seat) == 0 < money(drop, seat)
        recovery = rollout("return-and-drop", west.state(),
                           [action("EAST"), drop.action()], advance, context=context)
        recovered = splice(west, recovery)
        assert money(recovered, seat) == money(drop, seat)
        # An identical position is insufficient when the seed prerequisite differs.
        empty = fixture(engine, step=714, seat=seat)
        empty_prefix = rollout("empty-prefix", empty, [action()], advance, context=context)
        seeded = empty_prefix.state()
        seeded["privates"][seat]["seeds"]["WHEAT"] = 1
        plant = rollout("plant", seeded, [action(["PLANT", "WHEAT"])], advance, context=context)
        no_seed = rollout("no-seed-naive", empty_prefix.state(), [plant.action()], advance, context=context)
        x, y = engine._default_spawn(10)
        assert incompatible_splice(empty_prefix, plant)
        assert no_seed.state()["farms"][seat]["tiles"][y][x] is None
        assert plant.state()["farms"][seat]["tiles"][y][x]["crop"] == "WHEAT"
        # Mapping order is executable state: the first carried good takes last room.
        order_state = fixture(engine, step=714, seat=seat)
        order_state["privates"][seat]["shed"]["WHEAT"] = 99
        order_state["privates"][seat]["inventories"][0] = {"MILK": 1, "WOOL": 1}
        reversed_state = deepcopy(order_state)
        reversed_state["privates"][seat]["inventories"][0] = {"WOOL": 1, "MILK": 1}
        assert json.dumps(order_state, sort_keys=True) == json.dumps(reversed_state, sort_keys=True)
        assert exact_key(order_state) != exact_key(reversed_state)
        orders = [action("DROP", [["SELL", "MILK", 1], ["SELL", "WOOL", 1]])]
        milk_first = rollout("milk-first", order_state, orders, advance, context=context)
        wool_first = rollout("wool-first", reversed_state, orders, advance, context=context)
        assert (money(milk_first, seat), money(wool_first, seat)) == (160, 200)
        live = BoundRoute(milk_first)
        fallback = action("PASS", [["BUY_SEED", "WHEAT", 1]])
        assert live.act(reversed_state, fallback) == fallback and live.status == "state_mismatch"
        # Exact endpoint dominance: zero-profit SELL/BUY vs idle, same final state.
        liquid = fixture(engine, step=714, seat=seat)
        liquid["farms"][seat]["money"] = 100.0
        liquid["privates"][seat]["shed"]["WHEAT"] = 1
        cycle = rollout("temporary-liquidity", liquid,
                        [action(market=[["SELL", "WHEAT", 1]]),
                         action(market=[["BUY_PRODUCT", "WHEAT", 1]])], advance, context=context)
        idle = rollout("idle", liquid, [action(), action()], advance, context=context)
        assert cycle.exit == idle.exit
        exact_alts = [Alternative(t.name, (t,), ("cash_after_first", "terminal_cash"),
                                  ((money(t, seat, 1), money(t, seat)),)) for t in (cycle, idle)]
        exact_frontier = pareto_frontier(exact_alts)
        assert [a.name for a in exact_frontier.kept] == [cycle.name]
        # Last executable market: a suffix cannot resurrect an already DONE state.
        last = fixture(engine, step=718, seat=seat)
        last["privates"][seat]["inventories"][0] = {"MILK": 2}
        now = rollout("last-sale", last, [early_actions[0]], advance, context=context)
        missed = rollout("missed-sale", last, [action()], advance, context=context)
        terminal_rejected = False
        try:
            rollout("after-DONE", missed.state(), [early_actions[0]], advance, context=context)
        except Incompatible:
            terminal_rejected = True
        assert terminal_rejected and money(now, seat) > money(missed, seat) == 0
        kernel_receipt = {"status": "not_run"}
        if kernel is not None:
            model = kernel_model(kernel, [early, late], lambda s, _: s["farms"][seat]["money"])
            result = kernel.search(model, [initial], [context], "early",
                                   limits=kernel.Limits(seconds=2, max_depth=1, max_transitions=20))
            assert result.status == "complete" and result.action == "late"
            assert result.values == (money(late, seat),)
            kernel_receipt = {"status": result.status, "action": result.action,
                              "values": list(result.values), "transitions": result.transitions,
                              "cache_hits": result.cache_hits}
        row = {"seat": seat, "timing_tradeoff": {"early_cash": money(early, seat),
                "late_cash": money(late, seat), "early_cash_at_716": money(early, seat, 1),
                "late_cash_at_716": money(late, seat, 1), "frontier": [a.name for a in frontier.kept],
                "no_cash_deadline": unconstrained, "cash_100_due_after_716": funded},
                "exact_splice_matches": True, "wrong_position_splice_rejected": True,
                "naive_wrong_position_cash": money(naive, seat), "corrected_route_cash": money(recovered, seat),
                "insufficient_seed_splice_rejected": True, "naive_missing_seed_plant": None,
                "ordered_drop_cash": [money(milk_first, seat), money(wool_first, seat)],
                "exact_endpoint_dominance": list(exact_frontier.dominated),
                "zero_profit_cycle_final_cash": money(cycle, seat),
                "last_sale_cash": money(now, seat), "after_done_rejected": terminal_rejected,
                "t06_macro_consumer": kernel_receipt}
        results.append(row)
        for t in (early, late, prefix, suffix, west, drop, naive, recovery, empty_prefix,
                  plant, no_seed, milk_first, wool_first, cycle, idle, now, missed):
            evidence.append({"name": t.name, "context": t.context,
                             "states": [json.loads(s) for s in t.snapshots],
                             "actions": [json.loads(a) for a in t.actions]})
    return {"engine_ref": ENGINE_REF, "engine_sha256": ENGINE_HASHES,
            "method": "Fixed synthetic states through unmodified official interpreter; both seats; no game panel or new seeds.",
            "results": results, "recorded_traces": len(evidence),
            "recorded_transitions": sum(len(t["actions"]) for t in evidence),
            "bound_route_double_call_max_seconds": max(timings),
            "elapsed_seconds": time.perf_counter() - start}, evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-dir", type=Path, default=Path("engine"))
    parser.add_argument("--kernel-file", type=Path)
    parser.add_argument("--output", type=Path, default=Path("engine-results.json"))
    args = parser.parse_args()
    kernel = None
    if args.kernel_file is not None:
        data = args.kernel_file.read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if blob != KERNEL_BLOB:
            raise ValueError("T06 file differs from the recorded consumed blob")
        kernel = load_module(args.kernel_file, "bridge_t06_kernel")
    report, traces = run(load_engine(args.engine_dir), kernel)
    raw = json.dumps(traces, separators=(",", ":")).encode()
    compressed = gzip.compress(raw, mtime=0)
    evidence_file = args.output.with_name("engine-traces.json.gz.b64")
    evidence_file.write_text(base64.b64encode(compressed).decode() + "\n")
    report["trace_archive"] = {"file": evidence_file.name, "raw_bytes": len(raw),
                               "compressed_bytes": len(compressed),
                               "raw_sha256": hashlib.sha256(raw).hexdigest(),
                               "gzip_sha256": hashlib.sha256(compressed).hexdigest()}
    report["source_sha256"] = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                for name in ("route_frontier.py", "engine_cases.py")}
    report["t06_kernel_blob"] = KERNEL_BLOB if kernel else None
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
