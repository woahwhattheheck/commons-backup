# SPDX-License-Identifier: Apache-2.0
"""Official-engine economic stress and deadline-fallback runner.

This lab consumes, but does not copy or modify, the published integrated-selected
runtime.  Natural trajectories discover economically difficult frames.  A
separately labelled injected-overrun arm delays only the already-selected SELL
transform at one reached step; the 1-second guard then returns that exact legal
producer action.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import statistics
import sys
import time
import types
from typing import Any, Callable
import deadline_adapter as deadline_fix


ENGINE_REF = "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c"
PRODUCTS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
            "EGG", "MILK", "WOOL", "FERTILIZER")


class Struct(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None
    __setattr__ = dict.__setitem__


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_engine(cache: Path):
    """Load the pinned upstream interpreter with its real upstream seed helper."""
    import ast
    engine_path = cache / "kaggriculture.py"
    helper_path = cache / "utils.py"
    parsed = ast.parse(helper_path.read_text())
    helper = next(n for n in parsed.body
                  if isinstance(n, ast.FunctionDef) and n.name == "resolve_episode_seed")
    namespace = {"Any": Any, "Callable": Callable, "random": random}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), "upstream_seed_helper", "exec"), namespace)
    package = types.ModuleType("kaggle_environments")
    utils = types.ModuleType("kaggle_environments.utils")
    utils.resolve_episode_seed = namespace["resolve_episode_seed"]
    sys.modules["kaggle_environments"] = package
    sys.modules["kaggle_environments.utils"] = utils
    spec = importlib.util.spec_from_file_location("economic_stress_official", engine_path)
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    return engine


def load_runtime(runtime: Path):
    sys.path.insert(0, str(runtime))
    name = "economic_stress_integrated_" + str(time.time_ns())
    spec = importlib.util.spec_from_file_location(name, runtime / "integrated_selected.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def intact_arlene(runtime: Path):
    path = runtime / "reference/next-panel/vendor/arlene.py"
    name = "economic_stress_arlene_" + str(time.time_ns())
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    owner = module.Agent()
    return lambda obs, cfg=None: owner.act(obs)


# Retain the old import names while using the single shared cancellation type.
DeadlineExceeded = deadline_fix.DeadlineExceeded
_alarm = deadline_fix._alarm


def action_cost(action, obs, cfg):
    """Known current-order cash demand, before any engine clamp."""
    farm = obs["farms"][int(obs["player"])]
    prices = obs["market"]["prices"]
    hires = int(farm.get("hires_today", 0))
    land = len(farm.get("unlocked_quadrants", ["NW"])) - 1
    fib = [1, 1]
    while len(fib) < 20:
        fib.append(fib[-1] + fib[-2])
    total = 0
    for order in action.get("market", []):
        if not order:
            continue
        if order[0] == "HIRE":
            total += int(cfg.get("farmHandCostMult", 1)) * fib[min(hires, len(fib)-1)]
            hires += 1
        elif order[0] == "BUY_LAND":
            total += (1000, 2000, 4000)[min(land, 2)]
            land += 1
        elif len(order) >= 3 and order[0] == "BUY_PRODUCT":
            total += int(prices.get(order[1], 0)) * max(0, int(order[2]))
        elif len(order) >= 3 and order[0] == "BUY_SEED":
            seed_cost = {"WHEAT": 10, "CARROT": 20, "TOMATO": 50,
                         "STRAWBERRY": 100, "MELON": 80}
            total += seed_cost.get(order[1], 0) * max(0, int(order[2]))
        elif len(order) >= 3 and order[0] == "BUY_ANIMAL":
            animal_cost = {"GOOSE": 300, "COW": 400, "SHEEP": 500}
            total += animal_cost.get(order[1], 0) * max(0, int(order[2]))
    return total


def classify(obs, cfg, selected, output, diagnostics, elapsed, production_elapsed):
    seat = int(obs["player"])
    private = obs["private"]
    farm = obs["farms"][seat]
    shed = sum(int(q) for q in private["shed"].values())
    carried = sum(sum(int(q) for q in inv.values()) for inv in private["inventories"])
    pending = 0
    packet = getattr(diagnostics.pop("_owner"), "last_packet", None)
    if packet:
        pending = sum(int(e.get("pending_capacity_units", 0))
                      for e in packet.get("arrival_contract", {}).get("capacity_events", []))
    cap = int(cfg.get("shedCapacity", 100))
    cash = int(farm["money"])
    cost = action_cost(selected, obs, cfg)
    prices = obs["market"]["prices"]
    unit_ops = [selected.get("farmer", ["PASS"]), *selected.get("hands", [])]
    families = []
    if shed + carried + pending >= cap - 5 and len(unit_ops) >= 2:
        families.append("near_full_multiworker_arrival")
    if cost and cash <= cost + 250:
        families.append("marginal_cash_order")
    if any(int(prices.get(p, 2)) == 1 for p in PRODUCTS):
        families.append("market_floor_boundary")
    step = int(obs.get("step", int(obs["day"])*int(cfg.get("turnsPerDay", 24)) + int(obs["hour"])))
    if step >= int(cfg.get("episodeSteps", 720)) - 26 and (
            any(o and o[0] == "SELL" for o in selected.get("market", [])) or carried or pending):
        families.append("terminal_sale_or_arrival")
    complexity = (len(unit_ops) + len(selected.get("market", [])) + carried + pending
                  + sum(len(v) for v in private["inventories"]))
    return {
        "step": step, "cash": cash, "known_order_cost": cost, "shed": shed,
        "carried": carried, "pending": pending, "workers": len(unit_ops),
        "min_price": min(int(v) for v in prices.values()), "families": families,
        "complexity": complexity, "elapsed_s": elapsed,
        "production_elapsed_s": production_elapsed,
        "transform_elapsed_s": max(0.0, elapsed-production_elapsed),
        "selected": copy.deepcopy(selected), "output": copy.deepcopy(output),
        "status": diagnostics.get("status"), "reason": diagnostics.get("reason"),
        "seed_reason": diagnostics.get("seed_reason"),
    }


class _MeasuredDeadlinePhases:
    """Observe the existing owner's phases inside the shared guard.

    This object constructs no actor and owns no timer. The guard still performs
    the only producer call; its normal before_transform hook records selection.
    """
    def __init__(self, runner, step):
        self.runner, self.step = runner, step
        self.production = self
        self.selected = self.selected_at = None

    @property
    def diagnostics(self):
        return self.runner.owner.diagnostics

    def act(self, observation):
        r = self.runner
        if self.step == r.inject_step and r.inject_stage == "production":
            time.sleep(r.inject_seconds)
        return r.owner.production.act(observation)

    def before_transform(self, observation, configuration, selected):
        self.selected_at = time.perf_counter()
        self.selected = copy.deepcopy(selected)
        r = self.runner
        if self.step == r.inject_step and r.inject_stage == "transform":
            time.sleep(r.inject_seconds)

    def transform(self, *args, **kwargs):
        return self.runner.owner.transform(*args, **kwargs)


class InstrumentedIntegrated:
    def __init__(self, module, *, sell=True, deadline_s=None, inject_step=None,
                 inject_seconds=1.05, inject_stage="transform"):
        self.owner = module.make_agent(seed=True, committed=True, sell=sell)
        self.deadline_s = deadline_s
        self.inject_step = inject_step
        self.inject_seconds = inject_seconds
        self.inject_stage = inject_stage
        self.calls = []
        self.timeouts = 0
        self.production_timeout_fallback = "pass"

    def _guarded(self, obs, cfg, step, started):
        phases = _MeasuredDeadlinePhases(self, step)
        guard = deadline_fix.DeadlineFallbackAgent(
            phases, budget_seconds=self.deadline_s, reserve_seconds=0,
            before_transform=phases.before_transform)
        output = guard.act(obs, cfg)
        ended = time.perf_counter()
        timed_out = guard.diagnostics["status"] == "deadline_fallback"
        stage = guard.diagnostics["fallback_stage"]
        if timed_out:
            self.timeouts += 1
            if stage == "production":
                # Keep the two explicitly named experimental treatments. This
                # selection does not call the producer or change the shared guard.
                output = (deadline_fix.terminal_liquidation_fallback(obs, cfg)
                          if self.production_timeout_fallback == "terminal_liquidation"
                          else deadline_fix.legal_pass(obs))
            self.owner.diagnostics = {
                "status": "deadline_fallback",
                "reason": "one-second action budget exhausted" + (
                    " before selection" if stage == "production" else ""),
                "selected_unit_stages": 0 if stage == "production" else 1,
            }
        # If cancellation interrupted the selection snapshot, the guard's exact
        # saved fallback is the only available completed action for the receipt.
        selected = phases.selected if phases.selected is not None else output
        selected_at = phases.selected_at if phases.selected_at is not None else ended
        diag = copy.deepcopy(self.owner.diagnostics); diag["_owner"] = self.owner
        row = classify(obs, cfg, selected, output, diag, ended-started, selected_at-started)
        row.update(timed_out=timed_out, fallback_stage=stage,
                   selection_completed=stage != "production", deadline_binding="shared-guard-v1")
        self.calls.append(row)
        return output

    def __call__(self, observation, configuration=None):
        obs = copy.deepcopy(dict(observation)); cfg = dict(configuration or {})
        step = int(obs.get("step", int(obs["day"])*int(cfg.get("turnsPerDay", 24)) + int(obs["hour"])))
        obs["step"] = step
        started = time.perf_counter()
        if self.deadline_s is not None:
            return self._guarded(obs, cfg, step, started)
        # Natural runs still call the same producer and transform directly.
        if step == self.inject_step and self.inject_stage == "production":
            time.sleep(self.inject_seconds)
        selected = self.owner.production.act(obs)
        selected_at = time.perf_counter()
        if step == self.inject_step and self.inject_stage == "transform":
            time.sleep(self.inject_seconds)
        output = self.owner.transform(obs, cfg, selected, fallback_action=selected)
        ended = time.perf_counter()
        diag = copy.deepcopy(self.owner.diagnostics)
        diag["_owner"] = self.owner
        row = classify(obs, cfg, selected, output, diag, ended-started, selected_at-started)
        row["timed_out"] = False
        self.calls.append(row)
        return output


def play(engine, agents, seed):
    cfg = Struct()
    for key, value in engine.specification["configuration"].items():
        cfg[key] = value.get("default") if isinstance(value, dict) else value
    cfg.seed = seed
    env = Struct(configuration=cfg, done=False, info={})
    state = [Struct(observation=Struct(), action={}, status="ACTIVE", reward=0)
             for _ in agents]
    engine.interpreter(state, env)
    errors = []
    for step in range(int(cfg.episodeSteps)):
        for seat, actor in enumerate(agents):
            state[seat].observation.step = step
            try:
                action = actor(copy.deepcopy(state[seat].observation), cfg)
                if not isinstance(action, dict):
                    raise TypeError("agent returned non-dict")
            except Exception as error:  # explicit runner receipt; legal PASS only on actor error
                errors.append({"step": step, "seat": seat, "error": repr(error)})
                action = {"farmer": ["PASS"], "hands": [], "market": []}
            state[seat].action = action
        engine.interpreter(state, env)
        if any(s.status == "DONE" for s in state):
            break
    return {"seed": seed, "cash": [s.reward for s in state], "steps": step+1,
            "status": [s.status for s in state], "errors": errors}


def run_one(engine, runtime, seed, seat, arm, inject_step=None, inject_stage="transform"):
    module = load_runtime(runtime)
    deadline = 1.0 if arm in ("deadline", "injected_overrun", "injected_overrun_repaired") else None
    candidate = InstrumentedIntegrated(module, sell=True, deadline_s=deadline,
                                       inject_step=inject_step if arm in ("injected_overrun", "injected_overrun_repaired") else None,
                                       inject_stage=inject_stage)
    if arm == "injected_overrun_repaired":
        candidate.production_timeout_fallback = "terminal_liquidation"
    rival = intact_arlene(runtime)
    agents = [candidate, rival] if seat == 0 else [rival, candidate]
    result = play(engine, agents, seed)
    own, other = result["cash"][seat], result["cash"][1-seat]
    result.update({"seat": seat, "arm": arm, "own_cash": own, "rival_cash": other,
                   "margin": own-other, "timeouts": candidate.timeouts,
                   "max_call_s": max(row["elapsed_s"] for row in candidate.calls),
                   "p99_call_s": sorted(row["elapsed_s"] for row in candidate.calls)[
                       max(0, math.ceil(.99*len(candidate.calls))-1)],
                   "calls": candidate.calls})
    return result


def summarize(games):
    by_arm = {}
    for arm in sorted({g["arm"] for g in games}):
        rows = [g for g in games if g["arm"] == arm]
        by_arm[arm] = {
            "games": len(rows), "wins": sum(g["margin"] > 0 for g in rows),
            "ties": sum(g["margin"] == 0 for g in rows),
            "losses": sum(g["margin"] < 0 for g in rows),
            "mean_own_cash": statistics.mean(g["own_cash"] for g in rows),
            "mean_rival_cash": statistics.mean(g["rival_cash"] for g in rows),
            "timeouts": sum(g["timeouts"] for g in rows),
            "errors": sum(len(g["errors"]) for g in rows),
            "peak_call_s": max(g["max_call_s"] for g in rows),
            "peak_p99_s": max(g["p99_call_s"] for g in rows),
        }
    return by_arm


def compact_game(game):
    calls = game.pop("calls")
    family = {}
    for name in ("near_full_multiworker_arrival", "marginal_cash_order",
                 "market_floor_boundary", "terminal_sale_or_arrival"):
        rows = [r for r in calls if name in r["families"]]
        family[name] = {"count": len(rows), "steps": [r["step"] for r in rows[:12]],
                        "first": rows[0] if rows else None,
                        "last": rows[-1] if rows else None}
    slow = sorted(calls, key=lambda r: r["elapsed_s"], reverse=True)[:8]
    game["families"] = family
    game["slow_calls"] = slow
    game["changed_calls"] = [r for r in calls
                             if r["selected"] != r["output"] or r["timed_out"]]
    game["complex_calls"] = sorted(calls, key=lambda r: r["complexity"], reverse=True)[:8]
    return game


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", type=Path, required=True)
    ap.add_argument("--runtime", type=Path, required=True)
    ap.add_argument("--seeds", type=int, nargs="+", required=True)
    ap.add_argument("--arms", nargs="+", default=["natural", "deadline"])
    ap.add_argument("--inject-step", type=int)
    ap.add_argument("--inject-stage", choices=("production", "transform"), default="transform")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    engine = load_engine(args.engine)
    games = []
    for seed in args.seeds:
        for arm in args.arms:
            for seat in (0, 1):
                game = run_one(engine, args.runtime, seed, seat, arm, args.inject_step,
                               args.inject_stage)
                print(json.dumps({k: game[k] for k in
                      ("seed", "seat", "arm", "cash", "margin", "timeouts", "max_call_s")}), flush=True)
                games.append(game)
    report = {
        "engine_ref": ENGINE_REF,
        "runner_sha256": sha256(Path(__file__)),
        "deadline_adapter_sha256": sha256(Path(deadline_fix.__file__)),
        "deadline_binding": "shared-guard-v1",
        "engine_sha256": {p.name: sha256(p) for p in args.engine.iterdir() if p.is_file()},
        "integrated_manifest_sha256": sha256(args.runtime / "SOURCE.json"),
        "method": "Unmodified official interpreter; natural trajectories and separately labelled injected overrun.",
        "seeds": args.seeds, "summary": summarize(games),
        "games": [compact_game(g) for g in games],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print("SUMMARY " + json.dumps(report["summary"]), flush=True)


if __name__ == "__main__":
    main()
