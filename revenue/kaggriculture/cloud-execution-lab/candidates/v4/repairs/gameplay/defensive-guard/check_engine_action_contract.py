# SPDX-License-Identifier: Apache-2.0
"""Independent engine contract; these are NEW tests, not the missing 24 donor tests."""
from __future__ import annotations

import argparse
import copy
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

from engine_action_contract import EngineOracle, PINS, verify_inputs

ORACLE = None
NONFINITE = (float("inf"), float("-inf"), float("nan"))


class ActionContract(unittest.TestCase):
    def setUp(self):
        if ORACLE is None:
            self.fail("explicit offline --engine-dir and --loader are required")
        self.o = ORACLE

    def equal_worlds(self, left, right):
        self.assertEqual(self.o.snapshot(left), self.o.snapshot(right))

    def stock_world(self, seat, **kw):
        w = self.o.world(**kw)
        w[0][seat].observation.private["shed"]["WHEAT"] = 10
        return w

    def test_live_market_infinities_raise_but_suffix_never_parsed(self):
        for seat in (0, 1):
            for op, item in (("SELL", "WHEAT"), ("BUY_PRODUCT", "WHEAT"),
                             ("BUY_SEED", "WHEAT"), ("BUY_ANIMAL", "COW"),
                             ("SELL", "NOT_A_PRODUCT"), ("BUY_PRODUCT", "MILK")):
                for quantity in NONFINITE[:2]:
                    for cap in (1, 3, 10):
                        with self.subTest(seat=seat, op=op, item=item, qty=quantity, cap=cap):
                            w = self.stock_world(seat, cap=cap)
                            row = [op, item, quantity]
                            with self.assertRaises(OverflowError):
                                self.o.run(w, seat, {"market": [[]] * (cap - 1) + [row]})
                            self.equal_worlds(self.o.run(w, seat, {"market": [[]] * cap + [row]}),
                                              self.o.run(w, seat, {"market": [[]] * cap}))

    def test_market_invalid_quantities_are_noop_slots_not_fatal(self):
        for seat in (0, 1):
            for quantity in (float("nan"), None, "inf", "nan", "1.2", "", [], {}, 0, -2, False):
                with self.subTest(seat=seat, qty=quantity):
                    w = self.stock_world(seat)
                    self.equal_worlds(self.o.run(w, seat, {"market": [["SELL", "WHEAT", quantity]]}),
                                      self.o.run(w, seat, {"market": [[]]}))

    def test_market_finite_coercion_is_actual_int_semantics(self):
        for seat in (0, 1):
            for quantity in (True, 1.9, 2.9, "2", " +2 ", "02", 10 ** 400):
                with self.subTest(seat=seat, qty=str(quantity)[:30]):
                    w = self.stock_world(seat)
                    actual = self.o.run(w, seat, {"market": [["SELL", "WHEAT", quantity]]})
                    reference = self.o.run(w, seat, {"market": [["SELL", "WHEAT", int(quantity)]]})
                    self.equal_worlds(actual, reference)
                    self.assertEqual(actual[0][seat].observation.private["shed"]["WHEAT"],
                                     10 - min(10, int(quantity)))

    def test_invalid_raw_slots_cannot_be_compacted_at_cap(self):
        for seat in (0, 1):
            for invalid in ([], None, {}, ["NOOP"], ["SELL", "WHEAT", float("nan")]):
                w = self.stock_world(seat, cap=1)
                action = {"market": [invalid, ["SELL", "WHEAT", 2]]}
                original = self.o.run(w, seat, action)
                mask = self.o.run(w, seat, {"market": [[], ["SELL", "WHEAT", 2]]})
                compacted = self.o.run(w, seat, {"market": [["SELL", "WHEAT", 2]]})
                self.equal_worlds(original, mask)
                self.assertNotEqual(self.o.snapshot(original), self.o.snapshot(compacted))
                self.assertEqual(original[0][seat].observation.private["shed"]["WHEAT"], 10)

    def test_raw_slots_determine_lockstep_opponent_prices(self):
        for seat in (0, 1):
            w = self.stock_world(seat)
            rival = {"market": [["BUY_PRODUCT", "WHEAT", 10]]}
            queued = self.o.run(w, seat, {"market": [[], ["SELL", "WHEAT", 10]]}, rival)
            compact = self.o.run(w, seat, {"market": [["SELL", "WHEAT", 10]]}, rival)
            self.assertNotEqual(queued[0][0].observation.farms, compact[0][0].observation.farms)
            self.assertEqual(queued[0][seat].observation.private["shed"]["WHEAT"], 0)
            self.assertEqual(compact[0][seat].observation.private["shed"]["WHEAT"], 0)

    def test_market_cap_is_max_one_int_not_positive_only(self):
        for seat in (0, 1):
            for cap in (0, -2, "0", "-3", 1.9, "1"):
                w = self.stock_world(seat, cap=cap)
                a = {"market": [["SELL", "WHEAT", 1], ["SELL", "WHEAT", float("inf")]]}
                out = self.o.run(w, seat, a)
                self.assertEqual(out[0][seat].observation.private["shed"]["WHEAT"], 9)

    def test_atomic_market_ops_ignore_numeric_extra_fields(self):
        for seat in (0, 1):
            for op in ("HIRE", "BUY_LAND"):
                for quantity in (*NONFINITE, None, [], {}):
                    w = self.o.world()
                    actual = self.o.run(w, seat, {"market": [[op, "IGNORED", quantity]]})
                    reference = self.o.run(w, seat, {"market": [[op]]})
                    self.equal_worlds(actual, reference)
                    if op == "HIRE":
                        self.assertEqual(len(actual[0][seat].observation.farms[seat]["hands"]), 1)
                    else:
                        self.assertIn("NE", actual[0][seat].observation.farms[seat]["unlocked_quadrants"])

    def test_unknown_market_op_ignores_bad_third_field(self):
        for seat in (0, 1):
            for quantity in NONFINITE:
                w = self.o.world()
                self.equal_worlds(self.o.run(w, seat, {"market": [["NOT_AN_OP", "WHEAT", quantity]]}),
                                  self.o.run(w, seat, {"market": [[]]}))

    def test_short_market_and_nonlist_queues_are_noop(self):
        for seat in (0, 1):
            for market in (None, {}, "SELL", [["SELL"]], [["SELL", "WHEAT"]],
                           [["BUY_SEED", "WHEAT"]], [("SELL", "WHEAT", 2)]):
                w = self.stock_world(seat)
                self.equal_worlds(self.o.run(w, seat, {"market": market}), self.o.run(w, seat, {}))

    def test_unsupported_product_buys_are_not_fills(self):
        for seat in (0, 1):
            for item in ("MILK", "WOOL", "EGG", "CARROT", "COW"):
                w = self.o.world()
                self.equal_worlds(self.o.run(w, seat, {"market": [["BUY_PRODUCT", item, 2]]}),
                                  self.o.run(w, seat, {}))

    def test_reachable_unit_quantity_conversion_errors(self):
        for seat in (0, 1):
            for actor in (0, 1):
                for op in ("PICKUP", "PLACE"):
                    for quantity, error in (*[(x, OverflowError) for x in NONFINITE[:2]],
                                             (float("nan"), ValueError), (None, TypeError), ("bad", ValueError)):
                        with self.subTest(seat=seat, actor=actor, op=op, qty=quantity):
                            w = self.stock_world(seat)
                            self.o.actors(w, seat, [(4, 4)] * (actor + 1))
                            w[0][seat].observation.private["inventories"][actor]["WHEAT"] = 3
                            action = {"farmer": [op, "WHEAT", quantity]} if actor == 0 else {
                                "farmer": ["PASS"], "hands": [[op, "WHEAT", quantity]]}
                            with self.assertRaises(error):
                                self.o.run(w, seat, action)

    def test_nonexistent_unit_quantity_is_never_parsed(self):
        for seat in (0, 1):
            for op in ("PICKUP", "PLACE"):
                for quantity in (*NONFINITE, None, "bad"):
                    w = self.stock_world(seat)
                    a = {"farmer": ["PASS"], "hands": [[op, "WHEAT", quantity]]}
                    self.equal_worlds(self.o.run(w, seat, a), self.o.run(w, seat, {}))

    def test_nonadjacent_unit_quantity_is_never_parsed(self):
        for seat in (0, 1):
            for op in ("PICKUP", "PLACE"):
                for quantity in (*NONFINITE, None, "bad"):
                    w = self.stock_world(seat)
                    self.o.actors(w, seat, [(0, 0)])
                    self.equal_worlds(self.o.run(w, seat, {"farmer": [op, "WHEAT", quantity]}),
                                      self.o.run(w, seat, {}))

    def test_animal_place_ignores_bad_quantity_and_preserves_work(self):
        for seat in (0, 1):
            for animal, info in self.o.engine.ANIMALS.items():
                for pos in ((0, 0), (4, 4)):
                    for quantity in (*NONFINITE, None, "bad", [], {}):
                        with self.subTest(seat=seat, animal=animal, pos=pos, qty=quantity):
                            w = self.o.world()
                            self.o.actors(w, seat, [pos])
                            w[0][seat].observation.farms[seat]["tiles"][pos[1]][pos[0]] = {"kind": info["structure"]}
                            w[0][seat].observation.private["inventories"][0][animal] = 1
                            actual = self.o.run(w, seat, {"farmer": ["PLACE", animal, quantity]})
                            good = self.o.run(w, seat, {"farmer": ["PLACE", animal]})
                            self.equal_worlds(actual, good)
                            self.assertEqual(actual[0][seat].observation.farms[seat]["tiles"][pos[1]][pos[0]]["animal"], animal)

    def test_matching_animal_place_without_inventory_still_ignores_quantity(self):
        for seat in (0, 1):
            for quantity in NONFINITE:
                w = self.o.world()
                w[0][seat].observation.farms[seat]["tiles"][4][4] = {"kind": "PASTURE"}
                self.equal_worlds(self.o.run(w, seat, {"farmer": ["PLACE", "COW", quantity]}),
                                  self.o.run(w, seat, {}))

    def test_animal_place_on_wrong_structure_uses_shed_quantity(self):
        for seat in (0, 1):
            for structure in (None, {"kind": "COOP"}, "LOCKED"):
                w = self.o.world()
                w[0][seat].observation.farms[seat]["tiles"][4][4] = structure
                w[0][seat].observation.private["inventories"][0]["COW"] = 1
                with self.assertRaises(OverflowError):
                    self.o.run(w, seat, {"farmer": ["PLACE", "COW", float("inf")]})

    def test_shed_unit_finite_coercion_and_default_quantity(self):
        for seat in (0, 1):
            for op in ("PICKUP", "PLACE"):
                for quantity in (True, 1.9, "2", 10 ** 400):
                    w = self.stock_world(seat)
                    w[0][seat].observation.private["inventories"][0]["WHEAT"] = 10
                    self.equal_worlds(self.o.run(w, seat, {"farmer": [op, "WHEAT", quantity]}),
                                      self.o.run(w, seat, {"farmer": [op, "WHEAT", int(quantity)]}))
                w = self.stock_world(seat)
                w[0][seat].observation.private["inventories"][0]["WHEAT"] = 10
                self.equal_worlds(self.o.run(w, seat, {"farmer": [op, "WHEAT"]}),
                                  self.o.run(w, seat, {"farmer": [op, "WHEAT", 1]}))

    def test_ignored_unit_quantities_do_not_strip_actions(self):
        for seat in (0, 1):
            for op, item in (("WEST", "ignored"), ("DROP", "ignored"), ("PLANT", "WHEAT"),
                             ("WATER", "ignored"), ("CARE", "ignored"), ("FEED", "ignored")):
                for quantity in NONFINITE:
                    w = self.stock_world(seat)
                    priv = w[0][seat].observation.private
                    priv["seeds"]["WHEAT"] = 1
                    priv["inventories"][0]["WHEAT"] = 2
                    if op == "WATER":
                        w[0][seat].observation.farms[seat]["tiles"][4][4] = self.o.engine._new_plant("WHEAT", 0, 24)
                    if op in ("CARE", "FEED"):
                        w[0][seat].observation.farms[seat]["tiles"][4][4] = self.o.engine._new_animal("COW", 0)
                    self.equal_worlds(self.o.run(w, seat, {"farmer": [op, item, quantity]}),
                                      self.o.run(w, seat, {"farmer": [op, item]}))

    def test_plant_overdemand_blocks_all_same_crop(self):
        for seat in (0, 1):
            for crop in self.o.engine.CROPS:
                for count in (2, 3, 4):
                    w = self.o.world()
                    self.o.actors(w, seat, [(x, 0) for x in range(count)])
                    w[0][seat].observation.private["seeds"][crop] = count - 1
                    a = {"farmer": ["PLANT", crop], "hands": [["PLANT", crop] for _ in range(count - 1)]}
                    self.equal_worlds(self.o.run(w, seat, a), self.o.run(w, seat, {}))

    def test_exact_plant_demand_funded_before_market_succeeds(self):
        for seat in (0, 1):
            for crop in self.o.engine.CROPS:
                for count in (1, 2, 4):
                    w = self.o.world()
                    self.o.actors(w, seat, [(x, 0) for x in range(count)])
                    w[0][seat].observation.private["seeds"][crop] = count
                    a = {"farmer": ["PLANT", crop], "hands": [["PLANT", crop] for _ in range(count - 1)]}
                    out = self.o.run(w, seat, a)
                    self.assertEqual(out[0][seat].observation.private["seeds"][crop], 0)
                    for x in range(count):
                        self.assertEqual(out[0][seat].observation.farms[seat]["tiles"][0][x]["crop"], crop)

    def test_ghost_plant_blocks_real_actor_but_ghost_nonplant_does_not(self):
        for seat in (0, 1):
            for crop in self.o.engine.CROPS:
                w = self.o.world()
                w[0][seat].observation.private["seeds"][crop] = 1
                a = {"farmer": ["PLANT", crop], "hands": [["PLANT", crop]]}
                self.equal_worlds(self.o.run(w, seat, a), self.o.run(w, seat, {}))
                for extra in (["WEST"], ["PASS"], ["PICKUP", "WHEAT", float("inf")]):
                    self.equal_worlds(self.o.run(w, seat, {"farmer": ["PLANT", crop], "hands": [extra]}),
                                      self.o.run(w, seat, {"farmer": ["PLANT", crop]}))

    def test_locked_occupied_duplicate_positions_still_count_demand(self):
        for seat in (0, 1):
            for kind in ("locked", "occupied", "same"):
                w = self.o.world()
                pos = (5, 4) if kind == "locked" else ((0, 0) if kind == "occupied" else (4, 4))
                self.o.actors(w, seat, [(4, 4), pos])
                if kind == "occupied":
                    w[0][seat].observation.farms[seat]["tiles"][0][0] = {"kind": "WEED"}
                w[0][seat].observation.private["seeds"]["WHEAT"] = 1
                self.equal_worlds(self.o.run(w, seat, {"farmer": ["PLANT", "WHEAT"], "hands": [["PLANT", "WHEAT"]]}),
                                  self.o.run(w, seat, {}))

    def test_same_turn_seed_buy_is_too_late_for_current_plant(self):
        for seat in (0, 1):
            for crop in self.o.engine.CROPS:
                w = self.o.world()
                a = {"farmer": ["PLANT", crop], "market": [["BUY_SEED", crop, 1]]}
                out = self.o.run(w, seat, a)
                self.assertIsNone(out[0][seat].observation.farms[seat]["tiles"][4][4])
                self.assertEqual(out[0][seat].observation.private["seeds"][crop], 1)

    def test_unfunded_crop_does_not_block_other_crop(self):
        for seat in (0, 1):
            w = self.o.world()
            self.o.actors(w, seat, [(0, 0), (1, 0), (2, 0)])
            w[0][seat].observation.private["seeds"].update(WHEAT=1, CARROT=1)
            a = {"farmer": ["PLANT", "WHEAT"], "hands": [["PLANT", "WHEAT"], ["PLANT", "CARROT"]]}
            out = self.o.run(w, seat, a)
            tiles = out[0][seat].observation.farms[seat]["tiles"]
            self.assertIsNone(tiles[0][0]); self.assertIsNone(tiles[0][1])
            self.assertIsInstance(tiles[0][2], dict)
            self.assertEqual(tiles[0][2]["crop"], "CARROT")

    def test_naive_first_n_cap_wastes_seed_on_ineligible_first_actor(self):
        # These are manually authored controls, NOT an implementation of the donor.
        for seat in (0, 1):
            for first in ("weed", "locked"):
                w = self.o.world()
                pos = (0, 0) if first == "weed" else (5, 4)
                self.o.actors(w, seat, [pos, (1, 0)])
                if first == "weed":
                    w[0][seat].observation.farms[seat]["tiles"][0][0] = {"kind": "WEED"}
                w[0][seat].observation.private["seeds"]["WHEAT"] = 1
                raw = {"farmer": ["PLANT", "WHEAT"], "hands": [["PLANT", "WHEAT"]]}
                first_n = {"farmer": ["PLANT", "WHEAT"], "hands": [["PASS"]]}
                eligible = {"farmer": ["PASS"], "hands": [["PLANT", "WHEAT"]]}
                self.equal_worlds(self.o.run(w, seat, raw), self.o.run(w, seat, first_n))
                out = self.o.run(w, seat, eligible)
                self.assertEqual(out[0][seat].observation.farms[seat]["tiles"][0][1]["crop"], "WHEAT")
                self.assertEqual(out[0][seat].observation.private["seeds"]["WHEAT"], 0)

    def test_nonlist_hands_do_not_contribute_plant_demand(self):
        for seat in (0, 1):
            for value in (None, {}, "PLANT", (["PLANT", "WHEAT"],)):
                w = self.o.world()
                w[0][seat].observation.private["seeds"]["WHEAT"] = 1
                self.equal_worlds(self.o.run(w, seat, {"farmer": ["PLANT", "WHEAT"], "hands": value}),
                                  self.o.run(w, seat, {"farmer": ["PLANT", "WHEAT"]}))

    def test_unit_operations_precede_market_and_inputs_are_unmodified(self):
        for seat in (0, 1):
            w = self.stock_world(seat)
            a = {"farmer": ["PICKUP", "WHEAT", 10], "market": [["SELL", "WHEAT", 10]]}
            before_world, before_action = self.o.snapshot(w), copy.deepcopy(a)
            out = self.o.run(w, seat, a)
            self.assertEqual(out[0][seat].observation.farms[seat]["money"], 10000.0)
            self.assertEqual(out[0][seat].observation.private["inventories"][0]["WHEAT"], 10)
            self.assertEqual(self.o.snapshot(w), before_world)
            self.assertEqual(a, before_action)


class DependencyContract(unittest.TestCase):
    def test_every_dependency_pin_fails_closed_on_mutation(self):
        with tempfile.TemporaryDirectory(prefix="bridge-pin-test-") as name:
            root = Path(name)
            for dep in PINS:
                src = ORACLE.loader_path if dep == "loader.py" else ORACLE.engine_dir / dep
                (root / dep).write_bytes(src.read_bytes())
            for dep in PINS:
                path = root / dep
                raw = path.read_bytes()
                path.write_bytes(raw + b"\n# changed\n")
                with self.assertRaisesRegex(ValueError, "source pin mismatch"):
                    verify_inputs(root, root / "loader.py")
                path.write_bytes(raw)

    def test_every_missing_dependency_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="bridge-missing-test-") as name:
            root = Path(name)
            for dep in PINS:
                src = ORACLE.loader_path if dep == "loader.py" else ORACLE.engine_dir / dep
                (root / dep).write_bytes(src.read_bytes())
            for dep in PINS:
                path = root / dep
                raw = path.read_bytes(); path.unlink()
                with self.assertRaisesRegex(ValueError, "missing offline dependency"):
                    verify_inputs(root, root / "loader.py")
                path.write_bytes(raw)


def run_suite(oracle, stream=None):
    global ORACLE
    ORACLE = oracle
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(cls)
                               for cls in (ActionContract, DependencyContract))
    return unittest.TextTestRunner(stream=stream or sys.stderr, verbosity=2).run(suite)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-dir", type=Path, required=True)
    parser.add_argument("--loader", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        oracle = EngineOracle(args.engine_dir, args.loader)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    result = run_suite(oracle)
    report = {"schema": "titan.defensive.engine-contract.v1", "success": result.wasSuccessful(),
              "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
              "skipped": len(result.skipped), "python": sys.version, "optimize": sys.flags.optimize,
              "inputs": oracle.identities, "execution": oracle.counts(),
              "scope": "NEW direct-full-interpreter contract tests; no donor/runtime/transport/full-game/economics gate"}
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, sort_keys=True))
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
