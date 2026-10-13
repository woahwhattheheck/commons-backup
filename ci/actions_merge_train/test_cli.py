import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ci.actions_merge_train import cli, core
from ci.actions_merge_train.test_train import capture
# Keep boundary cases in the existing source-parses test command.
from ci.actions_merge_train.test_boundaries import BoundaryTests  # noqa:F401


class CliTests(unittest.TestCase):
    def write_json(self, path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_compile_markdown_verify_and_create_exclusive(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            cap = root / "capture.json"
            receipt = root / "receipt.json"
            md = root / "report.md"
            verify = root / "verify.json"
            self.write_json(cap, capture())

            cmd = [
                sys.executable,
                str(HERE / "cli.py"),
                "compile",
                "--capture",
                str(cap),
                "--out",
                str(receipt),
                "--markdown",
                str(md),
            ]
            first = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn("READY_FOR_GUARDED_REVIEW", md.read_text())

            second = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(second.returncode, 2)

            verification = subprocess.run(
                [
                    sys.executable,
                    str(HERE / "cli.py"),
                    "verify",
                    "--receipt",
                    str(receipt),
                    "--capture",
                    str(cap),
                    "--out",
                    str(verify),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(verification.returncode, 0, verification.stderr)
            self.assertTrue(json.loads(verify.read_text())["valid"])

    def test_mixed_newlines_ctrl_z_and_nul_round_trip_byte_exact(self):
        payload = b"alpha\r\nbeta\n\x1a\x00omega\r\n"
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            source = root / "source.bin"
            dest = root / "dest.bin"
            source.write_bytes(payload)
            readback = cli.read_regular(str(source), max_bytes=1024, label="mixed")
            self.assertEqual(readback, payload)
            cli.write_exclusive(str(dest), readback, label="mixed output")
            self.assertEqual(dest.read_bytes(), payload)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_symlink_capture_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            real = root / "real.json"
            link = root / "link.json"
            out = root / "out.json"
            self.write_json(real, capture())
            os.symlink(real, link)
            result = subprocess.run(
                [
                    sys.executable,
                    str(HERE / "cli.py"),
                    "compile",
                    "--capture",
                    str(link),
                    "--out",
                    str(out),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertFalse(out.exists())

    def test_malformed_capture_returns_evidence_error(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            bad = root / "bad.json"
            out = root / "out.json"
            bad.write_text('{"a":1,"a":2}', encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(HERE / "cli.py"),
                    "compile",
                    "--capture",
                    str(bad),
                    "--out",
                    str(out),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("duplicate JSON key", result.stderr)

    def test_package_import_does_not_replace_preexisting_generic_core(self):
        sentinel = object()
        prior = sys.modules.get("core")
        sys.modules["core"] = sentinel
        try:
            self.assertIs(sys.modules["core"], sentinel)
            self.assertTrue(hasattr(core, "compile_train"))
            self.assertFalse(hasattr(core, "RUN_SCHEMA"))
        finally:
            if prior is None:
                sys.modules.pop("core", None)
            else:
                sys.modules["core"] = prior


if __name__ == "__main__":
    unittest.main(verbosity=2)
