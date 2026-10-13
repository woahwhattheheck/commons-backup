"""Pinned-output checks never rewrite their expected values or input fixtures."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from fixture_lab import CatalogError
import reproduce

HERE = Path(__file__).resolve().parent


class ReproductionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "output"
        self.pin_path = HERE / "EXPECTED_EXAMPLE.json"
        self.pin_before = self.pin_path.read_bytes()

    def tearDown(self):
        self.assertEqual(self.pin_path.read_bytes(), self.pin_before)

    def test_all_fifteen_outputs_match_the_retained_pin(self):
        reproduce.reproduce(self.out)
        self.assertEqual(reproduce.verify(self.out)["files"], 15)

    def test_output_edit_cannot_heal_the_retained_pin(self):
        reproduce.reproduce(self.out)
        (self.out / "example_review.md").write_text("Changed narrative")
        for _ in range(3):
            with self.assertRaises(CatalogError): reproduce.verify(self.out)

    def test_missing_output_does_not_pass(self):
        reproduce.reproduce(self.out)
        (self.out / "canonical_bridge/mapping.json").unlink()
        with self.assertRaises(CatalogError): reproduce.verify(self.out)

    def test_extra_output_does_not_pass(self):
        reproduce.reproduce(self.out)
        (self.out / "unexpected.txt").write_text("extra")
        with self.assertRaises(CatalogError): reproduce.verify(self.out)

    def test_reproduction_refuses_to_replace_prior_output(self):
        reproduce.reproduce(self.out)
        before = (self.out / "example_bundle/manifest.json").read_bytes()
        with self.assertRaises(CatalogError): reproduce.reproduce(self.out)
        self.assertEqual((self.out / "example_bundle/manifest.json").read_bytes(), before)

    def test_cli_reproduction_and_verification_all_interpreter_modes(self):
        for i, flags in enumerate(([], ["-O"], ["-OO"])):
            target = Path(self.tmp.name) / f"cli-{i}"
            for tail in ([], ["--verify-only"]):
                result = subprocess.run([sys.executable, *flags, str(HERE / "reproduce.py"), str(target), *tail],
                                        capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("PINNED_FICTIONAL_EXAMPLE_MATCH", result.stdout)


if __name__ == "__main__":
    unittest.main()
