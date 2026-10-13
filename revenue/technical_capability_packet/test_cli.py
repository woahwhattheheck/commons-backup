from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import io
import json
import os
import tempfile
import unittest

from revenue.technical_capability_packet.cli import main

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures" / "synthetic_request.json"


class CliTests(unittest.TestCase):
    def test_compile_json_then_verify(self):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = main(["compile", str(FIXTURE), "--format", "json"])
        self.assertEqual(rc, 0)
        report = json.loads(out.getvalue())
        self.assertEqual(report["readiness"], "READY_FOR_OWNER_SEND_REVIEW")
        with tempfile.TemporaryDirectory() as td:
            report_path = Path(td) / "report.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            verify_out = io.StringIO()
            with redirect_stdout(verify_out):
                verify_rc = main(["verify", str(FIXTURE), str(report_path)])
            self.assertEqual(verify_rc, 0)
            self.assertEqual(json.loads(verify_out.getvalue())["verdict"], "CURRENT_VERIFIED")

    def test_compile_markdown(self):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = main(["compile", str(FIXTURE), "--format", "markdown"])
        self.assertEqual(rc, 0)
        self.assertIn("# Technical Capability Packet", out.getvalue())
        self.assertIn("Authority ceiling", out.getvalue())

    @unittest.skipUnless(hasattr(os, "symlink") and hasattr(os, "O_NOFOLLOW"), "requires symlink + O_NOFOLLOW")
    def test_final_component_symlink_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            link = Path(td) / "packet.json"
            os.symlink(FIXTURE, link)
            err = io.StringIO()
            with redirect_stderr(err):
                rc = main(["compile", str(link)])
            self.assertEqual(rc, 4)
            self.assertIn("ERROR:", err.getvalue())

    def test_duplicate_key_file_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "bad.json"
            bad.write_text('{"schema":"x","schema":"y"}', encoding="utf-8")
            err = io.StringIO()
            with redirect_stderr(err):
                rc = main(["compile", str(bad)])
            self.assertEqual(rc, 4)
            self.assertIn("duplicate JSON key", err.getvalue())


if __name__ == "__main__":
    unittest.main()
