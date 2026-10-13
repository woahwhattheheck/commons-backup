# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import json
from pathlib import Path
import unittest
import flockbind_field_gate as g

HERE = Path(__file__).resolve().parent
PANEL = json.loads((HERE / "FLOCKBIND-FIELD-B567.json").read_text())


class FieldGateTests(unittest.TestCase):
    def test_published_panel_is_valid_hold(self):
        out = g.validate_panel(deepcopy(PANEL))
        self.assertTrue(out["valid"])
        self.assertEqual(out["disposition"], "HOLD_NEGATIVE_CELLS")
        self.assertEqual(out["cells"], 8)
        self.assertEqual(len(out["negative_cells"]), 4)
        self.assertEqual(out["mean_own_delta"], 3626.75)
        self.assertEqual(out["mean_margin_delta"], 3743.25)
        self.assertFalse(out["activation_authority"])

    def test_source_drift_is_invalid(self):
        panel = deepcopy(PANEL)
        panel["source"]["native_runtime_git_blob"] = "0" * 40
        out = g.validate_panel(panel)
        self.assertFalse(out["valid"])
        self.assertEqual(out["disposition"], "INVALID")
        self.assertIn("source_mismatch:native_runtime_git_blob", out["reasons"])

    def test_missing_and_duplicate_cells_are_invalid(self):
        panel = deepcopy(PANEL)
        panel["cells"][-1] = deepcopy(panel["cells"][0])
        out = g.validate_panel(panel)
        self.assertFalse(out["valid"])
        self.assertTrue(any("duplicate_coordinate" in r for r in out["reasons"]))
        self.assertTrue(any(r.startswith("missing_coordinates:") for r in out["reasons"]))

    def test_boolean_seat_alias_is_invalid(self):
        panel = deepcopy(PANEL)
        cell = next(c for c in panel["cells"] if c["seat"] == 1)
        cell["seat"] = True
        out = g.validate_panel(panel)
        self.assertFalse(out["valid"])
        self.assertEqual(out["disposition"], "INVALID")
        self.assertTrue(any("bad_coordinate" in r for r in out["reasons"]))

    def test_score_mutation_without_delta_update_is_invalid(self):
        panel = deepcopy(PANEL)
        panel["cells"][0]["candidate_scores"][0] += 1
        out = g.validate_panel(panel)
        self.assertFalse(out["valid"])
        self.assertTrue(any("delta_mismatch" in r for r in out["reasons"]))

    def test_failure_and_unfulfilled_obligation_are_invalid(self):
        panel = deepcopy(PANEL)
        panel["cells"][0]["failure"] = "timeout"
        panel["cells"][1]["engagement"]["obligation_status"] = "pending"
        out = g.validate_panel(panel)
        self.assertFalse(out["valid"])
        self.assertTrue(any("failure_present" in r for r in out["reasons"]))
        self.assertTrue(any("obligation_unfulfilled" in r for r in out["reasons"]))

    def test_all_nonnegative_is_evidence_predicate_not_activation(self):
        panel = deepcopy(PANEL)
        for cell in panel["cells"]:
            seat = cell["seat"]
            base = cell["baseline_scores"]
            candidate = list(base)
            candidate[seat] += 1
            cell["candidate_scores"] = candidate
            cell["own_delta"] = 1
            cell["rival_delta"] = 0
            cell["margin_delta"] = 1
        # Restore starter mirror symmetry after editing seat-oriented scores.
        for seed in g.REQUIRED_SEEDS:
            a = next(c for c in panel["cells"] if c["seed"] == seed and c["seat"] == 0)
            b = next(c for c in panel["cells"] if c["seed"] == seed and c["seat"] == 1)
            b["candidate_scores"] = list(reversed(a["candidate_scores"]))
        out = g.validate_panel(panel)
        self.assertTrue(out["valid"])
        self.assertEqual(out["disposition"], "ALL_CELLS_NONNEGATIVE")
        self.assertFalse(out["activation_authority"])


if __name__ == "__main__":
    unittest.main()
