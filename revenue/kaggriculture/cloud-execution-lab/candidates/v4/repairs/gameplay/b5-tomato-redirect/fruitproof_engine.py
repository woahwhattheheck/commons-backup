# SPDX-License-Identifier: Apache-2.0
"""Independent full-interpreter tomato fertilizer evidence; NOT an agent policy.

Fixtures are constructed microstates, explicitly not naturally reached native
states. Both counterfactual arms get identical later commands. A leftover input
is sold by the control, making fertilizer opportunity cost realized rather than
an assumed quote. No production module, configuration, or donor is modified.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Any

PINS = {
    "checks/reference/evaluator/evaluate.py": "1fb6b655bb4ca1e1684be165a8ef513e2e6c2325",
    "checks/reference/evaluator/loader.py": "23948e10cfc3d32f46c9abb1321b0d8fc8db21d5",
    "checks/reference/engine/kaggriculture.py": "3c202c7ee921da239356789e266b694635103fc4",
    "checks/reference/engine/kaggriculture.json": "b354d06b742fe48402513792253f1a5c29366b20",
    "checks/reference/engine/utils.py": "91c8822ee6201ba4a5a8416c7dbe34f95dd61c87",
}


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def load_engine(runtime_root: Path):
    """Authenticate all five executable/spec inputs before any import; offline."""
    root = Path(runtime_root).resolve()
    for rel, expected in PINS.items():
        data = (root / rel).read_bytes()
        if git_blob(data) != expected:
            raise ValueError(f"reference identity mismatch: {rel}")
    name = "fruitproof_pinned_evaluator"
    spec = importlib.util.spec_from_file_location(name, root / "checks/reference/evaluator/evaluate.py")
    if spec is None or spec.loader is None:
        raise ValueError("cannot load authenticated evaluator")
    ev = importlib.util.module_from_spec(spec)
    sys.modules[name] = ev
    spec.loader.exec_module(ev)
    engine, _ = ev.get_engine(root / "checks/reference/engine", root / "checks/reference/evaluator/loader.py")
    return engine, ev.Struct


@dataclass(frozen=True)
class Fixture:
    seat: int = 0
    day: int = 15
    hour: int = 22
    age: int = 7
    held_yield: int = 0
    watered: bool = True
    unwatered_days: int = 0
    coverage_delta: int = -1
    carried_fert: int = 1
    tomato_inventory: int = 10000
    fertilizer_inventory: int = 10000
    shed_wheat: int = 0
    seed: int = 2611151001
    episode_steps: int = 720
    shops: tuple[str, ...] = ()
    rival_tomato: int = 0
    rival_fert: int = 0

    def __post_init__(self):
        integers = (self.seat, self.day, self.hour, self.age, self.held_yield,
                    self.unwatered_days, self.coverage_delta, self.carried_fert,
                    self.tomato_inventory, self.fertilizer_inventory, self.shed_wheat,
                    self.seed, self.episode_steps, self.rival_tomato, self.rival_fert)
        if any(type(x) is not int for x in integers):
            raise TypeError("fixture counts must be plain integers")
        if (self.seat not in (0, 1) or not 0 <= self.hour < 24 or self.day < self.age
                or self.age < 0 or not 0 <= self.held_yield <= 4
                or min(self.unwatered_days, self.carried_fert, self.shed_wheat,
                       self.rival_tomato, self.rival_fert) < 0
                or self.shed_wheat > 100 or type(self.watered) is not bool
                or self.episode_steps < 2 or self.step > self.episode_steps - 2):
            raise ValueError("invalid constructed fixture")

    @property
    def step(self):
        return self.day * 24 + self.hour


def world(engine, Struct, case: Fixture):
    """Build one shared public world and separate private inventories per seat."""
    cfg = Struct({k: v.get("default") if isinstance(v, dict) else v
                  for k, v in engine.specification["configuration"].items()})
    cfg.weedSpawnChance = 0
    cfg.episodeSteps = case.episode_steps
    farms = [engine._new_farm(10, 3000), engine._new_farm(10, 3000)]
    plant = engine._new_plant("TOMATO", case.day - case.age, 24)
    plant.update(yield_units=case.held_yield, watered_today=case.watered,
                 consecutive_unwatered=case.unwatered_days,
                 fertilized_until_day=case.day + case.coverage_delta)
    farms[case.seat]["tiles"][4][4] = plant
    market = engine._new_market()
    market["inventory"].update(TOMATO=case.tomato_inventory, FERTILIZER=case.fertilizer_inventory)
    engine._refresh_prices(market)
    town = {"unlocked_shops": list(case.shops)}
    state = []
    for seat in (0, 1):
        private = engine._new_private()
        if seat == case.seat:
            private["inventories"][0] = {"FERTILIZER": case.carried_fert}
            private["shed"]["WHEAT"] = case.shed_wheat
        else:
            private["shed"].update(TOMATO=case.rival_tomato, FERTILIZER=case.rival_fert)
        state.append(Struct(observation=Struct(player=seat, step=case.step,
                        day=case.day, hour=case.hour, farms=farms, private=private,
                        market=market, town=town), action=pass_action(), status="ACTIVE", reward=0))
    env = Struct(configuration=cfg, done=False, info={"seed": case.seed})
    return state, env


def pass_action(farmer=None, hands=None, market=None):
    return {"farmer": ["PASS"] if farmer is None else farmer,
            "hands": [] if hands is None else hands,
            "market": [] if market is None else market}


def pulse_oracle(*, age: int, held: int, watered: bool, consecutive_unwatered: int,
                 coverage: int, day: int) -> tuple[int | None, bool]:
    """Independent TOMATO-only expected EOD result, not copied engine code.

    Four pulses arrive at ages 8..11. The supplying service nights are 7..10.
    None denotes death from two consecutive unwatered days.
    """
    streak = 0 if watered else consecutive_unwatered + 1
    if streak >= 2:
        return None, False
    due = age in (7, 8, 9, 10)
    addition = int(due) * (1 + int(watered and coverage >= day))
    return min(4, held + addition), due


def execute(engine, state, env, step: int, actions: list[dict]) -> None:
    if any(s.status != "ACTIVE" for s in state):
        raise ValueError("cannot execute after terminal state")
    for seat, s in enumerate(state):
        s.observation.step = step
        s.action = copy.deepcopy(actions[seat])
    engine.interpreter(state, env)


def outcome(state, env, seat: int):
    obs = state[seat].observation
    tile = obs.farms[seat]["tiles"][4][4]
    return {
        "money": float(obs.farms[seat]["money"]),
        "rival_money": float(obs.farms[1 - seat]["money"]),
        "margin": float(obs.farms[seat]["money"] - obs.farms[1 - seat]["money"]),
        "shed": copy.deepcopy(obs.private["shed"]),
        "carried": copy.deepcopy(obs.private["inventories"]),
        "tile": copy.deepcopy(tile),
        "market": copy.deepcopy(obs.market),
        "status": [s.status for s in state],
        "state_hash": digest([state, env]),
    }


def paired_once(engine, Struct, case: Fixture, baseline: dict, candidate: dict,
                rival: dict | None = None, configure: Callable | None = None):
    initial = world(engine, Struct, case)
    if configure is not None:
        configure(*initial)
    before = digest(initial)
    result = {}
    for name, own in (("baseline", baseline), ("candidate", candidate)):
        state, env = copy.deepcopy(initial)  # Copy sharing graph as one object.
        actions = [pass_action(), pass_action()]
        actions[case.seat] = own
        actions[1 - case.seat] = rival or pass_action()
        execute(engine, state, env, case.step, actions)
        result[name] = outcome(state, env, case.seat)
    if digest(initial) != before:
        raise RuntimeError("counterfactual mutated initial world")
    result["delta_money"] = result["candidate"]["money"] - result["baseline"]["money"]
    result["delta_margin"] = result["candidate"]["margin"] - result["baseline"]["margin"]
    return result


def cycle_pair(engine, Struct, case: Fixture, *, harvest="daily", water_daily=True,
               end_day=None, sell_unused_fert=True, candidate_action=None):
    """Actual multi-day interpreter counterfactual with fixed subsequent commands.

    A constructed plant at the shed-adjacent spawn isolates input economics from
    routing. This is NOT a replacement native policy or a competitive field gate.
    If supplied, candidate_action is the already-computed owner's exact action.
    """
    if harvest not in ("daily", "hold") or case.hour != 22:
        raise ValueError("cycle fixture requires hour22 and daily/hold harvesting")
    end_day = case.day + 5 if end_day is None else end_day
    end = min(end_day * 24 + 5, case.episode_steps - 2)
    if end < case.step:
        raise ValueError("end before cut")
    initial = world(engine, Struct, case)
    before = digest(initial)
    result = {}
    for arm in ("baseline", "candidate"):
        state, env = copy.deepcopy(initial)
        harvested = 0
        pulses = []
        commands = []
        callbacks = 0
        for step in range(case.step, end + 1):
            day, hour = divmod(step, 24)
            farmer = ["PASS"]
            market = []
            if step == case.step:
                if arm == "candidate":
                    own = candidate_action if candidate_action is not None else pass_action(["FERTILIZE"])
                else:
                    own = pass_action()
            else:
                if hour == 0 and (harvest == "daily" or day >= case.day - case.age + 11):
                    farmer = ["HARVEST"]
                elif hour == 1:
                    farmer = ["DROP"]
                elif hour == 2 and water_daily:
                    farmer = ["WATER"]
                if hour == 4:
                    market = [["SELL", "TOMATO", 100]]
                    if sell_unused_fert:
                        market.append(["SELL", "FERTILIZER", 100])
                own = pass_action(farmer, market=market)
            actions = [pass_action(), pass_action()]
            actions[case.seat] = own
            if hour == 4:
                actions[1 - case.seat] = pass_action(market=[["SELL", "TOMATO", 100], ["SELL", "FERTILIZER", 100]])
            obs = state[case.seat].observation
            prev_cargo = sum(inv.get("TOMATO", 0) for inv in obs.private["inventories"])
            execute(engine, state, env, step, actions)
            callbacks += 1
            obs = state[case.seat].observation
            new_cargo = sum(inv.get("TOMATO", 0) for inv in obs.private["inventories"])
            if own["farmer"] == ["HARVEST"]:
                harvested += new_cargo - prev_cargo
            if hour == 23:
                pulses.append({"service_day": day, "tile": copy.deepcopy(obs.farms[case.seat]["tiles"][4][4])})
            commands.append([step, actions])
            if state[0].status == "DONE":
                break
        result[arm] = outcome(state, env, case.seat)
        result[arm].update(harvested=harvested, callbacks=callbacks, pulses=pulses,
                           action_hash=digest(commands))
    if digest(initial) != before:
        raise RuntimeError("cycle mutated common initial world")
    for key in ("money", "margin", "rival_money", "harvested"):
        result["delta_" + key] = result["candidate"][key] - result["baseline"][key]
    return result
