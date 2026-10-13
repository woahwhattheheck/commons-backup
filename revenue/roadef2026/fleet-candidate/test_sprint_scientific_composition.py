#!/usr/bin/env python3
"""Join the existing native-number reader to the existing sprint consumer.

References here are small, explicitly constructed test data, not the official
sprint CSV or competitive evidence. No native checker or solver is executed.
"""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import compare_checker as reader


class SprintScientificComposition(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sprint-scientific-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.reference = self.root / "constructed-reference.csv"
        self.reference.write_text("Instance,Best team,1,2\nfixture-a,fixture-team,1,0.000001\nfixture-b,fixture-team,1,0\n", encoding="utf-8")
        self.reference_hash = hashlib.sha256(self.reference.read_bytes()).hexdigest()

    def checker(self, name, values, valid=True, cost=0):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        # Deliberately numeric JSON tokens, not quoted decimal strings.
        rows = ','.join('{"t":%d,"from":0,"to":1,"sat":%s}' % (i, v) for i, v in enumerate(values))
        path.write_text('{"valid":%s,"total_cost":%s,"saturations":[%s]}\n' %
                        ('true' if valid else 'false', cost, rows), encoding="utf-8")
        return path

    def report(self, left, instance=None):
        with patch.object(reader, "SPRINT_SHA256", self.reference_hash):
            return reader.sprint_report(left, self.reference, instance=instance)

    def test_native_scientific_value_reaches_sprint_without_rounding(self):
        path = self.checker("a.json", ["1", "9.933579335793359e-7"])
        out = self.report(path, "fixture-a")["instances"][0]
        self.assertEqual(out["winner"], "candidate")
        self.assertEqual(out["first_changed_rank"], 2)
        self.assertEqual(Decimal(out["candidate_at_first_change"]), Decimal("9.933579335793359e-7"))
        self.assertEqual(Decimal(out["reference_at_first_change"]), Decimal("0.000001"))
        self.assertEqual(out["candidate_checker_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertFalse(out["cost_used_in_ranking"])

    def test_small_positive_value_is_not_substituted_with_zero(self):
        path = self.checker("a.json", ["1", "9.933579335793359e-7"])
        out = self.report(path, "fixture-b")["instances"][0]
        self.assertEqual(out["winner"], "reference")
        self.assertEqual(out["first_changed_rank"], 2)
        self.assertNotEqual(Decimal(out["candidate_at_first_change"]), 0)

    def test_folder_uses_the_same_reader_and_exact_instance_labels(self):
        root = self.root / "reports"
        self.checker("reports/fixture-a/checker-6.json", ["1", "9.9e-7"])
        self.checker("reports/fixture-b/checker-6.json", ["1", "0"])
        result = self.report(root)
        self.assertEqual(result["counts"], {"candidate": 1, "reference": 0, "tie": 1})
        self.assertEqual(result["reference_instances_not_compared"], [])
        self.assertEqual(result["invalid_candidate_count"], 0)
        self.assertFalse(result["resource_budgets_matched"])

    def test_sprint_csv_precision_contract_remains_distinct(self):
        for text in ("1e-7", "9.9e-7", "0.1234567"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                reader.parse_sprint_csv(("Instance,Best team,1\nfixture-a,team," + text + "\n").encode())

    def test_reference_digest_check_remains_active(self):
        with self.assertRaises(ValueError):
            reader.load_sprint_reference(self.reference)
        with patch.object(reader, "SPRINT_SHA256", self.reference_hash):
            actual = reader.load_sprint_reference(self.reference)
        self.assertEqual(actual["sha256"], self.reference_hash)
        self.assertEqual(actual["records"]["fixture-a"]["vector"], [Decimal("1"), Decimal("0.000001")])

    def test_excess_precision_outside_native_band_still_fails_through_sprint(self):
        for value in ("1.234567e-6", "1e-8", "0.1234567"):
            with self.subTest(value=value):
                path = self.checker("bad.json", ["1", value])
                with self.assertRaises(ValueError):
                    self.report(path, "fixture-a")

    def test_cost_does_not_break_tied_sprint_vector(self):
        for cost in (0, 999999):
            path = self.checker("tie.json", ["1", "0.000001"], cost=cost)
            out = self.report(path, "fixture-a")["instances"][0]
            self.assertEqual(out["winner"], "tie")
            self.assertFalse(out["cost_used_in_ranking"])

    def test_invalid_candidate_retains_existing_disposition(self):
        path = self.checker("invalid.json", [], valid=False)
        out = self.report(path, "fixture-a")
        self.assertEqual(out["invalid_candidate_count"], 1)
        self.assertEqual(out["instances"][0]["winner"], "reference")
        self.assertEqual(out["instances"][0]["comparison_status"], "candidate_invalid")

    def test_unknown_instance_and_wrong_vector_length_remain_errors(self):
        path = self.checker("a.json", ["1", "9e-7"])
        with self.assertRaises(ValueError):
            self.report(path, "unknown")
        path = self.checker("short.json", ["1"])
        with self.assertRaises(ValueError):
            self.report(path, "fixture-a")

    def test_real_cli_join_preserves_decimal_and_report_output(self):
        path = self.checker("a.json", ["1", "9.933579335793359e-7"])
        output = self.root / "result.json"
        # Bind a constructed reference in the harness only; production stays unchanged.
        script = "import compare_checker as r, sys; r.SPRINT_SHA256=sys.argv.pop(1); r.main()"
        result = subprocess.run([sys.executable, "-B", "-c", script, self.reference_hash,
                                 str(path), str(self.reference), "--sprint", "--instance", "fixture-a",
                                 "--output", str(output)], cwd=Path(reader.__file__).parent,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout, output.read_text(encoding="utf-8"))
        out = json.loads(result.stdout)
        self.assertEqual(out["counts"], {"candidate": 1, "reference": 0, "tie": 0})
        self.assertEqual(Decimal(out["instances"][0]["candidate_at_first_change"]), Decimal("9.933579335793359e-7"))


if __name__ == "__main__":
    unittest.main()
