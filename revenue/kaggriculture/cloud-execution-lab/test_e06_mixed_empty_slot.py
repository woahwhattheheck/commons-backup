"""Contracts for E06 mixed-queue inert-slot reclamation."""
import copy
import unittest

from e06_mixed_empty_slot import reclaim_mixed_empty_slot


def full_mixed(vacancy=None):
    rows = [
        ["SELL", "WOOL", 2],
        ["BUY_SEED", "WHEAT", 2],
        ["HIRE"],
        ["BUY_PRODUCT", "FERTILIZER", 1],
        ["SELL", "CARROT", 3],
        ["BUY_LAND"],
        ["BUY_ANIMAL", "CHICKEN", 1],
        ["SELL", "TOMATO", 2],
        ["SELL", "MILK", 1],
        ["SELL", "WOOL", 1],
        ["SELL", "STRAWBERRY", 4],  # clipped suffix
    ]
    if vacancy is not None:
        rows[vacancy] = []
    return rows


def receipt(queue, *, candidate_gain=5, reject_acquisition_change=False, fail=False):
    if fail:
        return {"complete": False}
    inserted = any(row == ["SELL", "MILK", 4] for row in queue[:10])
    values = {"quiet": 100, "rival_before": 80}
    if inserted:
        values = {k: v + candidate_gain for k, v in values.items()}
    acquisitions = {
        "quiet": (("BUY_SEED", "WHEAT", 2), ("HIRE",)),
        "rival_before": (("BUY_SEED", "WHEAT", 2), ("HIRE",)),
    }
    if inserted and reject_acquisition_change:
        acquisitions["rival_before"] = (("BUY_SEED", "WHEAT", 2),)
    return {
        "complete": True,
        "scenario_value": values,
        "successful_acquisitions": acquisitions,
    }


class MixedEmptySlotTests(unittest.TestCase):
    def test_full_mixed_prefix_fills_one_vacancy_and_preserves_other_rows_and_suffix(self):
        market = full_mixed(vacancy=0)
        before = copy.deepcopy(market)
        result, report = reclaim_mixed_empty_slot(
            market,
            {"MILK": 4},
            max_orders=10,
            evaluate=lambda queue: receipt(queue),
        )
        self.assertTrue(report["changed"])
        self.assertEqual(result[0], ["SELL", "MILK", 4])
        self.assertEqual(result[1:], before[1:])
        self.assertEqual(result[10], before[10])
        self.assertEqual(market, before)

    def test_append_capacity_is_existing_path_noop(self):
        market = full_mixed(vacancy=0)[:9]
        result, report = reclaim_mixed_empty_slot(
            market, {"MILK": 4}, max_orders=10, evaluate=lambda queue: receipt(queue)
        )
        self.assertEqual(result, market)
        self.assertEqual(report["reason"], "append_capacity_available")

    def test_full_queue_without_inert_slot_declines(self):
        market = full_mixed()
        result, report = reclaim_mixed_empty_slot(
            market, {"MILK": 4}, max_orders=10, evaluate=lambda queue: receipt(queue)
        )
        self.assertEqual(result, market)
        self.assertEqual(report["reason"], "no_inert_executable_slot")

    def test_sale_only_prefix_delegates_to_existing_compactor(self):
        market = [["SELL", "WOOL", 2], [], ["SELL", "MILK", 1]] + [[] for _ in range(7)]
        result, report = reclaim_mixed_empty_slot(
            market, {"MILK": 4}, max_orders=10, evaluate=lambda queue: receipt(queue)
        )
        self.assertEqual(result, market)
        self.assertEqual(report["reason"], "sale_only_delegate")

    def test_zero_quantity_sell_is_a_proven_inert_slot(self):
        market = full_mixed()
        market[0] = ["SELL", "MILK", 0]
        result, report = reclaim_mixed_empty_slot(
            market, {"MILK": 4}, max_orders=10, evaluate=lambda queue: receipt(queue)
        )
        self.assertTrue(report["changed"])
        self.assertEqual(result[0], ["SELL", "MILK", 4])

    def test_complete_receipt_models_funding_and_rejects_acquisition_change(self):
        market = full_mixed(vacancy=0)
        result, report = reclaim_mixed_empty_slot(
            market,
            {"MILK": 4},
            max_orders=10,
            evaluate=lambda queue: receipt(queue, reject_acquisition_change=True),
        )
        self.assertEqual(result, market)
        self.assertEqual(report["reason"], "no_strict_scenario_safe_replacement")

    def test_candidate_must_strictly_improve_every_same_scenario(self):
        market = full_mixed(vacancy=0)
        def evaluate(queue):
            base = receipt(queue)
            if any(row == ["SELL", "MILK", 4] for row in queue[:10]):
                base["scenario_value"]["rival_before"] = 80  # tie in one scenario
            return base
        result, report = reclaim_mixed_empty_slot(
            market, {"MILK": 4}, max_orders=10, evaluate=evaluate
        )
        self.assertEqual(result, market)
        self.assertEqual(report["accepted_count"], 0)

    def test_candidate_choice_is_bounded_and_deterministic(self):
        market = full_mixed(vacancy=0)
        def evaluate(queue):
            base = receipt(queue, candidate_gain=0)
            for row in queue[:10]:
                if row == ["SELL", "MILK", 4]:
                    base["scenario_value"] = {"quiet": 107, "rival_before": 87}
                if row == ["SELL", "CARROT", 2]:
                    base["scenario_value"] = {"quiet": 106, "rival_before": 86}
            return base
        remaining = {"MILK": 4, "CARROT": 2, "WOOL": 0}
        first, report1 = reclaim_mixed_empty_slot(market, remaining, max_orders=10, evaluate=evaluate)
        second, report2 = reclaim_mixed_empty_slot(market, dict(reversed(list(remaining.items()))), max_orders=10, evaluate=evaluate)
        self.assertEqual(first, second)
        self.assertEqual(report1, report2)
        self.assertEqual(report1["candidate_count"], 2)
        self.assertEqual(report1["chosen"]["product"], "MILK")

    def test_evaluator_receives_exact_executable_prefix_not_clipped_suffix(self):
        market = full_mixed(vacancy=0)
        seen = []
        def evaluate(queue):
            seen.append(copy.deepcopy(queue))
            self.assertEqual(len(queue), 10)
            self.assertNotIn(["SELL", "STRAWBERRY", 4], queue)
            return receipt(queue)
        result, report = reclaim_mixed_empty_slot(
            market, {"MILK": 4}, max_orders=10, evaluate=evaluate
        )
        self.assertTrue(report["changed"])
        self.assertGreaterEqual(len(seen), 2)
        self.assertEqual(result[10], ["SELL", "STRAWBERRY", 4])

    def test_incomplete_baseline_is_exact_noop(self):
        market = full_mixed(vacancy=0)
        result, report = reclaim_mixed_empty_slot(
            market, {"MILK": 4}, max_orders=10, evaluate=lambda queue: {"complete": False}
        )
        self.assertEqual(result, market)
        self.assertEqual(report["reason"], "baseline_receipt_incomplete")

    def test_int_vs_string_scenario_ids_cannot_alias(self):
        market = full_mixed(vacancy=0)
        def evaluate(queue):
            inserted = any(row == ["SELL", "MILK", 4] for row in queue)
            key = 1 if inserted else "1"
            return {
                "complete": True,
                "scenario_value": {key: 105 if inserted else 100},
                "successful_acquisitions": {key: (("HIRE",),)},
            }
        with self.assertRaisesRegex(ValueError, "scenario ids must be non-empty strings"):
            reclaim_mixed_empty_slot(
                market, {"MILK": 4}, max_orders=10, evaluate=evaluate
            )

    def test_mixed_raw_scenario_keys_are_rejected_before_collision(self):
        market = full_mixed(vacancy=0)
        bad = {
            "complete": True,
            "scenario_value": {1: 100, "1": 101},
            "successful_acquisitions": {1: (("HIRE",),), "1": (("HIRE",),)},
        }
        with self.assertRaisesRegex(ValueError, "scenario ids must be non-empty strings"):
            reclaim_mixed_empty_slot(
                market, {"MILK": 4}, max_orders=10, evaluate=lambda queue: bad
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
