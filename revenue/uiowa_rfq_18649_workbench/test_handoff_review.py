"""Synthetic unit tests plus full-parent integration when the checkout is present."""
from __future__ import annotations

import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import handoff_review as hr


def report_fixture():
    return {
        "schema": "UNIT_TEST_STUB_NOT_COMPILER_OUTPUT", "mode": hr.MODE,
        "receipt_sha256": "a" * 64, "aggregate_state": "HOLD_TRUSTED_AUTHORITY_REQUIRED",
        "trust": {"authority_root_supplied_out_of_band": False, "current_evidence_review_authority": False},
        "assessment_matrix": [{"group": group, "dimension": dimension,
                               "status": "UNTRUSTED_EVIDENCE_CONSISTENT",
                               "source_ids": [f"fictional-{group}-{dimension}"],
                               "source_record_sha256s": ["b" * 64],
                               "reason_codes": ["TRUSTED_AUTHORITY_ROOT_REQUIRED"]}
                              for group, dimension in hr.CELLS],
    }


def integrity_fixture(report):
    return {"integrity_valid": True, "semantic_recompile_valid": True,
            "trusted_authority_root_verified": False, "current_authority_verified": False,
            "receipt_sha256": report["receipt_sha256"]}


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.report = report_fixture()
        self.first = hr._blank_handoff(self.report)
        self.second = hr._blank_handoff(self.report)
        self.verifier = patch.object(hr, "_parent_integrity", side_effect=integrity_fixture)
        self.verifier.start()
        self.addCleanup(self.verifier.stop)

    def compare(self):
        return hr.reconcile(self.report, [("a", self.first), ("b", self.second)])

    def test_all_unreviewed_is_not_acceptance(self):
        result = self.compare()
        self.assertEqual(result["reason_counts"], {"ALL_UNREVIEWED": 12})
        self.assertEqual(len(result["review_queue"]), 12)
        self.assertEqual(result["distinct_handoff_content_count"], 1)
        self.assertEqual(result["identical_content_groups"], [["a", "b"]])
        self.assertTrue(all(value is False for value in result["authority"].values()))
        self.assertIs(result["source_authenticity_verified"], False)
        self.assertIs(result["reviewer_identity_verified"], False)

    def test_disagreement_and_incomplete_review_both_survive(self):
        self.first["cell_notes"][0]["disposition"] = "NEEDS_EVIDENCE"
        self.second["cell_notes"][0]["disposition"] = "DISCUSS_WITH_PRIME"
        third = hr._blank_handoff(self.report)
        result = hr.reconcile(self.report, [("a", self.first), ("b", self.second), ("c", third)])
        reasons = result["assessment_cells"][0]["review_reason_codes"]
        self.assertIn("DISPOSITION_DISAGREEMENT", reasons)
        self.assertIn("INCOMPLETE_REVIEW", reasons)
        self.assertEqual(len(result["assessment_cells"][0]["entries"]), 3)

    def test_matching_drafts_are_not_consensus(self):
        for handoff in (self.first, self.second):
            handoff["cell_notes"][0].update(disposition="TECHNICAL_DRAFT_NOTE", analyst_note="FICTIONAL: same words")
        # Two distinct exports may agree on this cell. A duplicate of a single
        # export is covered separately by test_handoff_review_duplicates.py.
        self.second["cell_notes"][1]["analyst_note"] = "FICTIONAL: separate draft context."
        result = self.compare()
        self.assertEqual(result["assessment_cells"][0]["review_reason_codes"], ["MATCHING_DRAFT_ENTRIES"])
        self.assertEqual(len(result["review_queue"]), 11)
        self.assertNotIn("consensus", hr.canonical(result).decode().lower())

    def test_single_handoff_still_requires_review(self):
        self.first["cell_notes"][0]["disposition"] = "TECHNICAL_DRAFT_NOTE"
        result = hr.reconcile(self.report, [("one", self.first)])
        self.assertEqual(result["assessment_cells"][0]["review_reason_codes"], ["SINGLE_DRAFT_ENTRY"])
        self.assertEqual(len(result["review_queue"]), 12)

    def test_note_variation_does_not_assert_contradictory_evidence(self):
        self.first["cell_notes"][0]["analyst_note"] = "FICTIONAL: discuss source scope"
        self.second["cell_notes"][0]["analyst_note"] = "FICTIONAL: clarify source scope"
        result = self.compare()
        codes = result["assessment_cells"][0]["review_reason_codes"]
        self.assertIn("NOTE_VARIATION_REQUIRES_REVIEW", codes)
        self.assertNotIn("DISPOSITION_DISAGREEMENT", codes)

    def test_inputs_not_mutated_and_source_links_retained(self):
        saved = copy.deepcopy((self.report, self.first, self.second))
        result = self.compare()
        self.assertEqual((self.report, self.first, self.second), saved)
        cell = result["assessment_cells"][0]
        self.assertEqual(cell["source_ids"], self.report["assessment_matrix"][0]["source_ids"])
        self.assertEqual(cell["source_record_sha256s"], ["b" * 64])
        cell["source_ids"].append("unrelated")
        self.assertEqual((self.report, self.first, self.second), saved)

    def test_deterministic_under_input_and_cell_order(self):
        self.second["cell_notes"][2]["disposition"] = "NEEDS_EVIDENCE"
        expected = self.compare()
        self.first["cell_notes"].reverse()
        self.second["cell_notes"].reverse()
        self.report["assessment_matrix"].reverse()
        observed = hr.reconcile(self.report, [("b", self.second), ("a", self.first)])
        self.assertEqual(expected, observed)

    def test_receipt_covers_output(self):
        result = self.compare()
        receipt = result.pop("reconciliation_sha256")
        self.assertEqual(receipt, hr.digest(result))
        result["assessment_cells"][0]["entries"][0]["analyst_note"] = "changed"
        self.assertNotEqual(receipt, hr.digest(result))

    def test_foreign_receipt_rejected(self):
        self.first["report_receipt_sha256"] = "c" * 64
        with self.assertRaisesRegex(hr.ReviewError, "different report"):
            self.compare()

    def test_mode_aggregate_and_demo_mismatch_rejected(self):
        for key, value in (("report_mode", "CURRENT"), ("aggregate_state", "READY"), ("synthetic_demo", True), ("synthetic_demo", 0)):
            with self.subTest(key=key, value=value):
                self.first = hr._blank_handoff(self.report)
                self.first[key] = value
                with self.assertRaises(hr.ReviewError):
                    self.compare()

    def test_authority_flags_strictly_false(self):
        for key in hr.AUTHORITY_KEYS:
            for value in (True, 0, "false", None):
                with self.subTest(key=key, value=value):
                    self.first = hr._blank_handoff(self.report)
                    self.first["authority"][key] = value
                    with self.assertRaises(hr.ReviewError):
                        self.compare()

    def test_missing_extra_and_invalid_fields_rejected(self):
        mutations = [lambda h: h.pop("authority"), lambda h: h.update(extra="not accepted"),
                     lambda h: h["authority"].update(extra=False),
                     lambda h: h["cell_notes"][0].update(score=5),
                     lambda h: h.update(schema="v2"), lambda h: h.update(status="APPROVED")]
        for mutate in mutations:
            self.first = hr._blank_handoff(self.report)
            mutate(self.first)
            with self.assertRaises(hr.ReviewError):
                self.compare()

    def test_missing_duplicate_and_unknown_cells_rejected(self):
        for action in ("missing", "duplicate", "unknown", "nonobject"):
            with self.subTest(action=action):
                self.first = hr._blank_handoff(self.report)
                if action == "missing":
                    self.first["cell_notes"].pop()
                elif action == "duplicate":
                    self.first["cell_notes"][1] = self.first["cell_notes"][0].copy()
                elif action == "unknown":
                    self.first["cell_notes"][0]["group"] = "XYZ"
                else:
                    self.first["cell_notes"][0] = []
                with self.assertRaises(hr.ReviewError):
                    self.compare()

    def test_status_and_disposition_not_rewritable(self):
        for key, value in (("compiler_status", "READY"), ("disposition", "APPROVED"), ("disposition", [])):
            self.first = hr._blank_handoff(self.report)
            self.first["cell_notes"][0][key] = value
            with self.assertRaises(hr.ReviewError):
                self.compare()

    def test_unicode_bound_matches_browser_utf16_units(self):
        note = "🙂" * 2000
        self.first["cell_notes"][0]["analyst_note"] = note
        self.assertEqual(self.compare()["assessment_cells"][0]["entries"][0]["analyst_note"], note)
        self.first["cell_notes"][0]["analyst_note"] += "x"
        with self.assertRaisesRegex(hr.ReviewError, "4000 UTF-16"):
            self.compare()

    def test_notes_reject_bad_unicode_and_nonstrings(self):
        for note in (None, [], 3, "\ud800", "x" * 4001):
            self.first["cell_notes"][0]["analyst_note"] = note
            with self.assertRaises(hr.ReviewError):
                self.compare()

    def test_unique_bounded_labels(self):
        for labels in (("same", "same"), ("", "ok"), ("../name", "ok"), ("a" * 65, "ok"), ([], "ok")):
            with self.assertRaises(hr.ReviewError):
                hr.reconcile(self.report, [(labels[0], self.first), (labels[1], self.second)])
        for collection in ([], [(str(n), self.first) for n in range(21)], [None]):
            with self.assertRaises(hr.ReviewError):
                hr.reconcile(self.report, collection)

    def test_report_boundary_and_shape_rejected(self):
        mutations = [lambda r: r.update(mode="CURRENT"), lambda r: r.update(synthetic_demo=True),
                     lambda r: r.update(receipt_sha256="short"),
                     lambda r: r["trust"].update(current_evidence_review_authority=True),
                     lambda r: r["trust"].update(authority_root_supplied_out_of_band=0),
                     lambda r: r["assessment_matrix"].pop(),
                     lambda r: r["assessment_matrix"].__setitem__(1, r["assessment_matrix"][0]),
                     lambda r: r["assessment_matrix"][0].update(group=[])]
        for mutate in mutations:
            self.report = report_fixture()
            mutate(self.report)
            with self.assertRaises(hr.ReviewError):
                self.compare()

    def test_verifier_failure_not_replaced_with_hash_only(self):
        with patch.object(hr, "_parent_integrity", side_effect=hr.ReviewError("semantic failure")):
            with self.assertRaisesRegex(hr.ReviewError, "semantic failure"):
                self.compare()
        for key, value in (("semantic_recompile_valid", False), ("integrity_valid", 1),
                           ("trusted_authority_root_verified", True), ("current_authority_verified", True),
                           ("receipt_sha256", "f" * 64)):
            result = integrity_fixture(self.report)
            result[key] = value
            with patch.object(hr, "_parent_integrity", return_value=result):
                with self.assertRaises(hr.ReviewError):
                    self.compare()

    def test_markdown_keeps_notes_literal(self):
        self.first["cell_notes"][0]["analyst_note"] = "FICTIONAL\n```\n<script>no</script>\n# fake header"
        rendered = hr.render_markdown(self.compare())
        self.assertNotIn("\n<script>", rendered)
        self.assertNotIn("\n# fake header", rendered)
        self.assertIn("not adjudication or University findings", rendered)
        self.assertIn("\\n```\\n<script>", rendered)


class FileAndCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_strict_json_input(self):
        bad = [b'{"x":1,"x":2}', b'{"x":{"y":1,"y":2}}', b'{"x":NaN}',
               b'{"x":Infinity}', b'{"x":1e999}', b'"\\ud800"', b'\xff', b'{}{}', b'{']
        for content in bad:
            path = self.root / "bad.json"
            path.write_bytes(content)
            with self.assertRaises(hr.ReviewError):
                hr.load_json(path)

    def test_oversize_and_deep_json_rejected(self):
        path = self.root / "bad.json"
        for content in (b" " * (hr.MAX_BYTES + 1), b"[" * 2000 + b"0" + b"]" * 2000):
            path.write_bytes(content)
            with self.assertRaises(hr.ReviewError):
                hr.load_json(path)

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "POSIX final-component symlink contract")
    def test_symlink_rejected(self):
        target = self.root / "data.json"
        target.write_text("{}")
        link = self.root / "link.json"
        link.symlink_to(target)
        with self.assertRaises(OSError):
            hr.load_json(link)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO test")
    def test_fifo_rejected_without_blocking(self):
        path = self.root / "pipe"
        os.mkfifo(path)
        with self.assertRaises(hr.ReviewError):
            hr.load_json(path)

    def test_output_never_overwrites(self):
        path = self.root / "out.json"
        hr._write_new(path, b"original")
        with self.assertRaises(FileExistsError):
            hr._write_new(path, b"replacement")
        self.assertEqual(path.read_bytes(), b"original")
        if os.name == "posix":
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_cli_full_flow_with_explicit_unit_stub(self):
        report = report_fixture()
        handoff = hr._blank_handoff(report)
        (self.root / "report.json").write_bytes(hr.canonical(report))
        (self.root / "notes.json").write_bytes(hr.canonical(handoff))
        out = self.root / "review.json"
        args = ["compare", str(self.root / "report.json"), "--handoff", "unit-stub", str(self.root / "notes.json"), "--output", str(out)]
        with patch.object(hr, "_parent_integrity", side_effect=integrity_fixture), redirect_stdout(io.StringIO()):
            self.assertEqual(hr.main(args), 0)
        result = hr.load_json(out)
        self.assertEqual(result["status"], hr.DRAFT)
        with patch.object(hr, "_parent_integrity", side_effect=integrity_fixture), redirect_stderr(io.StringIO()):
            self.assertEqual(hr.main(args), 2)
        self.assertEqual(hr.load_json(out), result)

    def test_failure_leaves_no_output_and_does_not_echo_private_path(self):
        out = self.root / "review.json"
        errors = io.StringIO()
        with redirect_stderr(errors):
            self.assertEqual(hr.main(["compare", str(self.root / "private-absent.json"),
                                     "--handoff", "one", str(self.root / "notes.json"), "--output", str(out)]), 2)
        self.assertFalse(out.exists())
        self.assertNotIn(str(self.root), errors.getvalue())


class ParentCompilerIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parent = Path(__file__).resolve().parents[1] / "uiowa_rfq_18649_workshare"
        if not (parent / "compiler.py").is_file():
            if os.environ.get("UIOWA_REQUIRE_PARENT") == "1":
                raise RuntimeError("full parent checkout required for integration evidence")
            raise unittest.SkipTest("isolated unit run; parent integration not executed")

    def test_synthetic_example_uses_real_parent_and_repeats_exactly(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, second = Path(tmp) / "one", Path(tmp) / "two"
            hr.write_example(first)
            hr.write_example(second)
            self.assertEqual(sorted(p.name for p in first.iterdir()), sorted(p.name for p in second.iterdir()))
            for path in first.iterdir():
                self.assertEqual(path.read_bytes(), (second / path.name).read_bytes())
            result = hr.load_json(first / "reconciliation.json")
            self.assertEqual(result["reason_counts"]["DISPOSITION_DISAGREEMENT"], 1)
            self.assertEqual(result["reason_counts"]["INCOMPLETE_REVIEW"], 1)
            self.assertEqual(result["reason_counts"]["MATCHING_DRAFT_ENTRIES"], 1)
            self.assertEqual(result["reason_counts"]["ALL_UNREVIEWED"], 9)
            report = hr.load_json(first / "report.json")
            report["assessment_matrix"][0]["status"] = "READY"
            with self.assertRaises(hr.ReviewError):
                hr.reconcile(report, [("one", hr.load_json(first / "analyst-a.json"))])

    def test_missing_parent_never_accepts_ui_only_report(self):
        fake = report_fixture()
        fake.update(schema="SYNTHETIC_UI_DEMO_NOT_COMPILER_OUTPUT", synthetic_demo=True)
        with self.assertRaisesRegex(hr.ReviewError, "UI-only"):
            hr.reconcile(fake, [("one", hr._blank_handoff(fake))])


if __name__ == "__main__":
    unittest.main()
