from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from ._test_support import NOW, ClarificationTestBase, compiler, raw_input


class ClarificationHostileTests(ClarificationTestBase):
    def test_duplicate_json_key_is_rejected(self):
        with self.assertRaisesRegex(compiler.Error, "duplicate JSON key"):
            compiler.compile_current(b'{"schema":"x","schema":"y"}')

    def test_bool_priority_is_rejected(self):
        raw = self.mutate(raw_input(), lambda v: v["candidate_questions"][0].__setitem__("priority", True))
        with self.assertRaisesRegex(compiler.Error, "integer required"):
            self.compile(raw)

    def test_packet_markdown_and_receipt_tamper_are_rejected(self):
        output = self.compile()
        with patch.object(compiler, "_clock", return_value=NOW):
            with self.assertRaisesRegex(compiler.Error, "packet mismatch"):
                compiler.verify(raw_input(), output.packet.replace(b"READY_FOR_OWNER_REVIEW", b"HOLD_DEADLINE_PASSED"), output.markdown, output.receipt)
            with self.assertRaisesRegex(compiler.Error, "markdown mismatch"):
                compiler.verify(raw_input(), output.packet, output.markdown + b"tamper\n", output.receipt)
            with self.assertRaisesRegex(compiler.Error, "receipt mismatch"):
                compiler.verify(raw_input(), output.packet, output.markdown, output.receipt + b"tamper\n")

    def test_cli_compile_verify_normal_and_optimized(self):
        root = Path(__file__).resolve().parents[2]
        for optimized in (False, True):
            with self.subTest(optimized=optimized), tempfile.TemporaryDirectory() as td:
                td = Path(td)
                input_path = td / "input.json"
                input_path.write_bytes(raw_input())
                out = td / "out"
                prefix = [sys.executable] + (["-O"] if optimized else [])
                env = dict(os.environ, PYTHONPATH=str(root))
                cp = subprocess.run(
                    prefix + ["-m", "revenue.rfp_clarification_questions.compiler", "compile", "--input", str(input_path), "--out-dir", str(out)],
                    cwd=root,
                    env=env,
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(0, cp.returncode, cp.stderr)
                self.assertIn("READY_FOR_OWNER_REVIEW", cp.stdout)
                verify = subprocess.run(
                    prefix + [
                        "-m", "revenue.rfp_clarification_questions.compiler", "verify",
                        "--input", str(input_path),
                        "--packet", str(out / "packet.json"),
                        "--markdown", str(out / "questions.md"),
                        "--receipt", str(out / "receipt.json"),
                    ],
                    cwd=root,
                    env=env,
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(0, verify.returncode, verify.stderr)
                result = json.loads(verify.stdout)
                self.assertTrue(result["verified"])
                self.assertEqual("READY_FOR_OWNER_REVIEW", result["current_status"])

    def test_cli_refuses_overwrite(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            input_path = td / "input.json"
            input_path.write_bytes(raw_input())
            out = td / "out"
            env = dict(os.environ, PYTHONPATH=str(root))
            cmd = [sys.executable, "-m", "revenue.rfp_clarification_questions.compiler", "compile", "--input", str(input_path), "--out-dir", str(out)]
            first = subprocess.run(cmd, cwd=root, env=env, text=True, capture_output=True)
            second = subprocess.run(cmd, cwd=root, env=env, text=True, capture_output=True)
            self.assertEqual(0, first.returncode, first.stderr)
            self.assertEqual(2, second.returncode)
