# SPDX-License-Identifier: Apache-2.0
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

from cli import main
from test_qualification import qualified_payload


class CliTests(unittest.TestCase):
    def test_public_fixture_holds_with_exit_3(self):
        fixture = Path(__file__).parent / "fixtures" / "public_listing_only.json"
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main([str(fixture)])
        self.assertEqual(code, 3)
        receipt = json.loads(out.getvalue())
        self.assertEqual(receipt["decision"], "HOLD")
        self.assertFalse(receipt["current_authority"])

    def test_qualified_bundle_remains_hold_without_production_root(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as td:
            td = Path(td)
            src = td / "bundle.json"
            dst = td / "receipt.json"
            src.write_text(json.dumps(qualified_payload()), encoding="utf-8")
            code = main([str(src), "--output", str(dst)])
            self.assertEqual(code, 3)
            receipt = json.loads(dst.read_text(encoding="utf-8"))
            self.assertEqual(receipt["decision"], "HOLD")
            self.assertFalse(receipt["current_authority"])
            self.assertTrue(
                {
                    "TRUSTED_COMPLETENESS_ROOT_MISSING_OR_INVALID",
                    "TRUSTED_COMPLETENESS_ROOT_MISMATCH",
                }
                & set(receipt["holds"])
            )
            self.assertFalse((td / "receipt.json.tmp").exists())

    def test_malformed_json_exit_2(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as td:
            src = Path(td) / "bad.json"
            src.write_text("{", encoding="utf-8")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = main([str(src)])
            self.assertEqual(code, 2)
            self.assertIn("ERROR:", err.getvalue())

    def test_missing_file_exit_2(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = main(["/definitely/missing.json"])
        self.assertEqual(code, 2)

    def test_caller_clock_override_is_not_an_argument(self):
        fixture = Path(__file__).parent / "fixtures" / "public_listing_only.json"
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as caught:
            main([str(fixture), "--evaluated-at", "2026-09-13T09:30:00Z"])
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("unrecognized arguments: --evaluated-at", err.getvalue())

    @unittest.skipUnless(os.name == "posix", "POSIX input custody only")
    def test_final_component_symlink_input_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as td:
            td = Path(td)
            target = td / "target.json"
            target.write_text(json.dumps(qualified_payload()), encoding="utf-8")
            link = td / "bundle.json"
            link.symlink_to(target.name)
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = main([str(link)])
            self.assertEqual(code, 2)

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "mkfifo"), "FIFO test")
    def test_fifo_input_is_rejected_without_waiting_for_writer(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as td:
            fifo = Path(td) / "bundle.fifo"
            os.mkfifo(fifo, 0o600)
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = main([str(fifo)])
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
