import copy
import json
import math
import tempfile
import unittest
from pathlib import Path

import panel_diversity as p


def panel():
    return {
        "schema": p.PANEL_SCHEMA,
        "expected_labels": 4,
        "opponents": [
            {"id": "a1", "kind": "archetype", "family": "A", "source_id": "src-A", "status": "resolved"},
            {"id": "a2", "kind": "archetype", "family": "A", "source_id": "src-A", "status": "resolved"},
            {"id": "a3", "kind": "archetype", "family": "A", "source_id": "src-A", "status": "resolved"},
            {"id": "b", "kind": "real_policy", "family": "B", "source_id": "src-B", "status": "resolved"},
        ],
    }


def results():
    return {
        "schema": p.RESULTS_SCHEMA,
        "rows": [
            {"opponent_id": "a1", "wins": 6, "losses": 0, "draws": 0, "margin_sum": 600},
            {"opponent_id": "a2", "wins": 6, "losses": 0, "draws": 0, "margin_sum": 600},
            {"opponent_id": "a3", "wins": 6, "losses": 0, "draws": 0, "margin_sum": 600},
            {"opponent_id": "b", "wins": 0, "losses": 6, "draws": 0, "margin_sum": -600},
        ],
    }


class PanelDiversityTests(unittest.TestCase):
    def test_alias_multiplicity_and_ess(self):
        report = p.analyze(panel())
        self.assertEqual(report["panel"]["unique_families"], 2)
        self.assertEqual(report["panel"]["unique_sources"], 2)
        self.assertEqual(report["panel"]["max_family_multiplicity"], 3)
        self.assertAlmostEqual(report["panel"]["label_weight_effective_family_count"], 1.6)
        self.assertEqual(report["panel"]["family_aliases"][0]["labels"], ["a1", "a2", "a3"])

    def test_family_balanced_is_not_label_weighted(self):
        report = p.analyze(panel(), results())
        self.assertAlmostEqual(report["results"]["label_weighted"]["win_rate"], 0.75)
        self.assertAlmostEqual(report["results"]["family_balanced"]["win_rate"], 0.5)
        self.assertAlmostEqual(report["results"]["label_weighted"]["mean_margin_per_game"], 50.0)
        self.assertAlmostEqual(report["results"]["family_balanced"]["mean_margin_per_game"], 0.0)
        self.assertTrue(report["authoritative_family_weighting"])

    def test_same_outcome_different_sources_is_warning_not_collapse(self):
        pn = panel()
        pn["opponents"] = [
            {"id": "x", "kind": "real_policy", "family": "X", "source_id": "src-X", "status": "resolved"},
            {"id": "y", "kind": "real_policy", "family": "Y", "source_id": "src-Y", "status": "resolved"},
        ]
        pn["expected_labels"] = 2
        rs = {"schema": p.RESULTS_SCHEMA, "rows": [
            {"opponent_id": "x", "wins": 1, "losses": 1, "draws": 0, "margin_sum": 0},
            {"opponent_id": "y", "wins": 1, "losses": 1, "draws": 0, "margin_sum": 0},
        ]}
        report = p.analyze(pn, rs)
        self.assertEqual(report["panel"]["unique_families"], 2)
        self.assertEqual(len(report["results"]["outcome_equality_warnings"]), 1)

    def test_duplicate_opponent_id_rejected(self):
        pn = panel()
        pn["opponents"][1]["id"] = "a1"
        with self.assertRaises(p.DataError):
            p.analyze(pn)

    def test_same_source_conflicting_family_rejected(self):
        pn = panel()
        pn["opponents"][1]["family"] = "other"
        with self.assertRaises(p.DataError):
            p.analyze(pn)

    def test_family_conflicting_kind_rejected(self):
        pn = panel()
        pn["opponents"][1]["kind"] = "real_policy"
        pn["opponents"][1]["source_id"] = "new-source"
        with self.assertRaises(p.DataError):
            p.analyze(pn)

    def test_unresolved_identity_is_explicit_and_blocks_authority(self):
        pn = panel()
        pn["opponents"][-1] = {"id": "unknown", "kind": "unknown", "family": None, "source_id": None, "status": "unresolved"}
        rs = results()
        rs["rows"][-1]["opponent_id"] = "unknown"
        report = p.analyze(pn, rs)
        self.assertFalse(report["panel"]["identity_complete"])
        self.assertFalse(report["authoritative_family_weighting"])
        self.assertIn("panel_identity_incomplete", report["blocking_reasons"])

    def test_unresolved_cannot_smuggle_family(self):
        pn = panel()
        pn["opponents"][-1].update(status="unresolved", family="B", source_id=None)
        with self.assertRaises(p.DataError):
            p.analyze(pn)

    def test_expected_count_shortfall_is_incomplete_not_silently_complete(self):
        pn = panel()
        pn["opponents"].pop()
        report = p.analyze(pn)
        self.assertEqual(report["panel"]["missing_label_count"], 1)
        self.assertFalse(report["panel"]["identity_complete"])

    def test_more_than_expected_rejected(self):
        pn = panel()
        pn["expected_labels"] = 3
        with self.assertRaises(p.DataError):
            p.analyze(pn)

    def test_missing_result_blocks_authority(self):
        rs = results()
        rs["rows"].pop()
        report = p.analyze(panel(), rs)
        self.assertFalse(report["authoritative_family_weighting"])
        self.assertIn("b", report["results"]["missing_opponent_results"])

    def test_bool_count_rejected(self):
        rs = results()
        rs["rows"][0]["wins"] = True
        with self.assertRaises(p.DataError):
            p.analyze(panel(), rs)

    def test_huge_integer_margin_fails_closed(self):
        rs = results()
        rs["rows"][0]["margin_sum"] = 10 ** 10000
        with self.assertRaises(p.DataError):
            p.analyze(panel(), rs)

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(p.DataError):
            p.loads_strict('{"schema":"x","schema":"y"}')

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(p.DataError):
            p.loads_strict('{"x": NaN}')

    def test_cli_require_complete_without_results_checks_identity_only(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "panel.json"
            path.write_text(json.dumps(panel()), encoding="utf-8")
            self.assertEqual(p.main([str(path), "--require-complete"]), 0)

    def test_cli_require_complete_returns_three_for_unresolved(self):
        pn = panel()
        pn["opponents"][-1] = {"id": "unknown", "kind": "unknown", "family": None, "source_id": None, "status": "unresolved"}
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "panel.json"
            path.write_text(json.dumps(pn), encoding="utf-8")
            self.assertEqual(p.main([str(path), "--require-complete"]), 3)


if __name__ == "__main__":
    unittest.main()
