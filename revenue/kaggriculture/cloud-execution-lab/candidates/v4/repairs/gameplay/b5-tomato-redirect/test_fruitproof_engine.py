# SPDX-License-Identifier: Apache-2.0
"""Independent official-engine contracts; explicit unittest assertions survive -O."""
from __future__ import annotations
import copy
import itertools
import os
from pathlib import Path
import tempfile
import unittest

from fruitproof_engine import (Fixture, PINS, cycle_pair, digest, execute, load_engine,
                              outcome, paired_once, pass_action, pulse_oracle, world)

ROOT = Path(os.environ["FRUITPROOF_RUNTIME"])
ENGINE, STRUCT = load_engine(ROOT)
COUNTS = {"transitions": 0, "pulse_cells": 0, "cycle_pairs": 0}


def pair(case, baseline=None, candidate=None, rival=None, configure=None):
    COUNTS["transitions"] += 2
    return paired_once(ENGINE, STRUCT, case, baseline or pass_action(),
                       candidate or pass_action(["FERTILIZE"]), rival, configure)


def cycle(case, **kwargs):
    result = cycle_pair(ENGINE, STRUCT, case, **kwargs)
    COUNTS["cycle_pairs"] += 1
    COUNTS["transitions"] += sum(result[a]["callbacks"] for a in ("baseline", "candidate"))
    return result


class PulseMatrix(unittest.TestCase):
    def test_complete_service_cap_water_coverage_matrix(self):
        # 1,920 constructed full-interpreter pairs, both seats, zero skips.
        for seat, age, held, watered, dry, coverage, fert in itertools.product(
                (0, 1), range(6, 12), range(5), (False, True), (0, 1), (-2, -1, 0, 2), (0, 1)):
            with self.subTest(seat=seat, age=age, held=held, watered=watered, dry=dry, coverage=coverage, fert=fert):
                c = Fixture(seat=seat, hour=23, age=age, held_yield=held, watered=watered,
                            unwatered_days=dry, coverage_delta=coverage, carried_fert=fert)
                result = pair(c)
                COUNTS["pulse_cells"] += 1
                for arm in ("baseline", "candidate"):
                    actual_cov = c.day + coverage
                    if arm == "candidate" and fert:
                        actual_cov = max(actual_cov, c.day + 2)
                    expected, _ = pulse_oracle(age=age, held=held, watered=watered,
                                               consecutive_unwatered= dry, coverage=actual_cov, day=c.day)
                    tile = result[arm]["tile"]
                    if expected is None:
                        self.assertEqual(tile, {"kind": "WEED"})
                    else:
                        self.assertEqual(tile["kind"], "PLANT")
                        self.assertEqual(tile["yield_units"], expected)
                        self.assertEqual(tile["fertilized_until_day"], actual_cov)
                    remaining = fert if arm == "baseline" else 0
                    self.assertEqual(result[arm]["shed"]["FERTILIZER"], remaining)
                    self.assertEqual(result[arm]["carried"], [{}])
                    self.assertEqual(result[arm]["money"], 3000)
                self.assertEqual(result["baseline"]["market"], result["candidate"]["market"])


class Semantics(unittest.TestCase):
    def test_water_is_required_even_if_drought_streak_is_zero(self):
        r = pair(Fixture(hour=23, watered=False, unwatered_days=0))
        self.assertEqual(r["candidate"]["tile"]["yield_units"], 1)
        self.assertEqual(r["baseline"]["tile"]["yield_units"], 1)

    def test_inclusive_service_day_coverage(self):
        r = pair(Fixture(hour=23, coverage_delta=0))
        self.assertEqual(r["baseline"]["tile"]["yield_units"], 2)
        self.assertEqual(r["candidate"]["tile"]["yield_units"], 2)

    def test_first_pulse_is_service_age7_not_age8(self):
        r = pair(Fixture(hour=23, age=7))
        self.assertEqual(r["baseline"]["tile"]["yield_units"], 1)
        self.assertEqual(r["candidate"]["tile"]["yield_units"], 2)

    def test_last_pulse_is_service_age10_not_age11(self):
        for age, expected in ((10, 2), (11, 0)):
            r = pair(Fixture(hour=23, age=age))
            self.assertEqual(r["candidate"]["tile"]["yield_units"], expected)

    def test_full_plant_cannot_store_bonus(self):
        r = pair(Fixture(hour=23, held_yield=4))
        self.assertEqual(r["candidate"]["tile"]["yield_units"], 4)
        self.assertEqual(r["baseline"]["tile"]["yield_units"], 4)
        self.assertEqual(r["candidate"]["shed"]["FERTILIZER"], 0)
        self.assertEqual(r["baseline"]["shed"]["FERTILIZER"], 1)

    def test_consumption_is_not_just_requested_action(self):
        for fert, expected in ((0, 0), (1, 0), (2, 1)):
            r = pair(Fixture(hour=22, carried_fert=fert))
            self.assertEqual(r["candidate"]["carried"][0].get("FERTILIZER", 0), expected)
            self.assertEqual(r["candidate"]["tile"]["fertilized_until_day"], 17 if fert else 14)

    def test_no_early_pulse_at_hour22(self):
        r = pair(Fixture(hour=22))
        self.assertEqual(r["candidate"]["tile"]["yield_units"], 0)
        self.assertEqual(r["candidate"]["tile"]["fertilized_until_day"], 17)

    def test_terminal_age7_spend_cannot_pay(self):
        r = pair(Fixture(day=29, age=7, hour=22))
        self.assertEqual(r["candidate"]["status"], ["DONE", "DONE"])
        self.assertEqual(r["candidate"]["tile"]["yield_units"], 0)
        self.assertEqual(r["candidate"]["carried"], [{}])
        self.assertEqual(r["baseline"]["carried"], [{"FERTILIZER": 1}])

    def test_same_tile_double_fertilize_wastes_second_input(self):
        def setup(state, env):
            obs = state[0].observation
            obs.farms[0]["hands"] = [[4, 4]]
            obs.private["inventories"].append({"FERTILIZER": 1})
        r = pair(Fixture(hour=23), pass_action(["FERTILIZE"], [["PASS"]]),
                 pass_action(["FERTILIZE"], [["FERTILIZE"]]), configure=setup)
        self.assertEqual(r["candidate"]["tile"], r["baseline"]["tile"])
        self.assertEqual(r["candidate"]["shed"]["FERTILIZER"], 0)
        self.assertEqual(r["baseline"]["shed"]["FERTILIZER"], 1)

    def test_same_turn_water_then_fertilize_is_real_bonus(self):
        def setup(state, env):
            obs = state[0].observation
            obs.farms[0]["hands"] = [[4, 4]]
            obs.private["inventories"].append({"FERTILIZER": 1})
        r = pair(Fixture(hour=23, watered=False, carried_fert=0),
                 pass_action(["WATER"], [["PASS"]]), pass_action(["WATER"], [["FERTILIZE"]]), configure=setup)
        self.assertEqual(r["baseline"]["tile"]["yield_units"], 1)
        self.assertEqual(r["candidate"]["tile"]["yield_units"], 2)

    def test_same_turn_harvest_before_eod_opens_capacity(self):
        def setup(state, env):
            obs = state[0].observation
            obs.farms[0]["hands"] = [[4, 4]]
            obs.private["inventories"].append({})
        r = pair(Fixture(hour=23, age=8, held_yield=4),
                 pass_action(["PASS"], [["HARVEST"]]),
                 pass_action(["FERTILIZE"], [["HARVEST"]]), configure=setup)
        self.assertEqual(r["baseline"]["shed"]["TOMATO"], 4)
        self.assertEqual(r["candidate"]["shed"]["TOMATO"], 4)
        self.assertEqual(r["baseline"]["tile"]["yield_units"], 1)
        self.assertEqual(r["candidate"]["tile"]["yield_units"], 2)

    def test_capacity_before_market_and_eod_is_not_unlimited(self):
        r = pair(Fixture(hour=23, shed_wheat=100))
        self.assertEqual(r["baseline"]["shed"]["FERTILIZER"], 0)
        self.assertEqual(r["candidate"]["shed"]["FERTILIZER"], 0)
        self.assertEqual(r["candidate"]["shed"]["WHEAT"], 100)


class Economics(unittest.TestCase):
    def test_one_fertilizer_three_extra_with_regular_harvest(self):
        for seat in (0, 1):
            r = cycle(Fixture(seat=seat))
            self.assertEqual(r["baseline"]["harvested"], 4)
            self.assertEqual(r["candidate"]["harvested"], 7)
            self.assertEqual(r["delta_harvested"], 3)
            self.assertEqual(r["delta_money"], 66)
            self.assertEqual(r["delta_margin"], r["delta_money"] - r["delta_rival_money"])

    def test_no_turnover_is_realized_input_loss(self):
        for seat in (0, 1):
            r = cycle(Fixture(seat=seat), harvest="hold")
            self.assertEqual(r["baseline"]["harvested"], 4)
            self.assertEqual(r["candidate"]["harvested"], 4)
            self.assertEqual(r["delta_money"], -100)
            self.assertEqual(r["candidate"]["shed"], r["baseline"]["shed"])

    def test_glut_can_make_more_tomatoes_economically_negative(self):
        r = cycle(Fixture(tomato_inventory=10500))
        self.assertEqual(r["delta_harvested"], 3)
        self.assertEqual(r["delta_money"], -91)

    def test_scarcity_can_make_same_three_units_valuable(self):
        r = cycle(Fixture(tomato_inventory=9400))
        self.assertEqual(r["delta_harvested"], 3)
        self.assertEqual(r["delta_money"], 2564)

    def test_not_pricing_unused_fertilizer_inflates_gain(self):
        r = cycle(Fixture(), sell_unused_fert=False)
        self.assertEqual(r["delta_money"], 166)
        self.assertEqual(r["baseline"]["shed"]["FERTILIZER"], 1)
        self.assertEqual(r["candidate"]["shed"]["FERTILIZER"], 0)

    def test_three_day_coverage_limits_late_window_benefit(self):
        for age, delta in ((7, 3), (8, 3), (9, 2), (10, 1), (11, 0)):
            r = cycle(Fixture(age=age))
            self.assertEqual(r["delta_harvested"], delta)

    def test_zero_opportunity_control_is_trace_identical(self):
        r = cycle(Fixture(), candidate_action=pass_action())
        self.assertEqual(r["baseline"], r["candidate"])
        self.assertEqual(r["delta_money"], 0)

    def test_repetition_preserves_complete_state_and_action_evidence(self):
        a = cycle(Fixture(rival_tomato=50, rival_fert=50))
        b = cycle(Fixture(rival_tomato=50, rival_fert=50))
        self.assertEqual(a, b)

    def test_margin_reconciles_actual_other_player_effects(self):
        nonzero = []
        for seat, inv in itertools.product((0, 1), (9999, 10000, 10001)):
            r = cycle(Fixture(seat=seat, fertilizer_inventory=inv, rival_fert=50, rival_tomato=50))
            self.assertEqual(r["delta_margin"], r["delta_money"] - r["delta_rival_money"])
            nonzero.append(r["delta_rival_money"])
        self.assertTrue(any(v != 0 for v in nonzero), nonzero)


class Isolation(unittest.TestCase):
    def test_both_seats_share_exact_public_objects_and_not_private(self):
        state, env = world(ENGINE, STRUCT, Fixture())
        self.assertIs(state[0].observation.farms, state[1].observation.farms)
        self.assertIs(state[0].observation.market, state[1].observation.market)
        self.assertIsNot(state[0].observation.private, state[1].observation.private)
        copied, ce = copy.deepcopy((state, env))
        self.assertIs(copied[0].observation.farms, copied[1].observation.farms)
        self.assertIsNot(copied[0].observation.farms, state[0].observation.farms)

    def test_fixture_rejects_bool_float_and_invalid_domain(self):
        for bad in ({"seat": True}, {"age": 7.0}, {"hour": 24}, {"day": 2, "age": 7},
                    {"carried_fert": -1}, {"held_yield": 5}, {"shed_wheat": 101},
                    {"episode_steps": 3}, {"watered": 1}):
            with self.subTest(bad=bad), self.assertRaises((TypeError, ValueError)):
                Fixture(**bad)

    def test_all_reference_dependencies_missing_or_changed_fail_before_import(self):
        for rel in PINS:
            for mode in ("missing", "changed"):
                with self.subTest(rel=rel, mode=mode), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    for source in PINS:
                        dest = root / source
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        if source == rel and mode == "missing":
                            continue
                        data = (ROOT / source).read_bytes()
                        if source == rel:
                            data += b"\n# deliberately changed dependency\n"
                        dest.write_bytes(data)
                    with self.assertRaises((FileNotFoundError, ValueError)):
                        load_engine(root)

    def test_execution_after_done_is_rejected(self):
        state, env = world(ENGINE, STRUCT, Fixture(day=29, age=7))
        COUNTS["transitions"] += 1
        execute(ENGINE, state, env, 718, [pass_action(), pass_action()])
        with self.assertRaises(ValueError):
            execute(ENGINE, state, env, 719, [pass_action(), pass_action()])


if __name__ == "__main__":
    unittest.main(verbosity=2)
