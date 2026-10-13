# SPDX-License-Identifier: Apache-2.0
"""Actual retained integrated-family fork and completed-outcome consumption tests.

Point RILL_REACHED_ROOT to the extracted test environment described in the guide.
The tests load real existing controller, SELL, TRACE and DATE source; no game or
interpreter is initialized. The original prefix is restored once for this suite.
"""
from copy import deepcopy
import gzip
import json
import os
from pathlib import Path
import random
import sys
import unittest

import reached_integrated as subject


class ReachedIntegratedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ["RILL_REACHED_ROOT"])
        runtime = cls.root / "original-runtime/revenue/kaggriculture"
        cls.date = cls.root / "TITAN-DATE-capital-consumers-PR10098/cloud-capital-scenarios"
        sys.path[:0] = [str(runtime / "cloud-integration-differentials"),
                       str(runtime / "cloud-execution-lab")]
        factory = subject.load(runtime / "cloud-integration-differentials/funded_main.py", "rill_test_original")
        random.seed(subject.ACTOR_SEED)
        cls.actor = factory.make_agent(funded=False)
        trace = cls.root / "TITAN-TRACE-DELVE-control-inputs/candidate-inputs.jsonl.gz"
        cls.rows = [json.loads(v) for v in gzip.decompress(trace.read_bytes()).splitlines()]
        cls.row, cls.restore = subject.restore_prefix(cls.actor, cls.rows)
        cls.report = json.loads((cls.root / "work/reached-complete.json").read_text())
        cls.original = subject.state_digest(cls.actor)
        cls.original_row = subject.digest(cls.row)

    def tearDown(self):
        self.assertEqual(subject.state_digest(self.actor), self.original)
        self.assertEqual(subject.digest(self.row), self.original_row)

    def test_exact_retained_prefix(self):
        self.assertEqual(self.restore["matched_actions"], 226)
        self.assertEqual(self.restore["engine_calls"], 0)
        self.assertEqual(subject.digest(self.row["observation"]),
                         "ed4770f347b8c18b1e87dea25aac91b785adbeaee5adb6f59b5fc67bb46fe5e4")

    def test_fork_has_one_independent_controller(self):
        clone = subject.fork_integrated(self.actor)
        self.assertIsNot(clone.controller, self.actor.controller)
        self.assertIs(clone.controller, clone.production.agent)
        self.assertIs(clone.controller, clone.production.chooser.agent)

    def test_source_modules_shared_without_modification(self):
        clone = subject.fork_integrated(self.actor)
        self.assertIs(clone.production.A, self.actor.production.A)
        self.assertIs(clone.production.K, self.actor.production.K)
        self.assertIs(clone.production.chooser.K, self.actor.production.chooser.K)

    def test_all_mutable_instance_graphs_disjoint(self):
        # Immutable tuples/frozensets can be shared by deepcopy. Only mutable
        # object IDs are relevant to the independent actor-state contract.
        def mutables(root):
            values = {}
            seen = set()
            def visit(value):
                if isinstance(value, (subject.types.ModuleType, subject.types.FunctionType, type)):
                    return
                if value is None or type(value) in (str, int, float, bool, bytes): return
                if id(value) in seen: return
                seen.add(id(value))
                if isinstance(value, (dict, list, set)) or hasattr(value, "__dict__"):
                    values[id(value)] = value
                if isinstance(value, dict):
                    for k, v in value.items(): visit(k); visit(v)
                elif isinstance(value, (list, tuple, set, frozenset)):
                    for v in value: visit(v)
                elif hasattr(value, "__dict__"): visit(vars(value))
            visit(root)
            return set(values)
        clone = subject.fork_integrated(self.actor)
        self.assertFalse(mutables(self.actor) & mutables(clone))

    def test_live_state_unmodified_by_independent_mutations(self):
        clone = subject.fork_integrated(self.actor)
        clone.controller.cur = subject.SHEEP
        clone.production.plans[123] = {"new": [1]}
        clone.last_packet["post_unit_observation"]["private"]["shed"]["WHEAT"] = 999
        clone.execution.seller.horizon = 1
        self.assertEqual(subject.state_digest(self.actor), self.original)

    def test_checkpoint_action_matches_original(self):
        clone = subject.fork_integrated(self.actor)
        action = clone.act(deepcopy(self.row["observation"]), deepcopy(self.row["configuration"]))
        self.assertEqual(action, self.row["expected_action"])

    def test_alternate_keeps_matched_units_and_changes_whole_route(self):
        clone = subject.fork_integrated(self.actor)
        self.assertTrue(clone.controller._switch_ok(subject.SHEEP, 226))
        clone.controller.cur = subject.SHEEP
        action = clone.act(deepcopy(self.row["observation"]), deepcopy(self.row["configuration"]))
        self.assertEqual(action["farmer"], self.row["expected_action"]["farmer"])
        self.assertEqual(action["hands"], self.row["expected_action"]["hands"])
        self.assertEqual(action["market"][2], ["BUY_ANIMAL", "SHEEP", 1])
        self.assertEqual(clone.production.agent.cur, subject.SHEEP)

    def test_inconsistent_alias_is_not_silently_accepted(self):
        clone = subject.fork_integrated(self.actor)
        clone.production.chooser.agent = deepcopy(clone.controller)
        with self.assertRaises(ValueError): subject.fork_integrated(clone)

    def test_unknown_module_shape_is_not_reset(self):
        clone = subject.fork_integrated(self.actor)
        clone.production.K = object()
        with self.assertRaises(TypeError): subject.fork_integrated(clone)

    def test_prefix_clock_mismatch_is_detected_before_action(self):
        rows = deepcopy(self.rows[:2]); rows[0]["step"] = 1
        with self.assertRaises(ValueError):
            subject.restore_prefix(subject.fork_integrated(self.actor), rows, checkpoint=1)

    def test_private_seat_mismatch_is_detected(self):
        rows = deepcopy(self.rows[:2]); rows[0]["seat"] = 1
        with self.assertRaises(ValueError):
            subject.restore_prefix(subject.fork_integrated(self.actor), rows, checkpoint=1)

    def test_checkpoint_must_exist(self):
        with self.assertRaises(ValueError):
            subject.restore_prefix(subject.fork_integrated(self.actor), [], checkpoint=226)

    def test_date_consumes_whole_completed_bank(self):
        result = subject.consume_completed(self.report, self.date)
        self.assertEqual(result["comparison"]["selected"], subject.MAIN)
        self.assertEqual(result["comparison"]["candidates"][subject.SHEEP]["worst_paired_gain"], -5251)
        self.assertEqual(result["engine_calls"], 0)
        self.assertFalse(result["applied_to_live_actor"])

    def test_date_retains_original_when_bank_incomplete(self):
        report = deepcopy(self.report); report["replay"]["cases"].pop()
        result = subject.consume_completed(report, self.date)["comparison"]
        self.assertEqual(result["selected"], subject.MAIN)
        self.assertEqual(result["reason"], "execution_report_invalid")

    def test_date_retains_original_on_partial_result(self):
        report = deepcopy(self.report); report["replay"]["complete"] = False
        result = subject.consume_completed(report, self.date)["comparison"]
        self.assertEqual(result["selected"], subject.MAIN)
        self.assertEqual(result["reason"], "execution_report_invalid")

    def test_recorded_futures_share_causal_action_prefix(self):
        for route in (subject.MAIN, subject.SHEEP):
            cases = [c for c in self.report["replay"]["cases"] if c["offered_route"] == route]
            for step in range(226, 288):
                self.assertEqual(cases[0]["result"]["actions"][str(step)], cases[1]["result"]["actions"][str(step)])
                self.assertEqual(cases[0]["market_rows"][step-226], cases[1]["market_rows"][step-226])
            self.assertTrue(all(not c["result"]["discarded_stock"] for c in cases))


if __name__ == "__main__":
    unittest.main()
