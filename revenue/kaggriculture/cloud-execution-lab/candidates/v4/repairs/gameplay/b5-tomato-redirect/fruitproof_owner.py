# SPDX-License-Identifier: Apache-2.0
"""Independent acceptance for SOLANUM's ONE native discarded-fertilizer helper.

The original local-only R04 donor is deliberately not reconstructed here.
No tests below authorize promotion. They consume exact supplied owner bytes.
"""
from __future__ import annotations
import copy
import importlib.util
import io
import itertools
import json
from pathlib import Path
import re
import sys
import unittest

from fruitproof_engine import Fixture, cycle_pair, digest, git_blob, paired_once, pass_action, world


def load_owner(path: Path, expected: str):
    if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{40}", expected) is None:
        raise ValueError("owner source requires a full canonical Git blob identity")
    data = Path(path).read_bytes()
    if git_blob(data) != expected:
        raise ValueError("owner source identity mismatch")
    name = "fruitproof_exact_owner"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot import owner source")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    fn = getattr(mod, "apply_discarded_fertilizer", None)
    if not callable(fn):
        raise ValueError("owner contract not found: apply_discarded_fertilizer")
    return fn


def verify_owner(path, expected, engine, Struct, output):
    helper = load_owner(path, expected)
    counters = {"calls": 0, "transitions": 0, "eligible_cells": 0, "ineligible_cells": 0}

    def invoke(case, action=None, enabled=True, configure=None):
        state, env = world(engine, Struct, case)
        if configure:
            configure(state, env)
        # The owner receives only the public/current-own-private callback shape.
        obs = json.loads(json.dumps(state[case.seat].observation))
        cfg = json.loads(json.dumps(env.configuration))
        parent = pass_action() if action is None else action
        previous = digest([obs, cfg, parent])
        output = helper(obs, parent, cfg, enabled=enabled)
        counters["calls"] += 1
        if not (isinstance(output, tuple) and len(output) == 2 and isinstance(output[0], dict)):
            raise AssertionError("expected (action, report) API")
        if digest([obs, cfg, parent]) != previous:
            raise AssertionError("owner mutated a caller-owned input")
        return output[0], output[1], parent

    class OwnerTests(unittest.TestCase):
        def test_simple_exhaustive_eligibility_and_full_engine_certificate(self):
            # 480 candidate callbacks, including exact 24 positive cases.
            for seat, age, held, water, coverage, fert in itertools.product(
                    (0, 1), range(6, 12), range(5), (False, True), (-1, 0), (0, 1)):
                with self.subTest(seat=seat, age=age, held=held, water=water, coverage=coverage, fert=fert):
                    case = Fixture(seat=seat, hour=23, age=age, held_yield=held,
                                   watered=water, coverage_delta=coverage, carried_fert=fert, shed_wheat=100)
                    result, report, parent = invoke(case)
                    eligible = age in (7, 8, 9, 10) and held <= 2 and water and coverage < 0 and fert > 0
                    self.assertEqual(result["farmer"], ["FERTILIZE"] if eligible else ["PASS"])
                    self.assertEqual(result["hands"], parent["hands"])
                    self.assertEqual(result["market"], parent["market"])
                    if eligible:
                        counters["eligible_cells"] += 1
                        r = paired_once(engine, Struct, case, parent, result)
                        counters["transitions"] += 2
                        self.assertEqual(r["candidate"]["shed"], r["baseline"]["shed"])
                        self.assertEqual(r["candidate"]["carried"], r["baseline"]["carried"])
                        self.assertEqual(r["candidate"]["market"], r["baseline"]["market"])
                        self.assertEqual(r["delta_money"], 0)
                        self.assertEqual(r["delta_margin"], 0)
                        self.assertEqual(r["candidate"]["tile"]["yield_units"], r["baseline"]["tile"]["yield_units"] + 1)
                    else:
                        counters["ineligible_cells"] += 1
                        self.assertIs(result, parent)

        def test_default_and_disabled_are_exact_parent(self):
            case = Fixture(hour=23, shed_wheat=100)
            result, report, parent = invoke(case, enabled=False)
            self.assertIs(result, parent)
            state, env = world(engine, Struct, case)
            parent = pass_action()
            result, report = helper(state[case.seat].observation, parent, env.configuration)
            counters["calls"] += 1
            self.assertIs(result, parent)

        def test_full_shed_disposal_is_required(self):
            for stock in (0, 1, 98, 99):
                result, report, parent = invoke(Fixture(hour=23, shed_wheat=stock))
                self.assertIs(result, parent)

        def test_water_harvest_and_nonpass_ownership_preserved(self):
            for command in (["WATER"], ["HARVEST"], ["NORTH"], ["FERTILIZE"], ["PASS", "payload"]):
                result, report, parent = invoke(Fixture(hour=23, shed_wheat=100), pass_action(command))
                self.assertIs(result, parent)

        def test_room_releasing_market_or_unit_actions_do_not_get_free_cost_certificate(self):
            for orders in ([["SELL", "WHEAT", 1]], [["SELL", "WHEAT", 100]], [["SELL", "FERTILIZER", 1]]):
                result, report, parent = invoke(Fixture(hour=23, shed_wheat=100), pass_action(market=orders))
                self.assertIs(result, parent)
            def add_hand(state, env):
                obs = state[0].observation
                obs.farms[0]["hands"] = [[4, 4]]
                obs.private["inventories"].append({})
            result, report, parent = invoke(Fixture(hour=23, shed_wheat=100),
                    pass_action(hands=[["PICKUP", "WHEAT", 1]]), configure=add_hand)
            self.assertIs(result, parent)

        def test_same_tile_prior_service_is_not_double_spent(self):
            def add_hand(state, env):
                obs = state[0].observation
                obs.farms[0]["hands"] = [[4, 4]]
                obs.private["inventories"].append({"FERTILIZER": 1})
            result, report, parent = invoke(Fixture(hour=23, shed_wheat=100),
                    pass_action(["FERTILIZE"], [["PASS"]]), configure=add_hand)
            self.assertIs(result, parent)

        def test_non_eod_or_terminal_calendar_rejected(self):
            for case in (Fixture(hour=22, shed_wheat=100), Fixture(day=29, hour=22, shed_wheat=100)):
                result, report, parent = invoke(case)
                self.assertIs(result, parent)

        def test_same_returned_output_is_idempotent(self):
            case = Fixture(hour=23, shed_wheat=100)
            first, report, _ = invoke(case)
            second, report, parent = invoke(case, first)
            self.assertIs(second, first)

    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(OwnerTests))
    (Path(output) / "owner.log").write_text(log.getvalue())
    report = {"status": "PASS" if result.wasSuccessful() and not result.skipped else "FAIL",
              "source_blob": expected, "source_name": Path(path).name,
              "tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
              "skips": len(result.skipped), "counts": counters}
    if report["status"] != "PASS":
        print(log.getvalue(), file=sys.stderr)
        raise AssertionError(json.dumps(report))
    return report
