# SPDX-License-Identifier: Apache-2.0
"""Independent, source-pinned S8 interpreter controls; NOT a second policy.

Uses complete official interpreter transitions from a checked native artifact.
Fixtures with animals/inventory already present are explicitly constructed, not
natural-game reachability or profit evidence. Never activates or edits a runtime.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import types
import unittest

ENGINE_BLOBS = {
    "kaggriculture.py": "3c202c7ee921da239356789e266b694635103fc4",
    "kaggriculture.json": "b354d06b742fe48402513792253f1a5c29366b20",
    "utils.py": "91c8822ee6201ba4a5a8416c7dbe34f95dd61c87",
}
LOADER_SHA256 = "cd113a94ae99b03492502e425bdcf09c3db17a2aa2a8fd866f0d78caec9e311e"
ENGINE = None
WITNESSES = {}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load_engine(runtime):
    """Verify all three upstream bytes before using the existing offline loader."""
    reference = Path(runtime).resolve() / "checks/reference"
    root = reference / "engine"
    hashes = {}
    for name, expected in ENGINE_BLOBS.items():
        data = (root / name).read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if actual != expected:
            raise ValueError(f"Official source mismatch: {name}: {actual}")
        hashes[name] = digest(data)
    loader_path = reference / "evaluator/loader.py"
    if digest(loader_path.read_bytes()) != LOADER_SHA256:
        raise ValueError("Existing offline loader source mismatch")
    spec = importlib.util.spec_from_file_location("s8_existing_engine_loader", loader_path)
    if spec is None or spec.loader is None:
        raise ValueError("Cannot load existing evaluator loader")
    loader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loader)
    if loader.ENGINE_REF != "28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c":
        raise ValueError("Unexpected loader upstream reference")
    engine, _ = loader.get_engine(root)
    return engine, {"engine_sha256": hashes,
                    "loader_sha256": digest(loader_path.read_bytes()),
                    "engine_git_blobs": ENGINE_BLOBS}


class Struct(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None

    def __setattr__(self, key, value):
        self[key] = value


def action(command="PASS", hands=(), market=()):
    return {"farmer": [command], "hands": copy.deepcopy(list(hands)),
            "market": copy.deepcopy(list(market))}


class World:
    """Constructed state, complete interpreter, framework-equivalent step/DONE."""
    def __init__(self, engine, *, seat=0, day=8, hour=23, animal="GOOSE",
                 placed=0, held=0, pending=0, fed=True, cared=False,
                 unfed=0, available=True, shed=None, inventory=None, hands=(),
                 hand_inventories=(), capacity=100):
        self.e, self.seat = engine, seat
        self.cfg = Struct({k: v.get("default") if isinstance(v, dict) else v
                           for k, v in engine.specification["configuration"].items()})
        self.cfg.weedSpawnChance = 0
        self.cfg.shedCapacity = capacity
        self.env = Struct(configuration=self.cfg, done=False, info={"seed": 101})
        self.step = day * self.cfg.turnsPerDay + hour
        farms = [engine._new_farm(10, 3000) for _ in range(2)]
        farms[seat]["farmer"] = [4, 4]
        farms[seat]["hands"] = copy.deepcopy(list(hands))
        tile = engine._new_animal(animal, placed)
        tile.update(yield_units=held, pending_care_bonus=pending,
                    fed_today=fed, cared_today=cared,
                    consecutive_unfed=unfed, fertilizer_available=available)
        farms[seat]["tiles"][4][4] = tile
        market, town = engine._new_market(), engine._new_town()
        self.state = []
        for player in range(2):
            private = engine._new_private()
            if player == seat:
                private["shed"].update(shed or {})
                private["inventories"] = [dict(inventory or {}),
                                           *copy.deepcopy(list(hand_inventories))]
            self.state.append(Struct(observation=Struct(
                player=player, step=self.step, day=day, hour=hour,
                farms=farms, private=private, market=market, town=town),
                action=action(), status="ACTIVE", reward=0))
        self.calls = 0
        self.trace = hashlib.sha256()

    @property
    def obs(self):
        return self.state[self.seat].observation

    @property
    def tile(self):
        return self.obs.farms[self.seat]["tiles"][4][4]

    @property
    def private(self):
        return self.obs.private

    @property
    def cash(self):
        return self.obs.farms[self.seat]["money"]

    def tick(self, own=None, rival=None):
        if self.env.done:
            raise RuntimeError("No transitions after interpreter DONE")
        for s in self.state:
            s.observation.step = self.step
            s.observation.day = self.step // self.cfg.turnsPerDay
            s.observation.hour = self.step % self.cfg.turnsPerDay
        self.state[self.seat].action = own or action()
        self.state[1 - self.seat].action = rival or action()
        self.trace.update(json.dumps([self.step, [s.action for s in self.state]],
                                    sort_keys=True).encode())
        self.e.interpreter(self.state, self.env)
        self.trace.update(json.dumps(self.state, sort_keys=True).encode())
        self.calls += 1
        self.step += 1
        self.env.done = any(s.status == "DONE" for s in self.state)

    def until(self, step):
        while self.step < step:
            self.tick()

    def terminal(self):
        while not self.env.done:
            self.tick()
        return self.state[self.seat].reward

    def summary(self):
        return {"step": self.step, "calls": self.calls, "cash": self.cash,
                "tile": copy.deepcopy(self.tile), "shed": dict(self.private["shed"]),
                "inventories": copy.deepcopy(self.private["inventories"]),
                "trace_sha256": self.trace.hexdigest()}


def paired_sale(engine, seat, *, care_day=8, full=False, market_frees_room=False,
                feed_next=True, future_room=4):
    """Matched constructed CARE/COLLECT trajectories through realized sale.

    No market model substitutes for engine fills. Same follow-up script in both
    branches, including a capacity-unblocking sale before the harvest is dropped.
    """
    out = {}
    for treatment in ("COLLECT_FERTILIZER", "CARE"):
        w = World(engine, seat=seat, day=care_day, shed={"WHEAT": 100} if full else {})
        initial = action(treatment, market=[["SELL", "WHEAT", 1]] if market_frees_room else [])
        w.tick(initial)
        w.tick(action("PASS", market=[["SELL", "WHEAT", future_room]] if full else []))
        # Pickup+feed using real actions: same unit stays at shed-adjacent goose.
        w.tick({"farmer": ["PICKUP", "WHEAT", 1], "hands": [],
                "market": []} if full else action("PASS", market=[["BUY_PRODUCT", "WHEAT", 1]]))
        if not full:
            w.tick({"farmer": ["PICKUP", "WHEAT", 1], "hands": [], "market": []})
        w.tick(action("FEED") if feed_next else action())
        w.until((care_day + 2) * 24)
        w.tick(action("HARVEST"))
        w.tick(action("DROP"))
        w.tick(action(market=[["SELL", "EGG", 4], ["SELL", "FERTILIZER", 1]]))
        out[treatment] = w.summary()
        out[treatment]["terminal_cash"] = w.terminal()
    out["delta_cash"] = out["CARE"]["terminal_cash"] - out["COLLECT_FERTILIZER"]["terminal_cash"]
    return out


class LifecycleTests(unittest.TestCase):
    def world(self, **kw):
        return World(ENGINE, **kw)

    def test_care_costs_no_inventory_but_foregoes_collect(self):
        for seat in (0, 1):
            w = self.world(seat=seat, hour=20, inventory={"WHEAT": 2})
            w.tick(action("CARE"))
            self.assertTrue(w.tile["cared_today"])
            self.assertEqual(w.private["inventories"][0], {"WHEAT": 2})
            self.assertTrue(w.tile["fertilizer_available"])
            w.tick(action("COLLECT_FERTILIZER"))
            self.assertEqual(w.private["inventories"][0]["FERTILIZER"], 1)

    def test_bonus_is_banked_after_production_not_same_eod(self):
        for seat in (0, 1):
            w = self.world(seat=seat, inventory={"WHEAT": 1})
            w.tick(action("CARE"))
            self.assertEqual((w.tile["yield_units"], w.tile["pending_care_bonus"]), (1, 1))
            w.tick({"farmer": ["PICKUP", "WHEAT", 1], "hands": [], "market": []})
            w.tick(action("FEED"))
            w.until(10 * 24)
            self.assertEqual((w.tile["yield_units"], w.tile["pending_care_bonus"]), (3, 0))

    def test_unfed_care_does_not_bank(self):
        for seat in (0, 1):
            w = self.world(seat=seat, fed=False)
            w.tick(action("CARE"))
            self.assertEqual(w.tile["pending_care_bonus"], 0)
            self.assertEqual(w.tile["yield_units"], 1)

    def test_unfed_production_erases_pending_bonus(self):
        for seat in (0, 1):
            w = self.world(seat=seat, fed=False, pending=2)
            w.tick()
            self.assertEqual((w.tile["yield_units"], w.tile["pending_care_bonus"]), (1, 0))

    def test_two_unfed_days_escape_before_production(self):
        w = self.world(fed=False, unfed=1, pending=3)
        w.tick(action("CARE"))
        self.assertEqual(w.tile, {"kind": "COOP"})

    def test_duplicate_same_turn_care_banks_only_one(self):
        w = self.world(hands=[[4, 4]], hand_inventories=[{}])
        w.tick(action("CARE", hands=[["CARE"]]))
        self.assertEqual(w.tile["pending_care_bonus"], 1)

    def test_ordered_feed_care_shared_site(self):
        for first, second, inventories in (("FEED", "CARE", [{"WHEAT": 1}, {}]),
                                            ("CARE", "FEED", [{}, {"WHEAT": 1}])):
            for seat in (0, 1):
                w = self.world(seat=seat, fed=False, hands=[[4, 4]],
                               inventory=inventories[0], hand_inventories=[inventories[1]])
                w.tick(action(first, hands=[[second]]))
                self.assertEqual(w.tile["pending_care_bonus"], 1)
                self.assertEqual(w.tile["consecutive_unfed"], 0)

    def test_missing_feed_stock_cannot_make_bonus(self):
        w = self.world(fed=False, hands=[[4, 4]], hand_inventories=[{}])
        w.tick(action("CARE", hands=[["FEED"]]))
        self.assertEqual(w.tile["pending_care_bonus"], 0)

    def test_immature_care_banks_until_first_fed_production(self):
        w = self.world(day=1, pending=0, inventory={"WHEAT": 2})
        w.tick(action("CARE"))
        self.assertEqual((w.tile["yield_units"], w.tile["pending_care_bonus"]), (0, 1))
        for next_day in (2, 3):
            w.tick({"farmer": ["PICKUP", "WHEAT", 1], "hands": [], "market": []})
            w.tick(action("FEED"))
            w.until((next_day + 1) * 24)
        self.assertEqual((w.tile["yield_units"], w.tile["pending_care_bonus"]), (2, 0))

    def test_all_animal_intervals_produce_only_when_due(self):
        checked = 0
        for animal, first, interval, cap in (("GOOSE", 4, 1, 4), ("COW", 8, 2, 6), ("SHEEP", 6, 3, 6)):
            for day in range(1, 15):
                for seat in (0, 1):
                    w = self.world(seat=seat, day=day, animal=animal, pending=2)
                    w.tick(action("CARE"))
                    due = day + 1 >= first and (day + 1 - first) % interval == 0
                    self.assertEqual(w.tile["yield_units"], 3 if due else 0)
                    self.assertEqual(w.tile["pending_care_bonus"], 1 if due else 3)
                    checked += 1
        WITNESSES["interval_cases"] = checked

    def test_held_capacity_consumes_even_clipped_bonus(self):
        checked = 0
        for held in range(5):
            for pending in range(5):
                for fed in (False, True):
                    for seat in (0, 1):
                        w = self.world(seat=seat, held=held, pending=pending, fed=fed)
                        w.tick()
                        self.assertEqual(w.tile["yield_units"], min(4, held + 1 + (pending if fed else 0)))
                        self.assertEqual(w.tile["pending_care_bonus"], 0)
                        checked += 1
        WITNESSES["cap_cases"] = checked

    def test_harvest_before_refresh_preserves_headroom(self):
        w = self.world(held=4, pending=1)
        w.tick(action("HARVEST"))
        self.assertEqual(w.private["shed"]["EGG"], 4)
        self.assertEqual(w.tile["yield_units"], 2)

    def test_full_shed_actually_discards_collected_fertilizer(self):
        for seat in (0, 1):
            w = self.world(seat=seat, shed={"WHEAT": 100})
            w.tick(action("COLLECT_FERTILIZER"))
            self.assertEqual(w.private["shed"]["FERTILIZER"], 0)
            self.assertEqual(w.private["inventories"], [{}])
            self.assertEqual(sum(w.private["shed"].values()), 100)

    def test_same_turn_sale_frees_room_before_drop(self):
        for seat in (0, 1):
            w = self.world(seat=seat, shed={"WHEAT": 100})
            w.tick(action("COLLECT_FERTILIZER", market=[["SELL", "WHEAT", 1]]))
            self.assertEqual(w.private["shed"]["FERTILIZER"], 1)
            self.assertEqual(sum(w.private["shed"].values()), 100)

    def test_same_turn_purchase_fills_room_before_drop(self):
        w = self.world(shed={"WHEAT": 99})
        w.tick(action("COLLECT_FERTILIZER", market=[["BUY_PRODUCT", "WHEAT", 1]]))
        self.assertEqual(w.private["shed"]["FERTILIZER"], 0)
        self.assertEqual(w.private["shed"]["WHEAT"], 100)

    def test_foregone_fert_can_admit_other_actor_egg(self):
        result = {}
        for treatment in ("COLLECT_FERTILIZER", "CARE"):
            w = self.world(shed={"WHEAT": 99}, hands=[[4, 4]], hand_inventories=[{"EGG": 1}])
            w.tick(action(treatment, hands=[["PASS"]]))
            result[treatment] = w.private["shed"]
        self.assertEqual((result["COLLECT_FERTILIZER"]["FERTILIZER"], result["COLLECT_FERTILIZER"]["EGG"]), (1, 0))
        self.assertEqual((result["CARE"]["FERTILIZER"], result["CARE"]["EGG"]), (0, 1))

    def test_day27_can_harvest_bonus_before_terminal(self):
        w = self.world(day=27, inventory={"WHEAT": 1})
        w.tick(action("CARE"))
        w.tick({"farmer": ["PICKUP", "WHEAT", 1], "hands": [], "market": []})
        w.tick(action("FEED"))
        w.until(29 * 24)
        self.assertEqual(w.tile["yield_units"], 3)
        w.tick(action("HARVEST"))
        w.tick(action("DROP"))
        w.tick(action(market=[["SELL", "EGG", 3]]))
        self.assertGreater(w.terminal(), 3000)
        self.assertEqual(w.step, 719)
        WITNESSES["last_profitable_care_day_fixture"] = w.summary()

    def test_day28_bonus_never_produces_before_done(self):
        w = self.world(day=28, inventory={"WHEAT": 1})
        w.tick(action("CARE"))
        self.assertEqual((w.tile["yield_units"], w.tile["pending_care_bonus"]), (1, 1))
        w.tick({"farmer": ["PICKUP", "WHEAT", 1], "hands": [], "market": []})
        w.tick(action("FEED"))
        w.terminal()
        self.assertEqual(w.step, 719)
        self.assertEqual((w.tile["yield_units"], w.tile["pending_care_bonus"]), (1, 1))
        with self.assertRaises(RuntimeError):
            w.tick()

    def test_legal_initializer_to_goose_care_harvest_sale(self):
        # Unlike the other fixtures, this one never injects any state after init.
        e = ENGINE
        cfg = Struct({k: v.get("default") if isinstance(v, dict) else v
                      for k, v in e.specification["configuration"].items()})
        cfg.weedSpawnChance = 0
        cfg.seed = 17
        env = Struct(configuration=cfg, done=False, info={})
        state = [Struct(observation=Struct(), action={}, status="ACTIVE", reward=0) for _ in range(2)]
        e.interpreter(state, env)
        for step in range(124):
            a = action()
            if step == 0:
                a = action("BUILD_COOP", market=[["BUY_ANIMAL", "GOOSE", 1], ["BUY_PRODUCT", "WHEAT", 6]])
            elif step == 1:
                a["farmer"] = ["PICKUP", "GOOSE", 1]
            elif step == 2:
                a["farmer"] = ["PLACE", "GOOSE"]
            elif step % 24 == 3:
                a["farmer"] = ["PICKUP", "WHEAT", 1]
            elif step % 24 == 4:
                a["farmer"] = ["FEED"]
            elif step == 2 * 24 + 23:
                a["farmer"] = ["CARE"]
            elif step == 96:
                a["farmer"] = ["HARVEST"]
            elif step == 97:
                a["farmer"] = ["DROP"]
            elif step == 98:
                a["market"] = [["SELL", "EGG", 4]]
            for seat, s in enumerate(state):
                s.observation.step = step
                s.action = a if seat == 0 else action()
            e.interpreter(state, env)
            if step == 95:
                self.assertEqual(state[0].observation.farms[0]["tiles"][4][4]["yield_units"], 2)
            if step == 98:
                WITNESSES["legal_setup_cash_after_sale"] = state[0].observation.farms[0]["money"]
                self.assertEqual(state[0].observation.private["shed"]["EGG"], 0)
                self.assertEqual(state[0].observation.farms[0]["tiles"][4][4]["yield_units"], 0)
        # CASH movement is recorded, not asserted as profit over initial capital.

    def test_realized_economics_depend_on_actual_fert_admission(self):
        for seat in (0, 1):
            admitted = paired_sale(ENGINE, seat)
            discarded = paired_sale(ENGINE, seat, full=True)
            freed = paired_sale(ENGINE, seat, full=True, market_frees_room=True)
            unfed = paired_sale(ENGINE, seat, full=True, feed_next=False)
            future_clip = paired_sale(ENGINE, seat, full=True, future_room=1)
            self.assertLess(admitted["delta_cash"], 0)
            self.assertGreater(discarded["delta_cash"], 0)
            self.assertLess(freed["delta_cash"], 0)
            self.assertEqual(unfed["delta_cash"], 0)
            self.assertEqual(future_clip["delta_cash"], 0)
            WITNESSES[f"economics_seat{seat}"] = {"fert_admitted": admitted, "fert_discarded": discarded,
                                                  "market_frees_room": freed, "no_followup_feed": unfed,
                                                  "future_egg_clipped": future_clip}


MUTANTS = {
    "same_eod_bonus": ("bonus = tile.pop(\"pending_care_bonus\", 0) if tile[\"fed_today\"] else 0",
                       "bonus = (tile.pop(\"pending_care_bonus\", 0) + int(tile[\"cared_today\"])) if tile[\"fed_today\"] else 0"),
    "care_banks_unfed": ("if tile[\"cared_today\"] and tile[\"fed_today\"]:", "if tile[\"cared_today\"]:"),
    "bonus_pays_unfed": ("bonus = tile.pop(\"pending_care_bonus\", 0) if tile[\"fed_today\"] else 0", "bonus = tile.pop(\"pending_care_bonus\", 0)"),
    "goose_cap_five": ('"max_held": 4, "product": "EGG"', '"max_held": 5, "product": "EGG"'),
    "late_escape": ('if tile["consecutive_unfed"] >= 2:', 'if tile["consecutive_unfed"] >= 3:'),
    "bonus_lost_off_interval": ('if days_since_first >= 0 and days_since_first % a["interval"] == 0:',
                                'if days_since_first >= 0:'),
    "drop_ignores_capacity": ('room = max(0, capacity - current)', 'room = 1000000'),
    "reverse_inventory_drop": ('for inv in private["inventories"]:', 'for inv in reversed(private["inventories"]):'),
    "late_terminal_eod": ('if step >= cfg.episodeSteps - 2:', 'if step >= cfg.episodeSteps - 1:'),
    "care_consumes_fertilizer": ('if tile["cared_today"]:\n            return\n        tile["cared_today"] = True',
                                'if tile["cared_today"]:\n            return\n        if not _inv_take(inv, "FERTILIZER", 1):\n            return\n        tile["cared_today"] = True'),
}


def run_suite(engine):
    global ENGINE, WITNESSES
    ENGINE, WITNESSES = engine, {}
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(LifecycleTests))
    report = {"tests_run": result.testsRun, "failures": len(result.failures),
              "errors": len(result.errors), "skips": len(result.skipped),
              "success": result.wasSuccessful(), "witnesses": copy.deepcopy(WITNESSES)}
    return result, report, stream.getvalue()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mutations", action="store_true")
    args = parser.parse_args(argv)
    engine, provenance = load_engine(args.runtime)
    result, controls, log = run_suite(engine)
    print(log, end="")
    report = {"schema": "titan.s8.engine-lifecycle-controls.v1", "role": "validation_only",
              "default_changed": False, "native_field_games": 0,
              "scope": "constructed complete-interpreter controls plus legal initializer trajectory; not native profitability",
              "python": sys.version.split()[0], "optimized": bool(sys.flags.optimize),
              "source_sha256": digest(Path(__file__).read_bytes()), "provenance": provenance,
              "controls": controls, "mutations": {}}
    ok = result.wasSuccessful() and not result.skipped
    if ok and args.mutations:
        original = Path(engine.__file__).read_text()
        for name, (old, new) in MUTANTS.items():
            count = original.count(old)
            if count != 1:
                raise ValueError(f"Mutation {name} needs exactly one anchor, found {count}")
            module = types.ModuleType(f"s8_fault_{name}")
            module.__file__ = engine.__file__
            # Mutants exist only in memory, after the original source pin passes.
            changed = original.replace(old, new, 1)
            exec(compile(changed, str(engine.__file__) + ":" + name, "exec"), module.__dict__)
            mr, summary, mlog = run_suite(module)
            rejected = bool(mr.failures) and not mr.errors and not mr.skipped
            report["mutations"][name] = {"rejected_by_assertions": rejected,
                                         "tests_run": mr.testsRun, "failures": len(mr.failures),
                                         "errors": len(mr.errors), "skips": len(mr.skipped),
                                         "failed_tests": [str(t) for t, _ in mr.failures],
                                         "mutated_source_sha256": digest(changed.encode())}
            ok = ok and rejected
            if not rejected:
                print(mlog)
    report["success"] = ok
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"success": ok, "tests": controls["tests_run"],
                      "mutants": len(report["mutations"]), "output": str(args.output)}))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
