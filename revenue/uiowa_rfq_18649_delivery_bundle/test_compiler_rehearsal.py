"""Actual parent-function/transport integration and failure-preserving rehearsal."""
from __future__ import annotations

import contextlib
import io
import itertools
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from . import bundle, compiler_rehearsal as run, examples


class ActualCompilerTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.output = Path(cls.temp.name) / "actual"
        result = subprocess.run(run.python_command() + ["-m",
            "revenue.uiowa_rfq_18649_delivery_bundle.compiler_rehearsal",
            "--output", str(cls.output)], cwd=run.HERE.parents[1],
            capture_output=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stderr.decode("utf-8", errors="replace"))
        cls.receipt = json.loads(result.stdout)
        cls.report_bytes = (cls.output / "sender/report.json").read_bytes()
        cls.handoff_bytes = (cls.output / "sender/handoff.json").read_bytes()
        cls.archive = (cls.output / "recipient/draft.zip").read_bytes()

    def test_real_parent_semantic_verification(self):
        proof = self.receipt["parent_verification"]
        self.assertIs(proof["integrity_valid"], True)
        self.assertIs(proof["semantic_recompile_valid"], True)
        self.assertEqual(proof["receipt_sha256"],
                         "3b58382daa78e4c152ff87111e17322bc6f86fe0d92abc4cf69412ee8bb11530")
        self.assertIs(proof["trusted_authority_root_verified"], False)
        self.assertIs(proof["current_authority_verified"], False)

    def test_missing_conflict_stale_and_unknown_scores_preserved(self):
        report = json.loads(self.report_bytes)
        self.assertEqual(report["status_counts"], {"HOLD_CONFLICT": 1,
            "HOLD_MISSING_EVIDENCE": 1, "HOLD_STALE_EVIDENCE": 1,
            "UNTRUSTED_EVIDENCE_CONSISTENT": 9})
        held = {(c["group"], c["dimension"]): c["status"]
                for c in report["assessment_matrix"] if c["status"].startswith("HOLD_")}
        self.assertEqual(held, {("ESS", "ai_readiness"): "HOLD_MISSING_EVIDENCE",
            ("RIS", "security"): "HOLD_CONFLICT", ("IAM", "deployment"): "HOLD_STALE_EVIDENCE"})
        self.assertTrue(all(c["maturity"] is None and c["confidence_bp"] is None
                            for c in report["assessment_matrix"]))
        self.assertEqual(report["evaluated_at"], "2026-08-26T12:00:00Z")

    def test_report_draft_and_recipient_bytes_are_identical(self):
        with zipfile.ZipFile(io.BytesIO(self.archive)) as archive:
            self.assertEqual(archive.read("report.json"), self.report_bytes)
            self.assertEqual(archive.read("handoff.json"), self.handoff_bytes)
        self.assertEqual(self.archive, (self.output / "sender/draft.zip").read_bytes())
        self.assertEqual(bundle.sha256(self.archive),
                         "4514043016f69cd99fc093ff65f9eef6157a2a2dea161a828d626a078d114da0")

    def test_generated_notes_are_unreviewed_fiction_not_browser_export(self):
        handoff = json.loads(self.handoff_bytes)
        self.assertEqual(len(handoff["cell_notes"]), 12)
        self.assertTrue(all(n["disposition"] == "UNREVIEWED"
                            and "SYNTHETIC REHEARSAL" in n["analyst_note"]
                            for n in handoff["cell_notes"]))
        self.assertTrue(all(v is False for v in handoff["authority"].values()))
        self.assertIs(handoff["synthetic_demo"], False)
        self.assertIs(self.receipt["synthetic_source_fixtures"], True)
        self.assertIs(self.receipt["browser_import_export_executed"], False)
        self.assertIs(self.receipt["parent_public_cli_executed"], False)
        self.assertIs(self.receipt["independent_external_channel_exercised"], False)

    def test_transport_does_not_claim_parent_semantics(self):
        proof = bundle.verify_bundle(self.archive, self.receipt["archive_sha256"])
        self.assertIs(proof["parent_compiler_receipt_recomputed"], False)
        self.assertEqual(proof["verification_scope"], "BYTE_INTEGRITY_AND_HANDOFF_CROSS_REFERENCES_ONLY")
        self.assertTrue(all(value is False for value in proof["authority"].values()))

    def test_executed_no_overwrite_tamper_and_source_checks(self):
        for key in ("existing_archive_refused_and_preserved", "changed_recipient_archive_rejected",
                    "deterministic_archive_rebuilt", "exact_payload_bytes_preserved",
                    "source_files_unchanged", "retained_sender_digest_checked"):
            self.assertIs(self.receipt[key], True, key)
        self.assertFalse((self.output / "FAILURE.json").exists())
        self.assertEqual(json.loads((self.output / "RECEIPT.json").read_bytes()), self.receipt)


class RehearsalFailureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.output = self.base / "new-run"

    def failure_receipt(self):
        self.assertFalse((self.output / "RECEIPT.json").exists())
        failure = json.loads((self.output / "FAILURE.json").read_bytes())
        self.assertEqual(failure["status"], "REHEARSAL_FAILED")
        return failure

    def test_existing_directory_and_prior_receipt_remain_unchanged(self):
        self.output.mkdir()
        old = self.output / "RECEIPT.json"
        old.write_bytes(b"retained earlier receipt")
        with self.assertRaises(FileExistsError):
            run.rehearsal(self.output)
        self.assertEqual(old.read_bytes(), b"retained earlier receipt")
        self.assertEqual([p.name for p in self.output.iterdir()], ["RECEIPT.json"])

    def test_existing_symlink_is_not_followed_for_publication(self):
        target = self.base / "target"
        target.mkdir()
        (target / "keep.txt").write_text("keep", encoding="utf-8")
        try:
            self.output.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Platform cannot create a test symlink: {exc}")
        with self.assertRaises(FileExistsError):
            run.rehearsal(self.output)
        self.assertTrue(self.output.is_symlink())
        self.assertEqual([p.name for p in target.iterdir()], ["keep.txt"])

    def test_missing_output_parent_is_not_created(self):
        target = self.base / "missing-parent" / "child"
        with self.assertRaises(FileNotFoundError):
            run.rehearsal(target)
        self.assertFalse(target.parent.exists())

    def test_changed_pinned_fixture_refused_before_output_or_execution(self):
        fixtures = self.base / "fixtures"
        fixtures.mkdir()
        for name in run.FIXTURES:
            raw = (run.PARENT / "fixtures" / name).read_bytes()
            (fixtures / name).write_bytes(raw + (b"\n" if name == "synthetic_packet.json" else b""))
        with patch.object(run, "PARENT", self.base), patch.object(run, "execute") as child:
            with self.assertRaisesRegex(run.RehearsalError, "Pinned synthetic fixture changed"):
                run.rehearsal(self.output)
        child.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_failed_parent_never_writes_a_success_receipt(self):
        with patch.object(run, "execute", side_effect=run.RehearsalError("parent failed")):
            with self.assertRaisesRegex(run.RehearsalError, "parent failed"):
                run.rehearsal(self.output)
        self.assertEqual(self.failure_receipt()["error"], "RehearsalError")
        self.assertFalse((self.output / "sender/report.json").exists())

    def test_parent_timeout_is_failure_not_skipped_or_passed(self):
        with patch.object(run, "execute", side_effect=subprocess.TimeoutExpired("parent", 20)):
            with self.assertRaises(subprocess.TimeoutExpired):
                run.rehearsal(self.output)
        self.assertEqual(self.failure_receipt()["error"], "TimeoutExpired")

    def test_malformed_child_receipt_is_failure(self):
        with patch.object(run, "execute", return_value={}):
            with self.assertRaisesRegex(run.RehearsalError, "payload must be text"):
                run.rehearsal(self.output)
        self.assertEqual(self.failure_receipt()["error"], "RehearsalError")

    def test_false_parent_semantic_result_is_not_positive_acceptance(self):
        fake = {"report_utf8": "{}", "verification": {
            "integrity_valid": True, "semantic_recompile_valid": False}}
        with patch.object(run, "execute", return_value=fake):
            with self.assertRaisesRegex(run.RehearsalError, "semantic verification"):
                run.rehearsal(self.output)
        self.failure_receipt()

    def test_changed_sources_leave_diagnostic_not_success(self):
        inputs, sources = run.snapshot()
        altered = dict(sources, **{"workshare_compile.py": "0" * 40})
        with patch.object(run, "snapshot", side_effect=[(inputs, sources), (inputs, altered)]):
            with self.assertRaisesRegex(run.RehearsalError, "Source files changed"):
                run.rehearsal(self.output)
        self.failure_receipt()
        self.assertTrue((self.output / "sender/draft.zip").is_file())

    def test_child_nonzero_rejected_before_parsing_stdout(self):
        result = subprocess.CompletedProcess(["python"], 3, b'{"ok":true}', b"intentional failure")
        with patch.object(run.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(run.RehearsalError, "Child exit 3; expected 0"):
                run.execute(["-c", "pass"], cwd=self.base)

    def test_optimized_child_matches_requested_interpreter_mode(self):
        command = run.python_command()
        self.assertIn("-B", command)
        if run.sys.flags.optimize:
            self.assertIn("-" + "O" * run.sys.flags.optimize, command)
        else:
            self.assertNotIn("-O", command)

    def test_main_reports_structured_failure_and_no_positive_stdout(self):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(run, "rehearsal", side_effect=run.RehearsalError("failure")):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = run.main(["--output", str(self.output)])
        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(json.loads(err.getvalue())["status"], "REHEARSAL_FAILED")


class CompleteGridAuditTests(unittest.TestCase):
    def test_all_192_named_and_external_grid_pairs(self):
        accepted = rejected = 0
        schemas = ("uiowa-rfq18649-workshare-report/v2",
                   "SYNTHETIC_UI_DEMO_NOT_COMPILER_OUTPUT", "external-untrusted-report/v1")
        masks = tuple(itertools.product((0, 1), repeat=3))
        for schema, report_mask, note_mask in itertools.product(schemas, masks, masks):
            with self.subTest(schema=schema, report_mask=report_mask, note_mask=note_mask):
                report, handoff = examples.synthetic_pair()
                synthetic = schema == schemas[1]
                report.update(schema=schema, synthetic_demo=synthetic)
                handoff["synthetic_demo"] = synthetic
                for rows, mask in ((report["assessment_matrix"], report_mask),
                                   (handoff["cell_notes"], note_mask)):
                    for row in rows:
                        if row["dimension"] == "software_development" and mask[("ESS", "RIS", "IAM").index(row["group"])]:
                            row["dimension"] = "software"
                expected = report_mask == note_mask and report_mask in ((0, 0, 0), (1, 1, 1))
                if schema == schemas[0]:
                    expected = expected and report_mask == (1, 1, 1)
                elif schema == schemas[1]:
                    expected = expected and report_mask == (0, 0, 0)
                try:
                    proof = bundle.verify_bundle(bundle.build_bundle(
                        bundle.canonical(report), bundle.canonical(handoff)))
                except bundle.BundleError as exc:
                    self.assertFalse(expected)
                    self.assertEqual(exc.code, "CELL_COVERAGE")
                    rejected += 1
                else:
                    self.assertTrue(expected)
                    self.assertTrue(all(value is False for value in proof["authority"].values()))
                    accepted += 1
        self.assertEqual((accepted, rejected), (4, 188))


if __name__ == "__main__":
    unittest.main()
