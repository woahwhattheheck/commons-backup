import csv
import tempfile
import unittest
from pathlib import Path

import check as consistency
import generate_examples
from model import load_csv


class OutputConsistencyTests(unittest.TestCase):
    def test_corrected_bundle_passes(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            generate_examples.write_bundle(p, mismatch=False)
            result = consistency.check_bundle(p)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["diagnostic_count"], 0)

    def test_deliberate_mismatches_are_field_specific(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            generate_examples.write_bundle(p, mismatch=True)
            result = consistency.check_bundle(p)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["diagnostic_count"], 5)
            signatures = {
                (d["code"], d["artifact"], d["entity_id"], d["field"])
                for d in result["diagnostics"]
            }
            self.assertIn(("FIELD_MISMATCH", "matrix.csv", "F-002", "state"), signatures)
            self.assertIn(("FIELD_MISMATCH", "recommendations.csv", "R-002", "phase"), signatures)
            self.assertIn(("COUNT_MISMATCH", "executive-summary.json", "ALL", "recommendations"), signatures)
            self.assertIn(("FIELD_MISMATCH", "executive-summary.json", "R-001", "estimate_low"), signatures)
            self.assertIn(("UNKNOWN_REFERENCE", "presentation.json", "S-999", "finding_id"), signatures)

    def test_unknown_state_is_preserved_not_coerced(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            generate_examples.write_bundle(p, mismatch=False)
            matrix = load_csv(p / "matrix.csv")
            f4 = next(r for r in matrix if r["finding_id"] == "F-004")
            self.assertEqual(f4["finding_state"], "UNKNOWN")
            result = consistency.check_bundle(p)
            self.assertEqual(result["status"], "PASS")

    def test_missing_canonical_recommendation_is_reported(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            generate_examples.write_bundle(p, mismatch=False)
            rows = load_csv(p / "recommendations.csv")
            rows = [r for r in rows if r["recommendation_id"] != "R-002"]
            with (p / "recommendations.csv").open("w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(
                    fh,
                    fieldnames=["recommendation_id","linked_findings","phase","estimate_low","estimate_high"],
                )
                w.writeheader()
                w.writerows(rows)
            result = consistency.check_bundle(p)
            self.assertTrue(any(
                d["code"] == "MISSING_ENTITY" and d["entity_id"] == "R-002"
                for d in result["diagnostics"]
            ))

    def test_reports_are_deterministic_and_operator_readable(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            generate_examples.write_bundle(p, mismatch=True)
            first = consistency.check_bundle(p)
            second = consistency.check_bundle(p)
            self.assertEqual(first, second)
            md = consistency.markdown_report(first)
            self.assertIn("Cross-output consistency report", md)
            self.assertIn("matrix.csv", md)
            self.assertIn("UNKNOWN remains a literal state", md)


if __name__ == "__main__":
    unittest.main()
