import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from revenue.nm_ocs_tprm.cli import _strict_load, main
from revenue.nm_ocs_tprm.tests.test_tprm import assessment


class CliTests(unittest.TestCase):
    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.json"
            p.write_text('{"a":1,"a":2}', encoding="utf-8")
            with self.assertRaises(ValueError):
                _strict_load(p)

    def test_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.json"
            p.write_text('{"a":NaN}', encoding="utf-8")
            with self.assertRaises(ValueError):
                _strict_load(p)

    def test_refuses_output_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            inp = Path(td) / "in.json"
            out = Path(td) / "out.json"
            inp.write_text(json.dumps(assessment()), encoding="utf-8")
            out.write_text("occupied", encoding="utf-8")
            with self.assertRaises(ValueError):
                main(["assessment", str(inp), str(out)])

    def test_compile_then_verify(self):
        with tempfile.TemporaryDirectory() as td:
            inp = Path(td) / "in.json"
            out = Path(td) / "out.json"
            inp.write_text(json.dumps(assessment()), encoding="utf-8")
            self.assertEqual(main(["assessment", str(inp), str(out)]), 0)
            self.assertEqual(main(["verify-assessment", str(out)]), 0)

    def test_direct_script_entrypoint(self):
        with tempfile.TemporaryDirectory() as td:
            inp = Path(td) / "in.json"
            out = Path(td) / "out.json"
            inp.write_text(json.dumps(assessment()), encoding="utf-8")
            cli = Path(__file__).resolve().parents[1] / "cli.py"
            run = subprocess.run(
                [sys.executable, str(cli), "assessment", str(inp), str(out)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            verify = subprocess.run(
                [sys.executable, str(cli), "verify-assessment", str(out)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(verify.returncode, 0, verify.stderr)


if __name__ == "__main__":
    unittest.main()
