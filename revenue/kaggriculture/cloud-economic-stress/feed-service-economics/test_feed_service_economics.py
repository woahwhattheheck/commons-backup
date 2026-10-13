# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

from feed_service_economics import (
    FeedService,
    FeedSupplyCandidate,
    SupplyArrival,
    choose_feed_supply,
    current_buy_candidate,
    evaluate_feed_supply,
    exact_wheat_sale_receipts,
    retained_wheat_candidate,
    simulate_current_wheat_buy,
)


class Mechanics:
    PRICE_FLOOR = 1
    MARKET_PARAMS = {
        "WHEAT": {
            "base": 25, "I0": 10000, "T": 400,
            "below_func": "linear", "below_target": 1.0,
            "above_func": "linear", "above_target": 1.0,
        }
    }

    @staticmethod
    def market_price(item, inventory, params=None):
        assert item == "WHEAT"
        # Buying lowers inventory and raises the price; selling above the floor
        # raises inventory and lowers the price.
        return max(1, 25 + (10000 - int(inventory)))


def obs(step=100, inventory=10000):
    return {
        "step": step,
        "market": {"inventory": {"WHEAT": inventory}, "params": None},
    }


def service(
    *,
    actor=0,
    pickup=101,
    request=1,
    feeds=(102,),
    carried=0,
    value=100,
    realize=110,
    animal="COW",
    consecutive_unfed=0,
    escape=None,
):
    return FeedService(
        actor=actor,
        pickup_step=pickup,
        pickup_quantity=request,
        feed_steps=tuple(feeds),
        carried_wheat=carried,
        completion_value=value,
        value_realization_step=realize,
        animal=animal,
        consecutive_unfed=consecutive_unfed,
        escape_deadline_step=escape,
    )


class FeedServiceEconomicsContracts(unittest.TestCase):
    def test_current_buy_is_not_same_turn_pickup_stock(self):
        candidate = current_buy_candidate(
            Mechanics, obs(), 1, cash_available=100, shed_room=10)
        report = evaluate_feed_supply(
            [service(pickup=100, feeds=(101,))], candidate, now=100, terminal_step=718)
        self.assertFalse(report["physical"])
        self.assertEqual(report["reason"], "same_turn_arrival_cannot_supply_pickup")
        self.assertEqual(candidate.metadata["same_turn_pickup_credit"], 0)

    def test_current_buy_can_supply_later_pickup_and_feed(self):
        candidate = current_buy_candidate(
            Mechanics, obs(), 1, cash_available=100, shed_room=10)
        report = evaluate_feed_supply(
            [service(pickup=101, feeds=(102,), value=100)], candidate,
            now=100, terminal_step=718)
        self.assertTrue(report["physical"])
        self.assertTrue(report["admissible"])
        self.assertEqual(report["service_reports"][0]["actual_pickup"], 1)
        self.assertEqual(report["total_supply_cost"], 25)

    def test_partial_purchase_then_oversized_pickup_cannot_invent_missing_wheat(self):
        candidate = current_buy_candidate(
            Mechanics, obs(), 3, cash_available=25, shed_room=10)
        self.assertEqual(candidate.metadata["filled_units"], 1)
        self.assertEqual(candidate.metadata["fill_reason"], "cash_partial_fill")
        report = evaluate_feed_supply(
            [service(pickup=101, request=3, feeds=(102, 103), value=300)],
            candidate, now=100, terminal_step=718)
        self.assertFalse(report["physical"])
        self.assertEqual(report["reason"], "pickup_fill_does_not_cover_feed_suffix")
        self.assertEqual(report["service_reports"][0]["actual_pickup"], 1)

    def test_two_actors_compete_for_actual_pickup_stock(self):
        candidate = FeedSupplyCandidate(
            key="two", mode="inherited", initial_shed_wheat=2)
        services = [
            service(actor=0, request=2, feeds=(102,), value=100),
            service(actor=1, request=1, feeds=(103,), value=100),
        ]
        report = evaluate_feed_supply(
            services, candidate, now=100, terminal_step=718)
        self.assertFalse(report["physical"])
        self.assertEqual(report["reason"], "pickup_fill_does_not_cover_feed_suffix")
        self.assertEqual(report["service_reports"][0]["actual_pickup"], 2)

        services[0] = service(actor=0, request=1, feeds=(102,), value=100)
        report = evaluate_feed_supply(
            services, candidate, now=100, terminal_step=718)
        self.assertTrue(report["physical"])
        self.assertEqual([r["actual_pickup"] for r in report["service_reports"]], [1, 1])

    def test_feed_before_pickup_must_be_carried(self):
        candidate = FeedSupplyCandidate(
            key="stock", mode="inherited", initial_shed_wheat=10)
        report = evaluate_feed_supply(
            [service(pickup=103, request=1, feeds=(102, 104), carried=0)],
            candidate, now=100, terminal_step=718)
        self.assertFalse(report["physical"])
        self.assertEqual(report["reason"], "feed_before_pickup_uncovered")
        covered = evaluate_feed_supply(
            [service(pickup=103, request=1, feeds=(102, 104), carried=1)],
            candidate, now=100, terminal_step=718)
        self.assertTrue(covered["physical"])

    def test_second_unfed_day_requires_feed_before_escape_deadline(self):
        candidate = FeedSupplyCandidate(
            key="stock", mode="inherited", initial_shed_wheat=1)
        late = evaluate_feed_supply(
            [service(pickup=101, feeds=(105,), consecutive_unfed=1, escape=104)],
            candidate, now=100, terminal_step=718)
        self.assertFalse(late["physical"])
        self.assertEqual(late["reason"], "feed_misses_escape_deadline")
        on_time = evaluate_feed_supply(
            [service(pickup=101, feeds=(104,), consecutive_unfed=1, escape=104)],
            candidate, now=100, terminal_step=718)
        self.assertTrue(on_time["physical"])

    def test_already_unfed_service_requires_explicit_escape_deadline(self):
        candidate = FeedSupplyCandidate(
            key="stock", mode="inherited", initial_shed_wheat=1)
        report = evaluate_feed_supply(
            [service(pickup=101, feeds=(102,), consecutive_unfed=1, escape=None)],
            candidate, now=100, terminal_step=718)
        self.assertFalse(report["physical"])
        self.assertFalse(report["admissible"])
        self.assertEqual(report["reason"], "missing_escape_deadline")
        self.assertEqual(report["service_reports"], [])

    def test_late_supply_with_no_terminal_value_is_rejected(self):
        candidate = FeedSupplyCandidate(
            key="late-buy", mode="buy", initial_shed_wheat=0,
            arrivals=(SupplyArrival(710, 1, "market"),), costs={"cash": 1})
        report = evaluate_feed_supply(
            [service(pickup=711, feeds=(712,), value=100, realize=719)],
            candidate, now=700, terminal_step=718)
        self.assertFalse(report["physical"])
        self.assertEqual(report["reason"], "service_value_realizes_after_terminal")

    def test_already_carried_service_keeps_inherited_no_purchase(self):
        inherited = FeedSupplyCandidate(
            key="inherited", mode="inherited", initial_shed_wheat=0)
        buy = current_buy_candidate(
            Mechanics, obs(), 1, key="buy", cash_available=100, shed_room=10)
        services = [service(pickup=None, request=0, feeds=(102,), carried=1, value=100)]
        choice = choose_feed_supply(
            services, [inherited, buy], inherited_key="inherited",
            now=100, terminal_step=718)
        self.assertFalse(choice["changed"])
        self.assertEqual(choice["chosen"], "inherited")
        self.assertEqual(choice["reason"], "inherited_complete_service_is_best")

    def test_buy_price_impact_is_unitwise_and_partial_fill_is_explicit(self):
        report = simulate_current_wheat_buy(
            Mechanics, obs(), 3, cash_available=1000, shed_room=3)
        self.assertEqual(report["unit_prices"], [25, 26, 27])
        self.assertEqual(report["cash_spent"], 78)
        capacity = simulate_current_wheat_buy(
            Mechanics, obs(), 3, cash_available=1000, shed_room=2)
        self.assertEqual(capacity["filled_units"], 2)
        self.assertEqual(capacity["fill_reason"], "shed_capacity_partial_fill")

    def test_retention_prices_exact_sale_opportunity_cost(self):
        sale = exact_wheat_sale_receipts(Mechanics, obs(), 3)
        self.assertEqual(sale["unit_prices"], [25, 24, 23])
        retained = retained_wheat_candidate(Mechanics, obs(), 3)
        self.assertEqual(retained.costs["foregone_current_sale_receipts"], 72)
        self.assertEqual(retained.initial_shed_wheat, 3)

    def test_make_can_win_only_if_delivery_precedes_pickup(self):
        inherited = retained_wheat_candidate(
            Mechanics, obs(), 1, key="retain")
        make = FeedSupplyCandidate(
            key="make", mode="make", initial_shed_wheat=0,
            arrivals=(SupplyArrival(100, 1, "producer_drop"),),
            costs={"seed_service_travel_opportunity": 10},
        )
        services = [service(pickup=101, feeds=(102,), value=100)]
        choice = choose_feed_supply(
            services, [inherited, make], inherited_key="retain",
            now=100, terminal_step=718)
        self.assertTrue(choice["changed"])
        self.assertEqual(choice["chosen"], "make")

        too_late = FeedSupplyCandidate(
            key="same-step-make", mode="make", initial_shed_wheat=0,
            arrivals=(SupplyArrival(101, 1, "producer_drop"),),
            costs={"all": 1},
        )
        report = evaluate_feed_supply(
            services, too_late, now=100, terminal_step=718)
        self.assertFalse(report["physical"])
        self.assertEqual(report["reason"], "same_turn_arrival_cannot_supply_pickup")

    def test_arrival_surplus_is_not_double_credited_between_actors(self):
        candidate = FeedSupplyCandidate(
            key="buy", mode="buy", initial_shed_wheat=0,
            arrivals=(SupplyArrival(100, 2, "market"),), costs={"cash": 1})
        services = [
            service(actor=0, pickup=101, request=2, feeds=(102,), value=100),
            service(actor=1, pickup=101, request=1, feeds=(102,), value=100),
        ]
        report = evaluate_feed_supply(
            services, candidate, now=100, terminal_step=718)
        self.assertFalse(report["physical"])
        self.assertEqual(report["service_reports"][0]["unused_actor_wheat_after_feeds"], 1)
        self.assertEqual(report["reason"], "pickup_fill_does_not_cover_feed_suffix")

    def test_nonpositive_complete_value_is_explicit_noop(self):
        candidate = FeedSupplyCandidate(
            key="costly", mode="buy", initial_shed_wheat=1, costs={"cash": 200})
        report = evaluate_feed_supply(
            [service(value=100)], candidate, now=100, terminal_step=718)
        self.assertTrue(report["physical"])
        self.assertFalse(report["admissible"])
        self.assertEqual(report["reason"], "nonpositive_completed_service_value")

    def test_future_sale_cash_is_never_a_purchase_funding_input(self):
        report = simulate_current_wheat_buy(
            Mechanics, obs(), 2, cash_available=25, shed_room=10)
        self.assertEqual(report["filled_units"], 1)
        self.assertEqual(report["future_sale_cash_credit"], 0)

    @unittest.skipUnless(
        (Path(__file__).resolve().parents[2] / "cloud-execution-lab" / "mechanics.py").is_file(),
        "full Commons source tree not present",
    )
    def test_current_extracted_engine_mechanics_support_exact_wheat_buy_curve(self):
        path = Path(__file__).resolve().parents[2] / "cloud-execution-lab" / "mechanics.py"
        spec = importlib.util.spec_from_file_location("_e11_current_mechanics", path)
        mechanics = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mechanics)
        observation = {
            "step": 100,
            "market": {"inventory": {"WHEAT": 9800}, "params": None},
        }
        report = simulate_current_wheat_buy(
            mechanics, observation, 8, cash_available=10000, shed_room=8)
        self.assertEqual(report["filled_units"], 8)
        self.assertEqual(report["cash_spent"], sum(report["unit_prices"]))
        self.assertTrue(all(a <= b for a, b in zip(
            report["unit_prices"], report["unit_prices"][1:])))
        self.assertEqual(report["inventory_after_fill"], 9792)


if __name__ == "__main__":
    unittest.main(verbosity=2)
