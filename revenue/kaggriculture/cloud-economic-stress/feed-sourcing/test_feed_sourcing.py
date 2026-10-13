# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
import unittest

from feed_sourcing import (
    WheatProductionRoute,
    make_e11_candidate,
    observed_feed_reserve_units,
    validate_wheat_route,
    wheat_route_cost,
)


class Mechanics:
    CROPS = {
        "WHEAT": {
            "seed": 10,
            "first_yield_day": 2,
            "max_yield_day": 4,
            "max_yield": 6,
            "ongoing": False,
        }
    }


def route(**patch):
    values = dict(
        plant_step=0,
        water_steps=(1,),
        harvest_step=20,
        deposit_step=21,
        units=1,
        purchased_seed_units=1,
    )
    values.update(patch)
    return WheatProductionRoute(**values)


def load_e11():
    name = "_p18_e11"
    if name in sys.modules:
        return sys.modules[name]
    path = Path(__file__).resolve().parents[1] / "feed-service-economics" / "feed_service_economics.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FeedSourcingContracts(unittest.TestCase):
    def test_first_yield_day_is_a_hard_lower_bound(self):
        report = validate_wheat_route(
            Mechanics, route(harvest_step=19, deposit_step=20),
            turns_per_day=10, terminal_step=718, dependent_pickup_step=30)
        self.assertFalse(report["physical"])
        self.assertEqual(report["reason"], "harvest_before_first_yield_day")

    def test_planting_day_water_keeps_one_unit_route_alive_to_day_two(self):
        report = validate_wheat_route(
            Mechanics, route(), turns_per_day=10, terminal_step=718,
            dependent_pickup_step=30, shed_room_at_deposit=10)
        self.assertTrue(report["physical"])
        self.assertEqual(report["certified_yield_units"], 1)

    def test_same_step_plant_water_without_actor_order_proof_is_declined(self):
        report = validate_wheat_route(
            Mechanics, route(water_steps=(0,)), turns_per_day=10,
            terminal_step=718, dependent_pickup_step=30)
        self.assertFalse(report["physical"])
        self.assertEqual(
            report["reason"],
            "water_outside_certified_postplant_preharvest_route",
        )

    def test_missing_planting_day_water_weeds_before_harvest(self):
        report = validate_wheat_route(
            Mechanics, route(water_steps=()), turns_per_day=10,
            terminal_step=718, dependent_pickup_step=30)
        self.assertFalse(report["physical"])
        self.assertEqual(report["reason"], "crop_weeds_before_harvest")
        self.assertEqual(report["weed_refresh_day"], 0)

    def test_one_unwatered_day_after_reset_is_survivable(self):
        report = validate_wheat_route(
            Mechanics, route(harvest_step=29, deposit_step=30), turns_per_day=10,
            terminal_step=718, dependent_pickup_step=31)
        self.assertTrue(report["physical"])

    def test_two_unwatered_refreshes_after_reset_are_not_survivable(self):
        report = validate_wheat_route(
            Mechanics, route(harvest_step=30, deposit_step=31), turns_per_day=10,
            terminal_step=718, dependent_pickup_step=40)
        self.assertFalse(report["physical"])
        self.assertEqual(report["reason"], "crop_weeds_before_harvest")

    def test_yield_window_water_can_certify_a_second_unit(self):
        report = validate_wheat_route(
            Mechanics, route(water_steps=(1, 20), harvest_step=21, deposit_step=22, units=2),
            turns_per_day=10, terminal_step=718, dependent_pickup_step=30)
        self.assertTrue(report["physical"])
        self.assertEqual(report["certified_yield_units"], 2)

    def test_promised_units_above_certified_yield_are_rejected(self):
        report = validate_wheat_route(
            Mechanics, route(units=2), turns_per_day=10,
            terminal_step=718, dependent_pickup_step=30)
        self.assertFalse(report["physical"])
        self.assertEqual(report["reason"], "promised_units_exceed_certified_yield")

    def test_deposit_must_follow_harvest_and_precede_dependent_pickup(self):
        wrong_order = validate_wheat_route(
            Mechanics, route(deposit_step=20), turns_per_day=10,
            terminal_step=718, dependent_pickup_step=30)
        self.assertFalse(wrong_order["physical"])
        self.assertEqual(wrong_order["reason"], "route_order_not_plant_harvest_deposit")
        same_turn_pickup = validate_wheat_route(
            Mechanics, route(), turns_per_day=10,
            terminal_step=718, dependent_pickup_step=21)
        self.assertFalse(same_turn_pickup["physical"])
        self.assertEqual(same_turn_pickup["reason"], "deposit_not_before_dependent_pickup")

    def test_shed_room_is_part_of_completed_delivery(self):
        report = validate_wheat_route(
            Mechanics, route(), turns_per_day=10, terminal_step=718,
            dependent_pickup_step=30, shed_room_at_deposit=0)
        self.assertFalse(report["physical"])
        self.assertEqual(report["reason"], "shed_room_cannot_accept_promised_wheat")

    def test_terminal_deposit_is_not_future_value(self):
        report = validate_wheat_route(
            Mechanics, route(deposit_step=719), turns_per_day=10,
            terminal_step=718, dependent_pickup_step=720)
        self.assertFalse(report["physical"])
        self.assertEqual(report["reason"], "deposit_after_terminal")

    def test_completed_make_cost_includes_seed_field_action_travel_and_sale_opportunity(self):
        r = route(
            field_opportunity_cost=20,
            actor_action_opportunity_cost=7,
            travel_opportunity_cost=3,
            feed_use_sale_opportunity_cost=25,
        )
        report = wheat_route_cost(Mechanics, r)
        self.assertEqual(report["costs"]["seed_cash"], 10)
        self.assertEqual(report["delivered_cost"], 65)
        self.assertEqual(report["future_sale_cash_credit"], 0)

    def test_existing_seed_can_remove_seed_cash_without_inventing_revenue(self):
        report = wheat_route_cost(Mechanics, route(purchased_seed_units=0))
        self.assertEqual(report["costs"]["seed_cash"], 0)
        self.assertEqual(report["future_sale_cash_credit"], 0)

    def test_p18_adapts_to_e11_supply_arrival_instead_of_second_feed_ledger(self):
        e11 = load_e11()
        candidate, certificate = make_e11_candidate(
            e11, Mechanics, route(), key="make", turns_per_day=10,
            terminal_step=718, dependent_pickup_step=30, shed_room_at_deposit=10)
        self.assertTrue(certificate["physical"])
        self.assertEqual(candidate.mode, "make")
        self.assertEqual(candidate.arrivals[0].step, 21)
        self.assertEqual(candidate.arrivals[0].source, "p18_completed_wheat_route")

    def test_imminent_feed_deadline_declines_make_candidate(self):
        e11 = load_e11()
        candidate, certificate = make_e11_candidate(
            e11, Mechanics, route(), key="make", turns_per_day=10,
            terminal_step=718, dependent_pickup_step=20, shed_room_at_deposit=10)
        self.assertFalse(certificate["physical"])
        self.assertFalse(candidate.funded)
        self.assertEqual(candidate.arrivals, ())

    def test_e11_comparison_can_choose_cheap_completed_make_over_costly_retention(self):
        e11 = load_e11()
        make, _ = make_e11_candidate(
            e11, Mechanics, route(purchased_seed_units=0), key="make", turns_per_day=10,
            terminal_step=718, dependent_pickup_step=30, shed_room_at_deposit=10)
        retain = e11.FeedSupplyCandidate(
            key="retain", mode="retain", initial_shed_wheat=1,
            costs={"foregone_sale": 25})
        service = e11.FeedService(
            actor=0, pickup_step=30, pickup_quantity=1, feed_steps=(31,),
            completion_value=100, value_realization_step=40)
        choice = e11.choose_feed_supply(
            [service], [retain, make], inherited_key="retain", now=0, terminal_step=718)
        self.assertTrue(choice["changed"])
        self.assertEqual(choice["chosen"], "make")

    def test_high_field_opportunity_cost_keeps_inherited_supply(self):
        e11 = load_e11()
        make, _ = make_e11_candidate(
            e11, Mechanics, route(purchased_seed_units=0, field_opportunity_cost=100),
            key="make", turns_per_day=10, terminal_step=718,
            dependent_pickup_step=30, shed_room_at_deposit=10)
        retain = e11.FeedSupplyCandidate(
            key="retain", mode="retain", initial_shed_wheat=1, costs={"foregone_sale": 25})
        service = e11.FeedService(
            actor=0, pickup_step=30, pickup_quantity=1, feed_steps=(31,),
            completion_value=100, value_realization_step=40)
        choice = e11.choose_feed_supply(
            [service], [retain, make], inherited_key="retain", now=0, terminal_step=718)
        self.assertFalse(choice["changed"])
        self.assertEqual(choice["chosen"], "retain")

    def test_zero_one_two_day_reserve_uses_only_observed_due_feed(self):
        feeds = (105, 115, 125, 200)
        zero = observed_feed_reserve_units(
            feeds, now_step=100, turns_per_day=10, reserve_days=0)
        one = observed_feed_reserve_units(
            feeds, now_step=100, turns_per_day=10, reserve_days=1)
        two = observed_feed_reserve_units(
            feeds, now_step=100, turns_per_day=10, reserve_days=2)
        self.assertEqual(zero["target_reserve_units"], 0)
        self.assertEqual(one["target_reserve_units"], 1)
        self.assertEqual(two["target_reserve_units"], 2)
        self.assertEqual(two["speculative_units"], 0)

    def test_already_covered_feed_is_a_reserve_noop(self):
        report = observed_feed_reserve_units(
            (105, 115), now_step=100, turns_per_day=10, reserve_days=2,
            already_covered_units=2)
        self.assertEqual(report["target_reserve_units"], 0)

    def test_reserve_horizon_is_intentionally_bounded(self):
        with self.assertRaises(ValueError):
            observed_feed_reserve_units(
                (105,), now_step=100, turns_per_day=10, reserve_days=3)

    def test_owned_certificate_docs_pass_open_door_guard(self):
        repo = Path(__file__).resolve().parents[4]
        guard = repo / "open_door_guard.py"
        if not guard.is_file():
            self.skipTest("full Commons source tree not present")
        here = Path(__file__).resolve().parent
        chunks = []
        for name in ("README.md", "feed_sourcing.py"):
            rel = f"revenue/kaggriculture/cloud-economic-stress/feed-sourcing/{name}"
            lines = (here / name).read_text(encoding="utf-8").splitlines()
            chunks.append(f"diff --git a/{rel} b/{rel}\n")
            chunks.append("--- /dev/null\n")
            chunks.append(f"+++ b/{rel}\n")
            chunks.append(f"@@ -0,0 +1,{len(lines)} @@\n")
            for line in lines:
                chunks.append(f"+{line}\n")
        proc = subprocess.run(
            [sys.executable, str(guard), "--diff-file", "-"],
            input="".join(chunks),
            text=True,
            capture_output=True,
            cwd=str(repo),
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + "\n" + proc.stderr)

    @unittest.skipUnless(
        (Path(__file__).resolve().parents[2] / "cloud-execution-lab" / "mechanics.py").is_file(),
        "full Commons source tree not present",
    )
    def test_current_extracted_engine_wheat_constants_match_certificate_assumptions(self):
        path = Path(__file__).resolve().parents[2] / "cloud-execution-lab" / "mechanics.py"
        spec = importlib.util.spec_from_file_location("_p18_current_mechanics", path)
        mechanics = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mechanics)
        wheat = mechanics.CROPS["WHEAT"]
        self.assertEqual(wheat["seed"], 10)
        self.assertEqual(wheat["first_yield_day"], 2)
        self.assertEqual(wheat["max_yield_day"], 4)
        self.assertEqual(wheat["max_yield"], 6)
        self.assertFalse(wheat["ongoing"])
        report = validate_wheat_route(
            mechanics, route(), turns_per_day=10, terminal_step=718,
            dependent_pickup_step=30, shed_room_at_deposit=10)
        self.assertTrue(report["physical"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
