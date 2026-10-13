from __future__ import annotations

import copy
import json
import os
import random
import stat
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import compiler


def load_fixture():
    return json.loads((HERE / "fixtures" / "vendor_example.json").read_text(encoding="utf-8"))


class CompilerTests(unittest.TestCase):
    def setUp(self):
        self.profile, self.profile_sha = compiler.load_profile()

    def compile(self, data=None):
        return compiler.compile_report(self.profile, self.profile_sha, load_fixture() if data is None else data)

    def test_profile_is_retained_and_stable(self):
        raw = (HERE / "profile.json").read_bytes()
        self.assertEqual(self.profile_sha, compiler.sha256_bytes(raw))
        self.assertEqual(self.profile["solicitation"]["id"], "RFP 10915-26")

    def test_fixture_is_review_required_not_false_ready(self):
        report = self.compile()
        self.assertEqual(report["readiness"], "REVIEW_REQUIRED")
        states = {row["requirement_id"]: row["state"] for row in report["compliance_matrix"]}
        self.assertEqual(states["RM-001"], "met")
        self.assertEqual(states["PRR-003"], "partial")
        self.assertEqual(states["INT-001"], "partial")
        self.assertEqual(states["SUB-001"], "partial")
        self.assertEqual(report["summary"]["total"], len(self.profile["requirements"]))

    def test_missing_critical_response_blocks(self):
        data = load_fixture()
        data["responses"] = [r for r in data["responses"] if r["requirement_id"] != "RET-001"]
        report = self.compile(data)
        self.assertEqual(report["readiness"], "BLOCKED")
        item = next(x for x in report["blocker_ledger"] if x["requirement_id"] == "RET-001")
        self.assertEqual(item["state"], "unknown")
        self.assertIn("MISSING_RESPONSE", item["reason_codes"])

    def test_critical_not_supported_blocks(self):
        data = load_fixture()
        response = next(r for r in data["responses"] if r["requirement_id"] == "TEC-002")
        response["rating"] = "N"
        report = self.compile(data)
        row = next(x for x in report["compliance_matrix"] if x["requirement_id"] == "TEC-002")
        self.assertEqual(row["state"], "blocker")
        self.assertIn("NOT_SUPPORTED", row["reason_codes"])

    def test_future_only_critical_blocks(self):
        data = load_fixture()
        response = next(r for r in data["responses"] if r["requirement_id"] == "SUP-001")
        response["rating"] = "F"
        report = self.compile(data)
        row = next(x for x in report["compliance_matrix"] if x["requirement_id"] == "SUP-001")
        self.assertEqual(row["state"], "blocker")
        self.assertIn("FUTURE_ONLY", row["reason_codes"])

    def test_y_without_supporting_evidence_is_unknown_and_blocks_if_critical(self):
        data = load_fixture()
        response = next(r for r in data["responses"] if r["requirement_id"] == "RM-001")
        response["evidence_ids"] = []
        report = self.compile(data)
        row = next(x for x in report["compliance_matrix"] if x["requirement_id"] == "RM-001")
        self.assertEqual(row["state"], "unknown")
        self.assertIn("NO_SUPPORTING_EVIDENCE", row["reason_codes"])
        self.assertEqual(report["readiness"], "BLOCKED")

    def test_contradiction_is_ledgered_and_blocks_critical(self):
        data = load_fixture()
        data["evidence"].append({
            "id": "EV-RM-CONTRA",
            "kind": "source",
            "source_ref": "fixture://rm-contra",
            "statement": "Synthetic contradiction.",
            "effects": [{"requirement_id": "RM-001", "effect": "contradiction"}],
        })
        response = next(r for r in data["responses"] if r["requirement_id"] == "RM-001")
        response["evidence_ids"].append("EV-RM-CONTRA")
        report = self.compile(data)
        row = next(x for x in report["compliance_matrix"] if x["requirement_id"] == "RM-001")
        self.assertEqual(row["state"], "blocker")
        self.assertEqual(report["contradiction_ledger"][0]["requirement_id"], "RM-001")

    def test_unlinked_contradiction_cannot_be_hidden(self):
        data = load_fixture()
        data["evidence"].append({
            "id": "EV-RM-UNLINKED-CONTRA",
            "kind": "source",
            "source_ref": "fixture://rm-unlinked-contra",
            "statement": "Synthetic contradiction omitted from response linkage.",
            "effects": [{"requirement_id": "RM-001", "effect": "contradiction"}],
        })
        report = self.compile(data)
        row = next(x for x in report["compliance_matrix"] if x["requirement_id"] == "RM-001")
        self.assertEqual(row["state"], "blocker")
        self.assertIn("UNLINKED_CONTRADICTION", row["reason_codes"])
        self.assertIn("EV-RM-UNLINKED-CONTRA", row["contradiction_evidence_ids"])

    def test_noncritical_contradiction_is_partial_but_visible(self):
        data = load_fixture()
        data["evidence"].append({
            "id": "EV-AI-CONTRA",
            "kind": "source",
            "source_ref": "fixture://ai-contra",
            "statement": "Synthetic AI limitation.",
            "effects": [{"requirement_id": "AI-001", "effect": "contradiction"}],
        })
        response = next(r for r in data["responses"] if r["requirement_id"] == "AI-001")
        response["evidence_ids"].append("EV-AI-CONTRA")
        report = self.compile(data)
        row = next(x for x in report["compliance_matrix"] if x["requirement_id"] == "AI-001")
        self.assertEqual(row["state"], "partial")
        self.assertIn("CONTRADICTORY_EVIDENCE", row["reason_codes"])

    def test_duplicate_response_rejected(self):
        data = load_fixture()
        data["responses"].append(copy.deepcopy(data["responses"][0]))
        with self.assertRaisesRegex(compiler.ContractError, "duplicate response requirement"):
            self.compile(data)

    def test_duplicate_evidence_id_rejected_even_same_content(self):
        data = load_fixture()
        data["evidence"].append(copy.deepcopy(data["evidence"][0]))
        with self.assertRaisesRegex(compiler.ContractError, "duplicate evidence id"):
            self.compile(data)

    def test_unknown_requirement_rejected(self):
        data = load_fixture()
        data["responses"][0]["requirement_id"] = "NOPE-001"
        with self.assertRaisesRegex(compiler.ContractError, "unknown requirement"):
            self.compile(data)

    def test_unknown_evidence_reference_rejected(self):
        data = load_fixture()
        data["responses"][0]["evidence_ids"] = ["EV-NOPE"]
        with self.assertRaisesRegex(compiler.ContractError, "unknown evidence id"):
            self.compile(data)

    def test_stable_output_under_input_reordering(self):
        a = load_fixture()
        b = copy.deepcopy(a)
        random.Random(7).shuffle(b["responses"])
        random.Random(11).shuffle(b["evidence"])
        for evidence in b["evidence"]:
            random.Random(evidence["id"]).shuffle(evidence["effects"])
        self.assertEqual(compiler.canon(self.compile(a)), compiler.canon(self.compile(b)))

    def test_report_receipt_binds_report_without_self_reference(self):
        report = self.compile()
        receipt = report["report_sha256"]
        without = dict(report)
        without.pop("report_sha256")
        self.assertEqual(receipt, compiler.sha256_bytes(compiler.canon(without)))

    def test_markdown_is_deterministic_and_contains_authority_boundary(self):
        report = self.compile()
        one = compiler.render_markdown(report)
        two = compiler.render_markdown(report)
        self.assertEqual(one, two)
        text = one.decode("utf-8")
        self.assertIn("Authority boundary", text)
        self.assertIn("does **not** submit a proposal", text)

    def test_strict_json_rejects_duplicate_object_keys(self):
        with self.assertRaisesRegex(compiler.ContractError, "duplicate JSON key"):
            compiler.loads_strict(b'{"a":1,"a":2}')

    def test_strict_json_rejects_nonfinite_numbers(self):
        with self.assertRaisesRegex(compiler.ContractError, "non-finite"):
            compiler.loads_strict(b'{"a":NaN}')

    def test_regular_reader_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            target = base / "target.json"
            target.write_text("{}", encoding="utf-8")
            link = base / "link.json"
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symlink unavailable")
            with self.assertRaisesRegex(compiler.ContractError, "non-symlink"):
                compiler._read_regular(link)

    def test_exclusive_writer_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "report.json"
            compiler._write_exclusive(out, b"one")
            with self.assertRaises(FileExistsError):
                compiler._write_exclusive(out, b"two")
            self.assertEqual(out.read_bytes(), b"one")

    def test_cli_has_no_caller_time_or_submission_switch(self):
        parser = compiler.build_parser()
        options = {action.dest for action in parser._actions}
        self.assertNotIn("now", options)
        self.assertNotIn("as_of", options)
        self.assertNotIn("submit", options)
        self.assertNotIn("email", options)

    def test_acceptance_plan_covers_every_requirement(self):
        report = self.compile()
        ids = {r["id"] for r in self.profile["requirements"]}
        self.assertEqual(ids, {x["requirement_id"] for x in report["acceptance_test_plan"]})

    def test_evidence_effects_must_reference_known_requirement(self):
        data = load_fixture()
        data["evidence"][0]["effects"][0]["requirement_id"] = "NOPE-999"
        with self.assertRaisesRegex(compiler.ContractError, "unknown requirement"):
            self.compile(data)


if __name__ == "__main__":
    unittest.main()
