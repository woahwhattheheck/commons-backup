import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from components import InputError, bundle, json_bytes
from example import example
from verify_bundle import verify


class BundleVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "input.json"
        self.source.write_bytes(json_bytes(example()))
        self.output = self.root / "bundle"
        self.output.mkdir()
        for n, b in bundle(example()).items():
            (self.output / n).write_bytes(b)

    def test_exact_recompile(self):
        self.assertEqual(len(verify(self.source, self.output)), 8)

    def test_rehashed_fabricated_report_not_accepted(self):
        p = self.output / "assessment.json"
        report = json.loads(p.read_bytes())
        report["components"][1]["support_state"] = "supported"
        p.write_bytes(json_bytes(report))
        m = self.output / "manifest.json"
        manifest = json.loads(m.read_bytes())
        manifest["files"][p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
        m.write_bytes(json_bytes(manifest))
        with self.assertRaisesRegex(InputError, "recompile mismatch"):
            verify(self.source, self.output)

    def test_missing_or_extra_member_rejected(self):
        (self.output / "extra.txt").write_text("not in contract")
        with self.assertRaisesRegex(InputError, "file set mismatch"):
            verify(self.source, self.output)
        (self.output / "extra.txt").unlink()
        (self.output / "manifest.json").unlink()
        with self.assertRaisesRegex(InputError, "file set mismatch"):
            verify(self.source, self.output)

    def test_symlink_not_followed(self):
        p = self.output / "summary.md"
        external = self.root / "other.md"
        external.write_bytes(p.read_bytes())
        p.unlink()
        p.symlink_to(external)
        with self.assertRaisesRegex(InputError, "regular file"):
            verify(self.source, self.output)

    def test_changed_input_invalidates_old_report(self):
        doc = example()
        doc["as_of"] = "2026-09-20"
        self.source.write_bytes(json_bytes(doc))
        with self.assertRaisesRegex(InputError, "recompile mismatch"):
            verify(self.source, self.output)

    def test_verifier_cli(self):
        command = [sys.executable, str(Path(__file__).with_name("verify_bundle.py")), str(self.source), str(self.output)]
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
        (self.output / "components.csv").write_text("changed")
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()
