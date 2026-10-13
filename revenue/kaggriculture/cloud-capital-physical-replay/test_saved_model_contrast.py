# SPDX-License-Identifier: Apache-2.0
"""Saved-record arithmetic/coverage checks; no controller or engine executions."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import unittest

import contrast_saved_models as subject


class SavedModelContrastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(os.environ["RILL_REACHED_ROOT"])
        portable = (root / "data/reached-final.json").is_file()
        physical = root / ("data/reached-final.json" if portable else "work/reached-final.json")
        nominal = root / ("data/current-date-result.json" if portable else
                          "osprey-reached-quote-case/evidence/current-date-result.json")
        path = root / ("dependencies/reached_states.py" if portable else
                       "osprey-reached-quote-case/source/cloud-terminal-sell/reached_states.py")
        cls.physical = json.loads(physical.read_text())
        cls.nominal = json.loads(nominal.read_text())
        spec = importlib.util.spec_from_file_location("rill_contrast_normalizer", path)
        normalizer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(normalizer)
        row = cls.physical["validation"]["input_row"]
        cls.inputs = normalizer.actor_input(row, row["seat"])

    def run_case(self, physical=None, nominal=None, inputs=None):
        return subject.compare_reports(self.physical if physical is None else physical,
                self.nominal if nominal is None else nominal, self.inputs if inputs is None else inputs)

    def test_exact_saved_four_case_cash_bridge(self):
        before = subject.digest([self.physical, self.nominal, self.inputs])
        result = self.run_case()
        self.assertEqual([c["physical_minus_nominal"] for c in result["cases"]], [2371, 2682, 2162, 3133])
        self.assertEqual(sum(c["queues"] for c in result["cases"]), 1972)
        self.assertEqual(result["engine_calls"], 0)
        for c in result["cases"]:
            self.assertEqual(sum(r["delta"] for r in c["rows"]), c["physical_minus_nominal"])
        self.assertEqual(subject.digest([self.physical, self.nominal, self.inputs]), before)

    def test_first_cash_change_is_available_stock_withheld_not_missing_stock(self):
        for c in self.run_case()["cases"]:
            self.assertEqual(c["first_indexed_queue_difference"]["step"], 237)
            w = c["first_cash_difference"]
            self.assertEqual(w["step"], 258)
            self.assertEqual(c["first_effective_queue_difference"]["step"], 258)
            self.assertEqual(w["nominal_cash_delta"], 1732)
            self.assertEqual(w["physical_cash_delta"], 0)
            self.assertEqual(w["physical_shed_before"]["MILK"], 12)
            self.assertEqual(w["physical_shed_after"]["MILK"], 12)

    def test_zero_placeholders_do_not_compact_later_slots(self):
        a = subject.indexed([["SELL", "WHEAT", 0], ["HIRE"]])
        b = subject.indexed([[], ["HIRE"]])
        c = subject.indexed([["HIRE"]])
        self.assertEqual(subject.effective(a), subject.effective(b))
        self.assertNotEqual(subject.effective(a), subject.effective(c))

    def test_incomplete_bank_is_not_compared(self):
        p = deepcopy(self.physical); p["complete"] = False
        with self.assertRaises(ValueError): self.run_case(physical=p)
        p = deepcopy(self.physical); p["replay"]["cases"].pop()
        with self.assertRaises(ValueError): self.run_case(physical=p)

    def test_mutated_input_or_program_identity_is_not_compared(self):
        n = deepcopy(self.nominal); n["input_sha256"] = "different"
        with self.assertRaises(ValueError): self.run_case(nominal=n)
        n = deepcopy(self.nominal); n["program_sha256"][next(iter(n["program_sha256"]))] = "different"
        with self.assertRaises(ValueError): self.run_case(nominal=n)

    def test_unmatched_scenario_or_future_draw_is_not_paired(self):
        n = deepcopy(self.nominal); n["scenario_specifications"][1]["shop_additions"] = {"289": ["YARN_STORE"]}
        with self.assertRaises(ValueError): self.run_case(nominal=n)
        n = deepcopy(self.nominal); n["scenario_specifications"].pop()
        with self.assertRaises(ValueError): self.run_case(nominal=n)

    def test_missing_physical_row_or_cash_discontinuity_is_detected(self):
        p = deepcopy(self.physical); p["replay"]["cases"][0]["market_rows"].pop(30)
        with self.assertRaises(ValueError): self.run_case(physical=p)
        p = deepcopy(self.physical); p["replay"]["cases"][0]["market_rows"][2]["cash_before"] += 1
        with self.assertRaises(ValueError): self.run_case(physical=p)

    def test_duplicate_nominal_slot_is_detected(self):
        n = deepcopy(self.nominal); trace = n["flow"]["rows"][0][0]["trace"]
        trace.append(deepcopy(trace[0]))
        with self.assertRaises(ValueError): self.run_case(nominal=n)

    def test_nonfinite_fractional_and_boolean_cash_are_not_silently_rounded(self):
        for value in (True, 0.25, float("nan"), float("inf")):
            with self.subTest(value=str(value)):
                with self.assertRaises(ValueError): subject.cash(value)

    def test_terminal_row_drift_is_detected(self):
        n = deepcopy(self.nominal); n["flow"]["rows"][0][0]["final_marked_cash"] += 1
        with self.assertRaises(ValueError): self.run_case(nominal=n)
        p = deepcopy(self.physical); p["replay"]["cases"][0]["final_cash"] -= 1
        with self.assertRaises(ValueError): self.run_case(physical=p)


if __name__ == "__main__":
    unittest.main()
