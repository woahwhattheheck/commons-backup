# SPDX-License-Identifier: Apache-2.0
"""Source-pinned native-delegate / official-interpreter terminal feed experiments.

Requires an existing extracted runtime. Never downloads files or dispatches jobs.
Full fixtures start at a specified initialized state, not a natural game opening.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys
import types
import unittest

HERE = Path(__file__).resolve().parent
COUNTS = {"paired_tail_cells": 0, "interpreter_calls": 0,
          "terminal_parent_cash_advantage_min": None,
          "terminal_parent_cash_advantage_max": None}


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


MUTANTS = {
    "ignore-starvation": [("_integer(tile.get(\"consecutive_unfed\"), 0, 0)",
                           "_integer(tile.get(\"consecutive_unfed\"), 0, 1)")],
    "ignore-care-bonus": [("_integer(tile.get(\"pending_care_bonus\"), 0, 0)",
                          "_integer(tile.get(\"pending_care_bonus\"), 0, 9)")],
    "ignore-future-care": [('or action[0] == "CARE"', 'or False')],
    "ignore-proposal-custody": [("not _only_wheat_reduction(selected, proposed)", "False")],
    "allow-penultimate-day": [("_integer(now, 672, 694)", "_integer(now, 648, 694)"),
                             ('window["through_step"] != 695', 'window["through_step"] not in (671, 695)')],
    "never-override": [('return selected, {', 'return proposed, {')],
}


def configure(root, mutant):
    pins = json.loads((HERE / "PINS.json").read_text())
    for rel, expected in pins.items():
        data = (root / rel).read_bytes()
        if git_blob(data) != expected:
            raise ValueError(f"source mismatch: {rel}")
    sys.path.insert(0, str(root))
    global mechanics, delegate, gate, engine, S
    mechanics = load(root / "mechanics.py", "mechanics")
    delegate = load(root / "operating_stock.py", "operating_stock").protect_feed_stock
    source = (HERE / "terminal_feed_gate.py").read_text()
    if mutant:
        for before, after in MUTANTS[mutant]:
            if source.count(before) != 1:
                raise ValueError(f"ambiguous mutant replacement: {before}")
            source = source.replace(before, after)
    module = types.ModuleType("terminal_feed_gate_under_test")
    exec(compile(source, "terminal_feed_gate_under_test", "exec"), module.__dict__)
    gate = module.admit_terminal_feed_override
    evaluator = load(root / "checks/reference/evaluator/evaluate.py", "feed_official_evaluator")
    engine, _ = evaluator.get_engine(root / "checks/reference/engine",
                                     root / "checks/reference/evaluator/loader.py")
    S = evaluator.Struct
    return pins


def passive():
    return {"farmer": ["PASS"], "hands": [], "market": []}


def fixture(seat=0, animal="COW", placed=1, held=0, actor=1,
            inventory=10000, quantity=2, now=690):
    cfg = S({k: v.get("default") if isinstance(v, dict) else v
             for k, v in engine.specification["configuration"].items()})
    cfg.weedSpawnChance = 0
    farms = [engine._new_farm(10, 50000) for _ in range(2)]
    market = engine._new_market()
    market["inventory"]["WHEAT"] = inventory
    engine._refresh_prices(market)
    town = {"unlocked_shops": []}
    state = [S(observation=S(player=i, step=now, day=now // 24, hour=now % 24,
                farms=farms, market=market, town=town, private=engine._new_private()),
                action=passive(), status="ACTIVE", reward=0) for i in range(2)]
    farm = farms[seat]
    private = state[seat].observation.private
    farm["farmer"] = [4, 4] if actor == 0 else [0, 0]
    farm["hands"] = [[4, 4] if actor == 1 else [0, 0]]
    farm["hires_today"] = 1
    private["inventories"] = [{}, {}]
    private["shed"]["WHEAT"] = quantity
    for x in range(3, 3 - quantity, -1):
        farm["tiles"][4][x] = engine._new_animal(animal, placed)
        farm["tiles"][4][x]["yield_units"] = held
    selected = {"farmer": ["PASS"], "hands": [["PASS"]],
                "market": [["SELL", "WHEAT", quantity]]}
    route = [{"farmer": ["PASS"], "hands": [["PASS"]], "market": []} for _ in range(720)]
    moves = [["PICKUP", "WHEAT", quantity], ["WEST"], ["FEED"]]
    if quantity == 2:
        moves += [["WEST"], ["FEED"]]
    for offset, action in enumerate(moves, 1):
        if actor == 0:
            route[now + offset]["farmer"] = action
        else:
            route[now + offset]["hands"][0] = action
    return state, S(configuration=cfg, done=False, info={"seed": 9600803}), selected, route


def propose(fx):
    state, env, selected, route = fx
    seat = next(i for i in range(2) if state[i].observation.farms[i]["hands"])
    obs = state[seat].observation
    out, report = delegate(mechanics, obs, dict(env.configuration), selected,
                           obs.farms[seat], obs.private, route)
    amended, diag = gate(obs, dict(env.configuration), selected, out, report, obs.farms[seat], route)
    return out, report, amended, diag


def finish(fx, action):
    state, env, selected, route = copy.deepcopy(fx)
    seat = next(i for i in range(2) if state[i].observation.farms[i]["hands"])
    now = state[seat].observation.step
    for step in range(now, 719):
        for s in state:
            s.observation.step = step
            s.action = passive()
        state[seat].action = copy.deepcopy(action if step == now else route[step])
        engine.interpreter(state, env)
        COUNTS["interpreter_calls"] += 1
    return state


class TerminalFeedTests(unittest.TestCase):
    def kept(self, fx):
        out, report, amended, diag = propose(fx)
        self.assertIs(amended, out)
        self.assertIs(diag, report)
        return out, report

    def test_01_paired_official_terminal_matrix(self):
        grid = itertools.product(range(2), ("COW", "SHEEP", "GOOSE"), range(1, 7),
                                 (0, 4), range(2), (9600, 10000, 12000), (1, 2))
        if ARGS.smoke:
            grid = [(seat, "COW", 1, 0, 1, 10000, 2) for seat in range(2)]
        for seat, animal, placed, held, actor, inventory, quantity in grid:
            with self.subTest(seat=seat, animal=animal, placed=placed, held=held,
                              actor=actor, inventory=inventory, quantity=quantity):
                fx = fixture(seat, animal, placed, held, actor, inventory, quantity)
                before = copy.deepcopy(fx)
                old, report, amended, diag = propose(fx)
                self.assertTrue(report["changed"])
                self.assertTrue(report["certified"])
                self.assertIs(amended, fx[2])
                self.assertFalse(diag["certified"])
                self.assertEqual(fx, before)
                protected, released = finish(fx, old), finish(fx, amended)
                p, r = protected[seat].observation, released[seat].observation
                self.assertEqual(protected[seat].status, "DONE")
                self.assertEqual(released[seat].status, "DONE")
                advantage = r.farms[seat]["money"] - p.farms[seat]["money"]
                self.assertGreater(advantage, 0)
                self.assertEqual(r.farms[1-seat], p.farms[1-seat])
                self.assertEqual(r.private, p.private)
                # Physical animal state is identical except the known, unused
                # starvation-history counter. Global WHEAT price/supply also
                # differ: this is NOT an adaptive-policy equivalence assertion.
                rp, pp = copy.deepcopy(r.farms[seat]), copy.deepcopy(p.farms[seat])
                for farm in (rp, pp):
                    farm.pop("money")
                    for row in farm["tiles"]:
                        for tile in row:
                            if isinstance(tile, dict) and "animal" in tile:
                                tile.pop("consecutive_unfed")
                self.assertEqual(rp, pp)
                for product in engine.PRODUCTS:
                    if product != "WHEAT":
                        self.assertEqual(r.market["inventory"][product], p.market["inventory"][product])
                COUNTS["paired_tail_cells"] += 1
                for key, fn in (("terminal_parent_cash_advantage_min", min),
                                ("terminal_parent_cash_advantage_max", max)):
                    COUNTS[key] = advantage if COUNTS[key] is None else fn(COUNTS[key], advantage)

    def test_02_escape_prevention_is_retained_and_engine_discriminates(self):
        for seat in range(2):
            fx = fixture(seat=seat, quantity=1)
            fx[0][seat].observation.farms[seat]["tiles"][4][3]["consecutive_unfed"] = 1
            old, _ = self.kept(fx)
            safe, unsafe = finish(fx, old), finish(fx, fx[2])
            self.assertEqual(safe[seat].observation.farms[seat]["tiles"][4][3]["animal"], "COW")
            self.assertNotIn("animal", unsafe[seat].observation.farms[seat]["tiles"][4][3])

    def test_03_pending_care_output_is_retained_and_engine_discriminates(self):
        for seat in range(2):
            fx = fixture(seat=seat, quantity=1, placed=19)
            fx[0][seat].observation.farms[seat]["tiles"][4][3]["pending_care_bonus"] = 2
            old, _ = self.kept(fx)
            safe, unsafe = finish(fx, old), finish(fx, fx[2])
            self.assertEqual(safe[seat].observation.farms[seat]["tiles"][4][3]["yield_units"], 3)
            self.assertEqual(unsafe[seat].observation.farms[seat]["tiles"][4][3]["yield_units"], 1)

    def test_04_penultimate_day_kept_and_second_refresh_matters(self):
        for seat in range(2):
            fx = fixture(seat=seat, quantity=1, now=666)
            old, _ = self.kept(fx)
            safe, unsafe = finish(fx, old), finish(fx, fx[2])
            self.assertIn("animal", safe[seat].observation.farms[seat]["tiles"][4][3])
            self.assertNotIn("animal", unsafe[seat].observation.farms[seat]["tiles"][4][3])

    def test_05_mixed_obligations_are_not_partially_reallocated(self):
        fx = fixture()
        fx[0][0].observation.farms[0]["tiles"][4][2]["consecutive_unfed"] = 1
        self.kept(fx)

    def test_06_current_and_future_care_are_retained(self):
        fx = fixture()
        fx[0][0].observation.farms[0]["tiles"][4][3]["cared_today"] = True
        self.kept(fx)
        fx = fixture()
        fx[3][695]["farmer"] = ["CARE"]
        self.kept(fx)

    def test_07_incomplete_or_coerced_animal_facts_do_not_release(self):
        for key in ("consecutive_unfed", "pending_care_bonus", "fed_today", "cared_today"):
            for value in (None, "0", False if "unfed" in key or "bonus" in key else 0):
                fx = fixture()
                out, report, _, _ = propose(fx)
                obs = fx[0][0].observation
                obs.farms[0]["tiles"][4][3][key] = value
                amended, diag = gate(obs, dict(fx[1].configuration), fx[2], out,
                                     report, obs.farms[0], fx[3])
                self.assertIs(amended, out)
                self.assertIs(diag, report)

    def test_08_unrelated_units_rows_and_metadata_are_never_reverted(self):
        for kind in ("units", "product", "length", "metadata", "suffix"):
            fx = fixture()
            fx[2]["market"] += [[] for _ in range(9)] + [["SELL", "MILK", 1]]
            out, report, _, _ = propose(fx)
            tampered = copy.deepcopy(out)
            if kind == "units": tampered["farmer"] = ["EAST"]
            elif kind == "product": tampered["market"][0] = ["SELL", "MILK", 1]
            elif kind == "length": tampered["market"].append([])
            elif kind == "metadata": tampered["extra"] = "later_owner"
            else: tampered["market"][10] = []
            obs = fx[0][0].observation
            amended, diag = gate(obs, dict(fx[1].configuration), fx[2], tampered,
                                 report, obs.farms[0], fx[3])
            self.assertIs(amended, tampered)
            self.assertIs(diag, report)

    def test_09_duplicate_lots_and_raw_suffix_are_restored_exactly(self):
        fx = fixture()
        fx[2]["market"] = [["SELL", "WHEAT", 1], [], ["SELL", "WHEAT", 1]] + [[]]*7 + [["HIRE"]]
        _, report, amended, _ = propose(fx)
        self.assertTrue(report["changed"])
        self.assertIs(amended, fx[2])
        self.assertEqual(amended["market"][10], ["HIRE"])

    def test_10_configuration_and_two_seat_checks(self):
        fx = fixture()
        out, report, _, _ = propose(fx)
        obs = fx[0][0].observation
        for key in ("boardSize", "turnsPerDay", "episodeSteps", "shedCapacity", "maxMarketOrdersPerTurn"):
            for val in (False, str(fx[1].configuration[key]), 0):
                cfg = dict(fx[1].configuration); cfg[key] = val
                self.assertIs(gate(obs, cfg, fx[2], out, report, obs.farms[0], fx[3])[0], out)
        for seat in (False, 2, "0"):
            other = dict(obs, player=seat)
            self.assertIs(gate(other, dict(fx[1].configuration), fx[2], out, report, obs.farms[0], fx[3])[0], out)

    def test_11_bad_or_unproven_delegate_reports_keep_identity(self):
        fx = fixture(); out, report, _, _ = propose(fx); obs = fx[0][0].observation
        for field, val in (("certified", False), ("changed", False), ("withheld_units", 3),
                           ("reason", "other_owner"), ("window", {})):
            bad = dict(report); bad[field] = val
            amended, diag = gate(obs, dict(fx[1].configuration), fx[2], out, bad, obs.farms[0], fx[3])
            self.assertIs(amended, out); self.assertIs(diag, bad)

    def test_12_malformed_route_keeps_identity(self):
        fx = fixture(); out, report, _, _ = propose(fx); obs = fx[0][0].observation
        for bad in ([], None, fx[3][:695], fx[3][:695] + [None], fx[3][:695] + [{"hands": "x"}]):
            amended, diag = gate(obs, dict(fx[1].configuration), fx[2], out, report, obs.farms[0], bad)
            self.assertIs(amended, out); self.assertIs(diag, report)

    def test_13_no_baseline_change_preserves_identity(self):
        fx = fixture(); fx[2]["market"] = []
        self.kept(fx)


def main():
    global ARGS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--mutant", choices=sorted(MUTANTS))
    parser.add_argument("--receipt", type=Path)
    ARGS = parser.parse_args()
    try:
        pins = configure(ARGS.runtime.resolve(), ARGS.mutant)
    except (ValueError, OSError, ImportError) as exc:
        print(f"INPUT ERROR: {exc}", file=sys.stderr)
        return 2
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TerminalFeedTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    # Recheck the full named input set after execution, not just before imports.
    unchanged = all(git_blob((ARGS.runtime / p).read_bytes()) == sha for p, sha in pins.items())
    receipt = {"scope": "synthetic source-pinned fixed-route terminal interpreter fixtures",
               "not_whole_agent_economics": True, "debug": __debug__, "mutant": ARGS.mutant,
               "tests_run": result.testsRun, "failures": len(result.failures),
               "errors": len(result.errors), "source_pins": pins,
               "input_hashes_unchanged": unchanged, **COUNTS}
    if ARGS.receipt:
        ARGS.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, sort_keys=True))
    return 0 if result.wasSuccessful() and unchanged else 1


if __name__ == "__main__":
    raise SystemExit(main())
