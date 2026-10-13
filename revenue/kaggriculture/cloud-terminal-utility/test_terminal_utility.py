# SPDX-License-Identifier: Apache-2.0
"""Focused objective, paired-record, unchanged-solver and CLI regressions."""
from __future__ import annotations
import copy
from fractions import Fraction
import lzma
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from terminal_utility import build_table, solve_terminal, win_points

HERE = Path(__file__).resolve().parent
SOLVER_FILE = Path(os.environ.get("TITAN_T15_SOLVER", HERE.parent / "cloud-market-game-theory/solver.py"))


def document(margins=((-2, -2), (1, -1), (-1, 1))):
    plans = ["base", "a", "b"][:len(margins)]
    scenarios = ["x", "y"][:len(margins[0])]
    return {"baseline": "base", "plan_ids": plans, "scenario_ids": scenarios,
            "source": {"kind": "constructed_arithmetic_control"},
            "receipts": [{"plan": p, "scenario": s, "own_cash": 100 + margins[i][j],
                          "rival_cash": 100, "done": True,
                          "plan_sha256": p, "scenario_sha256": s, "public_state_sha256": "same"}
                         for i, p in enumerate(plans) for j, s in enumerate(scenarios)]}


class Numbers(unittest.TestCase):
    def test_win_loss_tie(self):
        self.assertEqual([win_points(2, 1), win_points(1, 2), win_points(2, 2)], [1, 0, Fraction(1, 2)])

    def test_exact_fraction_tie(self):
        self.assertEqual(win_points("1/3", Fraction(1, 3)), Fraction(1, 2))

    def test_large_integer_not_rounded(self):
        self.assertEqual(win_points(2**60 + 1, 2**60), 1)

    def test_exact_decimal_boundary(self):
        self.assertEqual(win_points("0.100000000000000001", "0.1"), 1)

    def test_nonfinite_and_boolean_values(self):
        for value in (True, False, float("nan"), float("inf"), "nan", "1/0", None, {}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                win_points(value, 1)


class PairedTables(unittest.TestCase):
    def test_baseline_is_first_without_changing_column_order(self):
        data = document(); data["plan_ids"] = ["b", "base", "a"]; data["scenario_ids"] = ["y", "x"]
        out = build_table(data)
        self.assertEqual(out["plan_ids"], ["base", "b", "a"])
        self.assertEqual(out["scenario_ids"], ["y", "x"])
        self.assertEqual(out["utility_deltas"], [["0", "0"], ["2", "0"], ["0", "2"]])

    def test_exact_centered_and_absolute_objectives(self):
        out = build_table(document())
        self.assertEqual(out["absolute_centered_utilities"], [["-1", "-1"], ["1", "-1"], ["-1", "1"]])
        self.assertEqual(out["utility_deltas"], [["0", "0"], ["2", "0"], ["0", "2"]])
        self.assertEqual(out["cash_margin_deltas"], [["0", "0"], ["3", "1"], ["1", "3"]])

    def test_rival_cash_is_part_of_outcome(self):
        data = document(); data["receipts"][2]["rival_cash"] = 1000
        self.assertEqual(build_table(data)["win_points"][1][0], "0")

    def test_missing_cell_stays_incomplete(self):
        data = document(); data["receipts"].pop()
        out = build_table(data)
        self.assertFalse(out["solver_ready"])
        self.assertEqual(out["incomplete_cells"], [{"plan": "b", "scenario": "y"}])
        self.assertIsNone(out["receipts"][2][1])

    def test_nonterminal_values_are_only_margin_proxy(self):
        data = document(); data["receipts"][0]["done"] = False
        out = build_table(data)
        self.assertEqual(out["objective"], "cash_margin_proxy")
        self.assertIsNone(out["win_points"])
        self.assertIsNone(out["utility_deltas"])
        self.assertEqual(out["cash_margins"][0], ["-2", "-2"])

    def test_missing_done_is_not_inferred_from_cash(self):
        data = document(); del data["receipts"][0]["done"]
        self.assertFalse(build_table(data)["terminal"])

    def test_null_cash_is_not_inferred_as_zero(self):
        data = document(); data["receipts"][1]["own_cash"] = None
        out = build_table(data)
        self.assertFalse(out["terminal"])
        self.assertIsNone(out["cash_margin_deltas"][1][1])

    def test_duplicate_pair_is_a_data_error(self):
        data = document(); data["receipts"].append(copy.deepcopy(data["receipts"][0]))
        with self.assertRaises(ValueError): build_table(data)

    def test_plan_binding_does_not_change_by_scenario(self):
        data = document(); data["receipts"][1]["plan_sha256"] = "different-action"
        with self.assertRaises(ValueError): build_table(data)

    def test_scenario_binding_is_shared_by_all_plans(self):
        data = document(); data["receipts"][2]["scenario_sha256"] = "different-rival"
        with self.assertRaises(ValueError): build_table(data)

    def test_public_decision_binding_is_shared(self):
        data = document(); data["receipts"][1]["public_state_sha256"] = "different-observation"
        with self.assertRaises(ValueError): build_table(data)

    def test_missing_hashes_reported_without_fabrication(self):
        data = document(); del data["receipts"][0]["plan_sha256"]
        out = build_table(data)
        self.assertEqual(len(out["bindings"]["omissions"]), 1)
        self.assertTrue(out["terminal"])

    def test_input_and_output_are_detached(self):
        data = document(); original = copy.deepcopy(data); out = build_table(data)
        out["source"]["kind"] = "changed"; out["receipts"][0][0]["own_cash"] = "999"
        self.assertEqual(data, original)

    def test_bad_done_is_not_truthiness(self):
        data = document(); data["receipts"][0]["done"] = "false"
        with self.assertRaises(ValueError): build_table(data)

    def test_duplicate_labels_and_missing_baseline(self):
        for edit in ({"plan_ids": ["base", "base"]}, {"baseline": "unknown"}, {"scenario_ids": []}):
            data = document(); data.update(edit)
            with self.subTest(edit=edit), self.assertRaises(ValueError): build_table(data)

    def test_unknown_receipt_label(self):
        data = document(); data["receipts"][0]["scenario"] = "new-unlisted-world"
        with self.assertRaises(ValueError): build_table(data)


@unittest.skipUnless(SOLVER_FILE.is_file(), "Supply the existing T15 solver with TITAN_T15_SOLVER.")
class ExistingSolver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = SOLVER_FILE.read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if blob != "3a6446d96e8470374dd5b5ba72a8e5c6d41a8ad3":
            raise AssertionError("T15 source differs from the recorded consumer pin.")
        spec = importlib.util.spec_from_file_location("test_existing_t15_solver", SOLVER_FILE)
        cls.module = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.module)

    def test_exact_mixture_when_baseline_utility_constant(self):
        out = solve_terminal(build_table(document()), self.module.solve_table)
        self.assertEqual(out["weights"], ["0", "1/2", "1/2"])
        self.assertEqual(out["worst_expected_win_points"], "1/2")
        self.assertIsNone(out["win_probability"])

    def test_winning_baseline_remains_optimal(self):
        out = solve_terminal(build_table(document(((1, 1), (100, 100), (-1, 100)))), self.module.solve_table)
        self.assertEqual(out["weights"], ["1", "0", "0"])
        self.assertEqual(out["worst_expected_win_points"], "1")

    def test_varying_baseline_does_not_masquerade_as_absolute(self):
        table = build_table(document(((-1, 1), (1, 1), (-1, -1))))
        def not_called(_): raise AssertionError("Wrong solver interface invoked.")
        out = solve_terminal(table, not_called)
        self.assertEqual(out["status"], "absolute_matrix_solver_needed")
        self.assertFalse(out["solver_called"])

    def test_relative_mode_is_explicitly_a_different_objective(self):
        table = build_table(document(((-1, 1), (1, 1), (-1, -1))))
        out = solve_terminal(table, self.module.solve_table, objective="baseline_relative")
        self.assertEqual(out["objective"], "baseline_relative_terminal_win_points")
        self.assertEqual(out["weights"], ["1", "0", "0"])
        self.assertEqual(table["win_points"][1], ["1", "1"])

    def test_no_solver_call_on_nonterminal_projection(self):
        data = document(); data["receipts"][0]["done"] = False
        def not_called(_): raise AssertionError("Nonterminal solver call.")
        self.assertFalse(solve_terminal(build_table(data), not_called)["solver_called"])

    def test_bad_weights_and_value_are_not_accepted(self):
        for result in ({"weights": ["-1", "1", "1"], "value": "0"},
                       {"weights": ["0", "1/2", "1/2"], "value": "999"}):
            with self.subTest(result=result), self.assertRaises(ValueError):
                solve_terminal(build_table(document()), lambda _: result)

    def test_cli_round_trip_with_actual_t15(self):
        with tempfile.TemporaryDirectory() as root:
            src, dst = Path(root)/"input.json", Path(root)/"output.json"
            src.write_text(json.dumps(document()))
            run = subprocess.run([sys.executable, str(HERE/"terminal_utility.py"), "--input", str(src),
                                  "--output", str(dst), "--solver-file", str(SOLVER_FILE)],
                                 capture_output=True, text=True, check=False)
            self.assertEqual(run.returncode, 0, run.stderr)
            out = json.loads(dst.read_text())
            self.assertEqual(out["solution"]["weights"], ["0", "1/2", "1/2"])
            self.assertEqual(out["input_sha256"], hashlib.sha256(src.read_bytes()).hexdigest())

    def test_cli_invalid_json_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as root:
            src, dst = Path(root)/"input.json", Path(root)/"output.json"
            src.write_text("not JSON")
            run = subprocess.run([sys.executable, str(HERE/"terminal_utility.py"), "--input", str(src),
                                  "--output", str(dst)], capture_output=True, text=True, check=False)
            self.assertEqual(run.returncode, 2)
            self.assertFalse(dst.exists())
            self.assertEqual(json.loads(run.stderr)["error"], "JSONDecodeError")


class RetainedEngineEvidence(unittest.TestCase):
    def test_all_retained_receipts_rebuild_exact_tables(self):
        artifact = HERE/"engine-cases.json.xz"
        if not artifact.is_file(): self.skipTest("Generate the retained engine artifact first.")
        data = json.loads(lzma.decompress(artifact.read_bytes()))
        self.assertEqual(data["official_action_transitions"], 66)
        self.assertEqual(data["case_count"], 10)
        for case in data["cases"]:
            self.assertEqual(build_table(case["document"]), case["table"])
            if case["table"]["terminal"]:
                for r in case["document"]["receipts"]:
                    self.assertEqual(r["official_rewards"], [r["own_cash"], r["rival_cash"]])
                    self.assertEqual(r["statuses"], ["DONE", "DONE"])


if __name__ == "__main__":
    unittest.main()
