from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from revenue.commercial_experiment_lab import cli
from revenue.commercial_experiment_lab.common import canonical_json


class CliTests(unittest.TestCase):
    def compiled(self) -> dict:
        packet = {"schema": "packet", "state": "READY"}
        receipt = {"evaluated_at": "2026-09-13T12:00:00Z", "receipt_sha256": "a" * 64}
        return {
            "packet": packet,
            "receipt": receipt,
            "json": b"{}\n",
            "csv": b"a,b\n",
            "markdown": b"# report\n",
        }

    def test_compile_creates_exclusive_complete_output_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "input.json"
            input_path.write_text("{}", encoding="utf-8")
            out = root / "out"
            with patch("revenue.commercial_experiment_lab.cli.compile_experiment", return_value=self.compiled()):
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    code = cli.main(["compile", str(input_path), "--out-dir", str(out)])
            self.assertEqual(code, 0)
            self.assertEqual(stdout.getvalue().strip(), "a" * 64)
            self.assertEqual(sorted(p.name for p in out.iterdir()), sorted(cli.OUTPUT_NAMES))
            self.assertEqual((out / "packet.json").read_bytes(), canonical_json(self.compiled()["packet"]))

    def test_compile_refuses_existing_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "input.json"
            input_path.write_text("{}", encoding="utf-8")
            out = root / "out"
            out.mkdir()
            with patch("revenue.commercial_experiment_lab.cli.compile_experiment", return_value=self.compiled()):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    code = cli.main(["compile", str(input_path), "--out-dir", str(out)])
            self.assertEqual(code, 2)
            self.assertIn("already exists", stderr.getvalue())

    def test_verify_success_and_mismatch_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = {}
            for name, data in {
                "input": b"{}",
                "packet": b"{}",
                "receipt": b'{"evaluated_at":"2026-09-13T12:00:00Z"}',
                "json": b"{}\n",
                "csv": b"x\n",
                "md": b"# x\n",
            }.items():
                p = root / name
                p.write_bytes(data)
                paths[name] = p
            argv = [
                "verify",
                str(paths["input"]),
                "--packet", str(paths["packet"]),
                "--receipt", str(paths["receipt"]),
                "--report-json", str(paths["json"]),
                "--report-csv", str(paths["csv"]),
                "--report-md", str(paths["md"]),
            ]
            with patch("revenue.commercial_experiment_lab.cli.verify_artifacts", return_value=True):
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    self.assertEqual(cli.main(argv), 0)
                self.assertIn("VERIFIED", stdout.getvalue())
            with patch("revenue.commercial_experiment_lab.cli.verify_artifacts", return_value=False):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    self.assertEqual(cli.main(argv), 4)
                self.assertIn("VERIFY_MISMATCH", stderr.getvalue())

    def test_symlink_input_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target.json"
            target.write_text("{}", encoding="utf-8")
            link = root / "input.json"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("symlink unsupported")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = cli.main(["compile", str(link), "--out-dir", str(root / "out")])
            self.assertEqual(code, 2)
            self.assertIn("non-regular input", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
