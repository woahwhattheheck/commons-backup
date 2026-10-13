"""Harness accounting/cleanup tests; no browser installation or network required."""
import contextlib
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("r7q_acceptance_under_test", Path(__file__).with_name("browser_http_acceptance.py"))
h = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(h)


class HarnessAccountingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        for name in ("server.py", "app.js", "style.css"):
            (self.source / name).write_text("# synthetic fixture\n")
        (self.source / "index.html").write_text('<script src="/app.js" defer></script>')
        self.out = self.root / "result"

    def call(self, extra=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return h.main(["--source", str(self.source), "--out", str(self.out)] + (extra or []))

    def receipt(self):
        return json.loads((self.out / "receipt.json").read_text())

    def test_git_hash_uses_real_blob_header(self):
        data = b"synthetic\n"
        self.assertEqual(h.fingerprint(data)["git_blob_sha1"], hashlib.sha1(b"blob 10\0" + data).hexdigest())

    def test_boundary_error_is_blocked_not_empty_pass(self):
        with patch.object(h, "Runtime", side_effect=RuntimeError("net::ERR_BLOCKED_BY_ADMINISTRATOR")) as runtime:
            self.assertEqual(self.call(), 2)
            self.assertEqual(runtime.call_count, 1, "no retry/fallback is permitted")
            self.assertEqual(runtime.call_args.args[1], "native")
        r = self.receipt()
        self.assertEqual(r["status"], "BLOCKED")
        self.assertEqual(r["tests_run"], 0)
        self.assertIs(r["native_browser_http_verified"], False)
        self.assertIs(r["parent_compiler_verified"], False)
        self.assertIn("ERR_BLOCKED_BY_ADMINISTRATOR", r["blocked_reason"])
        self.assertIs(r["source_unchanged"], True)

    def test_explicit_split_is_preserved_on_missing_runtime(self):
        with patch.object(h, "Runtime", side_effect=ImportError("playwright absent")) as runtime:
            self.assertEqual(self.call(["--mode", "split"]), 2)
            self.assertEqual(runtime.call_args.args[1], "split")
        self.assertEqual(self.receipt()["mode"], "split")

    def test_existing_output_never_overwritten(self):
        self.out.mkdir()
        marker = self.out / "receipt.json"
        marker.write_text("retained")
        with self.assertRaises(FileExistsError):
            self.call()
        self.assertEqual(marker.read_text(), "retained")

    def test_output_cannot_mutate_source(self):
        self.out = self.source / "out"
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.call()
        self.assertFalse(self.out.exists())

    def test_missing_source_fails_before_output(self):
        (self.source / "server.py").unlink()
        with self.assertRaises(ValueError):
            self.call()
        self.assertFalse(self.out.exists())

    def test_external_and_parent_script_references_rejected(self):
        for script in ("https://example.invalid/x.js", "../other.js", "/nested/other.js"):
            with self.subTest(script=script):
                (self.source / "index.html").write_text(f'<script src="{script}"></script>')
                with self.assertRaises(ValueError):
                    h.snapshot(self.source)

    def test_local_script_is_in_source_binding(self):
        (self.source / "index.html").write_text('<script src="/helper.js"></script><script src="/app.js"></script>')
        (self.source / "helper.js").write_text("// fictional helper\n")
        self.assertIn("helper.js", h.snapshot(self.source))

    def test_source_symlink_rejected(self):
        target = self.root / "external.js"
        target.write_text("// outside source")
        (self.source / "app.js").unlink()
        (self.source / "app.js").symlink_to(target)
        with self.assertRaises(ValueError):
            h.snapshot(self.source)

    def test_synthetic_report_has_no_approval_or_scoring(self):
        report = h.synthetic_report()
        self.assertIn("NOT_COMPILER_OUTPUT", report["schema"])
        self.assertEqual(len(report["assessment_matrix"]), 12)
        self.assertIs(report["trust"]["current_evidence_review_authority"], False)
        for row in report["assessment_matrix"]:
            self.assertIsNone(row["maturity"])
            self.assertIsNone(row["confidence_bp"])

    def test_recorded_subtest_failure_cannot_become_success(self):
        class Fails(unittest.TestCase):
            def test_bad(self):
                with self.subTest(case="broken"):
                    self.assertEqual(1, 2)
        result = unittest.TextTestRunner(stream=io.StringIO(), resultclass=h.RecordedResult).run(unittest.defaultTestLoader.loadTestsFromTestCase(Fails))
        self.assertFalse(result.wasSuccessful())
        self.assertEqual([x["result"] for x in result.cases], ["FAIL"])

    def test_recorded_subtest_exception_is_error(self):
        class Errors(unittest.TestCase):
            def test_bad(self):
                with self.subTest(case="broken"):
                    raise ValueError("synthetic fixture")
        result = unittest.TextTestRunner(stream=io.StringIO(), resultclass=h.RecordedResult).run(unittest.defaultTestLoader.loadTestsFromTestCase(Errors))
        self.assertFalse(result.wasSuccessful())
        self.assertEqual([x["result"] for x in result.cases], ["ERROR"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
