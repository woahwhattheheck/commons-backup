# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from copy import deepcopy
import json
import time
import unittest

from production_realization import (
    AdmissionConfig,
    InvalidLifecycle,
    admit_realized_patch,
    materialize_candidate,
    route_sha256,
)


ENGINE = "e" * 64
TRACE_A = "a" * 64
TRACE_B = "b" * 64
CONTROL = "c" * 64


def action(*, farmer=None, market=None, hands=None):
    return {
        "farmer": list(farmer or ["PASS"]),
        "hands": deepcopy(hands or []),
        "market": deepcopy(market or []),
    }


def route(size=12):
    return [action() for _ in range(size)]


def valid_events(commit_step=2, item="WHEAT", quantity=3, cash=12.0):
    return [
        {"kind": "commit", "step": commit_step, "lot": "lot-1", "item": item, "quantity": 1},
        {"kind": "harvest", "step": 6, "lot": "lot-1", "item": item, "quantity": quantity},
        {"kind": "drop", "step": 6, "lot": "lot-1", "item": item, "quantity": quantity, "explicit": True},
        {"kind": "sale", "step": 7, "lot": "lot-1", "item": item, "quantity": quantity, "cash_delta": cash},
    ]


class Evaluator:
    def __init__(self, config, *, scenario_scores=None, mutate=None, events=None):
        self.config = config
        self.scenario_scores = scenario_scores or {"known": (100.0, 112.0), "pressure": (100.0, 106.0)}
        self.mutate = mutate
        self.events = events
        self.calls = []

    def __call__(self, base, candidate, scenario, deadline):
        self.calls.append((scenario, deadline))
        base_hash = route_sha256(base, self.config.now, self.config.terminal_step)
        candidate_hash = route_sha256(candidate, self.config.now, self.config.terminal_step)
        base_score, candidate_score = self.scenario_scores[scenario]
        receipt = {
            "complete": True,
            "scenario": scenario,
            "base_route_sha256": base_hash,
            "candidate_route_sha256": candidate_hash,
            "engine_sha256": ENGINE,
            "trace_sha256": TRACE_A if scenario == "known" else TRACE_B,
            "rejoin_control_base_sha256": CONTROL,
            "rejoin_control_candidate_sha256": CONTROL,
            "existing_obligations_preserved": True,
            "base_terminal_score": base_score,
            "candidate_terminal_score": candidate_score,
            "candidate_minimum_cash": 5.0,
            "events": deepcopy(self.events or valid_events()),
        }
        if self.mutate:
            self.mutate(receipt, scenario)
        return receipt


class ProductionRealizationTests(unittest.TestCase):
    def setUp(self):
        self.base = route()
        self.patches = {2: action(farmer=["PLANT", "WHEAT"]), 3: action(farmer=["WATER"])}
        self.config = AdmissionConfig(now=0, terminal_step=10, rejoin_step=4, minimum_gain=0.0, seconds=1.0)

    def test_full_lifecycle_all_scenarios_admits_detached_candidate(self):
        original = deepcopy(self.base)
        evaluator = Evaluator(self.config)
        output, report = admit_realized_patch(
            self.base,
            self.patches,
            config=self.config,
            scenarios=("known", "pressure"),
            evaluate=evaluator,
        )
        self.assertIsNot(output, self.base)
        self.assertEqual(self.base, original)
        self.assertEqual(output[2]["farmer"], ["PLANT", "WHEAT"])
        self.assertEqual(output[3]["farmer"], ["WATER"])
        self.assertEqual(output[4:], self.base[4:])
        self.assertTrue(report["complete"])
        self.assertTrue(report["admitted"])
        self.assertEqual(report["reason"], "strict_realized_terminal_gain")
        self.assertEqual(report["changed_steps"], [2, 3])
        self.assertEqual(report["worst_gain"], 6.0)
        self.assertEqual(report["worst_realized_units"], 3)
        self.assertEqual(report["worst_realized_cash"], 12.0)
        self.assertEqual([row[0] for row in evaluator.calls], ["known", "pressure"])
        json.dumps(report, allow_nan=False)

    def test_score_null_plant_water_without_harvest_preserves_exact_parent(self):
        evaluator = Evaluator(
            self.config,
            events=[
                {"kind": "commit", "step": 2, "lot": "lot-1", "item": "WHEAT", "quantity": 1},
            ],
        )
        output, report = admit_realized_patch(
            self.base, self.patches, config=self.config,
            scenarios=("known",), evaluate=evaluator,
        )
        self.assertIs(output, self.base)
        self.assertTrue(report["complete"])
        self.assertFalse(report["admitted"])
        self.assertEqual(report["reason"], "scenario_rejected")
        self.assertIn("commit, harvest, explicit drop, and sale", report["detail"])

    def test_terminal_tie_is_rejected_even_with_physical_lifecycle(self):
        evaluator = Evaluator(self.config, scenario_scores={"known": (100.0, 100.0)})
        output, report = admit_realized_patch(
            self.base, self.patches, config=self.config,
            scenarios=("known",), evaluate=evaluator,
        )
        self.assertIs(output, self.base)
        self.assertIn("strict terminal score gain", report["detail"])

    def test_minimum_gain_is_strict_and_applies_to_worst_scenario(self):
        config = AdmissionConfig(now=0, terminal_step=10, rejoin_step=4, minimum_gain=6.0, seconds=1.0)
        evaluator = Evaluator(config)
        output, report = admit_realized_patch(
            self.base, self.patches, config=config,
            scenarios=("known", "pressure"), evaluate=evaluator,
        )
        self.assertIs(output, self.base)
        self.assertEqual(report["rejected_scenario"], "pressure")

    def test_receipt_is_cryptographically_bound_to_candidate_tape(self):
        def mutate(receipt, _scenario):
            receipt["candidate_route_sha256"] = "0" * 64
        output, report = admit_realized_patch(
            self.base, self.patches, config=self.config,
            scenarios=("known",), evaluate=Evaluator(self.config, mutate=mutate),
        )
        self.assertIs(output, self.base)
        self.assertIn("not bound to the candidate route", report["detail"])

    def test_receipt_is_cryptographically_bound_to_base_tape(self):
        def mutate(receipt, _scenario):
            receipt["base_route_sha256"] = "0" * 64
        output, report = admit_realized_patch(
            self.base, self.patches, config=self.config,
            scenarios=("known",), evaluate=Evaluator(self.config, mutate=mutate),
        )
        self.assertIs(output, self.base)
        self.assertIn("not bound to the base route", report["detail"])

    def test_engine_digest_must_match_across_scenarios(self):
        def mutate(receipt, scenario):
            if scenario == "pressure":
                receipt["engine_sha256"] = "f" * 64
        output, report = admit_realized_patch(
            self.base, self.patches, config=self.config,
            scenarios=("known", "pressure"), evaluate=Evaluator(self.config, mutate=mutate),
        )
        self.assertIs(output, self.base)
        self.assertEqual(report["rejected_scenario"], "pressure")
        self.assertIn("different engine artifacts", report["detail"])

    def test_unrelated_control_state_must_rejoin(self):
        def mutate(receipt, _scenario):
            receipt["rejoin_control_candidate_sha256"] = "d" * 64
        output, report = admit_realized_patch(
            self.base, self.patches, config=self.config,
            scenarios=("known",), evaluate=Evaluator(self.config, mutate=mutate),
        )
        self.assertIs(output, self.base)
        self.assertIn("control state does not rejoin", report["detail"])

    def test_existing_obligation_displacement_rejects(self):
        def mutate(receipt, _scenario):
            receipt["existing_obligations_preserved"] = False
        output, report = admit_realized_patch(
            self.base, self.patches, config=self.config,
            scenarios=("known",), evaluate=Evaluator(self.config, mutate=mutate),
        )
        self.assertIs(output, self.base)
        self.assertIn("obligations were not preserved", report["detail"])

    def test_negative_cash_trough_rejects(self):
        def mutate(receipt, _scenario):
            receipt["candidate_minimum_cash"] = -0.01
        output, report = admit_realized_patch(
            self.base, self.patches, config=self.config,
            scenarios=("known",), evaluate=Evaluator(self.config, mutate=mutate),
        )
        self.assertIs(output, self.base)
        self.assertIn("cash trough is negative", report["detail"])

    def test_automatic_end_of_day_drop_is_not_realization(self):
        events = valid_events()
        events[2].pop("explicit")
        output, report = admit_realized_patch(
            self.base, self.patches, config=self.config,
            scenarios=("known",), evaluate=Evaluator(self.config, events=events),
        )
        self.assertIs(output, self.base)
        self.assertIn("explicitly executed", report["detail"])

    def test_floor_price_or_failed_sale_with_zero_cash_rejects(self):
        events = valid_events(cash=12.0)
        events[-1]["cash_delta"] = 0
        output, report = admit_realized_patch(
            self.base, self.patches, config=self.config,
            scenarios=("known",), evaluate=Evaluator(self.config, events=events),
        )
        self.assertIs(output, self.base)
        self.assertIn("positive cash", report["detail"])

    def test_partial_drop_rejects(self):
        events = valid_events(quantity=3)
        events[2]["quantity"] = 2
        output, report = admit_realized_patch(
            self.base, self.patches, config=self.config,
            scenarios=("known",), evaluate=Evaluator(self.config, events=events),
        )
        self.assertIs(output, self.base)
        self.assertIn("DROP quantity must equal", report["detail"])

    def test_partial_sale_rejects(self):
        events = valid_events(quantity=3)
        events[3]["quantity"] = 2
        output, report = admit_realized_patch(
            self.base, self.patches, config=self.config,
            scenarios=("known",), evaluate=Evaluator(self.config, events=events),
        )
        self.assertIs(output, self.base)
        self.assertIn("sold quantity must equal", report["detail"])

    def test_item_identity_cannot_change_inside_lot(self):
        events = valid_events()
        events[-1]["item"] = "CORN"
        output, report = admit_realized_patch(
            self.base, self.patches, config=self.config,
            scenarios=("known",), evaluate=Evaluator(self.config, events=events),
        )
        self.assertIs(output, self.base)
        self.assertIn("cannot change item identity", report["detail"])

    def test_commit_must_be_on_a_changed_action_step(self):
        events = valid_events(commit_step=1)
        output, report = admit_realized_patch(
            self.base, self.patches, config=self.config,
            scenarios=("known",), evaluate=Evaluator(self.config, events=events),
        )
        self.assertIs(output, self.base)
        self.assertIn("commitment on a changed action step", report["detail"])

    def test_commit_after_rejoin_rejects(self):
        events = valid_events(commit_step=4)
        output, report = admit_realized_patch(
            self.base, self.patches, config=self.config,
            scenarios=("known",), evaluate=Evaluator(self.config, events=events),
        )
        self.assertIs(output, self.base)
        self.assertIn("before rejoin_step", report["detail"])

    def test_out_of_order_sale_before_drop_rejects(self):
        events = valid_events()
        events[2], events[3] = events[3], events[2]
        output, report = admit_realized_patch(
            self.base, self.patches, config=self.config,
            scenarios=("known",), evaluate=Evaluator(self.config, events=events),
        )
        self.assertIs(output, self.base)
        self.assertIn("engine execution order", report["detail"])

    def test_two_independent_lots_admit_and_aggregate(self):
        events = valid_events()
        events += [
            {"kind": "commit", "step": 3, "lot": "lot-2", "item": "CORN", "quantity": 1},
            {"kind": "harvest", "step": 8, "lot": "lot-2", "item": "CORN", "quantity": 2},
            {"kind": "drop", "step": 8, "lot": "lot-2", "item": "CORN", "quantity": 2, "explicit": True},
            {"kind": "sale", "step": 9, "lot": "lot-2", "item": "CORN", "quantity": 2, "cash_delta": 7},
        ]
        events.sort(key=lambda row: (row["step"], {"commit": 0, "harvest": 1, "drop": 2, "sale": 3}[row["kind"]]))
        output, report = admit_realized_patch(
            self.base, self.patches, config=self.config,
            scenarios=("known",), evaluate=Evaluator(self.config, events=events),
        )
        self.assertIsNot(output, self.base)
        row = report["scenarios"][0]
        self.assertEqual(row["realized_lots"], 2)
        self.assertEqual(row["realized_units"], 5)
        self.assertEqual(row["realized_cash"], 19.0)

    def test_patch_at_rejoin_is_invalid_and_parent_identity_preserved(self):
        patches = {4: action(farmer=["WATER"])}
        output, report = admit_realized_patch(
            self.base, patches, config=self.config,
            scenarios=("known",), evaluate=Evaluator(self.config),
        )
        self.assertIs(output, self.base)
        self.assertEqual(report["reason"], "invalid_input")
        self.assertIn("[now, rejoin_step)", report["detail"])

    def test_noop_patch_is_invalid(self):
        output, report = admit_realized_patch(
            self.base, {2: deepcopy(self.base[2])}, config=self.config,
            scenarios=("known",), evaluate=Evaluator(self.config),
        )
        self.assertIs(output, self.base)
        self.assertIn("does not change", report["detail"])

    def test_duplicate_scenarios_fail_before_evaluation(self):
        evaluator = Evaluator(self.config)
        output, report = admit_realized_patch(
            self.base, self.patches, config=self.config,
            scenarios=("known", "known"), evaluate=evaluator,
        )
        self.assertIs(output, self.base)
        self.assertEqual(evaluator.calls, [])
        self.assertIn("unique", report["detail"])

    def test_receipt_scenario_label_must_match(self):
        def mutate(receipt, _scenario):
            receipt["scenario"] = "other"
        output, report = admit_realized_patch(
            self.base, self.patches, config=self.config,
            scenarios=("known",), evaluate=Evaluator(self.config, mutate=mutate),
        )
        self.assertIs(output, self.base)
        self.assertIn("does not match", report["detail"])

    def test_incomplete_receipt_rejects(self):
        def mutate(receipt, _scenario):
            receipt["complete"] = False
        output, report = admit_realized_patch(
            self.base, self.patches, config=self.config,
            scenarios=("known",), evaluate=Evaluator(self.config, mutate=mutate),
        )
        self.assertIs(output, self.base)
        self.assertIn("incomplete", report["detail"])

    def test_evaluator_exception_is_contained(self):
        def explode(*_args):
            raise RuntimeError("boom")
        output, report = admit_realized_patch(
            self.base, self.patches, config=self.config,
            scenarios=("known",), evaluate=explode,
        )
        self.assertIs(output, self.base)
        self.assertFalse(report["complete"])
        self.assertEqual(report["reason"], "evaluator_exception")
        self.assertIn("RuntimeError: boom", report["detail"])

    def test_budget_overrun_rejects_and_discards_partial_receipts(self):
        config = AdmissionConfig(now=0, terminal_step=10, rejoin_step=4, seconds=0.001)
        evaluator = Evaluator(config)
        original_call = evaluator.__call__
        def slow(base, candidate, scenario, deadline):
            time.sleep(0.003)
            return original_call(base, candidate, scenario, deadline)
        output, report = admit_realized_patch(
            self.base, self.patches, config=config,
            scenarios=("known",), evaluate=slow,
        )
        self.assertIs(output, self.base)
        self.assertFalse(report["complete"])
        self.assertEqual(report["reason"], "incomplete_budget")
        self.assertEqual(report["scenarios"], [])

    def test_strict_json_rejects_nan_patch_without_evaluator(self):
        evaluator = Evaluator(self.config)
        bad = {2: {"farmer": ["PLANT", "WHEAT"], "market": [["SELL", "WHEAT", float("nan")]]}}
        output, report = admit_realized_patch(
            self.base, bad, config=self.config,
            scenarios=("known",), evaluate=evaluator,
        )
        self.assertIs(output, self.base)
        self.assertEqual(evaluator.calls, [])
        self.assertIn("finite numbers", report["detail"])

    def test_bool_steps_and_quantities_are_not_integers(self):
        with self.assertRaises(InvalidLifecycle):
            materialize_candidate(self.base, {True: action(farmer=["WATER"])}, self.config)
        events = valid_events()
        events[1]["quantity"] = True
        output, report = admit_realized_patch(
            self.base, self.patches, config=self.config,
            scenarios=("known",), evaluate=Evaluator(self.config, events=events),
        )
        self.assertIs(output, self.base)
        self.assertIn("must be an integer", report["detail"])

    def test_invalid_hash_shape_rejects(self):
        def mutate(receipt, _scenario):
            receipt["trace_sha256"] = "ABC"
        output, report = admit_realized_patch(
            self.base, self.patches, config=self.config,
            scenarios=("known",), evaluate=Evaluator(self.config, mutate=mutate),
        )
        self.assertIs(output, self.base)
        self.assertIn("lowercase sha256", report["detail"])

    def test_route_digest_is_canonical_over_mapping_order(self):
        left = route(3)
        right = route(3)
        right[1] = {"market": [], "hands": [], "farmer": ["PASS"]}
        self.assertEqual(route_sha256(left, 0, 2), route_sha256(right, 0, 2))


    def test_inherited_maintenance_commit_can_support_changed_source_commit(self):
        config = AdmissionConfig(
            now=0, terminal_step=10, rejoin_step=5,
            minimum_gain=0.0, seconds=1.0,
        )
        events = valid_events()
        events.insert(1, {
            "kind": "commit", "step": 4, "lot": "lot-1",
            "item": "WHEAT", "quantity": 1,
        })
        output, report = admit_realized_patch(
            self.base, self.patches, config=config,
            scenarios=("known",), evaluate=Evaluator(config, events=events),
        )
        self.assertIsNot(output, self.base)
        self.assertTrue(report["admitted"])

    def test_evaluator_input_mutation_is_isolated_from_transaction_routes(self):
        original = deepcopy(self.base)

        def evaluator(base, candidate, scenario, _deadline):
            base[0]["farmer"] = ["CORRUPT"]
            candidate[2]["farmer"] = ["CORRUPT"]
            # Bind the receipt to the intended immutable transaction routes, not
            # the simulator's disposable mutated snapshots.
            clean_candidate = materialize_candidate(self.base, self.patches, self.config)
            return {
                "complete": True,
                "scenario": scenario,
                "base_route_sha256": clean_candidate.base_sha256,
                "candidate_route_sha256": clean_candidate.candidate_sha256,
                "engine_sha256": ENGINE,
                "trace_sha256": TRACE_A,
                "rejoin_control_base_sha256": CONTROL,
                "rejoin_control_candidate_sha256": CONTROL,
                "existing_obligations_preserved": True,
                "base_terminal_score": 100,
                "candidate_terminal_score": 105,
                "candidate_minimum_cash": 1,
                "events": valid_events(),
            }

        output, report = admit_realized_patch(
            self.base, self.patches, config=self.config,
            scenarios=("known",), evaluate=evaluator,
        )
        self.assertEqual(self.base, original)
        self.assertIsNot(output, self.base)
        self.assertEqual(output[2]["farmer"], ["PLANT", "WHEAT"])
        self.assertTrue(report["admitted"])

    def test_non_string_json_object_keys_reject_before_evaluation(self):
        evaluator = Evaluator(self.config)
        output, report = admit_realized_patch(
            self.base, {2: {1: ["PLANT", "WHEAT"]}}, config=self.config,
            scenarios=("known",), evaluate=evaluator,
        )
        self.assertIs(output, self.base)
        self.assertEqual(evaluator.calls, [])
        self.assertIn("object keys must be strings", report["detail"])

    def test_report_contains_no_raw_action_or_private_state(self):
        output, report = admit_realized_patch(
            self.base, self.patches, config=self.config,
            scenarios=("known",), evaluate=Evaluator(self.config),
        )
        self.assertIsNot(output, self.base)
        encoded = json.dumps(report, sort_keys=True)
        self.assertNotIn('"farmer"', encoded)
        self.assertNotIn('"hands"', encoded)
        self.assertNotIn('"market"', encoded)


if __name__ == "__main__":
    unittest.main()
