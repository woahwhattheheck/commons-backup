"""Tests of the independent observer, not a second horizon implementation."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest

import replay_horizons as replay


def fixture():
    doc = {"backlog_id": "SYN-ORACLE", "recommendations": [
        replay.record("P", (15, 30), "180+"), replay.record("A")]}
    payload = {"meta": {"synthetic": True, "authority": "FICTIONAL_REHEARSAL_ONLY"},
               "recommendations": [
                   {"recommendation_id": "P", "declared_horizon": "180+", "proposed_horizon": "90-180"},
                   {"recommendation_id": "A", "declared_horizon": "UNKNOWN", "proposed_horizon": "0-90"}],
               "by_horizon": {"0-90": [], "90-180": [], "180+": ["P"],
                              "NEEDS_ESTIMATE": [], "UNASSIGNED": ["A"]}, "violations": []}
    return doc, payload


class ReplayObserverTests(unittest.TestCase):
    def test_panel_has_224_unique_cases(self):
        docs = list(replay.cases())
        self.assertEqual(len(docs), 224)
        self.assertEqual(len({d["backlog_id"] for d in docs}), 224)
        self.assertTrue(all(len(d["recommendations"]) == 2 for d in docs))

    def test_generation_is_deterministic(self):
        self.assertEqual(replay.canonical(list(replay.cases())), replay.canonical(list(replay.cases())))

    def test_panel_covers_each_estimate_pair_and_both_record_orders(self):
        docs = list(replay.cases())
        observed = set()
        for d in docs:
            a = next(r for r in d["recommendations"] if r["recommendation_id"] == "A")
            observed.add((a["effort_days_low"], a["effort_days_high"]))
        self.assertEqual(observed, set(replay.EFFORTS))
        self.assertEqual({tuple(r["recommendation_id"] for r in d["recommendations"]) for d in docs},
                         {("A", "P"), ("P", "A")})

    def test_git_blob_identity_includes_header(self):
        self.assertEqual(replay.blob_sha(b""), "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391")
        self.assertNotEqual(replay.blob_sha(b"hello"), hashlib.sha1(b"hello").hexdigest())

    def test_valid_observation_passes_without_replanning(self):
        doc, payload = fixture()
        result = replay.inspect(doc, payload, copy.deepcopy(doc))
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(len(result["checks"]), 8)
        self.assertEqual(result["observed"]["proposals"]["P"], "90-180")

    def test_sized_in_needs_estimate_is_a_failure(self):
        doc, payload = fixture()
        payload["by_horizon"]["UNASSIGNED"] = []
        payload["by_horizon"]["NEEDS_ESTIMATE"] = ["A"]
        result = replay.inspect(doc, payload, doc)
        self.assertEqual(result["failed_checks"], ["sized_items_not_mislabeled_needs_estimate"])

    def test_unsized_missing_dependency_requires_named_diagnostic(self):
        doc, payload = fixture()
        doc["recommendations"][1].update(effort_days_low=None, effort_days_high=None,
                                         prerequisites=["MISSING"])
        result = replay.inspect(doc, payload, doc)
        self.assertEqual(result["failed_checks"], ["missing_prerequisites_diagnosed"])
        payload["violations"].append({"recommendation_id": "A", "code": "DANGLING_PREREQUISITE"})
        self.assertEqual(replay.inspect(doc, payload, doc)["status"], "PASS")

    def test_unrelated_diagnostic_does_not_clear_missing_dependency(self):
        doc, payload = fixture()
        doc["recommendations"][1]["prerequisites"] = ["MISSING"]
        payload["violations"].append({"recommendation_id": "P", "code": "DANGLING_PREREQUISITE"})
        self.assertIn("missing_prerequisites_diagnosed", replay.inspect(doc, payload, doc)["failed_checks"])

    def test_input_mutation_is_detected(self):
        doc, payload = fixture()
        after = copy.deepcopy(doc)
        after["recommendation_id"] = "not-an-input-field"
        self.assertIn("input_unchanged", replay.inspect(doc, payload, after)["failed_checks"])

    def test_missing_record_is_detected(self):
        doc, payload = fixture()
        payload["recommendations"].pop()
        self.assertIn("records_conserved", replay.inspect(doc, payload, doc)["failed_checks"])

    def test_lost_bucket_member_is_detected(self):
        doc, payload = fixture()
        payload["by_horizon"]["UNASSIGNED"] = []
        self.assertIn("bucket_membership_conserved", replay.inspect(doc, payload, doc)["failed_checks"])

    def test_duplicate_bucket_member_is_detected(self):
        doc, payload = fixture()
        payload["by_horizon"]["0-90"] = ["A"]
        self.assertIn("bucket_membership_conserved", replay.inspect(doc, payload, doc)["failed_checks"])

    def test_changed_known_declaration_is_detected(self):
        doc, payload = fixture()
        payload["recommendations"][0]["declared_horizon"] = "90-180"
        self.assertIn("declarations_preserved", replay.inspect(doc, payload, doc)["failed_checks"])

    def test_later_declared_prerequisite_needs_diagnostic(self):
        doc, payload = fixture()
        doc["recommendations"][1].update(declared_horizon="0-90", prerequisites=["P"])
        payload["recommendations"][1]["declared_horizon"] = "0-90"
        self.assertIn("declared_dependency_order_diagnosed", replay.inspect(doc, payload, doc)["failed_checks"])
        payload["violations"].append({"recommendation_id": "A", "code": "PREREQUISITE_AFTER_DEPENDENT"})
        self.assertEqual(replay.inspect(doc, payload, doc)["status"], "PASS")

    def test_fictional_boundary_is_checked(self):
        doc, payload = fixture()
        payload["meta"]["synthetic"] = False
        self.assertIn("fictional_authority_preserved", replay.inspect(doc, payload, doc)["failed_checks"])

    def test_execution_errors_cannot_be_counted_as_passes(self):
        class Broken:
            def __init__(self, doc):
                raise RuntimeError("synthetic execution fault")
        result = replay.execute(types.SimpleNamespace(Backlog=Broken))
        self.assertEqual((result["status"], result["passed"], result["failed"]), ("FAIL", 0, 224))
        self.assertEqual(result["failure_counts"], {"execution": 224})
        self.assertEqual(len(result["policy_observations"]["cases"]), 6)
        self.assertTrue(all("error" in r for r in result["policy_observations"]["cases"]))

    def test_nonfinite_json_is_not_serialized(self):
        with self.assertRaises(ValueError):
            replay.canonical({"value": float("nan")})

    def test_cli_source_binding_failure_is_error_and_no_output(self):
        with tempfile.TemporaryDirectory() as temp:
            source, output = Path(temp) / "method.py", Path(temp) / "out.json"
            source.write_text('raise RuntimeError("source must not run")\n', encoding="utf-8")
            proc = subprocess.run([sys.executable, str(Path(replay.__file__)), "--source", str(source),
                                   "--expected-blob", "0" * 40, "--out", str(output)],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("source Git blob differs", proc.stderr)
            self.assertFalse(output.exists())

    def test_cli_refuses_missing_backlog_api(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "method.py"
            source.write_text('VALUE = 1\n', encoding="utf-8")
            proc = subprocess.run([sys.executable, str(Path(replay.__file__)), "--source", str(source)],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(json.loads(proc.stderr)["status"], "ERROR")
            self.assertEqual(proc.stdout, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
