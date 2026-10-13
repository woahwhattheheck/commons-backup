import json
import os
import subprocess
import sys
import tempfile
import unittest

from pr_main_convergence import (
    CLASS_EXACT,
    CLASS_INSUFFICIENT,
    CLASS_PARTIAL,
    CLASS_UNIQUE,
    EvidenceError,
    audit,
)

A = "a" * 40
B = "b" * 40
C = "c" * 40


def doc(main_files, prs):
    return {
        "schema_version": 1,
        "canonical_base": "main",
        "main": {"ref": "main@abc", "files": main_files},
        "prs": prs,
    }


def pr(number, files, *, state="open", base="main", intent=None):
    row = {"number": number, "state": state, "base": base, "head": f"head-{number}", "files": files}
    if intent is not None:
        row["intent"] = intent
    return row


class ConvergenceTests(unittest.TestCase):
    def test_exact_already_on_main(self):
        result = audit(doc({"x.py": A, "y.py": B}, [pr(12755, {"x.py": A, "y.py": B})]))
        self.assertEqual(CLASS_EXACT, result["prs"][0]["classification"])
        self.assertFalse(result["policy"]["decision_authority"])
        self.assertTrue(result["policy"]["requires_live_reverification_before_write"])

    def test_unique_delta_requires_verified_absence(self):
        result = audit(doc({"new.py": None}, [pr(1, {"new.py": A})]))
        self.assertEqual(CLASS_UNIQUE, result["prs"][0]["classification"])

    def test_missing_main_coverage_is_insufficient_not_unique(self):
        result = audit(doc({}, [pr(1, {"new.py": A})]))
        self.assertEqual(CLASS_INSUFFICIENT, result["prs"][0]["classification"])
        self.assertEqual("MAIN_COVERAGE_INCOMPLETE", result["prs"][0]["reason"])

    def test_changed_existing_path_needs_review(self):
        result = audit(doc({"x.py": B}, [pr(1, {"x.py": A})]))
        self.assertEqual(CLASS_PARTIAL, result["prs"][0]["classification"])
        self.assertEqual(1, result["prs"][0]["counts"]["different"])

    def test_mixed_same_and_absent_needs_review(self):
        result = audit(doc({"x.py": A, "z.py": None}, [pr(1, {"x.py": A, "z.py": C})]))
        self.assertEqual(CLASS_PARTIAL, result["prs"][0]["classification"])

    def test_exact_duplicate_open_carriers_grouped(self):
        result = audit(doc({"x.py": A}, [
            pr(12749, {"x.py": A}, intent="agent-index"),
            pr(12755, {"x.py": A}, intent="agent-index"),
        ]))
        self.assertEqual([12749, 12755], result["exact_duplicate_groups"][0]["prs"])
        self.assertEqual([], result["intent_overlap_reviews"])

    def test_closed_carrier_not_in_live_duplicate_group(self):
        result = audit(doc({"x.py": A}, [pr(1, {"x.py": A}), pr(2, {"x.py": A}, state="closed")]))
        self.assertEqual([], result["exact_duplicate_groups"])

    def test_same_intent_different_postimage_is_review_not_duplicate(self):
        result = audit(doc({"a.py": None, "b.py": None}, [
            pr(12750, {"a.py": A}, intent="gauntlet-family-identity"),
            pr(12764, {"b.py": B}, intent="gauntlet-family-identity"),
        ]))
        self.assertEqual([], result["exact_duplicate_groups"])
        self.assertEqual([12750, 12764], result["intent_overlap_reviews"][0]["prs"])

    def test_noncanonical_base_fails_to_insufficient(self):
        result = audit(doc({"x.py": A}, [pr(1, {"x.py": A}, base="titan/v4-old")]))
        self.assertEqual(CLASS_INSUFFICIENT, result["prs"][0]["classification"])
        self.assertEqual("NONCANONICAL_BASE", result["prs"][0]["reason"])

    def test_duplicate_pr_number_rejected(self):
        with self.assertRaises(EvidenceError):
            audit(doc({"x.py": A}, [pr(1, {"x.py": A}), pr(1, {"x.py": A})]))

    def test_poison_paths_and_blobs_rejected(self):
        for bad_path in ("../x.py", "/x.py", "a\\b.py", "a/../b.py"):
            with self.subTest(path=bad_path), self.assertRaises(EvidenceError):
                audit(doc({bad_path: A}, [pr(1, {bad_path: A})]))
        with self.assertRaises(EvidenceError):
            audit(doc({"x.py": "A" * 40}, [pr(1, {"x.py": A})]))

    def test_output_is_deterministic_by_pr_number(self):
        source = doc({"a.py": None, "b.py": None}, [pr(9, {"b.py": B}), pr(2, {"a.py": A})])
        one = json.dumps(audit(source), sort_keys=True, separators=(",", ":"))
        source["prs"].reverse()
        two = json.dumps(audit(source), sort_keys=True, separators=(",", ":"))
        self.assertEqual(one, two)
        self.assertEqual([2, 9], [row["number"] for row in audit(source)["prs"]])

    def test_cli_normal_and_optimized(self):
        payload = doc({"x.py": A}, [pr(1, {"x.py": A})])
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "evidence.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)
            for optimized in (False, True):
                cmd = [sys.executable]
                if optimized:
                    cmd.append("-O")
                cmd += [os.path.join(os.path.dirname(__file__), "pr_main_convergence.py"), path]
                completed = subprocess.run(cmd, check=False, text=True, capture_output=True)
                self.assertEqual(0, completed.returncode, completed.stderr)
                parsed = json.loads(completed.stdout)
                self.assertEqual(CLASS_EXACT, parsed["prs"][0]["classification"])


if __name__ == "__main__":
    unittest.main()
