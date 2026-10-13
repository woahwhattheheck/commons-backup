# SPDX-License-Identifier: Apache-2.0
"""Independent, offline W2 lifecycle evidence using the COMPLETE official engine.

Synthetic paired continuations are not natural-game or promotion evidence. Nothing
here is a runtime policy. Reference files are authenticated before loader import;
no missing dependency is downloaded. Candidate-source loading is execution of
trusted project code, not a sandbox.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Callable

REFERENCE_BLOBS = {
    "engine/kaggriculture.py": "3c202c7ee921da239356789e266b694635103fc4",
    "engine/kaggriculture.json": "b354d06b742fe48402513792253f1a5c29366b20",
    "engine/utils.py": "91c8822ee6201ba4a5a8416c7dbe34f95dd61c87",
    "evaluator/loader.py": "23948e10cfc3d32f46c9abb1321b0d8fc8db21d5",
}
SITE = (4, 4)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def import_file(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_reference(reference: Path):
    reference = reference.resolve()
    for name, wanted in REFERENCE_BLOBS.items():
        path = reference / name
        if not path.is_file() or git_blob(path.read_bytes()) != wanted:
            raise ValueError(f"Reference custody failure: {name}")
    loader = import_file(reference / "evaluator/loader.py", "aftercare_pinned_loader")
    engine, _ = loader.get_engine(reference / "engine")
    return engine, loader.Struct


def load_lane(path: Path, expected_blob: str):
    if len(expected_blob) != 40 or git_blob(path.read_bytes()) != expected_blob:
        raise ValueError("Candidate source blob mismatch")
    module = import_file(path.resolve(), "aftercare_bound_lane")
    function = getattr(module, "apply_dead_feed_care", None)
    if not callable(function):
        raise ValueError("Missing callable apply_dead_feed_care")
    return function


def action(farmer=("PASS",), hands=(), market=()) -> dict:
    return {"farmer": list(farmer), "hands": [list(row) for row in hands],
            "market": [list(row) for row in market]}


@dataclass
class World:
    state: list
    env: Any
    step: int

    def clone(self):
        # One deepcopy preserves public farms/market/town sharing across both seats.
        return copy.deepcopy(self)

    def fingerprint(self):
        return hashlib.sha256(json.dumps(
            {"state": self.state, "env": self.env, "step": self.step},
            sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class Case:
    name: str
    species: str = "GOOSE"
    seat: int = 0
    day: int | None = None
    hour: int = 22
    ordered: bool = False
    first_feed_wheat: int = 1
    cared: bool = False
    fed: bool = True
    later_care: bool = False
    held_full: bool = False
    feed_continuation: bool = True
    redundant_care_later: bool = False
    shed_full: bool = False
    rival_sale: bool = False
    floor_sale: bool = False
    collateral_drop: bool = False


class Oracle:
    def __init__(self, reference: Path):
        self.engine, self.Struct = load_reference(reference)
        self.initializations = 0
        self.transitions = 0

    def world(self, case: Case) -> World:
        if case.species not in self.engine.ANIMALS or case.seat not in (0, 1):
            raise ValueError("Invalid fixture species/seat")
        cfg = self.Struct({key: value.get("default") if isinstance(value, dict) else value
                           for key, value in self.engine.specification["configuration"].items()})
        cfg.seed = 9922441
        env = self.Struct(configuration=cfg, done=False, info={})
        state = [self.Struct(observation=self.Struct(), action={}, status="ACTIVE", reward=0)
                 for _ in range(2)]
        self.engine.interpreter(state, env)
        self.initializations += 1
        day = case.day if case.day is not None else self.engine.ANIMALS[case.species]["first_yield_day"] - 1
        start = day * 24 + case.hour
        if not 0 <= start <= 718:
            raise ValueError("Invalid fixture start")
        farm = state[0].observation.farms[case.seat]
        tile = self.engine._new_animal(case.species, 0)
        tile.update(fed_today=case.fed and not case.ordered,
                    cared_today=case.cared, fertilizer_available=True)
        if case.held_full:
            tile["yield_units"] = self.engine.ANIMALS[case.species]["max_held"]
        farm["tiles"][4][4] = tile
        farm["farmer"] = [4, 4]
        farm["money"] = 1000.0
        farm["hands"] = ([[3, 4]] if case.collateral_drop else
                         ([[4, 4]] if case.ordered or case.later_care else []))
        farm["hires_today"] = len(farm["hands"])
        private = state[case.seat].observation.private
        private["inventories"] = [{"WHEAT": case.first_feed_wheat}]
        if farm["hands"]:
            private["inventories"].append({})
        private["shed"]["WHEAT"] = 8
        if case.shed_full:
            private["shed"]["MELON"] = 92
        if case.collateral_drop:
            # A predeclared crop co-service path; no goods/state injected later.
            first = self.engine.ANIMALS[case.species]["first_yield_day"]
            interval = self.engine.ANIMALS[case.species]["interval"]
            next_prod = next(n for n in range(day+2, 30) if n >= first and (n-first) % interval == 0)
            productions = sum(n >= first and (n-first) % interval == 0 for n in range(day+1, next_prod+1))
            feed_days = next_prod-day-1
            private["shed"]["MELON"] = 98 + feed_days - productions - 8
            farm["tiles"][4][3] = self.engine._new_plant("MELON", next_prod-10, 24)
        product = self.engine.ANIMALS[case.species]["product"]
        if case.rival_sale:
            state[1 - case.seat].observation.private["shed"][product] = 20
        if case.floor_sale:
            state[0].observation.market["inventory"][product] = 10**18
            self.engine._refresh_prices(state[0].observation.market)
        for i, s in enumerate(state):
            s.observation.step = start
            s.observation.day, s.observation.hour = divmod(start, 24)
            s.observation.player = i
        return World(state, env, start)

    def tick(self, world: World, actions: list[dict], *, trace=False) -> dict:
        if world.env.done or any(s.status == "DONE" for s in world.state):
            raise ValueError("Transition requested after terminal state")
        if len(actions) != 2:
            raise ValueError("Exactly two actions required")
        for seat, state in enumerate(world.state):
            state.observation.step = world.step
            state.observation.day, state.observation.hour = divmod(world.step, 24)
            state.action = copy.deepcopy(actions[seat])
        events = []
        commit_events = []
        original_unit = self.engine._apply_unit_action
        original_commit = self.engine._commit_unit
        farms = world.state[0].observation.farms

        def unit(farm, private, idx, row, *args, **kwargs):
            seat = next(i for i, known in enumerate(farms) if farm is known)
            positions = [farm["farmer"], *farm["hands"]]
            pos = positions[idx] if idx < len(positions) else None
            before_tile = copy.deepcopy(farm["tiles"][pos[1]][pos[0]]) if pos else None
            before_private = copy.deepcopy(private)
            result = original_unit(farm, private, idx, row, *args, **kwargs)
            after_tile = copy.deepcopy(farm["tiles"][pos[1]][pos[0]]) if pos else None
            events.append({"seat": seat, "actor": idx, "row": copy.deepcopy(row),
                           "site": copy.deepcopy(pos), "tile_before": before_tile,
                           "tile_after": after_tile,
                           "private_before": before_private, "private_after": copy.deepcopy(private)})
            return result

        def commit(op, item, price, farm, private, market, *args, **kwargs):
            seat = next(i for i, known in enumerate(farms) if farm is known)
            before = farm["money"]
            result = original_commit(op, item, price, farm, private, market, *args, **kwargs)
            commit_events.append({"seat": seat, "op": op, "item": item,
                                  "price": price, "filled": bool(result),
                                  "cash_delta": farm["money"] - before})
            return result

        if trace:
            self.engine._apply_unit_action, self.engine._commit_unit = unit, commit
        try:
            self.engine.interpreter(world.state, world.env)
            self.transitions += 1
        finally:
            self.engine._apply_unit_action, self.engine._commit_unit = original_unit, original_commit
        world.step += 1
        if any(s.status == "DONE" for s in world.state):
            world.env.done = True
        return {"units": events, "commits": commit_events}

    @staticmethod
    def parent(case: Case):
        hands = ([["WATER"]] if case.collateral_drop else
                 ([["FEED"]] if case.ordered else ([["CARE"]] if case.later_care else [])))
        return action(["FEED"], hands, [[], ["SELL", "CARROT", 1]])

    @staticmethod
    def manual_intervention(parent: dict, case: Case):
        out = copy.deepcopy(parent)
        if case.ordered:
            out["hands"][0] = ["CARE"]
        else:
            out["farmer"] = ["CARE"]
        return out

    def pair(self, case: Case, transform: Callable | None = None) -> dict:
        initial = self.world(case)
        left, right = initial.clone(), initial.clone()
        input_hash = initial.fingerprint()
        parent = self.parent(case)
        candidate = self.manual_intervention(parent, case) if transform is None else transform(
            copy.deepcopy(parent), copy.deepcopy(initial.state[case.seat].observation),
            copy.deepcopy(initial.env.configuration), enabled=True)
        if initial.fingerprint() != input_hash:
            raise ValueError("Fixture mutated during intervention construction")
        product = self.engine.ANIMALS[case.species]["product"]
        animal = self.engine.ANIMALS[case.species]
        day = initial.step // 24
        production_day = next((n for n in range(day + 2, 30)
                               if n >= animal["first_yield_day"]
                               and (n - animal["first_yield_day"]) % animal["interval"] == 0), None)
        # A constructed future is declared ahead of both arms, never tuned per arm.
        harvest_step = production_day * 24 if production_day is not None else None
        milestones = []
        first_events = []
        bought_wheat = [0, 0]
        sold_products = [0, 0]
        sold_melon = [0, 0]
        deliveries = [[], []]
        wheat_consumed = [0, 0]
        for world_index, (world, intervention) in enumerate(((left, parent), (right, candidate))):
            arm_milestones = []
            while not world.env.done:
                step = world.step
                hour = step % 24
                own = action()
                rival = action()
                if step == initial.step:
                    own = intervention
                elif case.redundant_care_later and step == initial.step + 1:
                    own = action(["CARE"])
                elif step // 24 > day and (harvest_step is None or step < harvest_step):
                    if hour == 0 and case.feed_continuation:
                        own = action(["PICKUP", "WHEAT", 1])
                    elif hour == 1 and case.feed_continuation:
                        own = action(["FEED"])
                    elif case.collateral_drop and hour in (2, 3, 4):
                        own = action([{2: "WEST", 3: "WATER", 4: "EAST"}[hour]])
                if harvest_step is not None:
                    if step == harvest_step:
                        own = action(["HARVEST"])
                    elif step == harvest_step + 1:
                        own = action(["DROP"])
                    elif case.collateral_drop and step in range(harvest_step+2, harvest_step+6):
                        own = action([{2: "WEST", 3: "HARVEST", 4: "EAST", 5: "DROP"}[step-harvest_step]])
                    elif case.collateral_drop and step == harvest_step + 6:
                        own = action(market=[["SELL", product, 10], ["SELL", "MELON", 100]])
                    elif not case.collateral_drop and step == harvest_step + 2:
                        own = action(market=[["SELL", product, 10]])
                        if case.rival_sale:
                            rival = action(market=[["SELL", product, 20]])
                pair_actions = [own, rival] if case.seat == 0 else [rival, own]
                details = self.tick(world, pair_actions, trace=True)
                if step == initial.step:
                    first_events.append(details["units"])
                for event in details["units"]:
                    if event["seat"] == case.seat and event["row"] in (["HARVEST"], ["DROP"]):
                        deliveries[world_index].append({"step": step, **event})
                    if event["seat"] == case.seat and event["row"] == ["FEED"]:
                        before = sum(inv.get("WHEAT", 0) for inv in event["private_before"]["inventories"])
                        after = sum(inv.get("WHEAT", 0) for inv in event["private_after"]["inventories"])
                        wheat_consumed[world_index] += before - after
                for event in details["commits"]:
                    if event["seat"] == case.seat and event["filled"]:
                        if event["op"] == "SELL" and event["item"] == product:
                            sold_products[world_index] += 1
                        if event["op"] == "SELL" and event["item"] == "MELON":
                            sold_melon[world_index] += 1
                        if event["op"] == "BUY_PRODUCT" and event["item"] == "WHEAT":
                            bought_wheat[world_index] += 1
                if (step + 1) % 24 == 0 and step <= (harvest_step or 718):
                    farm = world.state[0].observation.farms[case.seat]
                    arm_milestones.append({"after_step": step, "tile": copy.deepcopy(farm["tiles"][4][4]),
                                           "shed": copy.deepcopy(world.state[case.seat].observation.private["shed"])})
            milestones.append(arm_milestones)
        cash = [[s.reward for s in w.state] for w in (left, right)]
        delta_own = cash[1][case.seat] - cash[0][case.seat]
        delta_rival = cash[1][1-case.seat] - cash[0][1-case.seat]
        return {"case": case.__dict__, "source_mode": "manual_intervention" if transform is None else "bound_source",
                "synthetic": True, "initial_hash": input_hash,
                "initial_step": initial.step, "parent_action": parent, "candidate_action": candidate,
                "action_changed": candidate != parent, "first_unit_events": first_events,
                "production_day": production_day, "harvest_step": harvest_step,
                "eod_milestones": milestones, "terminal_cash": cash,
                "delta_own": delta_own, "delta_rival": delta_rival,
                "delta_margin": delta_own-delta_rival, "wheat_consumed": wheat_consumed,
                "wheat_bought": bought_wheat, "product_sold": sold_products,
                "melon_sold": sold_melon, "delivery_events": deliveries,
                "terminal_status": [[s.status for s in w.state] for w in (left, right)],
                "terminal_hashes": [w.fingerprint() for w in (left, right)],
                "transitions": 2 * (719-initial.step)}


def corpus():
    for species in ("GOOSE", "COW", "SHEEP"):
        for seat in (0, 1):
            for name, settings in (
                    ("entry-fed", {}), ("ordered-feed", {"ordered": True}),
                    ("held-clipping", {"held_full": True}),
                    ("later-care", {"redundant_care_later": True}),
                    ("unfed-followup", {"feed_continuation": False}),
                    ("late-season", {"day": 28}),
                    ("storage-full", {"shed_full": True}),
                    ("rival-sale", {"rival_sale": True}),
                    ("floor-sale", {"floor_sale": True}),
                    ("collateral-drop", {"collateral_drop": True, "day": 12})):
                yield Case(name=f"{species}:{seat}:{name}", species=species, seat=seat, **settings)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--lane", type=Path)
    parser.add_argument("--lane-blob")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if bool(args.lane) != bool(args.lane_blob):
        parser.error("--lane and --lane-blob must be supplied together")
    oracle = Oracle(args.reference)
    function = load_lane(args.lane, args.lane_blob) if args.lane else None
    rows = [oracle.pair(case, function) for case in corpus()]
    report = {"schema": "aftercare-lifecycle-v1", "scope": "synthetic continuations; NOT native games or EV",
              "reference_blobs": REFERENCE_BLOBS, "lane_blob": args.lane_blob,
              "initializations": oracle.initializations, "transitions": oracle.transitions,
              "case_count": len(rows), "rows": rows}
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False)+"\n")
    print(json.dumps({"case_count": len(rows), "transitions": oracle.transitions,
                      "action_changes": sum(r["action_changed"] for r in rows),
                      "source_blob": args.lane_blob}))


if __name__ == "__main__":
    main()
