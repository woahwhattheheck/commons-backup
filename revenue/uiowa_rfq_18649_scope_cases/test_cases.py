"""UIOWA-139 tests. Run normal and with python -O."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest

try:
    from .canonical import BASELINE, EXHIBIT_BLOB, EXHIBIT_PATH, SCHEMA, SECTION_2_TRIGGERS
    from .cli import main as cli_main
    from .dispositions import CaseError, classify
    from .renderer import load_case, load_cases_dir, validate_case
except ImportError:
    from canonical import BASELINE, EXHIBIT_BLOB, EXHIBIT_PATH, SCHEMA, SECTION_2_TRIGGERS
    from cli import main as cli_main
    from dispositions import CaseError, classify
    from renderer import load_case, load_cases_dir, validate_case

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = os.path.join(HERE, "cases")


def _git_blob_sha1(path):
    with open(path, "rb") as fh:
        data = fh.read()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


class StructureTests(unittest.TestCase):
    def test_six_cases_load(self):
        cases = load_cases_dir(CASES)
        self.assertEqual(len(cases), 6)
        self.assertEqual([c["id"] for c in cases], [f"CASE-0{i}" for i in range(1, 7)])

    def test_each_case_has_exact_edit_and_clauses(self):
        for case in load_cases_dir(CASES):
            self.assertTrue(case["request"]["exact_edit"].strip())
            self.assertGreaterEqual(len(case["source_clauses"]), 2)
            self.assertIn("before", case["artifact"])
            self.assertIn("after", case["artifact"])
            self.assertTrue(case["rationale"].strip())
            self.assertEqual(case["effort"]["label"], "HYPOTHETICAL / NOT ACCEPTED")
            self.assertTrue(case["commercial_triggers_preserved"])
            self.assertEqual(case["payment_effect"], "NONE_SECTION_2_UNCHANGED")

    def test_section_2_triggers_pinned(self):
        kicks = [t["trigger"] for t in SECTION_2_TRIGGERS]
        self.assertEqual(kicks, ["written_authorization", "delivery", "acceptance"])
        amounts = [t["amount_usd"] for t in SECTION_2_TRIGGERS]
        self.assertEqual(amounts, [9600, 9600, 4800])
        self.assertFalse(SECTION_2_TRIGGERS[0]["acceptance_triggered"])
        self.assertFalse(SECTION_2_TRIGGERS[1]["acceptance_triggered"])
        self.assertTrue(SECTION_2_TRIGGERS[2]["acceptance_triggered"])

    def test_roles_not_collapsed(self):
        self.assertEqual(BASELINE["roles"]["principal"], "prime")
        self.assertEqual(BASELINE["roles"]["specialist"], "subcontract")

    def test_exhibit_blob_pin(self):
        self.assertEqual(EXHIBIT_BLOB, "48465060fff1402af966871352e894686fffe05e")
        sibling = os.path.abspath(os.path.join(HERE, os.pardir, "uiowa_rfq_18649_workshare", "ACCEPTANCE_EXHIBIT.md"))
        if os.path.isfile(sibling):
            self.assertEqual(_git_blob_sha1(sibling), EXHIBIT_BLOB)
        self.assertEqual(EXHIBIT_PATH, "revenue/uiowa_rfq_18649_workshare/ACCEPTANCE_EXHIBIT.md")


class DispositionTests(unittest.TestCase):
    def test_broken_citation_is_in_scope_zero(self):
        case = load_case(os.path.join(CASES, "01_broken_citation.json"))
        self.assertEqual(case["disposition"], "ARTIFACT_CURE_IN_SCOPE")
        self.assertEqual(case["effort"]["usd_incremental"], 0)
        self.assertEqual(case["artifact"]["after_state"], "hold")

    def test_disputed_conclusion_is_not_a_defect(self):
        case = load_case(os.path.join(CASES, "02_disputed_supported_conclusion.json"))
        self.assertEqual(case["disposition"], "PRIME_JUDGMENT_NOT_DEFECT")
        self.assertFalse(case["artifact"]["technical_conclusion_changed"])
        self.assertIn("Partial", case["artifact"]["after"])
        self.assertNotIn("Established", case["artifact"]["after"].split("PRIME-JUDGMENT")[0])

    def test_new_evidence_not_promoted(self):
        case = load_case(os.path.join(CASES, "03_newly_supplied_evidence.json"))
        self.assertEqual(case["disposition"], "EVIDENCE_DEPENDENCY_HOLD")
        self.assertEqual(case["artifact"]["before_state"], "hold")
        self.assertEqual(case["artifact"]["after_state"], "hold")
        self.assertIn("not promoted", case["artifact"]["after"].lower())

    def test_wording_preference_not_defect(self):
        case = load_case(os.path.join(CASES, "04_wording_preference.json"))
        self.assertEqual(case["disposition"], "PRIME_JUDGMENT_NOT_DEFECT")
        self.assertFalse(case["artifact"]["technical_conclusion_changed"])
        self.assertIn("[SRC-018]", case["artifact"]["after"])

    def test_extra_group_is_proposed_not_added(self):
        case = load_case(os.path.join(CASES, "05_extra_stakeholder_group.json"))
        self.assertEqual(case["disposition"], "PROPOSED_NEW_SCOPE")
        self.assertIn("NOT added", case["artifact"]["after"])
        self.assertIn("12 cells", case["artifact"]["after"])
        self.assertEqual(case["effort"]["usd_incremental"], 2400)
        self.assertEqual(case["effort"]["label"], "HYPOTHETICAL / NOT ACCEPTED")

    def test_new_deliverable_is_proposed_not_added(self):
        case = load_case(os.path.join(CASES, "06_new_deliverable.json"))
        self.assertEqual(case["disposition"], "PROPOSED_NEW_SCOPE")
        self.assertIn("NOT added", case["artifact"]["after"])
        self.assertIn("4.5", case["artifact"]["after"])
        self.assertEqual(case["effort"]["usd_incremental"], 1800)

    def test_vendor_recommendation_refused(self):
        spec = classify("product_vendor_recommendation")
        self.assertEqual(spec["code"], "VENDOR_RECOMMENDATION_REFUSED")
        self.assertFalse(spec["authority"]["product_vendor_recommendation"])
        path = os.path.join(HERE, "fixtures", "vendor_recommendation_request.json")
        case = load_case(path)
        self.assertEqual(case["disposition"], "VENDOR_RECOMMENDATION_REFUSED")
        self.assertIn("REFUSED", case["artifact"]["after"])


class BoundaryTests(unittest.TestCase):
    def test_unknown_class_refused(self):
        with self.assertRaises(CaseError):
            classify("magic_rewrite")

    def test_schema_mismatch_refused(self):
        with self.assertRaises(CaseError):
            validate_case({"schema": "nope"})

    def test_silent_promotion_refused(self):
        bad = load_case(os.path.join(CASES, "03_newly_supplied_evidence.json"))
        bad["artifact"]["after_state"] = "supported"
        with self.assertRaises(CaseError):
            validate_case(bad)

    def test_judgment_cannot_rewrite_conclusion(self):
        bad = load_case(os.path.join(CASES, "02_disputed_supported_conclusion.json"))
        bad["artifact"]["technical_conclusion_changed"] = True
        with self.assertRaises(CaseError):
            validate_case(bad)

    def test_non_scope_cannot_invent_fee(self):
        bad = load_case(os.path.join(CASES, "01_broken_citation.json"))
        bad["effort"]["usd_incremental"] = 500
        with self.assertRaises(CaseError):
            validate_case(bad)

    def test_required_checks_are_not_assert(self):
        for name in ("renderer.py", "dispositions.py", "canonical.py", "cli.py"):
            with open(os.path.join(HERE, name), encoding="utf-8") as fh:
                src = fh.read()
            self.assertNotRegex(src, r"(?m)^\s*assert ", msg=name)

    def test_cli_exit_zero(self):
        dest = os.path.join(tempfile.mkdtemp(prefix="uiowa139-"), "out")
        code = cli_main(["--cases", CASES, "--out", dest])
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(os.path.join(dest, "decision_aid.md")))
        self.assertTrue(os.path.isfile(os.path.join(dest, "bundle.json")))
        with open(os.path.join(dest, "bundle.json"), encoding="utf-8") as fh:
            bundle = json.loads(fh.read())
        self.assertEqual(bundle["schema"], SCHEMA)
        self.assertEqual(len(bundle["cases"]), 6)
        self.assertFalse(bundle["decision_aid"]["automatic_engine"])

    def test_cli_overwrite_exit_two(self):
        dest = os.path.join(tempfile.mkdtemp(prefix="uiowa139-"), "out")
        self.assertEqual(cli_main(["--cases", CASES, "--out", dest]), 0)
        self.assertEqual(cli_main(["--cases", CASES, "--out", dest]), 2)


if __name__ == "__main__":
    unittest.main()
