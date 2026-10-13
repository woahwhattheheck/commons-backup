from __future__ import annotations
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import rehearse


class RehearsalTests(unittest.TestCase):
    def expected(self):
        return json.loads((rehearse.ROOT / "example/expected-output-sha256.json").read_text())

    def test_generated_files_match_published_manifest(self):
        rehearse.verify(rehearse.generated_files(), self.expected())

    def test_changed_byte_is_rejected(self):
        files = rehearse.generated_files()
        files["summary.csv"] += "\n"
        with self.assertRaisesRegex(ValueError, "digest mismatch: summary.csv"):
            rehearse.verify(files, self.expected())

    def test_missing_or_extra_manifest_member_is_rejected(self):
        expected = self.expected()
        del expected["summary.csv"]
        with self.assertRaisesRegex(ValueError, "exactly"):
            rehearse.verify(rehearse.generated_files(), expected)

    def test_full_cli_rehearsal_writes_verified_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, str(rehearse.ROOT / "rehearse.py"), "--out", tmp], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PASS: 8 generated files", result.stdout)
            self.assertEqual(len(list((Path(tmp) / "result").iterdir())), 7)
            actual = {"synthetic-input.json": (Path(tmp) / "synthetic-input.json").read_text()}
            actual.update({p.name: p.read_text() for p in (Path(tmp) / "result").iterdir()})
            rehearse.verify(actual, self.expected())

    def test_rehearsal_cannot_overwrite_checked_in_source(self):
        result = subprocess.run([sys.executable, str(rehearse.ROOT / "rehearse.py"), "--out", str(rehearse.ROOT / "example")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("outside the source component", result.stderr)


if __name__ == "__main__":
    unittest.main()
