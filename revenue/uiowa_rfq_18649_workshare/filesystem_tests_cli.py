#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent

class CliBoundaryTests(unittest.TestCase):
    def test_normal_and_optimized_cli_bytes_match(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            candidate = root / "candidate.json"
            authority = root / "authority.json"
            out_a = root / "a.json"
            out_b = root / "b.json"
            candidate.write_bytes((HERE / "fixtures" / "synthetic_packet.json").read_bytes())
            authority.write_bytes((HERE / "fixtures" / "synthetic_authority.json").read_bytes())
            for flags, output in [([], out_a), (["-O"], out_b)]:
                run = subprocess.run(
                    [
                        sys.executable,
                        *flags,
                        str(HERE / "compiler.py"),
                        "compile",
                        str(candidate),
                        str(authority),
                        str(output),
                    ],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(out_a.read_bytes(), out_b.read_bytes())

    def test_cli_verify_is_explicitly_integrity_only_and_rendered_boundary_is_clear(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            candidate = root / "candidate.json"
            authority = root / "authority.json"
            report = root / "report.json"
            rendered = root / "report.md"
            candidate.write_bytes((HERE / "fixtures" / "synthetic_packet.json").read_bytes())
            authority.write_bytes((HERE / "fixtures" / "synthetic_authority.json").read_bytes())
            compile_run = subprocess.run(
                [sys.executable, str(HERE / "compiler.py"), "compile", str(candidate), str(authority), str(report)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(compile_run.returncode, 0, compile_run.stderr)
            verify_run = subprocess.run(
                [sys.executable, str(HERE / "compiler.py"), "verify", str(report)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(verify_run.returncode, 0, verify_run.stderr)
            self.assertIn("UNTRUSTED_INTEGRITY_ONLY", verify_run.stdout)
            render_run = subprocess.run(
                [sys.executable, str(HERE / "compiler.py"), "render", str(report), str(rendered)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(render_run.returncode, 0, render_run.stderr)
            text = rendered.read_text(encoding="utf-8")
            self.assertIn("did **not** independently authenticate", text)
            self.assertIn("No award, buyer acceptance, payment", text)
